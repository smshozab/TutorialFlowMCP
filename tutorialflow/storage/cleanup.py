from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime, timedelta

from tutorialflow.config import settings

logger = logging.getLogger(__name__)


def cleanup_expired_projects() -> list[str]:
    root = settings.workspace_path
    if not root.exists():
        return []
    now = datetime.now(UTC)
    deleted: list[str] = []
    for folder in root.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        try:
            info = json.loads((folder / "project.json").read_text(encoding="utf-8"))
            expiry = datetime.fromisoformat(info["expires_at"])
            status = info.get("status", "")
            active = status == "rendering" or status.startswith("processing_")
            started_at = info.get("processing_started_at", info.get("created_at"))
            stale = not started_at or now - datetime.fromisoformat(started_at) > timedelta(hours=3)
            if expiry <= now and (not active or stale):
                shutil.rmtree(folder)
                deleted.append(folder.name)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            # Remove abandoned partial projects after the TTL; never delete active renders.
            try:
                if datetime.fromtimestamp(folder.stat().st_mtime, UTC) < now - timedelta(hours=settings.ttl_hours):
                    shutil.rmtree(folder)
                    deleted.append(folder.name)
            except OSError:
                logger.warning("Could not inspect expired project directory")
    if deleted:
        logger.info("Expired project cleanup completed count=%d", len(deleted))
    return deleted
