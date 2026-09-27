---
name: tutorialflow
description: Create a complete narrated software tutorial from an uploaded screen recording with TutorialFlow MCP tools, including ElevenLabs voiceover, synchronized video, and a neutral thumbnail. Use script-only when the user explicitly requests a draft or review.
---

# TutorialFlow workflow

Use this skill when the user uploads a screen recording and asks to create, start, or produce a tutorial.

## Complete tutorial (default when the user asks to create or produce a tutorial)

1. Call `inspect_tutorial_video` with the uploaded video file. The tool accepts ChatGPT file parameters; do not ask for a local path or public URL.
2. Visually inspect the returned contact sheet and keyframe images. Base the topic, pages, clicks, text, dropdown choices, errors, confirmations, and final state only on the actual images. Never infer from the filename. If the frames do not establish an action, omit it or tell the user what evidence is unclear.
3. Draft concise, professional narration in chronological order. Only describe visibly supported actions. Mention example values only if readable. Do not claim an action succeeded unless the recording visibly shows success. Keep each cue short enough to fit before the next scene timestamp; omit extra commentary instead of filling every pause.
4. For a complete tutorial request, create ordered `narration_segments` with `start_seconds` anchored to the returned keyframe timestamps and a short `text` cue for each visible scene. Leave silence between action groups when useful. Never invent precise scene times from the filename or stretch the video to fill the voiceover. Call `finish_tutorial` once with the inspected `project_id`, concise title, and `narration_segments`. The server selects Roger, makes separate ElevenLabs clips, checks each clip fits before the next cue, and stream-copies the source video at its original timing. If a cue is too long or Roger is unavailable, report the tool error and revise/stop instead of switching voices or retiming the recording. If the app's name is clearly visible, pass it as `product_name`; otherwise omit it. Never invent a product name or logo, and never ask for pre-generated audio.
5. Return the MP4, PNG thumbnail, script, and optional MP3 links. Mention the project expiry time. Keep the wrap-up concise.

## Script-only or review requests

If video inspection fails, stop and report its exact tool error. Do not draft from uninspected footage or ask the user to provide an ElevenLabs MP3. If the user asks only for a script, draft, or review, show the script and pause before calling `finish_tutorial`. Otherwise, a request to create or produce a tutorial means they want the complete flow. If ElevenLabs returns a missing-key, missing-permission, quota, or voice error, report that tool error and stop; do not ask the user to upload audio.

## Rules

- Actual video evidence takes priority over filename, user assumptions, or plausible workflow conventions.
- Never fabricate UI actions, values, errors, or confirmations.
- Keep API keys and artifact tokens private. Do not repeat them in conversation.
- If an upload expires, ask the user to upload it again. If a frame is unreadable, say so and avoid making a claim from it.
- Use `delete_tutorial_project` when the user asks to remove their project. Projects expire automatically after the configured TTL.
