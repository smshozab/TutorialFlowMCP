from __future__ import annotations

import math
import shutil

from tutorialflow.utils.subprocess_utils import run_media_command


def media_tools_status() -> dict[str, bool]:
    return {name: shutil.which(name) is not None for name in ("ffmpeg", "ffprobe")}


def timeline_audio_command(segments: list[dict], duration: float, output: str) -> list[str]:
    """Place each narration clip at its source timestamp and pad untouched spans with silence."""
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Video duration must be positive to build the narration timeline.")
    if not segments:
        raise ValueError("At least one narration segment is required.")
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    for segment in segments:
        args.extend(["-i", str(segment["path"])])
    filters = []
    labels = []
    for index, segment in enumerate(segments):
        delay_ms = max(0.0, float(segment["start_seconds"])) * 1000
        label = f"cue{index}"
        filters.append(
            f"[{index}:a]asetpts=PTS-STARTPTS,adelay={delay_ms:.3f}|{delay_ms:.3f}[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:dropout_transition=0:normalize=0,"
        f"apad=whole_dur={duration:.6f},atrim=duration={duration:.6f},asetpts=PTS-STARTPTS[mix]"
    )
    args.extend([
        "-filter_complex", ";".join(filters), "-map", "[mix]", "-c:a", "libmp3lame",
        "-q:a", "3", "-t", f"{duration:.6f}", "-y", output,
    ])
    return args


def render_command(video: str, audio: str, output: str, video_duration: float) -> list[str]:
    """Mux narration while stream-copying every source video frame at its original timing."""
    if not math.isfinite(video_duration) or video_duration <= 0:
        raise ValueError("Source video duration must be positive.")
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video, "-i", audio,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k", "-t", f"{video_duration:.6f}",
        "-movflags", "+faststart", "-y", output,
    ]


def render_video(args: list[str]) -> None:
    run_media_command(args, timeout=1800)
