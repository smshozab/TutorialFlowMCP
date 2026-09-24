from __future__ import annotations

from tutorialflow.storage.workspace import (
    load_project,
    project_path,
    save_project,
    set_project_status,
)


def save_tutorial_script(project_id: str, script: str) -> dict:
    if not script.strip() or len(script) > 12000:
        raise ValueError("Provide a script between 1 and 12,000 characters.")
    record = load_project(project_id)
    if not record.get("source", {}).get("path"):
        raise ValueError("Inspect a recording before saving its tutorial script.")
    normalized = script.strip()
    (project_path(project_id) / "script.txt").write_text(normalized + "\n", encoding="utf-8")
    record["script"] = {"text": normalized, "character_count": len(normalized), "path": "script.txt"}
    set_project_status(record, "script_ready")
    save_project(project_id, record)
    return {"project_id": project_id, "status": "script_ready", "character_count": len(normalized)}
