from __future__ import annotations

import json
from pathlib import Path

from tutorialflow.brand_presets import canonical_brand_preset
from tutorialflow.config import settings
from tutorialflow.storage.workspace import load_project, project_path

BRANDS = Path(__file__).resolve().parents[1] / "brands"


def _artifact_url(project_id: str, relative: str, token: str) -> str:
    return f"{settings.app_base_url}/artifacts/{project_id}/{relative}?token={token}"


def get_tutorial_result(project_id: str) -> dict:
    record = load_project(project_id)
    root = project_path(project_id)
    token = record["artifact_token"]
    result = {
        "project_id": project_id, "status": record["status"],
        "expires_at": record["expires_at"],
        "script": record.get("script", {}).get("text"),
        "script_artifact": _artifact_url(project_id, "script.txt", token) if (root / "script.txt").is_file() else None,
        "narration": _artifact_url(project_id, "audio/narration.mp3", token) if (root / "audio/narration.mp3").is_file() else None,
        "synced_video": _artifact_url(project_id, "output/tutorial.mp4", token) if (root / "output/tutorial.mp4").is_file() else None,
        "thumbnail": _artifact_url(project_id, "output/thumbnail.png", token) if (root / "output/thumbnail.png").is_file() else None,
        "contact_sheet": _artifact_url(project_id, "frames/contact_sheet.jpg", token) if (root / "frames/contact_sheet.jpg").is_file() else None,
        "keyframes": [
            {"time_seconds": frame["time_seconds"], "url": _artifact_url(project_id, frame["path"], token)}
            for frame in record.get("frames", []) if (root / frame["path"]).is_file()
        ],
        "thumbnail_brief": record.get("thumbnail_brief"),
    }
    return result


def build_thumbnail_brief(project_id: str, title: str, brand: str = "education_global") -> dict:
    record = load_project(project_id)
    if not title.strip() or len(title) > 120:
        raise ValueError("Provide a concise thumbnail title of at most 120 characters.")
    brand = canonical_brand_preset(brand)
    brand_file = BRANDS / f"{brand}.json"
    if brand_file.resolve().parent != BRANDS.resolve() or not brand_file.is_file():
        raise ValueError("Unknown brand preset. Available presets: default, education_global.")
    guidelines = json.loads(brand_file.read_text(encoding="utf-8"))
    keyframes = record.get("frames", [])
    if not keyframes:
        raise ValueError("Inspect the video before preparing a thumbnail brief.")
    # Use a central frame as topic evidence; ChatGPT must preserve what is visibly present.
    selected = keyframes[len(keyframes) // 2]
    relative = selected["path"]
    record["thumbnail_brief"] = {
        "title": title,
        "brand": guidelines,
        "evidence_frame": relative,
        "prompt": (
            f"Create a landscape 16:9 tutorial thumbnail titled exactly: {title}. "
            f"Use the attached recording frame as the factual topic and UI reference. "
            f"Match this brand style: {guidelines.get('style')}; colors {guidelines.get('colors', guidelines.get('theme'))}; "
            f"layout: {guidelines.get('layout')}. Include a small tutorial badge. "
            "No people. Do not invent interface text or product features; keep UI text abstract where unreadable. "
            "Use bold, highly legible title typography and a clean SaaS education aesthetic."
        ),
    }
    from tutorialflow.storage.workspace import save_project
    save_project(project_id, record)
    return {**record["thumbnail_brief"], "evidence_frame_path": relative}
