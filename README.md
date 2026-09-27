# TutorialFlow

TutorialFlow is a Railway-first MCP server that inspects a screen recording, returns timestamped visual evidence to ChatGPT, and uses ElevenLabs and FFmpeg to make a narrated tutorial. ChatGPT writes short scene cues anchored to the recording timeline. Railway creates one voice clip per cue, places it at its cue time, and stream-copies the original video so frames are never stretched or sped up to fit narration. See the [editable Excalidraw architecture](TutorialFlow-Architecture.excalidraw).

## Install your own copy

This repository is public, but the running service is **not a shared hosted product**. Each friend or peer should deploy their own Railway service with their own ElevenLabs API key. The checked-in [`mcp.json`](mcp.json) contains a placeholder URL so installing a copy cannot silently use the maintainer's Railway service or ElevenLabs credits. The MCP endpoint has no user authentication yet; see [Security notes](#security-notes) before inviting others to one deployment.

### 1. Fork and deploy

1. [Fork TutorialFlowMCP on GitHub](https://github.com/smshozab/TutorialFlowMCP/fork) into your account. A local Python or FFmpeg installation is **not** needed for Railway use.
2. In [ElevenLabs](https://elevenlabs.io/), create an API key with **Voices Read** and **Text to Speech** access. Keep the key secret and set an account or key usage limit you are comfortable with. You need the **API key secret**, not the key ID.
3. In [Railway](https://railway.com/), create a project, choose **Deploy from GitHub repo**, and select your fork. The included `Dockerfile` installs Python and FFmpeg. Railway hosting and ElevenLabs usage may incur charges.
4. In the Railway service's **Variables** tab, set `ELEVENLABS_API_KEY` to your secret. Set `ARTIFACT_SECRET` to a long random value and, if desired, `PROJECT_TTL_HOURS=24` (the default). Leave `PORT` to Railway; the Docker start command uses it automatically.
5. In **Settings → Networking → Public Networking**, select **Generate Domain**. Copy the resulting HTTPS base URL, for example `https://your-service.up.railway.app`.
6. Set `APP_BASE_URL` in Railway to that exact base URL, **without** `/mcp` or a trailing slash, and deploy the variable change.
7. Open `https://your-service.up.railway.app/health` using your actual domain. It should report `"status":"ok"`, `"ffmpeg":true`, and `"ffprobe":true`. The health check does not spend ElevenLabs credits.

See [Railway's service deployment guide](https://docs.railway.com/services) and [public networking guide](https://docs.railway.com/networking/public-networking) for the current UI. [All configuration variables](#environment-variables) are listed below.

### 2. Connect it to ChatGPT

1. Use a ChatGPT account and workspace that permits developer mode and MCP **write** actions. Access depends on plan and workspace policy; see [OpenAI's current availability guide](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt). Read/fetch-only access cannot complete the render workflow.
2. Enable **Developer mode** in ChatGPT, open **Plugins**, and select **+** to add a connection. Enter a name such as `TutorialFlow` and the server URL `https://your-service.up.railway.app/mcp`. Use your own Railway domain. The current server has **No Auth**; connect only to a deployment you control and trust.
3. Review the discovered tools. You should see `inspect_tutorial_video`, `finish_tutorial`, and `list_elevenlabs_voices`. Start a **new chat** and select the TutorialFlow connection from the tools menu.
4. Attach a screen recording and ask for the complete tutorial. ChatGPT should inspect the frames, make short timed narration cues, then call `finish_tutorial`; it produces the MP4, timeline MP3, script, and thumbnail. You do **not** need to provide an ElevenLabs audio file.
5. Download the returned files before the project expires (24 hours by default). If you want to approve the wording first, explicitly ask for a script draft for review instead of a complete tutorial.

ChatGPT's [connection walkthrough](https://developers.openai.com/plugins/deploy/connect-chatgpt) covers the current developer-mode screens. A direct MCP connection loads the server's tools and instructions, **not** the [`SKILL.md`](skills/tutorialflow/SKILL.md) in this GitHub repo. The explicit prompt above works with a direct connection; the optional local plugin package below also bundles the skill.

### 3. Optional: install the bundled skill in ChatGPT desktop or Codex

Use this if you want the repeatable TutorialFlow workflow from the repository's skill, in addition to the direct MCP connection.

1. Clone **your fork** (or download and extract its ZIP) on the computer running ChatGPT desktop or Codex.
2. Edit the root `mcp.json` in that local copy. Replace `https://YOUR-RAILWAY-DOMAIN.up.railway.app/mcp` with **your** Railway `/mcp` URL. Do not commit the edited file to a public fork if you want to keep the endpoint URL private.
3. Open the cloned folder as a project in Codex, then restart the ChatGPT desktop app. In the **Plugins Directory**, choose the repo's **TutorialFlow** local marketplace and install the plugin. If the marketplace does not appear, run `codex plugin marketplace add ./` from the cloned folder, restart the app, and look again. The repository already includes `.agents/plugins/marketplace.json`.
4. Start a new chat with TutorialFlow enabled. A direct ChatGPT web connection from step 2 can be used separately; installing the local package is what makes the bundled skill available on supported local surfaces.

The [OpenAI plugin packaging and local marketplace guide](https://developers.openai.com/plugins/build/plugins) explains the local install flow. The plugin's `mcp.json` is a **template** until you replace its URL; do not install it with the placeholder.

### Updating your copy

After a new version is pushed here, sync your fork and let Railway redeploy (or deploy the new commit). If tool names or schemas changed, open your ChatGPT connection in **Plugins → Refresh**, then start a new chat. For the local plugin package, update your local checkout, reapply your own URL in `mcp.json`, refresh the local marketplace or reinstall the plugin, and restart the app. See [OpenAI's metadata refresh steps](https://developers.openai.com/plugins/deploy/connect-chatgpt#refresh-metadata).

## Architecture

```text
ChatGPT file upload → MCP fileParams (temporary URL) → Railway streamed download
→ ffprobe + FFmpeg keyframes/contact sheet → MCP image content for ChatGPT
→ ChatGPT maps scene cues to keyframe times → finish_tutorial → Roger TTS clips
→ FFmpeg lays clips on timeline and stream-copies source video → MP4 + timeline MP3
→ frame-based PNG thumbnail → token-protected artifact links → automatic TTL cleanup
```

The upload uses ChatGPT's documented MCP file input contract: `openai/fileParams` identifies a file object with `download_url` and `file_id`. The service streams the temporary HTTPS download to disk in bounded chunks and never reads the whole recording into memory. The inspection result includes actual MCP image blocks with source timestamps, a contact sheet, and sampled keyframes. ChatGPT writes short cues against those time anchors. Railway then handles Roger voice selection, one TTS request per cue, source-preserving synchronization, and a frame-based thumbnail in one `finish_tutorial` call. See [OpenAI's file parameter reference](https://developers.openai.com/plugins/reference#file-apis) and [MCP Python SDK media results](https://py.sdk.modelcontextprotocol.io/servers/media/).

## Railway and local storage

Normal use runs on Railway. Local development needs source code and Python only; no sample video is committed. The app uses ephemeral `/tmp/tutorialflow` by default. A Railway Volume is optional and useful if projects must survive a container restart; mount it at `/data` and set `WORKSPACE_PATH=/data/projects`. The TTL still deletes expired projects. No database or second service is required.

Each source is streamed to one temporary project directory. Frame sampling combines regular time intervals and scene changes and caps the count at `MAX_FRAME_COUNT` (default 18). Original-resolution JPEG keyframes are retained; compressed preview copies and a contact sheet are sent to ChatGPT as MCP image content. Temporary files and the source are removed with the project. Downloadable MP4, MP3, script, and frame links use per-project random tokens and expire with the project.

## Requirements

- Python 3.11+ for local development
- FFmpeg and ffprobe (preinstalled in the Docker image; no local installation required for Railway use)
- A Railway project with enough memory and temporary disk for your recordings; Hobby is recommended for regular FFmpeg use, while Trial/Free limits may be restrictive ([current limits](https://railway.com/pricing))
- ElevenLabs API key for voice generation
- A ChatGPT account and plan/workspace that supports the required MCP tool actions

ChatGPT product access can vary by plan and workspace policy. Current OpenAI guidance says full MCP write actions are available on Business, Enterprise, and Edu, while Pro currently supports read/fetch only. TutorialFlow needs write-capable tool calls for narration, sync, and deletion, so check your account's current MCP permissions before relying on the complete workflow. See [OpenAI's developer mode and MCP availability](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt).

## Configure ElevenLabs

1. Create an API key in your ElevenLabs account and confirm API access is enabled.
2. Set the key as the Railway variable `ELEVENLABS_API_KEY`; do not add it to Git or conversation text.
3. Allow **Voices Read** and **Text to Speech** for that API key. `finish_tutorial` requires the account voice **Roger - Laid-Back, Casual, Resonant** and never silently falls back to another voice. Optionally set `ELEVENLABS_VOICE_ID` to Roger's voice ID. Voice listing requires `voices_read` permission.
4. `ELEVENLABS_MODEL` defaults to `eleven_flash_v2_5` and is configurable. ElevenLabs currently lists Flash v2.5 as a balanced, lower-cost speech model; model and voice access still depend on your account. See [model selection](https://elevenlabs.io/docs/models) and the [Create speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert). Each cue MP3 is cached independently by text, voice, and model, so retries reuse completed segments.

The free tier's voice/model availability and quotas are controlled by ElevenLabs. TutorialFlow surfaces rate/quota, voice, and API-key errors without logging credentials.

## Environment variables

| Variable | Default | Purpose |
|---|---:|---|
| `ELEVENLABS_API_KEY` | empty | Required only for TTS and voice listing |
| `ELEVENLABS_VOICE_ID` | empty | Optional Roger voice ID; non-Roger IDs are ignored by `finish_tutorial` |
| `ELEVENLABS_MODEL` | `eleven_flash_v2_5` | TTS model ID |
| `PROJECT_TTL_HOURS` | `24` | Project retention limit |
| `MAX_PROJECT_SIZE_MB` | `500` | Maximum streamed source size |
| `MAX_VIDEO_DURATION_MINUTES` | `10` | Maximum accepted recording duration |
| `MAX_CONCURRENT_RENDERS` | `1` | Render concurrency limit |
| `MAX_FRAME_COUNT` | `18` | Upper bound on extracted frames |
| `APP_BASE_URL` | `http://localhost:8000` | Public Railway URL used in artifact links |
| `ARTIFACT_SECRET` | empty | Optional pepper for artifact-token hashes; set a long random value |
| `WORKSPACE_PATH` | `/tmp/tutorialflow` | Temporary project root; use `/data/projects` with a Volume |

Set secrets in Railway's variable UI. A Railway Volume is optional: add a volume mounted at `/data` and set `WORKSPACE_PATH=/data/projects` if you need project continuity across restarts. Do not store long-term video libraries there.

## ChatGPT workflow

The live MCP server advertises the complete flow in its instructions and tool descriptions. The bundled [`SKILL.md`](skills/tutorialflow/SKILL.md) applies when the full TutorialFlow plugin package is installed on a supported local surface.

1. Upload the recording in ChatGPT and ask “Create a tutorial from this recording.” The thumbnail uses a neutral general style by default, with the real screen recording as its visual reference.
2. `inspect_tutorial_video` streams it to Railway and returns metadata and the visual frames.
3. ChatGPT inspects the images and writes a fact-grounded narration script.
4. For a complete tutorial request, ChatGPT calls `finish_tutorial` with a short title and timestamped narration segments grounded in the returned keyframe times. Railway uses Roger, generates separate ElevenLabs clips, places them at the given times, preserves the original video stream and duration, and makes the PNG thumbnail. It pauses for script approval only when you ask for a script draft or review.
5. `finish_tutorial` returns the script and temporary download links. Projects are deleted after the TTL; `delete_tutorial_project` removes one immediately.

The automatic thumbnail uses a modern dark layout, a large real video frame, the tutorial title, and a compact product identity badge when the app name is visible. The screenshot preserves the actual product logo if it appears in the recording. ChatGPT may optionally create a more elaborate image from the `build_thumbnail_brief` result; the brief tells it to use only visible app branding. The assistant should never ask you to upload ElevenLabs audio: `finish_tutorial` creates it through the configured API key.

## Tools and endpoints

- `inspect_tutorial_video(video, brand="general")` — ChatGPT file parameter, streaming upload, metadata, contact sheet, frame image blocks. The default thumbnail style is neutral and generic; the supplied frame guides the visual context.
- `list_elevenlabs_voices()` — live account voice list; does not assume any voice is available.
- `save_tutorial_script(project_id, script)` — stores the ChatGPT-authored review draft.
- `generate_voiceover(project_id, script, voice_id, model)` — cached ElevenLabs MP3.
- `finish_tutorial(project_id, title, narration_segments, brand, product_name)` — generate Roger clips at each scene timestamp, preserve the video timing, create a thumbnail, and return artifact URLs. Each segment has `start_seconds` and `text`; `product_name` is optional and should match a name visible in the recording.
- `sync_tutorial(project_id, strategy)` — compose the timestamped narration with silence between cues and mux it with the unchanged source video. `strategy="segments"` requires per-scene cues; `auto` accepts those cues or a single manual voice track beginning at time zero. Global video retiming is disabled.
- `build_thumbnail_brief(project_id, title, brand, product_name)` — optional text brief plus a real evidence frame for native image generation.
- `get_tutorial_result(project_id)` — project status and artifact URLs.
- `delete_tutorial_project(project_id)` — removes one project.
- `GET /health` — app and FFmpeg status, no ElevenLabs request.
- `GET /artifacts/{project_id}/{path}?token=...` — allowlisted, temporary, token-protected download, including `output/thumbnail.png`.

## Synchronization

The ChatGPT workflow sends an ordered `narration_segments` array. Each item contains `start_seconds` on the source recording's timeline and the narration `text` for that scene. TutorialFlow makes one ElevenLabs request per segment using Roger, checks that each rendered clip finishes before the next cue and before the video ends, and returns a clear error if a cue overruns. FFmpeg places the clips at their timestamps, leaves all other spans silent, and replaces the recording's original audio. The source video stream is copied without re-encoding or changing its playback speed; a short voice track never shortens the recording, and a long one never stretches it. The final MP4 is capped to the probed video-stream duration. Manual one-script voice generation is placed at 0 seconds and must fit inside that duration.

For example, if the visible transition to Overleaf is confirmed at 10.23 seconds, its cue can start there:

```json
{
  "narration_segments": [
    {"start_seconds": 0.0, "text": "GitHub setup narration for the opening scene."},
    {"start_seconds": 10.23, "text": "Overleaf narration begins as the recording switches to Overleaf."}
  ]
}
```

Roger is selected by its account voice name (using `ELEVENLABS_VOICE_ID` only when it identifies a Roger voice). If Roger is unavailable, the full workflow stops with an actionable error instead of selecting another voice. The ElevenLabs error handler buffers a failed streaming response before decoding JSON, so the API's actual error is preserved. Segmented narration uses one TTS request per cue; shorter scenes therefore mean more API requests, and finished cue clips are cached for retries.

## Cleanup and project limits

Expired projects are deleted at application startup, by a lightweight hourly cleanup task, on project creation, and when results are fetched. Active inspection, voice generation, and render jobs receive a three-hour processing grace period; abandoned jobs older than that are cleaned up after their TTL. Projects also have a manual delete tool. Source size and duration are checked before expensive processing. The source recording is not duplicated as another intermediate.

## Development and tests

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

Tests mock ElevenLabs and do not use credits. The optional FFmpeg integration smoke test creates a tiny synthetic clip under pytest's temporary directory and removes it after the run. The repository ignores video and audio binaries.

For local HTTP serving:

```powershell
Copy-Item .env.example .env
uvicorn server:app --host 127.0.0.1 --port 8000
```

Local health is `http://127.0.0.1:8000/health`; local MCP is `http://127.0.0.1:8000/mcp`. For ChatGPT testing, use a public HTTPS deployment or a supported secure development tunnel.

## Troubleshooting

- **Upload expired:** re-upload the video; ChatGPT file download URLs are temporary.
- **No video stream / ffprobe failure:** try an MP4 encoded with H.264/AAC.
- **No frames extracted:** confirm the video is not corrupt and FFmpeg can decode it.
- **401 from ElevenLabs:** update `ELEVENLABS_API_KEY` in Railway.
- **Missing `voices_read` permission:** enable Voices Read on the key in ElevenLabs or configure `ELEVENLABS_VOICE_ID` in Railway. Text to Speech permission is required to generate narration.
- **429 from ElevenLabs:** free account quota or rate limit may be reached; wait or reduce regeneration.
- **Voice unavailable:** select an ID returned by `list_elevenlabs_voices`.
- **Artifact link fails:** use the link before its expiry; links expire with the project.
- **Railway storage pressure:** lower `PROJECT_TTL_HOURS`, use ephemeral storage, or delete completed projects manually.
- **ChatGPT cannot connect:** check that Railway serves HTTPS and the MCP path ends in `/mcp`; confirm your ChatGPT account/workspace permits the tools you need.
- **Health endpoint returns 502:** confirm the Railway public domain's target port matches the port the service listens on (`PORT`, or 8000 when unset). Check the deployment logs for the Uvicorn startup line.
- **Only a script appears:** select TutorialFlow in the new chat and ask for the complete tutorial, including a `finish_tutorial` call. A direct MCP connection does not install the repository's skill.
- **Local plugin cannot connect:** replace the placeholder in your local `mcp.json` with your own deployed `/mcp` URL, then refresh or reinstall the local plugin.

## Security notes

Upload URLs must be HTTPS and resolve to public addresses; redirects are revalidated. Downloads are size limited and streamed. Tool paths are constrained to a strict project ID pattern, and downloadable artifact paths are allowlisted. Artifact tokens are random and stored as peppered hashes for validation. API credentials are environment-only and omitted from logs and tool output.

The MCP endpoint itself currently has no user OAuth layer. Anyone who obtains its URL can call its tools, including actions that spend the configured ElevenLabs credits or consume Railway resources. Keep your own Railway URL private while testing, set ElevenLabs usage limits, and use a trusted ChatGPT connection. **Do not share one Railway endpoint with multiple people** until MCP OAuth 2.1, per-user project isolation, and usage limits are implemented; OpenAI's [authentication guidance](https://developers.openai.com/plugins/build/auth) describes the authorization flow. Artifact tokens protect downloads, but do not authenticate MCP tool callers.

## Roadmap

1. Segment-aware synchronization and alignment metadata.
2. Cursor/click cues, pauses, captions, and subtitles.
3. OAuth, user isolation, and usage controls before broader sharing.
4. Optional brand templates and publishing integrations; SaaS features are outside this MVP.
