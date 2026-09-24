---
name: tutorialflow
description: Create a narrated software tutorial from an uploaded screen recording using TutorialFlow MCP tools.
---

# TutorialFlow workflow

Use this skill when the user uploads a screen recording and asks to create, start, or produce a tutorial.

## Review mode (default)

1. Call `inspect_tutorial_video` with the uploaded video file and desired brand. The tool accepts ChatGPT file parameters; do not ask for a local path or public URL.
2. Visually inspect the returned contact sheet and keyframe images. Base the topic, pages, clicks, text, dropdown choices, errors, confirmations, and final state only on the actual images. Never infer from the filename. If the frames do not establish an action, omit it or tell the user what evidence is unclear.
3. Draft concise, professional narration in chronological order. Only describe visibly supported actions. Mention example values only if readable. Do not claim an action succeeded unless the recording visibly shows success. Target the returned recommended word count (about 150 words/minute, within the returned range).
4. Show the full script to the user and ask for approval or edits. Do not generate voiceover until the user approves.
5. After approval, call `save_tutorial_script`, then `generate_voiceover` with the exact approved script. Use `list_elevenlabs_voices` if the user wants to choose a voice or the configured voice is unavailable. Reuse the selected voice; never assume a voice such as Roger is available.
6. Call `sync_tutorial` to render the source with the generated narration.
7. Call `build_thumbnail_brief` using a concise title supported by the recording. Inspect the attached evidence frame, then generate the thumbnail with ChatGPT's native image-generation capability. Follow the returned brand brief. Do not call an external image-generation API or invent product features.
8. Call `get_tutorial_result` and return the MP4 link, thumbnail image, narration script, and optional audio link. Mention the project expiry time. Keep the wrap-up concise.

## Auto mode

Proceed through the same steps without pausing for script approval only when the user explicitly asks for automatic creation or says to skip review. Still return the script with the finished artifacts.

## Rules

- Actual video evidence takes priority over filename, user assumptions, or plausible workflow conventions.
- Never fabricate UI actions, values, errors, or confirmations.
- Keep API keys and artifact tokens private. Do not repeat them in conversation.
- If an upload expires, ask the user to upload it again. If a frame is unreadable, say so and avoid making a claim from it.
- Use `delete_tutorial_project` when the user asks to remove their project. Projects expire automatically after the configured TTL.
