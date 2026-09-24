from __future__ import annotations

import json
import math
from fractions import Fraction
from pathlib import Path

from tutorialflow.utils.subprocess_utils import run_media_command


def parse_duration(value: str | float | None) -> float:
    """Parse ffprobe seconds, HH:MM:SS, or MM:SS into seconds."""
    if value is None:
        raise ValueError("Video duration is missing.")
    try:
        seconds = float(value)
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError(f"Invalid duration: {value}")
        return seconds
    except (TypeError, ValueError):
        parts = str(value).split(":")
        if len(parts) not in (2, 3):
            raise ValueError(f"Invalid duration: {value}")
        try:
            numbers = [float(part) for part in parts]
        except ValueError as exc:
            raise ValueError(f"Invalid duration: {value}") from exc
        seconds = numbers[-1] + numbers[-2] * 60
        if len(numbers) == 3:
            seconds += numbers[0] * 3600
        return seconds


def parse_fps(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe_video(path: Path) -> dict:
    result = run_media_command([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate",
        "-of", "json", str(path),
    ], timeout=90)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("ffprobe returned invalid metadata; the file may be corrupted.") from exc
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("The uploaded file has no video stream.")
    duration = parse_duration(data.get("format", {}).get("duration"))
    fps = parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    return {
        "duration_seconds": duration,
        "fps": fps,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "video_codec": video.get("codec_name", "unknown"),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "file_size_bytes": path.stat().st_size,
    }
