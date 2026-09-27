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
# httpx's INFO log includes ChatGPT's signed upload URL and its temporary token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("tutorialflow")

from tutorialflow.audio.elevenlabs import ElevenLabsError, list_voices
from tutorialflow.brand_presets import canonical_brand_preset
from tutorialflow.config import settings
from tutorialflow.storage.cleanup import cleanup_expired_projects
from tutorialflow.storage.workspace import (
    ProjectError,
    project_path,
    resolve_artifact,
    validate_artifact_token,
)
from tutorialflow.tools.generate_voice import (
    generate_segmented_voiceover as make_segmented_voiceover,
    generate_voiceover as make_voiceover,
)
from tutorialflow.tools.get_result import build_thumbnail_brief as make_thumbnail_brief
from tutorialflow.tools.get_result import get_tutorial_result as result_for
from tutorialflow.tools.inspect_video import inspect_video
from tutorialflow.tools.project_manager import delete_tutorial_project as delete_project_tool
from tutorialflow.tools.save_script import save_tutorial_script as save_script_tool
from tutorialflow.tools.sync_video import sync_tutorial as sync_video_tool
from tutorialflow.video.ffmpeg import media_tools_status
from tutorialflow.video.thumbnail import render_thumbnail


class ChatGPTFile(BaseModel):
    """File reference supplied by ChatGPT's MCP fileParams contract."""

    model_config = ConfigDict(extra="forbid")
    download_url: str = Field(description="Temporary HTTPS URL from which the service streams the uploaded recording")
    file_id: str = Field(description="ChatGPT file identifier for this upload")
    mime_type: str | None = None
    file_name: str | None = None


class NarrationSegment(BaseModel):
    """One spoken scene cue, anchored to the original recording timeline."""

    model_config = ConfigDict(extra="forbid")
    start_seconds: float = Field(description="Original video time in seconds when this scene narration begins")
    text: str = Field(description="Narration for this scene only")


public_host = urlsplit(settings.app_base_url).hostname or "localhost"
local_hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*", "testserver"]
allowed_hosts = list(dict.fromkeys([public_host, f"{public_host}:*", *local_hosts]))
allowed_origins = [f"{urlsplit(settings.app_base_url).scheme}://{public_host}", "http://localhost", "http://127.0.0.1"]

mcp = MCPServer(
    name="TutorialFlow",
    version="0.3.0",
    instructions=(
        "An uploaded video addressed to TutorialFlow requests the complete tutorial unless the user explicitly "
        "asks for script review or script only. First call inspect_tutorial_video and inspect its returned frames. "
        "Never infer actions from the filename. Write short, timestamped narration segments anchored to the returned "
        "keyframe time_seconds values. Leave gaps when the recording pauses or changes task; never retime or stretch "
        "the video to fit speech. Then call finish_tutorial once with the project_id, short title, and ordered "
        "narration_segments. Include product_name only when visible in the recording. The server uses the Roger "
        "voice, calls ElevenLabs once per segment, places each clip on the source timeline, stream-copies the source "
        "video, and creates the thumbnail. "
        "Return the artifact links. Never ask the user to provide ElevenLabs audio. If inspection or completion "
        "fails, report the exact tool error and stop."
    ),
)


@mcp.tool(meta={"openai/fileParams": ["video"]})
def inspect_tutorial_video(video: ChatGPTFile, brand: str = "general"):
    """Inspect an uploaded recording and return actual frames with source timestamps."""
    try:
        details = inspect_video(video.model_dump(exclude_none=True), canonical_brand_preset(brand))
    except (TypeError, ValueError, ProjectError) as exc:
        raise ToolError(str(exc)) from exc
    details["next_step"] = "For a complete tutorial, write short narration_segments anchored to visible keyframe time_seconds values, then call finish_tutorial with project_id, title, and narration_segments. The server uses Roger, makes one speech clip per cue, preserves the original video timing, and returns the MP3, MP4, and thumbnail."
    root = project_path(details["project_id"])
    blocks = [TextContent(type="text", text=json.dumps(details, ensure_ascii=False))]
    blocks.append(Image(path=root / details["contact_sheet_path"]))
    for item in details["keyframes"]:
        blocks.append(Image(path=root / item["preview_path"]))
    return blocks


