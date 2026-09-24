import json

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
        assert inspect["_meta"]["openai/fileParams"] == ["video"]
        file_schema = inspect["inputSchema"]["$defs"]["ChatGPTFile"]
        assert file_schema["required"] == ["download_url", "file_id"]
        assert set(file_schema["properties"]) == {"download_url", "file_id", "mime_type", "file_name"}
