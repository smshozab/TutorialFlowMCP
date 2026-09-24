from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    workspace_path: Path = Path(os.getenv("WORKSPACE_PATH", "/tmp/tutorialflow"))
    ttl_hours: int = int(os.getenv("PROJECT_TTL_HOURS", "24"))
    max_project_size_mb: int = int(os.getenv("MAX_PROJECT_SIZE_MB", "500"))
    max_video_duration_minutes: int = int(os.getenv("MAX_VIDEO_DURATION_MINUTES", "10"))
    max_concurrent_renders: int = int(os.getenv("MAX_CONCURRENT_RENDERS", "1"))
    max_frame_count: int = int(os.getenv("MAX_FRAME_COUNT", "18"))
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    artifact_secret: str = os.getenv("ARTIFACT_SECRET", "")
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
    elevenlabs_voice_id: str = os.getenv("ELEVENLABS_VOICE_ID", "")
    elevenlabs_model: str = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")

    @property
    def max_project_bytes(self) -> int:
        return self.max_project_size_mb * 1024 * 1024


settings = Settings()
