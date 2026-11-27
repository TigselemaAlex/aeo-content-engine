# Content Engine worker

Python worker for the Content Engine. Managed with [uv](https://docs.astral.sh/uv/).

## Running commands

From `worker/`:

```
uv run python -m content_engine <command>    # hello, extract-audio, transcribe, cut, detect-faces, camera-path, captions, compose, verify-clip
uv run python -m pytest
uv run python -m pyright
uv run ruff check
```

Use `python -m` rather than the generated launchers (`uv run content-engine`, `uv run pyright`).
On Windows 11, Smart App Control can block the unsigned `.exe` launchers that uv creates in
`.venv/Scripts/` ("Failed to spawn ... Una directiva de Control de aplicaciones bloqueó este
archivo", os error 4551). It decides per file from Microsoft's cloud reputation, so a launcher
that ran yesterday can be blocked today. `python.exe` is signed, so `python -m` always runs.

## Face detection model

`models/blaze_face_short_range.tflite` is MediaPipe's BlazeFace short-range model, committed to
the repo so the worker does not download anything at run time.

## Caption fonts

`assets/fonts/Figtree-Bold.ttf` is Figtree v2.0.3 from
[erikdkennedy/figtree](https://github.com/erikdkennedy/figtree), under the SIL Open Font License
1.1 (`assets/fonts/OFL.txt`, which must stay next to it). `captions`, `compose --captions` and
`verify-clip --captions` read this folder by default (`--fonts-dir`), so run them from `worker/`.
libass falls back to a system font without failing when a font is missing; `compose` checks the
font libass picked and stops instead.
