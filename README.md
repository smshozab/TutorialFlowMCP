# TutorialFlow

TutorialFlow is a Railway-first MCP server that inspects a screen recording, returns real visual evidence to ChatGPT, and then uses FFmpeg and ElevenLabs to create a narrated tutorial. ChatGPT performs the visual reasoning, writes the script, and creates the thumbnail with its native image-generation capability. No OpenAI or other vision API is called by the backend.

## Architecture

```text
ChatGPT file upload → MCP fileParams (temporary URL) → Railway streamed download
→ ffprobe + FFmpeg keyframes/contact sheet → MCP image content for ChatGPT
→ ChatGPT script/review → ElevenLabs MP3 → FFmpeg H.264/AAC render
→ signed temporary artifact links → automatic TTL cleanup
```

The upload uses ChatGPT's documented MCP file input contract: `openai/fileParams` identifies a file object with `download_url` and `file_id`. The service streams the temporary HTTPS download to disk in bounded chunks and never reads the whole recording into memory. The inspection result includes actual MCP image blocks (contact sheet plus sampled keyframes) so the model can inspect what happened. See [OpenAI's file parameter reference](https://developers.openai.com/plugins/reference#file-apis) and [MCP Python SDK media results](https://py.sdk.modelcontextprotocol.io/servers/media/).

## Railway and local storage

Normal use runs on Railway. Local development needs source code and Python only; no sample video is committed. The app uses ephemeral `/tmp/tutorialflow` by default. A Railway Volume is optional and useful if projects must survive a container restart; mount it at `/data` and set `WORKSPACE_PATH=/data/projects`. The TTL still deletes expired projects. No database or second service is required.

Each source is streamed to one temporary project directory. Frame sampling combines regular time intervals and scene changes and caps the count at `MAX_FRAME_COUNT` (default 18). Original-resolution JPEG keyframes are retained; compressed preview copies and a contact sheet are sent to ChatGPT as MCP image content. Temporary files and the source are removed with the project. Downloadable MP4, MP3, script, and frame links use per-project random tokens and expire with the project.

## Requirements

- Python 3.11+ for local development
- FFmpeg and ffprobe (preinstalled in the Docker image; no local installation required for Railway use)
- Railway Hobby service
- ElevenLabs API key for voice generation
- A ChatGPT account and plan/workspace that supports the required MCP tool actions

ChatGPT product access can vary by plan and workspace policy. Current OpenAI guidance says full MCP write actions are available on Business, Enterprise, and Edu, while Pro currently supports read/fetch only. TutorialFlow needs write-capable tool calls for narration, sync, and deletion, so check your account's current MCP permissions before relying on the complete workflow. See [OpenAI's developer mode and MCP availability](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt).

## Configure ElevenLabs

