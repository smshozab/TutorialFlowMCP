import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import server


def test_health_endpoint_and_chatgpt_file_schema():
    with TestClient(server.app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert "ffmpeg" in health.json() and "ffprobe" in health.json()

        headers = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
        initialized = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        })
        assert initialized.status_code == 200, initialized.text
        session_id = initialized.headers.get("mcp-session-id")
        client.post("/mcp", headers={**headers, "mcp-session-id": session_id}, json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        response = client.post("/mcp", headers={**headers, "mcp-session-id": session_id}, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        data_line = next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
        tools = json.loads(data_line)["result"]["tools"]
        inspect = next(tool for tool in tools if tool["name"] == "inspect_tutorial_video")
        assert any(tool["name"] == "finish_tutorial" for tool in tools)
        assert inspect["_meta"]["openai/fileParams"] == ["video"]
        file_schema = inspect["inputSchema"]["$defs"]["ChatGPTFile"]
        assert file_schema["required"] == ["download_url", "file_id"]
        assert set(file_schema["properties"]) == {"download_url", "file_id", "mime_type", "file_name"}


def test_finish_tutorial_runs_voice_render_and_thumbnail_in_one_call(monkeypatch):
    events = []
    captured = {}
    monkeypatch.setattr(server, "settings", SimpleNamespace(elevenlabs_voice_id=""))
    monkeypatch.setattr(server, "save_script_tool", lambda *_args: events.append("script"))
    monkeypatch.setattr(server, "list_voices", lambda: [
        {"name": "Another Voice", "voice_id": "other-id"},
        {"name": "Roger - Laid-Back, Casual, Resonant", "voice_id": "roger-id"},
    ])

    def fake_segmented_voiceover(_project_id, segments, voice_id):
        events.append("voice")
        captured["segments"] = segments
        captured["voice_id"] = voice_id

    monkeypatch.setattr(server, "make_segmented_voiceover", fake_segmented_voiceover)
    monkeypatch.setattr(server, "sync_video_tool", lambda *_args: events.append("render"))
    monkeypatch.setattr(server, "render_thumbnail", lambda *_args: events.append("thumbnail"))
    monkeypatch.setattr(server, "result_for", lambda _project_id: {"status": "rendered"})

    segments = [
        server.NarrationSegment(start_seconds=0.0, text="Welcome to the editor."),
        server.NarrationSegment(start_seconds=12.5, text="Open the settings panel."),
    ]
    result = server.finish_tutorial("project-id", "Editor walkthrough", segments)

    assert events == ["script", "voice", "render", "thumbnail"]
    assert captured["voice_id"] == "roger-id"
    assert captured["segments"] == [
        {"start_seconds": 0.0, "text": "Welcome to the editor."},
        {"start_seconds": 12.5, "text": "Open the settings panel."},
    ]
    assert result == {"status": "rendered", "selected_voice_id": "roger-id"}
