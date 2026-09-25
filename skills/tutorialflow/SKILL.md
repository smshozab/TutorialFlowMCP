---
name: tutorialflow
description: Create a complete narrated software tutorial from an uploaded screen recording with TutorialFlow MCP tools, including ElevenLabs voiceover, synchronized video, and a branded thumbnail. Use script-only when the user explicitly requests a draft or review.
---

# TutorialFlow workflow

Use this skill when the user uploads a screen recording and asks to create, start, or produce a tutorial.

## Complete tutorial (default when the user asks to create or produce a tutorial)

1. Call `inspect_tutorial_video` with the uploaded video file and desired brand. The tool accepts ChatGPT file parameters; do not ask for a local path or public URL. Brand names may be supplied as preset IDs or display names, such as `education_global` or `Education Global`.
2. Visually inspect the returned contact sheet and keyframe images. Base the topic, pages, clicks, text, dropdown choices, errors, confirmations, and final state only on the actual images. Never infer from the filename. If the frames do not establish an action, omit it or tell the user what evidence is unclear.
3. Draft concise, professional narration in chronological order. Only describe visibly supported actions. Mention example values only if readable. Do not claim an action succeeded unless the recording visibly shows success. Target the returned recommended word count (about 150 words/minute, within the returned range).
4. For a complete tutorial request, call `finish_tutorial` once with the inspected `project_id`, the narration script, and a concise title. Railway selects an available account voice, calls ElevenLabs, renders the synchronized video, creates a branded thumbnail from a real frame, and returns the artifacts. Never ask the user to provide pre-generated ElevenLabs audio.
5. Return the MP4, PNG thumbnail, script, and optional MP3 links. Mention the project expiry time. Keep the wrap-up concise.

## Script-only or review requests

If video inspection fails, stop and report its exact tool error. Do not draft from uninspected footage or ask the user to provide an ElevenLabs MP3. If the user asks only for a script, draft, or review, show the script and pause before calling `finish_tutorial`. Otherwise, a request to create or produce a tutorial means they want the complete flow. If ElevenLabs returns a missing-key, missing-permission, quota, or voice error, report that tool error and stop; do not ask the user to upload audio.

## Rules

- Actual video evidence takes priority over filename, user assumptions, or plausible workflow conventions.
- Never fabricate UI actions, values, errors, or confirmations.
- Keep API keys and artifact tokens private. Do not repeat them in conversation.
- If an upload expires, ask the user to upload it again. If a frame is unreadable, say so and avoid making a claim from it.
- Use `delete_tutorial_project` when the user asks to remove their project. Projects expire automatically after the configured TTL.
