from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager, suppress
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import TextContent
from pydantic import BaseModel, ConfigDict, Field

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("uvicorn.access").disabled = True
logger = logging.getLogger("tutorialflow")

from tutorialflow.audio.elevenlabs import ElevenLabsError, list_voices
from tutorialflow.config import settings
from tutorialflow.brand_presets import canonical_brand_preset
from tutorialflow.storage.cleanup import cleanup_expired_projects
from tutorialflow.storage.workspace import (
    ProjectError,
    project_path,
    resolve_artifact,
    validate_artifact_token,
)
from tutorialflow.tools.generate_voice import generate_voiceover as make_voiceover
from tutorialflow.tools.get_result import build_thumbnail_brief as make_thumbnail_brief
from tutorialflow.tools.get_result import get_tutorial_result as result_for
from tutorialflow.tools.inspect_video import inspect_video
from tutorialflow.tools.project_manager import delete_tutorial_project as delete_project_tool
from tutorialflow.tools.save_script import save_tutorial_script as save_script_tool
from tutorialflow.tools.sync_video import sync_tutorial as sync_video_tool
from tutorialflow.video.ffmpeg import media_tools_status


class ChatGPTFile(BaseModel):
    """File reference supplied by ChatGPT's MCP fileParams contract."""

    model_config = ConfigDict(extra="forbid")
    download_url: str = Field(description="Temporary HTTPS URL from which the service streams the uploaded recording")
    file_id: str = Field(description="ChatGPT file identifier for this upload")
    mime_type: str | None = None
    file_name: str | None = None


public_host = urlsplit(settings.app_base_url).hostname or "localhost"
local_hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "testserver"]
allowed_hosts = list(dict.fromkeys([public_host, f"{public_host}:*", *local_hosts]))
allowed_origins = [f"{urlsplit(settings.app_base_url).scheme}://{public_host}", "http://localhost", "http://127.0.0.1"]

mcp = MCPServer(
    name="TutorialFlow",
    version="0.1.2",
    instructions=(
        "Use returned video frames as evidence; never infer actions from filenames. If video inspection fails, "
        "stop and report the tool error; do not draft from uninspected footage or ask the user for ElevenLabs audio. "
        "For a complete tutorial, "
        "save the narration, select an available voice with list_elevenlabs_voices when no voice ID is "
        "configured, call generate_voiceover (ElevenLabs API), sync the video, prepare a thumbnail "
        "brief, and fetch the result. Never ask the user to supply ElevenLabs audio. Pause only for an "
        "explicit script-review or script-only request. If TTS fails, report the tool error."
    ),
)


@mcp.tool(meta={"openai/fileParams": ["video"]})
def inspect_tutorial_video(video: ChatGPTFile, brand: str = "education_global"):
    """Inspect an uploaded recording and return its actual frames. Brand accepts education_global/Education Global or default/TutorialFlow."""
    try:
        details = inspect_video(video.model_dump(exclude_none=True), canonical_brand_preset(brand))
    except (ValueError, ProjectError) as exc:
        raise ToolError(str(exc)) from exc
    root = project_path(details["project_id"])
    blocks = [TextContent(type="text", text=json.dumps(details, ensure_ascii=False))]
    blocks.append(Image(path=root / details["contact_sheet_path"]))
    for item in details["keyframes"]:
        blocks.append(Image(path=root / item["preview_path"]))
    return blocks


@mcp.tool()
def list_elevenlabs_voices() -> dict:
    """List account voices so the workflow can select one when no default voice ID is configured."""
    try:
        return {"voices": list_voices()}
    except ElevenLabsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(annotations={"destructiveHint": False, "readOnlyHint": False})
def generate_voiceover(project_id: str, script: str, voice_id: str | None = None, model: str | None = None) -> dict:
    """Send narration text to the configured ElevenLabs API and return the generated audio artifact."""
    try:
        return make_voiceover(project_id, script, voice_id, model)
    except ElevenLabsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def save_tutorial_script(project_id: str, script: str) -> dict:
    """Save ChatGPT's reviewed, visibly-supported script without generating speech."""
    return save_script_tool(project_id, script)


@mcp.tool()
def sync_tutorial(project_id: str, strategy: str = "auto") -> dict:
    """Retiming-render the inspected screen recording to the generated narration."""
    return sync_video_tool(project_id, strategy)


@mcp.tool()
def build_thumbnail_brief(project_id: str, title: str, brand: str = "education_global"):
    """Prepare a branded thumbnail brief; brand accepts education_global/Education Global or default/TutorialFlow."""
    try:
        brief = make_thumbnail_brief(project_id, title, canonical_brand_preset(brand))
    except (ValueError, ProjectError) as exc:
        raise ToolError(str(exc)) from exc
    path = resolve_artifact(project_id, brief["evidence_frame_path"])
    return [TextContent(type="text", text=json.dumps(brief, ensure_ascii=False)), Image(path=path)]


@mcp.tool()
def get_tutorial_result(project_id: str) -> dict:
    """Return project status, script, and temporary download URLs for available artifacts."""
    cleanup_expired_projects()
    return result_for(project_id)


@mcp.tool(annotations={"destructiveHint": True, "readOnlyHint": False})
def delete_tutorial_project(project_id: str) -> dict:
    """Permanently remove one temporary project and all of its media."""
    return delete_project_tool(project_id)


@asynccontextmanager
async def lifespan(_: FastAPI):
    deleted = await asyncio.to_thread(cleanup_expired_projects)
    if deleted:
        logger.info("Startup cleanup removed projects count=%d", len(deleted))
    async with mcp.session_manager.run():
        cleanup_task = asyncio.create_task(_periodic_cleanup())
        try:
            yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task


async def _periodic_cleanup() -> None:
    while True:
        await asyncio.sleep(60 * 60)
        await asyncio.to_thread(cleanup_expired_projects)


app = FastAPI(title="TutorialFlow", version="0.1.2", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    tools = media_tools_status()
    return {"status": "ok" if all(tools.values()) else "degraded", **tools}


ARTIFACT_PATH_RE = re.compile(r"^(?:output/tutorial\.mp4|audio/narration\.mp3|script\.txt|frames/(?:contact_sheet\.jpg|frame_[0-9]{2}\.jpg|preview_[0-9]{2}\.jpg))$")


@app.get("/artifacts/{project_id}/{artifact_path:path}")
def download_artifact(project_id: str, artifact_path: str, token: str = Query(min_length=20)):
    if not ARTIFACT_PATH_RE.fullmatch(artifact_path):
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not validate_artifact_token(project_id, token):
        raise HTTPException(status_code=404, detail="Artifact not found or expired")
    try:
        path = resolve_artifact(project_id, artifact_path)
    except ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name, headers={"Cache-Control": "private, no-store"})


app.mount(
    "/",
    mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        )
    ),
)
