from __future__ import annotations

import shutil

from tutorialflow.utils.subprocess_utils import run_media_command


def media_tools_status() -> dict[str, bool]:
    return {name: shutil.which(name) is not None for name in ("ffmpeg", "ffprobe")}


def retiming_factor(video_duration: float, audio_duration: float) -> float:
    """Output duration / input video duration; values <1 speed video up."""
    if video_duration <= 0 or audio_duration <= 0:
        raise ValueError("Video and audio duration must both be positive.")
    return audio_duration / video_duration


def render_command(video: str, audio: str, output: str, video_duration: float, audio_duration: float) -> list[str]:
    factor = retiming_factor(video_duration, audio_duration)
    # setpts tolerates broad factors; cap to protect against extreme duration mismatches.
    if not 0.25 <= factor <= 4.0:
        raise ValueError("Narration/video duration ratio is outside the safe range (0.25–4.0). Revise the script.")
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video, "-i", audio,
        "-filter:v", f"setpts={factor:.8f}*PTS", "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-t", f"{audio_duration:.3f}",
        "-movflags", "+faststart", "-y", output,
    ]


def render_video(args: list[str]) -> None:
    run_media_command(args, timeout=1800)
