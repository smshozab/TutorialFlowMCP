from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tutorialflow.config import settings

PROJECT_ID_RE = re.compile(r"^[0-9]{8}_[a-f0-9]{32}$")


class ProjectError(ValueError):
    """A project or artifact is invalid, missing, or expired."""


def utcnow() -> datetime:
    return datetime.now(UTC)


def validate_project_id(project_id: str) -> str:
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise ProjectError("Invalid project ID.")
    return project_id


def project_path(project_id: str) -> Path:
    validate_project_id(project_id)
    root = settings.workspace_path.resolve()
    path = (root / project_id).resolve()
    if path.parent != root:
        raise ProjectError("Project path is outside the workspace.")
    return path


def create_project(source_name: str) -> tuple[str, Path, str]:
    settings.workspace_path.mkdir(parents=True, exist_ok=True)
    project_id = f"{utcnow():%Y%m%d}_{uuid.uuid4().hex}"
    root = project_path(project_id)
    for folder in ("source", "frames", "audio", "output"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    created = utcnow()
    record: dict[str, Any] = {
        "project_id": project_id,
        "created_at": created.isoformat(),
        "expires_at": (created + timedelta(hours=settings.ttl_hours)).isoformat(),
        "status": "uploaded",
        "source_name": Path(source_name).name[:200],
        "artifact_token": token,
        "artifact_token_hash": hashlib.sha256((settings.artifact_secret + token).encode()).hexdigest(),
        "source": {}, "script": {}, "audio": {}, "output": {},
    }
    save_project(project_id, record)
    return project_id, root, token


def load_project(project_id: str) -> dict[str, Any]:
    path = project_path(project_id) / "project.json"
    if not path.is_file():
        raise ProjectError("Tutorial project was not found or has expired.")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectError("Project metadata is unreadable.") from exc
    if datetime.fromisoformat(record["expires_at"]) <= utcnow():
        active = record.get("status") == "rendering" or record.get("status", "").startswith("processing_")
        started_at = record.get("processing_started_at", record.get("created_at"))
        stale = not started_at or utcnow() - datetime.fromisoformat(started_at) > timedelta(hours=3)
        if not active or stale:
            delete_project(project_id)
            raise ProjectError("Tutorial project has expired.")
    return record


def save_project(project_id: str, record: dict[str, Any]) -> None:
    path = project_path(project_id) / "project.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
    temporary.replace(path)


def set_project_status(record: dict[str, Any], status: str) -> None:
    record["status"] = status
    if status == "rendering" or status.startswith("processing_"):
        record["processing_started_at"] = utcnow().isoformat()
    else:
        record.pop("processing_started_at", None)


def resolve_artifact(project_id: str, relative_path: str) -> Path:
    root = project_path(project_id).resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents or not path.is_file():
        raise ProjectError("Artifact not found.")
    return path


def validate_artifact_token(project_id: str, token: str) -> bool:
    import hmac

    try:
        stored = load_project(project_id).get("artifact_token_hash", "")
    except ProjectError:
        return False
    return hmac.compare_digest(stored, hashlib.sha256((settings.artifact_secret + token).encode()).hexdigest())


def delete_project(project_id: str) -> bool:
    path = project_path(project_id)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True
