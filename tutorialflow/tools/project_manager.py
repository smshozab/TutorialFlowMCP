from __future__ import annotations

from tutorialflow.storage.workspace import delete_project, load_project


def delete_tutorial_project(project_id: str) -> dict:
    record = load_project(project_id)  # validates the project ID and rejects expired/malformed state
    if record.get("status") == "rendering" or record.get("status", "").startswith("processing_"):
        raise ValueError("This project is being processed. Retry deletion after the current job finishes.")
    delete_project(project_id)
    return {"project_id": project_id, "deleted": True}