@mcp.tool()
def list_elevenlabs_voices() -> dict:
    """List account voices. finish_tutorial uses the Roger voice and does not fall back to another voice."""
    try:
        return {"voices": list_voices()}
    except ElevenLabsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(annotations={"destructiveHint": False, "readOnlyHint": False})
def generate_voiceover(project_id: str, script: str, voice_id: str | None = None, model: str | None = None) -> dict:
    """Manual/review mode: send narration text to ElevenLabs. For complete tutorials call finish_tutorial instead."""
    try:
        return make_voiceover(project_id, script, voice_id, model)
    except ElevenLabsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def save_tutorial_script(project_id: str, script: str) -> dict:
    """Review mode only: save a visibly supported script without generating speech. Auto mode uses finish_tutorial."""
    return save_script_tool(project_id, script)


@mcp.tool()
def sync_tutorial(project_id: str, strategy: str = "auto") -> dict:
    """Place narrated scene clips at their source timestamps. The source video is never retimed."""
    return sync_video_tool(project_id, strategy)


@mcp.tool()
def build_thumbnail_brief(project_id: str, title: str, brand: str = "general",
                          product_name: str | None = None):
    """Optional manual brief for native image generation. Pass product_name only when visible in the recording."""
    try:
        brief = make_thumbnail_brief(project_id, title, canonical_brand_preset(brand), product_name)
    except (TypeError, ValueError, ProjectError) as exc:
        raise ToolError(str(exc)) from exc
    path = resolve_artifact(project_id, brief["evidence_frame_path"])
    return [TextContent(type="text", text=json.dumps(brief, ensure_ascii=False)), Image(path=path)]


def _roger_voice_id() -> str:
    voices = [voice for voice in list_voices() if voice.get("voice_id")]
    roger_voices = [voice for voice in voices if str(voice.get("name", "")).casefold().startswith("roger")]
    if settings.elevenlabs_voice_id:
        configured = next((voice for voice in roger_voices
                           if voice["voice_id"] == settings.elevenlabs_voice_id), None)
        if configured:
            return configured["voice_id"]
    exact = next((voice for voice in roger_voices
                  if str(voice.get("name", "")).casefold() == "roger - laid-back, casual, resonant"), None)
    selected = exact or next(iter(roger_voices), None)
    if selected:
        return selected["voice_id"]
    raise ElevenLabsError(
        "The Roger voice is not available on this ElevenLabs account. Add 'Roger - Laid-Back, Casual, Resonant' "
        "to the account before generating; TutorialFlow will not silently switch to another voice."
    )


@mcp.tool(annotations={"destructiveHint": False, "readOnlyHint": False})
def finish_tutorial(project_id: str, title: str, narration_segments: list[NarrationSegment],
                    brand: str = "general", product_name: str | None = None) -> dict:
    """Generate Roger voice clips at scene timestamps, preserve source video timing, and return the finished tutorial."""
    try:
        selected_brand = canonical_brand_preset(brand)
        segments = [segment.model_dump() for segment in narration_segments]
        script = "\n\n".join(segment["text"].strip() for segment in segments)
        save_script_tool(project_id, script)
        selected_voice = _roger_voice_id()
        make_segmented_voiceover(project_id, segments, selected_voice)
        sync_video_tool(project_id, "segments")
        thumbnail_error = None
        try:
            render_thumbnail(project_id, title, selected_brand, product_name)
        except (OSError, TypeError, ValueError, ProjectError) as exc:
            thumbnail_error = str(exc)
            logger.error("Thumbnail creation failed project_id=%s reason=%s", project_id, thumbnail_error)
        result = result_for(project_id)
        result["selected_voice_id"] = selected_voice
        if thumbnail_error:
            result["thumbnail_error"] = thumbnail_error
        return result
    except (ElevenLabsError, TypeError, ValueError, ProjectError) as exc:
        raise ToolError(str(exc)) from exc


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


app = FastAPI(title="TutorialFlow", version="0.3.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    tools = media_tools_status()
    return {"status": "ok" if all(tools.values()) else "degraded", **tools}


ARTIFACT_PATH_RE = re.compile(r"^(?:output/(?:tutorial\.mp4|thumbnail\.png)|audio/(?:narration|timeline)\.mp3|script\.txt|frames/(?:contact_sheet\.jpg|frame_[0-9]{2}\.jpg|preview_[0-9]{2}\.jpg))$")


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
