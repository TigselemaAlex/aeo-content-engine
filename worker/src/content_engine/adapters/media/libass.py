"""Draw a captions file with FFmpeg's libass and read what it drew and which fonts it used.

Shared by the compose (`ffmpeg.py`), which checks the font before burning the
captions, and by `verify-clip`, which measures them. Only running FFmpeg and reading its
log live here; the limits are applied by the pure clip domain (`caption_checks.py`).
Boxes are pixels of the frame FFmpeg draws on, 1080x1920 by default. The `ffmpeg`
program must be on the PATH.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from content_engine.piece_types.clip.domain.caption_checks import (
    CaptionFrame,
    FontPick,
    check_fonts,
)
from content_engine.piece_types.clip.domain.captions_ass import Box, read_ass_style
from content_engine.piece_types.clip.domain.ffmpeg_args import (
    CAPTION_FONTS_DIR,
    CAPTIONS_FILE,
    OUTPUT_H,
    OUTPUT_W,
    captions_filter,
)

FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
"""File types copied from a fonts folder for libass: TrueType, OpenType and collections."""

FONT_CHECK_SIZE = (270, 480)
"""Width and height of the quick render that checks the caption fonts before the compose.

The "render chico" of docs/03 §5.4 (row "Fuentes"): a quarter of 1080x1920 on each side.
libass picks the same fonts at any size, and a smaller frame draws faster. On the test
stretch `compose` takes 12.4 s with captions, this check included, and 7.5 s without
them (docs/03 §5.6).
"""

_BBOX = re.compile(
    r"\[bbox@(\w+) @ [^\]]*\] n:(\d+) .*?x1:(-?\d+) x2:(-?\d+) y1:(-?\d+) y2:(-?\d+)"
)
"""A box line of a named `bbox` filter: its name, the frame and x1, x2, y1, y2.

As FFmpeg 9.0.2 prints it, here for frame 2 of the test stretch (the first line entering
at 84 %): `[bbox@caption @ ...] n:2 pts:2 ... x1:322 x2:752 y1:1596 y2:1677 ...`. A frame
where nothing passed the threshold has no `x1`.
"""

_FONTSELECT = re.compile(r"fontselect: \((.*), -?\d+, -?\d+\) -> .*, -?\d+, (.*)$")
"""A font libass picked: the family asked for and the name of the font used.

As libass logs it at `-v debug`: `fontselect: (Figtree, 700, 0) -> Figtree-Bold, 0,
Figtree-Bold`; the last field is the name of the font used.
"""

_NO_FONT = re.compile(r"fontselect: failed to find any fallback.* for font: \((.*), -?\d+, -?\d+\)")
"""A font libass found nothing for, such as a glyph missing from every font: the family.

