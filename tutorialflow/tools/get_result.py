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
    narration_path = record.get("audio", {}).get("timeline_path") or record.get("audio", {}).get("path")
    if not narration_path or not (root / narration_path).is_file():
        narration_path = None
    result = {
        "project_id": project_id, "status": record["status"],
        "expires_at": record["expires_at"],
        "script": record.get("script", {}).get("text"),
        "script_artifact": _artifact_url(project_id, "script.txt", token) if (root / "script.txt").is_file() else None,
        "narration": _artifact_url(project_id, narration_path, token) if narration_path else None,
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


def build_thumbnail_brief(project_id: str, title: str, brand: str = "general",
                          product_name: str | None = None) -> dict:
    record = load_project(project_id)
    if not title.strip() or len(title) > 120:
        raise ValueError("Provide a concise thumbnail title of at most 120 characters.")
    if product_name is not None:
        if not isinstance(product_name, str):
            raise TypeError("Product name must be text visible in the recording.")
        product_name = " ".join(product_name.split())[:40].strip() or None
    brand = canonical_brand_preset(brand)
    brand_file = BRANDS / f"{brand}.json"
    if brand_file.resolve().parent != BRANDS.resolve() or not brand_file.is_file():
        raise ValueError("Unknown brand preset. Use `general`.")
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
        "product_name": product_name,
        "evidence_frame": relative,
        "prompt": (
            f"Create a polished, modern landscape 16:9 software tutorial thumbnail titled exactly: {title}. "
            f"Use the attached recording frame as the factual topic and UI reference. "
            f"Use a neutral general style: {guidelines.get('style')}; colors {guidelines.get('colors', guidelines.get('theme'))}; "
            f"layout: {guidelines.get('layout')}. Product name: {product_name or 'not identified'}. "
            "Make the captured software screen large and easy to recognize. Add a clean title panel, subtle depth, and a compact product identity badge. "
            "If a real product name or logo is visible in the screenshot, preserve it accurately; otherwise do not invent a logo or brand. "
            "No people. Do not invent interface text or product features; keep UI text abstract where unreadable. "
            "Use strong contrast, crisp composition, restrained gradients, and highly legible title typography."
        ),
    }
    from tutorialflow.storage.workspace import save_project
    save_project(project_id, record)
    return {**record["thumbnail_brief"], "evidence_frame_path": relative}
