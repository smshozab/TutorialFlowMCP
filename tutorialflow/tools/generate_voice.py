from __future__ import annotations

import logging
import re

from tutorialflow.audio.duration import audio_duration
from tutorialflow.audio.elevenlabs import ElevenLabsError, generate_speech
from tutorialflow.config import settings
from tutorialflow.storage.workspace import (
    load_project,
    project_path,
    save_project,
    set_project_status,
)

logger = logging.getLogger(__name__)
PROJECT_RE = re.compile(r"^[0-9]{8}_[a-f0-9]{32}$")


def generate_voiceover(project_id: str, script: str, voice_id: str | None = None, model: str | None = None) -> dict:
    if not PROJECT_RE.fullmatch(project_id):
        raise ValueError("Invalid project ID.")
    if not script or len(script) > 12000:
        raise ValueError("Provide a script between 1 and 12,000 characters.")
    record = load_project(project_id)
    previous_status = record.get("status", "inspected")
    chosen_voice = voice_id or settings.elevenlabs_voice_id
    chosen_model = model or settings.elevenlabs_model
    audio_file = project_path(project_id) / "audio" / "narration.mp3"
    set_project_status(record, "processing_voice")
    save_project(project_id, record)
    try:
        audio_info = generate_speech(script, chosen_voice, chosen_model, audio_file)
        duration = audio_duration(audio_file)
    except Exception as exc:
        set_project_status(record, previous_status)
        save_project(project_id, record)
        if isinstance(exc, ElevenLabsError):
            raise
        raise ValueError(f"Narration generation failed: {exc}") from exc
    script_file = project_path(project_id) / "script.txt"
    script_file.write_text(script.strip() + "\n", encoding="utf-8")
    record["script"] = {"text": script.strip(), "character_count": len(script), "path": "script.txt"}
    record["audio"] = {**audio_info, "duration_seconds": duration, "path": "audio/narration.mp3"}
    set_project_status(record, "voice_ready")
    save_project(project_id, record)
    logger.info("Voice generated project_id=%s cached=%s", project_id, audio_info.get("cached"))
    return {
        "project_id": project_id, "status": "voice_ready", "audio_duration": duration,
        "character_count": len(script), "voice_id": chosen_voice,
        "audio_artifact": f"{settings.app_base_url}/artifacts/{project_id}/audio/narration.mp3?token={record['artifact_token']}",
        "cached": audio_info.get("cached", False),
    }