1. Create an API key in your ElevenLabs account and confirm API access is enabled.
2. Set the key as the Railway variable `ELEVENLABS_API_KEY`; do not add it to Git or conversation text.
3. Optionally set `ELEVENLABS_VOICE_ID`. Otherwise choose a voice from `list_elevenlabs_voices`.
4. `ELEVENLABS_MODEL` defaults to `eleven_flash_v2_5` and is configurable. ElevenLabs currently lists Flash v2.5 as a balanced, lower-cost speech model; model and voice access still depend on your account. See [model selection](https://elevenlabs.io/docs/models) and the [Create speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert). The tool caches the MP3 when the script, voice, and model match, avoiding a second TTS request.

The free tier's voice/model availability and quotas are controlled by ElevenLabs. TutorialFlow surfaces rate/quota, voice, and API-key errors without logging credentials.

## Deploy to Railway

1. Push this repository to a private GitHub repository.
2. In Railway, create a project and deploy from that GitHub repository. Railway builds the included Dockerfile, which installs FFmpeg in a small Python 3.11 slim image.
3. Add the environment variables below in the Railway service settings.
4. Generate a public HTTPS domain. Set `APP_BASE_URL` to that exact URL, without a trailing slash.
5. Wait for `/health` to report `ffmpeg: true` and `ffprobe: true`.
6. In ChatGPT developer mode, add the public MCP URL `https://YOUR-DOMAIN/mcp`. OpenAI's current walkthrough is [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt).
7. Start a new chat with the TutorialFlow connection and try a short recording.

The root [`plugin.json`](plugin.json) packages the TutorialFlow skill and starter prompts, and [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) makes the local plugin discoverable in the desktop app. Once Railway assigns your domain, either add the MCP connection directly in ChatGPT developer mode or copy [`mcp.json.example`](mcp.json.example) to `mcp.json`, replace `YOUR-RAILWAY-DOMAIN`, then install the local plugin. OpenAI's current plugin package format keeps the skill under `skills/` and the remote MCP endpoint in `mcp.json`; see [Package your plugin](https://developers.openai.com/plugins/build/plugins).

### Environment variables

| Variable | Default | Purpose |
|---|---:|---|
| `ELEVENLABS_API_KEY` | empty | Required only for TTS and voice listing |
| `ELEVENLABS_VOICE_ID` | empty | Optional default voice ID |
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

The bundled [`SKILL.md`](skills/tutorialflow/SKILL.md) teaches ChatGPT the review-first flow.

1. Upload the recording in ChatGPT and ask “Create a tutorial from this recording.”
2. `inspect_tutorial_video` streams it to Railway and returns metadata and the visual frames.
3. ChatGPT inspects the images, writes a fact-grounded script, and presents it for approval.
4. After approval, ChatGPT calls `save_tutorial_script`, `generate_voiceover`, and `sync_tutorial`.
5. ChatGPT calls `build_thumbnail_brief`, inspects the evidence frame, and generates the thumbnail natively.
6. `get_tutorial_result` provides the script and temporary download links. Projects are deleted after the TTL; `delete_tutorial_project` removes one immediately.

Auto mode skips the script approval pause only when the user explicitly requests it. The server does not create or alter the thumbnail image; ChatGPT does.

## Tools and endpoints

- `inspect_tutorial_video(video, brand)` — ChatGPT file parameter, streaming upload, metadata, contact sheet, frame image blocks.
- `list_elevenlabs_voices()` — live account voice list; does not assume any voice is available.
- `save_tutorial_script(project_id, script)` — stores the ChatGPT-authored review draft.
- `generate_voiceover(project_id, script, voice_id, model)` — cached ElevenLabs MP3.
- `sync_tutorial(project_id, strategy)` — global video retiming and H.264/AAC MP4 render.
- `build_thumbnail_brief(project_id, title, brand)` — text brief plus a real evidence frame.
- `get_tutorial_result(project_id)` — project status and artifact URLs.
- `delete_tutorial_project(project_id)` — removes one project.
- `GET /health` — app and FFmpeg status, no ElevenLabs request.
- `GET /artifacts/{project_id}/{path}?token=...` — allowlisted, temporary, token-protected download.

## Synchronization

The MVP globally retimes the source video to the narration duration. If the narration is shorter, video speeds up; if it is longer, the video slows down. Extreme ratios outside 0.25–4.0 are rejected so the user can revise the script. The original video and audio tracks are not joined as a mix: output audio is the generated narration. Segment-aware alignment, silence trimming, cursor detection, subtitles, and zooms remain future work.

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
- **429 from ElevenLabs:** free account quota or rate limit may be reached; wait or reduce regeneration.
- **Voice unavailable:** select an ID returned by `list_elevenlabs_voices`.
- **Artifact link fails:** use the link before its expiry; links expire with the project.
- **Railway storage pressure:** lower `PROJECT_TTL_HOURS`, use ephemeral storage, or delete completed projects manually.
- **ChatGPT cannot connect:** check that Railway serves HTTPS and the MCP path ends in `/mcp`; confirm your ChatGPT account/workspace permits the tools you need.

## Security notes

Upload URLs must be HTTPS and resolve to public addresses; redirects are revalidated. Downloads are size limited and streamed. Tool paths are constrained to a strict project ID pattern, and downloadable artifact paths are allowlisted. Artifact tokens are random and stored as peppered hashes for validation. API credentials are environment-only and omitted from logs and tool output.

The MCP endpoint itself currently has no user OAuth layer. Keep the Railway URL private while testing and use a trusted ChatGPT connection. Before public distribution or use by multiple people, add MCP OAuth 2.1 and per-user project isolation; OpenAI's [authentication guidance](https://developers.openai.com/plugins/build/auth) describes the required authorization flow. Artifact tokens protect downloads, but do not authenticate MCP tool callers.

## Roadmap

1. Segment-aware synchronization and alignment metadata.
2. Cursor/click cues, pauses, captions, and subtitles.
3. OAuth, user isolation, and usage controls before broader sharing.
4. Optional brand templates and publishing integrations; SaaS features are outside this MVP.
