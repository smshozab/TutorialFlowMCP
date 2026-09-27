from __future__ import annotations

import logging
import math
import threading

from tutorialflow.audio.duration import audio_duration
from tutorialflow.config import settings
from tutorialflow.storage.workspace import (
    load_project,
    project_path,
    resolve_artifact,
    save_project,
    set_project_status,
)
from tutorialflow.video.ffmpeg import render_command, render_video, timeline_audio_command

logger = logging.getLogger(__name__)
_render_slots = threading.BoundedSemaphore(max(1, settings.max_concurrent_renders))


def _timeline_segments(project_id: str, record: dict, video_duration: float,
                       require_segments: bool) -> list[dict]:
    stored = record.get("audio_segments") or []
    if require_segments and not stored:
        raise ValueError("No timestamped narration segments were generated. Call finish_tutorial with scene timestamps.")
    if not stored:
        audio_path = record.get("audio", {}).get("path")
        if not audio_path:
            raise ValueError("Generate narration before syncing the tutorial.")
        path = resolve_artifact(project_id, audio_path)
        duration = audio_duration(path)
        if duration > video_duration + 0.005:
            raise ValueError(
                f"Narration lasts {duration:.2f}s but the source video is {video_duration:.2f}s. "
                "Shorten the narration; TutorialFlow will not speed up or extend the recording."
            )
        return [{
            "path": str(path),
            "start_seconds": 0.0,
            "duration_seconds": duration,
        }]

    root = project_path(project_id)
    segments = []
    previous_start = -1.0
    for index, segment in enumerate(stored, start=1):
        try:
            start = float(segment["start_seconds"])
            duration = float(segment["duration_seconds"])
            relative_path = segment["path"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Stored narration segment {index} has invalid timing metadata.") from exc
        if not math.isfinite(start) or not math.isfinite(duration) or start < 0 or duration <= 0:
            raise ValueError(f"Stored narration segment {index} has invalid timing metadata.")
        if start <= previous_start:
            raise ValueError("Stored narration segments are not in chronological order.")
        path = resolve_artifact(project_id, relative_path)
        actual_duration = audio_duration(path)
        if start + actual_duration > video_duration + 0.005:
            raise ValueError(
                f"Narration segment {index} ends after the source video. Shorten it or move it earlier."
            )
        if index < len(stored):
            try:
                next_start = float(stored[index]["start_seconds"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Stored narration segment {index + 1} has invalid timing metadata.") from exc
            if start + actual_duration > next_start + 0.005:
                raise ValueError(
                    f"Narration segment {index} overlaps the next timestamp. Shorten the cue or move it later."
                )
        segments.append({"path": str(path), "start_seconds": start, "duration_seconds": actual_duration})
        previous_start = start
    return segments


def sync_tutorial(project_id: str, strategy: str = "auto") -> dict:
    if strategy not in {"auto", "segments"}:
        raise ValueError("Use `auto` for timestamped cues or `segments` to require them. Global video retiming is disabled.")
    record = load_project(project_id)
    source_relative = record.get("source", {}).get("path")
    video_duration = float(record.get("source", {}).get("duration_seconds") or 0)
    if not source_relative or not math.isfinite(video_duration) or video_duration <= 0:
        raise ValueError("Inspect the source video before syncing the tutorial.")
    source = resolve_artifact(project_id, source_relative)
    segments = _timeline_segments(project_id, record, video_duration, require_segments=(strategy == "segments"))
    root = project_path(project_id)
    timeline_audio = root / "audio" / "timeline.mp3"
    output = root / "output" / "tutorial.mp4"

    set_project_status(record, "rendering")
    save_project(project_id, record)
    logger.info("Segmented render started project_id=%s segment_count=%d", project_id, len(segments))
    if not _render_slots.acquire(blocking=False):
        set_project_status(record, "voice_ready")
        save_project(project_id, record)
        raise ValueError("A render is already running on this service. Retry in a moment.")
    try:
        render_video(timeline_audio_command(segments, video_duration, str(timeline_audio)))
        render_video(render_command(str(source), str(timeline_audio), str(output), video_duration))
    except Exception as exc:
        set_project_status(record, "failed")
        save_project(project_id, record)
        raise ValueError(f"Video rendering failed: {exc}") from exc
    finally:
        _render_slots.release()

    set_project_status(record, "rendered")
    record.setdefault("audio", {})["timeline_path"] = "audio/timeline.mp3"
    record["audio"]["duration_seconds"] = video_duration
    has_scene_cues = bool(record.get("audio_segments"))
    record["output"] = {
        "path": "output/tutorial.mp4",
        "duration_seconds": video_duration,
        "video_stream_copied": True,
        "synchronization": "timestamped_segments" if has_scene_cues else "single_cue_at_zero",
        "segment_count": len(segments),
    }
    save_project(project_id, record)
    logger.info("Segmented render completed project_id=%s duration=%.3f", project_id, video_duration)
    return {
        "project_id": project_id,
        "status": "rendered",
        "duration_seconds": video_duration,
        "segment_count": len(segments),
        "video_stream_copied": True,
        "video_artifact": f"{settings.app_base_url}/artifacts/{project_id}/output/tutorial.mp4?token={record['artifact_token']}",
    }
