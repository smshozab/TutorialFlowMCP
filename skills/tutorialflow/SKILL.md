---
name: tutorialflow
description: Create a complete narrated software tutorial from an uploaded screen recording with TutorialFlow MCP tools, including ElevenLabs voiceover and synchronized video. Use script-only when the user explicitly requests a draft or review.
---

# TutorialFlow workflow

Use this skill when the user uploads a screen recording and asks to create, start, or produce a tutorial.

## Complete tutorial (default when the user asks to create or produce a tutorial)

1. Call `inspect_tutorial_video` with the uploaded video file and desired brand. The tool accepts ChatGPT file parameters; do not ask for a local path or public URL.
2. Visually inspect the returned contact sheet and keyframe images. Base the topic, pages, clicks, text, dropdown choices, errors, confirmations, and final state only on the actual images. Never infer from the filename. If the frames do not establish an action, omit it or tell the user what evidence is unclear.
3. Draft concise, professional narration in chronological order. Only describe visibly supported actions. Mention example values only if readable. Do not claim an action succeeded unless the recording visibly shows success. Target the returned recommended word count (about 150 words/minute, within the returned range).
4. For a complete tutorial request, call `save_tutorial_script`, then `generate_voiceover` with the narration you wrote. If the user did not select a voice and no default voice is configured, call `list_elevenlabs_voices` and select an available voice suitable for clear educational narration. The configured service calls ElevenLabs and returns the audio artifact. Never ask the user to provide pre-generated ElevenLabs audio. Reuse the selected voice; never assume a voice such as Roger is available.
5. Call `sync_tutorial` to render the source with the generated narration.
6. Call `build_thumbnail_brief` using a concise title supported by the recording. Inspect the attached evidence frame, then generate the thumbnail with ChatGPT's native image-generation capability. Follow the returned brand brief. Do not call an external image-generation API or invent product features.
7. Call `get_tutorial_result` and return the MP4 link, thumbnail image, narration script, and optional audio link. Mention the project expiry time. Keep the wrap-up concise.

## Script-only or review requests

If the user asks only for a script, draft, or review, show the script and pause before calling `generate_voiceover` or `sync_tutorial`. Otherwise, a request to create or produce a tutorial means they want the complete flow. If ElevenLabs returns a missing-key, invalid-key, quota, or voice error, report that tool error and stop; do not ask the user to upload audio.

## Rules

- Actual video evidence takes priority over filename, user assumptions, or plausible workflow conventions.
- Never fabricate UI actions, values, errors, or confirmations.
- Keep API keys and artifact tokens private. Do not repeat them in conversation.
- If an upload expires, ask the user to upload it again. If a frame is unreadable, say so and avoid making a claim from it.
- Use `delete_tutorial_project` when the user asks to remove their project. Projects expire automatically after the configured TTL.
