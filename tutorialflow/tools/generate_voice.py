from __future__ import annotations

import logging
import math
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
    record.pop("audio_segments", None)
    set_project_status(record, "voice_ready")
    save_project(project_id, record)
    logger.info("Voice generated project_id=%s cached=%s", project_id, audio_info.get("cached"))
    return {
        "project_id": project_id, "status": "voice_ready", "audio_duration": duration,
        "character_count": len(script), "voice_id": chosen_voice,
        "audio_artifact": f"{settings.app_base_url}/artifacts/{project_id}/audio/narration.mp3?token={record['artifact_token']}",
        "cached": audio_info.get("cached", False),
    }




def generate_segmented_voiceover(
    project_id: str,
    segments: list[dict],
    voice_id: str,
    model: str | None = None,
) -> dict:
    """Generate separate clips for timestamped scenes without retiming the source video."""
    if not PROJECT_RE.fullmatch(project_id):
        raise ValueError("Invalid project ID.")
    if not isinstance(segments, list) or not segments or len(segments) > 100:
        raise ValueError("Provide between 1 and 100 timestamped narration segments.")
    if not voice_id:
        raise ElevenLabsError("The Roger voice was not resolved for this tutorial.")

    record = load_project(project_id)
    video_duration = float(record.get("source", {}).get("duration_seconds") or 0)
    if not math.isfinite(video_duration) or video_duration <= 0:
        raise ValueError("Inspect the source video before generating timestamped narration.")

    normalized: list[dict] = []
    previous_start = -1.0
    total_characters = 0
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise ValueError(f"Narration segment {index} must contain start_seconds and text.")
        try:
            start = float(segment["start_seconds"])
            text = segment["text"].strip()
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"Narration segment {index} must contain a numeric start_seconds and non-empty text.") from exc
        if not math.isfinite(start) or start < 0 or start >= video_duration:
            raise ValueError(f"Narration segment {index} starts outside the {video_duration:.2f}-second source video.")
        if start <= previous_start:
            raise ValueError("Narration segments must be ordered by strictly increasing start_seconds.")
        if not text:
            raise ValueError(f"Narration segment {index} has no text.")
        total_characters += len(text)
        normalized.append({"start_seconds": start, "text": text})
        previous_start = start
    if total_characters > 12000:
        raise ValueError("The narration must be at most 12,000 characters.")

    root = project_path(project_id)
    chosen_model = model or settings.elevenlabs_model
    previous_status = record.get("status", "inspected")
    record.pop("audio_segments", None)
    record.pop("audio", None)
    set_project_status(record, "processing_voice")
    save_project(project_id, record)
    generated: list[dict] = []
    try:
        for index, segment in enumerate(normalized, start=1):
            path = root / "audio" / "segments" / f"segment_{index:03d}.mp3"
            audio_info = generate_speech(segment["text"], voice_id, chosen_model, path)
            duration = audio_duration(path)
            generated.append({
                **segment,
                "duration_seconds": duration,
                "path": str(path.relative_to(root).as_posix()),
                "cached": audio_info.get("cached", False),
            })

        for index, segment in enumerate(generated):
            next_start = (generated[index + 1]["start_seconds"]
                          if index + 1 < len(generated) else video_duration)
            end = segment["start_seconds"] + segment["duration_seconds"]
            if end > next_start + 0.005:
                if index + 1 < len(generated):
                    raise ValueError(
                        f"Narration segment {index + 1} lasts {segment['duration_seconds']:.2f}s and overlaps "
                        f"the next cue at {next_start:.2f}s. Shorten it or move the next cue later."
                    )
                raise ValueError(
                    f"The final narration segment ends at {end:.2f}s, after the source video ends at "
                    f"{video_duration:.2f}s. Shorten it or move it earlier."
                )
    except Exception as exc:
        set_project_status(record, previous_status)
        save_project(project_id, record)
        if isinstance(exc, (ElevenLabsError, ValueError)):
            raise
        raise ValueError(f"Segmented narration generation failed: {exc}") from exc

    script = "\n\n".join(segment["text"] for segment in normalized)
    script_file = root / "script.txt"
    script_file.write_text(script + "\n", encoding="utf-8")
    record["script"] = {"text": script, "character_count": len(script), "path": "script.txt"}
    record["audio_segments"] = generated
    record["audio"] = {
        "voice_id": voice_id,
        "model": chosen_model,
        "segment_count": len(generated),
        "duration_seconds": video_duration,
    }
    set_project_status(record, "voice_ready")
    save_project(project_id, record)
    logger.info("Segmented voice generated project_id=%s segment_count=%d", project_id, len(generated))
    return {
        "project_id": project_id,
        "status": "voice_ready",
        "segment_count": len(generated),
        "video_duration_seconds": video_duration,
        "voice_id": voice_id,
        "all_segments_cached": all(segment["cached"] for segment in generated),
    }