As libass logs it: `fontselect: failed to find any fallback with glyph 0x1F600 for font:
(Figtree, 700, 0)`.
"""


def stage_captions(captions_path: Path, fonts_dir: Path, work_dir: Path) -> None:
    """Copy a captions file and the font files of a folder into FFmpeg's working folder.

    They land as `CAPTIONS_FILE` and `CAPTION_FONTS_DIR`, so the `ass` filter gets bare
    relative names (a Windows path such as `C:/...` breaks a filter option on its `:`,
    docs/03 §5.6). Only the files with a `FONT_SUFFIXES` extension are copied, so a
    license such as `OFL.txt` stays behind. A folder without fonts stops here, because
    libass would not fail: it would draw with a system font (docs/03 §5.4).

    Args:
        captions_path: The ASS file to copy.
        fonts_dir: Folder with the caption fonts, such as `assets/fonts`.
        work_dir: The folder FFmpeg runs from, usually a new temporary one. It must not
            have a `CAPTION_FONTS_DIR` folder yet.

    Raises:
        RuntimeError: If `fonts_dir` has no `.ttf`, `.otf` or `.ttc` file.
    """
    fonts = [path for path in sorted(fonts_dir.glob("*")) if path.suffix.lower() in FONT_SUFFIXES]
    if not fonts:
        raise RuntimeError(f"no font files (.ttf, .otf, .ttc) in {fonts_dir}")
    shutil.copyfile(captions_path, work_dir / CAPTIONS_FILE)
    (work_dir / CAPTION_FONTS_DIR).mkdir()
    for font in fonts:
        shutil.copyfile(font, work_dir / CAPTION_FONTS_DIR / font.name)


def parse_caption_boxes(log: str, frames: int) -> list[CaptionFrame]:
    """Read the boxes the `bbox@caption` and `bbox@highlight` filters logged, per frame.

    Lines of other filters, and lines without a box (nothing drawn on that frame), are
    skipped.

    Args:
        log: FFmpeg's error output from `probe_captions`.
        frames: Number of frames drawn.

    Returns:
        One `CaptionFrame` per frame, from 0 to `frames - 1`, with None where its
        filter logged no box.

    Example:
        Test stretch: from the FFmpeg 9.0.2 line `[bbox@caption @ ...] n:2 ... x1:322
        x2:752 y1:1596 y2:1677 ...`, frame 2 gets the caption box x 322-752,
        y 1596-1677 (the first line, centered at y = 1642, entering at 84 %). Frames 0
        and 1, before "And" starts, logged no box and get None.
    """
    boxes: dict[str, dict[int, Box]] = {"caption": {}, "highlight": {}}
    for found in _BBOX.finditer(log):
        name, frame, x1, x2, y1, y2 = found.groups()
        if name in boxes:
            boxes[name][int(frame)] = Box(x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2))
    return [
        CaptionFrame(
            frame=frame,
            caption=boxes["caption"].get(frame),
            highlight=boxes["highlight"].get(frame),
        )
        for frame in range(frames)
    ]


def parse_font_picks(log: str) -> list[FontPick]:
    """Read which font libass used for each font it looked for, from its debug log.

    One pick per `fontselect` line, in log order: the family asked for and the font
    used, or None when libass found no font at all.

    Args:
        log: FFmpeg's error output, run with `-v debug`.

    Returns:
        The picks, in log order.

    Example:
        `fontselect: (Figtree, 700, 0) -> Figtree-Bold, 0, Figtree-Bold` gives
        Figtree -> Figtree-Bold, and with a misspelled family `(Figtreee, 700, 0) ->
        Arial-BoldMT, 0, Arial-BoldMT` gives Figtreee -> Arial-BoldMT (FFmpeg 9.0.2 on
        Windows, 26 nov 2026).
    """
    picks: list[FontPick] = []
    for line in log.splitlines():
        if found := _FONTSELECT.search(line):
            picks.append(FontPick(requested=found.group(1), chosen=found.group(2).strip()))
        elif found := _NO_FONT.search(line):
            picks.append(FontPick(requested=found.group(1), chosen=None))
    return picks


def probe_captions(
    captions_path: Path,
    fonts_dir: Path,
    frames: int,
    highlight: tuple[str, int] | None = None,
    size: tuple[int, int] = (OUTPUT_W, OUTPUT_H),
    fps: int = 30,
) -> tuple[list[CaptionFrame], list[FontPick]]:
    """Draw a captions file alone with libass and measure it on every frame.

    FFmpeg draws the captions over a transparent frame (`color=c=black@0`, RGBA) with
    the same `ass` filter as the compose (`captions_filter`, `alpha=1`). The box of
    everything drawn comes from the alpha plane, any pixel above 0 (`bbox@caption`),
    and the box of the highlighted word from the color plane and threshold of
    `highlight` (`bbox@highlight`). FFmpeg runs with `-v debug`, the level at which
    libass logs the font it picks, from a temporary folder with the captions and fonts
    (`stage_captions`), and is stopped after 300 s. The drawn frames are discarded
    (`-f null`); only the log is read.

    Args:
        captions_path: The ASS file.
        fonts_dir: Folder with the font files the captions use.
        frames: Number of frames to draw, one per keyframe of the clip.
        highlight: Color plane (`r`, `g` or `b`) and lowest value of the highlight,
            from `highlight_plane`. None measures only the caption box.
        size: Width and height to draw at. Smaller sizes are faster and pick the same
            fonts, but their boxes are not output pixels.
        fps: Frame rate of the clip.

    Returns:
        One `CaptionFrame` per frame, and the fonts libass picked.

    Raises:
        RuntimeError: If `fonts_dir` has no font file or FFmpeg exits with an error.
        subprocess.TimeoutExpired: If FFmpeg runs for more than 300 s.

    Example:
        Test stretch: 1004 frames in about 5 s (docs/03 §5.7), one font pick (Figtree
        -> Figtree-Bold) and 1002 frames with captions. On frame 2 the first line
        enters at 84 %: caption x 322-752, y 1596-1677, and "And" in white at x 339-428;
        on frame 4 it is full size, 518 px wide.
    """
    width, height = size
    draw = f"[0]{captions_filter()}:alpha=1"
    if highlight is None:
        graph = f"{draw},alphaextract,bbox@caption=min_val=1"
    else:
        plane, threshold = highlight
        graph = (
            f"{draw},split[all][color];"
            "[all]alphaextract,bbox@caption=min_val=1[a];"
            f"[color]extractplanes={plane},bbox@highlight=min_val={threshold}[b];"
            "[a][b]hstack"
        )
    args = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-v",
        "debug",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black@0:s={width}x{height}:r={fps},format=rgba",
        "-frames:v",
        str(frames),
        "-filter_complex",
        graph,
        "-f",
        "null",
        "-",
    ]
    with tempfile.TemporaryDirectory() as work_dir:
        stage_captions(captions_path, fonts_dir, Path(work_dir))
        try:
            result = subprocess.run(
                args, check=True, capture_output=True, timeout=300, cwd=work_dir
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"FFmpeg failed: {error.stderr.decode(errors='replace')}") from error
    log = result.stderr.decode(errors="replace")
    return parse_caption_boxes(log, frames), parse_font_picks(log)


def check_caption_fonts(captions_path: Path, fonts_dir: Path, frames: int) -> None:
    """Stop before the compose if libass would draw the captions with another font.

    Draws the captions small (`FONT_CHECK_SIZE`) with `probe_captions` and applies
    `check_fonts` with the style written in the file. libass falls back to a system
    font without failing when the font is missing (docs/03 §5.4: the step must fail
    instead).

    Args:
        captions_path: The ASS file.
        fonts_dir: Folder with the font files the captions use.
        frames: Number of frames to draw, one per keyframe of the clip, so every line
            of the file is drawn.

    Raises:
        RuntimeError: If `fonts_dir` has no font file, FFmpeg exits with an error,
            nothing was drawn, or libass picked a font of another family or weight, or
            none.
        subprocess.TimeoutExpired: If FFmpeg runs for more than 300 s.
        ValueError: If the file has no `Style: Caption,...` line (`read_ass_style`).

    Example:
        With the family misspelled as "Figtreee" in the ASS style, on Windows, it
        stops with `RuntimeError: the captions need Figtreee Bold in <fonts_dir>, but
        libass picked: Figtreee -> Arial-BoldMT`. With the test stretch's captions it
        passes, in 0.4 s (measured on 26 nov 2026).
    """
    _, fonts = probe_captions(captions_path, fonts_dir, frames, size=FONT_CHECK_SIZE)
    check = check_fonts(fonts, read_ass_style(captions_path.read_text(encoding="utf8")))
    if not check.ok:
        raise RuntimeError(
            f"the captions need {check.limit.removeprefix('only ')} in {fonts_dir}, "
            f"but libass picked: {check.value}"
        )
