import json

import httpx
import respx

from tutorialflow.audio import elevenlabs


def test_elevenlabs_mock_response_and_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(elevenlabs, "settings", type("S", (), {"elevenlabs_api_key": "fake", "elevenlabs_model": "eleven_flash_v2_5"})())
    target = tmp_path / "narration.mp3"
    with respx.mock as router:
        route = router.post("https://api.elevenlabs.io/v1/text-to-speech/voice-1").mock(
            return_value=httpx.Response(200, content=b"fake mp3 bytes")
        )
        first = elevenlabs.generate_speech("Hello tutorial", "voice-1", "eleven_flash_v2_5", target)
    assert route.called
    assert target.read_bytes() == b"fake mp3 bytes"
    assert first["cached"] is False
    # A repeat with identical inputs must reuse the saved MP3 without consuming credits.
    with respx.mock as router:
        router.post("https://api.elevenlabs.io/v1/text-to-speech/voice-1").mock(
            return_value=httpx.Response(500)
        )
        cached = elevenlabs.generate_speech("Hello tutorial", "voice-1", "eleven_flash_v2_5", target)
    assert cached["cached"] is True
    assert cached["cache_key"] == json.loads(target.with_suffix(".json").read_text())["cache_key"]


def test_validate_project_size():
    from tutorialflow.tools.inspect_video import validate_project_size

    assert validate_project_size(5, 10) == 5
    try:
        validate_project_size(11, 10)
    except ValueError as exc:
        assert "exceeds" in str(exc)
    else:
        raise AssertionError("oversized upload should fail")
