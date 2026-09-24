from __future__ import annotations

from pathlib import Path

from tutorialflow.utils.subprocess_utils import run_media_command


def audio_duration(path: Path) -> float:
    result = run_media_command([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ], timeout=60)
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise ValueError("Could not read narration duration.") from exc
