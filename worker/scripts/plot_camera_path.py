"""Plot a camera path over the face boxes, to check by eye that it is stable.

The top panel shows, over clip time in seconds, the horizontal span of each face box
(x to x + w) in gray and the edges and center of the crop window; the bottom panel shows
the width of the window, which shrinks on zooms and cut bridges. Positions are in
mezzanine pixels; times come in as clip milliseconds and are drawn in seconds
(ms / 1000 -> s). A development tool for docs/07 T2.2, outside the package.

Usage: uv run python scripts/plot_camera_path.py camera-path.json faces.json camera-path.png
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main(path_file: Path, faces_file: Path, output: Path) -> None:
    """Draw the crop window and the face boxes over time and save the chart as an image.

    Args:
        path_file: JSON of the `camera-path` command, with a `keyframes` list.
        faces_file: JSON of the `detect-faces` command: a list of face boxes.
        output: Image to write. Its extension picks the format, for example `.png`.

    Example:
        The chart is 14 x 7 inches at 100 dpi, so 1400x700 px; both values were picked by
        the developer so the chart reads well and can be changed. For the test mezzanine
        (words 29 to 108) it draws 1004 keyframes and 335 face boxes over 33.5 s.
    """
    keyframes = json.loads(path_file.read_text(encoding="utf8"))["keyframes"]
    faces = json.loads(faces_file.read_text(encoding="utf8"))

    window_t = [k["t_ms"] / 1000 for k in keyframes]
    face_t = [f["t_ms"] / 1000 for f in faces]

    figure, (top, bottom) = plt.subplots(2, 1, figsize=(14, 7), sharex=True, height_ratios=[3, 1])

    top.fill_between(
        face_t,
        [f["x"] for f in faces],
        [f["x"] + f["w"] for f in faces],
        color="#cccccc",
        label="face box",
    )
    top.plot(window_t, [k["x"] for k in keyframes], color="C1", lw=1, label="window edges")
    top.plot(window_t, [k["x"] + k["w"] for k in keyframes], color="C1", lw=1)
    top.plot(
        window_t,
        [k["x"] + k["w"] / 2 for k in keyframes],
        color="C0",
        lw=1.5,
        label="window center",
    )
    top.set_ylabel("x (px)")
    top.legend(loc="upper right")
    top.set_title("Camera path over time")

    bottom.plot(window_t, [k["w"] for k in keyframes], color="C2")
    bottom.set_ylabel("window width (px)")
    bottom.set_xlabel("clip time (s)")

    figure.tight_layout()
    # matplotlib types **kwargs of savefig as unknown; nothing to fix on our side.
    figure.savefig(output, dpi=100)  # pyright: ignore[reportUnknownMemberType]
    print(f"Plot saved to {output}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
