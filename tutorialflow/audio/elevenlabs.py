from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx

from tutorialflow.config import settings

API_ROOT = "https://api.elevenlabs.io/v1"


class ElevenLabsError(RuntimeError):
    pass


def _raise_api_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    detail = {}
    try:
        payload = response.json()
        candidate = payload.get("detail", {}) if isinstance(payload, dict) else {}
        if isinstance(candidate, dict):
            detail = candidate
    except (ValueError, json.JSONDecodeError):
        pass
    if detail.get("status") == "api_key_id_used_as_api_key":
        message = "ELEVENLABS_API_KEY contains the key ID, not the API key secret. Replace it with the secret key shown when the key was created; it starts with 'sk_'."
    elif detail.get("status") == "missing_permissions":
        missing = detail.get("message", "")
        if "voices_read" in missing:
            message = "The ElevenLabs API key lacks Voices Read (voices_read). Enable that permission on the key, or configure ELEVENLABS_VOICE_ID to bypass voice listing. Text to Speech permission is also required for narration."
        else:
            message = f"The ElevenLabs API key lacks a required permission: {missing or 'check the key restrictions'}."
    elif response.status_code == 401 or detail.get("code") == "invalid_api_key":
        message = "ElevenLabs rejected the API key. Check ELEVENLABS_API_KEY."
    elif response.status_code == 429:
        message = "ElevenLabs rate limit or account quota reached. Wait or check your plan quota."
    elif response.status_code == 422:
        message = "ElevenLabs rejected the voice or model. Check that both are available to your account."
    else:
        message = f"ElevenLabs request failed (HTTP {response.status_code})."
    raise ElevenLabsError(message)


def list_voices() -> list[dict]:
    if not settings.elevenlabs_api_key:
        raise ElevenLabsError("ELEVENLABS_API_KEY is not configured on the service.")
    try:
        response = httpx.get(f"{API_ROOT}/voices", headers={"xi-api-key": settings.elevenlabs_api_key}, timeout=30)
        _raise_api_error(response)
        data = response.json()
    except httpx.HTTPError as exc:
        raise ElevenLabsError("Could not reach ElevenLabs. Try again shortly.") from exc
    voices = []
    for voice in data.get("voices", []):
        voices.append({
            "name": voice.get("name"), "voice_id": voice.get("voice_id"),
            "category": voice.get("category"), "description": voice.get("description"),
            "labels": voice.get("labels", {}), "preview_url": voice.get("preview_url"),
        })
    return voices


def script_cache_key(script: str, voice_id: str, model: str) -> str:
    return hashlib.sha256(f"{script}\0{voice_id}\0{model}".encode()).hexdigest()


def generate_speech(script: str, voice_id: str, model: str, target: Path) -> dict:
    if not settings.elevenlabs_api_key:
        raise ElevenLabsError("ELEVENLABS_API_KEY is not configured on the service.")
    if not voice_id:
        raise ElevenLabsError("Choose a voice ID from list_elevenlabs_voices or configure ELEVENLABS_VOICE_ID.")
    key = script_cache_key(script, voice_id, model)
    metadata_path = target.with_suffix(".json")
    if target.exists() and metadata_path.exists():
        try:
            cached = json.loads(metadata_path.read_text(encoding="utf-8"))
            if cached.get("cache_key") == key:
                return {**cached, "cached": True}
        except (OSError, json.JSONDecodeError):
            pass
    url = f"{API_ROOT}/text-to-speech/{voice_id}"
    try:
        with httpx.stream(
            "POST", url,
            headers={"xi-api-key": settings.elevenlabs_api_key, "Accept": "audio/mpeg", "Content-Type": "application/json"},
            json={"text": script, "model_id": model}, timeout=120,
        ) as response:
            _raise_api_error(response)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as out:
                for chunk in response.iter_bytes(64 * 1024):
                    out.write(chunk)
    except httpx.HTTPError as exc:
        target.unlink(missing_ok=True)
        raise ElevenLabsError("Could not connect to ElevenLabs. Try again shortly.") from exc
    except Exception:
        target.unlink(missing_ok=True)
        raise
    metadata = {"cache_key": key, "voice_id": voice_id, "model": model, "character_count": len(script), "cached": False}
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
