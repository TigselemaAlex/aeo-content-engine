# Content Engine worker

Python worker for the Content Engine. Managed with [uv](https://docs.astral.sh/uv/).

## Running commands

From `worker/`:

```
uv run python -m content_engine <command>    # hello, extract-audio, transcribe, cut, detect-faces, camera-path, compose, verify-clip
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
