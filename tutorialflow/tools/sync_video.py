from __future__ import annotations

import logging
import threading

from tutorialflow.audio.duration import audio_duration
from tutorialflow.config import settings
from tutorialflow.storage.workspace import (
    load_project,
    project_path,
    save_project,
    set_project_status,
)
from tutorialflow.video.ffmpeg import render_command, render_video

logger = logging.getLogger(__name__)
_render_slots = threading.BoundedSemaphore(max(1, settings.max_concurrent_renders))


def sync_tutorial(project_id: str, strategy: str = "auto") -> dict:
    if strategy not in {"auto", "global"}:
        raise ValueError("Only the global auto sync strategy is available in this MVP.")
    record = load_project(project_id)
    if not record.get("source", {}).get("path") or not record.get("audio", {}).get("path"):
        raise ValueError("Inspect the recording and generate narration before syncing.")
    root = project_path(project_id)
    source = root / record["source"]["path"]
    audio = root / record["audio"]["path"]
    output = root / "output" / "tutorial.mp4"
    video_seconds = record["source"]["duration_seconds"]
    spoken_seconds = audio_duration(audio)
    command = render_command(str(source), str(audio), str(output), video_seconds, spoken_seconds)
    set_project_status(record, "rendering")
    save_project(project_id, record)
    logger.info("Render started project_id=%s", project_id)
    if not _render_slots.acquire(blocking=False):
        set_project_status(record, "voice_ready")
        save_project(project_id, record)
        raise ValueError("A render is already running on this service. Retry in a moment.")
    try:
        render_video(command)
    except Exception as exc:
        set_project_status(record, "failed")
        save_project(project_id, record)
        raise ValueError(f"Video rendering failed: {exc}") from exc
    finally:
        _render_slots.release()
    set_project_status(record, "rendered")
    record["output"] = {"path": "output/tutorial.mp4", "duration_seconds": spoken_seconds}
    save_project(project_id, record)
    logger.info("Render completed project_id=%s", project_id)
    return {
        "project_id": project_id, "status": "rendered", "duration_seconds": spoken_seconds,
        "video_artifact": f"{settings.app_base_url}/artifacts/{project_id}/output/tutorial.mp4?token={record['artifact_token']}",
    }
