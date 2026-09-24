import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from tutorialflow.storage import cleanup, workspace
from tutorialflow.tools.project_manager import delete_tutorial_project


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    fake = SimpleNamespace(workspace_path=tmp_path, ttl_hours=24, artifact_secret="")
    monkeypatch.setattr(workspace, "settings", fake)
    monkeypatch.setattr(cleanup, "settings", fake)
    return tmp_path


def test_project_creation_and_ttl(temp_workspace):
    project_id, root, token = workspace.create_project("a.mp4")
    record = workspace.load_project(project_id)
    assert root.is_dir()
    assert record["source_name"] == "a.mp4"
    expiry = datetime.fromisoformat(record["expires_at"])
    created = datetime.fromisoformat(record["created_at"])
    assert expiry - created == timedelta(hours=24)
    assert token and record["artifact_token_hash"]


def test_path_traversal_protection(temp_workspace):
    project_id, _root, _token = workspace.create_project("a.mp4")
    with pytest.raises(workspace.ProjectError):
        workspace.project_path("../other")
    with pytest.raises(workspace.ProjectError):
        workspace.resolve_artifact(project_id, "../../outside.txt")


def test_artifact_token_validation(temp_workspace):
    project_id, root, token = workspace.create_project("a.mp4")
    (root / "script.txt").write_text("safe")
    assert workspace.validate_artifact_token(project_id, token)
    assert not workspace.validate_artifact_token(project_id, "wrong-token-value-which-is-long-enough")


def test_cleanup_expired_project_but_keep_active_render(temp_workspace):
    expired, expired_root, _ = workspace.create_project("old.mp4")
    active, active_root, _ = workspace.create_project("active.mp4")
    now = datetime.now(UTC)
    for project_id, status in ((expired, "inspected"), (active, "rendering")):
        record = json.loads((temp_workspace / project_id / "project.json").read_text())
        record["expires_at"] = (now - timedelta(hours=1)).isoformat()
        record["status"] = status
        (temp_workspace / project_id / "project.json").write_text(json.dumps(record))
    assert cleanup.cleanup_expired_projects() == [expired]
    assert not expired_root.exists()
    assert active_root.exists()


def test_cleanup_keeps_processing_inspection(temp_workspace):
    _project_id, root, _token = workspace.create_project("active.mp4")
    record = json.loads((root / "project.json").read_text())
    record["expires_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    record["status"] = "processing_inspection"
    (root / "project.json").write_text(json.dumps(record))
    assert cleanup.cleanup_expired_projects() == []
    assert root.exists()


def test_cleanup_keeps_processing_voice(temp_workspace):
    _project_id, root, _token = workspace.create_project("active.mp4")
    record = json.loads((root / "project.json").read_text())
    record["expires_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    record["status"] = "processing_voice"
    (root / "project.json").write_text(json.dumps(record))
    assert cleanup.cleanup_expired_projects() == []
    assert root.exists()


def test_cleanup_removes_expired_stale_processing_job(temp_workspace):
    _project_id, root, _token = workspace.create_project("abandoned.mp4")
    record = json.loads((root / "project.json").read_text())
    record["expires_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    record["status"] = "rendering"
    record["processing_started_at"] = (datetime.now(UTC) - timedelta(hours=4)).isoformat()
    (root / "project.json").write_text(json.dumps(record))
    assert cleanup.cleanup_expired_projects() == [root.name]
    assert not root.exists()


def test_manual_delete_refuses_active_job(temp_workspace):
    project_id, root, _token = workspace.create_project("active.mp4")
    record = json.loads((root / "project.json").read_text())
    record["status"] = "rendering"
    (root / "project.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="being processed"):
        delete_tutorial_project(project_id)
    assert root.exists()
