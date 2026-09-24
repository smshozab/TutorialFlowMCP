from __future__ import annotations

import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from tutorialflow.config import settings
from tutorialflow.brand_presets import canonical_brand_preset
from tutorialflow.storage.cleanup import cleanup_expired_projects
from tutorialflow.storage.workspace import (
    create_project,
    load_project,
    save_project,
    set_project_status,
)
from tutorialflow.video.frames import create_contact_sheet, extract_keyframes
from tutorialflow.video.metadata import probe_video

logger = logging.getLogger(__name__)


def validate_project_size(size_bytes: int, limit_bytes: int) -> int:
    if size_bytes > limit_bytes:
        limit_mb = limit_bytes // (1024 * 1024)
        raise ValueError(f"Uploaded recording exceeds the configured {limit_mb} MB project size limit.")
    return size_bytes


def _validate_download_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("ChatGPT provided an invalid file download URL.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Could not resolve the temporary file host.") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("The file download URL points to a non-public network address.")


def _stream_chatgpt_file(download_url: str, target: Path) -> int:
    current_url = download_url
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with httpx.Client(timeout=httpx.Timeout(120, connect=15), follow_redirects=False) as client:
            for _ in range(4):
                _validate_download_url(current_url)
                with client.stream("GET", current_url) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Temporary file download redirected without a destination.")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status_code == 404 or response.status_code == 410:
                        raise ValueError("ChatGPT's temporary upload has expired. Upload the recording again.")
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length:
                        validate_project_size(int(content_length), settings.max_project_bytes)
                    with target.open("wb") as out:
                        for chunk in response.iter_bytes(1024 * 1024):
                            total += len(chunk)
                            validate_project_size(total, settings.max_project_bytes)
                            out.write(chunk)
                    if total == 0:
                        raise ValueError("The uploaded recording was empty.")
                    return total
            raise ValueError("Too many redirects while downloading the uploaded recording.")
    except httpx.HTTPError as exc:
        raise ValueError("Could not download the uploaded recording from ChatGPT. Try uploading it again.") from exc
    except OSError as exc:
        raise ValueError("Railway could not write the uploaded recording; check available project storage.") from exc
    finally:
        if target.exists() and total == 0:
            target.unlink(missing_ok=True)


def inspect_video(video: dict, brand: str = "education_global") -> dict:
    if not isinstance(video, dict) or not video.get("download_url") or not video.get("file_id"):
        raise ValueError("Attach a screen recording using ChatGPT's file upload control.")
    brand = canonical_brand_preset(brand)
    cleanup_expired_projects()
    filename = Path(video.get("file_name") or "recording.mp4").name
    project_id, root, _artifact_token = create_project(filename)
    extension = Path(filename).suffix.lower()
    if extension not in {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}:
        extension = ".mp4"
    source = root / "source" / f"video{extension}"
    record = load_project(project_id)
    set_project_status(record, "processing_inspection")
    save_project(project_id, record)
    try:
        size = _stream_chatgpt_file(video["download_url"], source)
        logger.info("Project upload received project_id=%s bytes=%d", project_id, size)
        metadata = probe_video(source)
        max_duration = settings.max_video_duration_minutes * 60
        if metadata["duration_seconds"] > max_duration:
            raise ValueError(f"Recording is {metadata['duration_seconds'] / 60:.1f} minutes; limit is {settings.max_video_duration_minutes} minutes.")
        frames = extract_keyframes(source, root / "frames", metadata["duration_seconds"])
        contact_sheet = root / "frames" / "contact_sheet.jpg"
        create_contact_sheet(frames, contact_sheet)
        record = load_project(project_id)
        set_project_status(record, "inspected")
        record["brand"] = brand
        record["source"] = {**metadata, "path": "source/" + source.name}
        record["frames"] = [
            {"time_seconds": f["time_seconds"], "path": str(Path(f["path"]).relative_to(root)),
             "preview_path": str(Path(f["preview_path"]).relative_to(root))}
            for f in frames
        ]
        record["contact_sheet"] = "frames/contact_sheet.jpg"
        save_project(project_id, record)
        logger.info("Video inspected project_id=%s frame_count=%d", project_id, len(frames))
        return {
            "project_id": project_id, "status": "inspected", **metadata,
            "duration": metadata["duration_seconds"],
            "resolution": f"{metadata['width']}x{metadata['height']}",
            "frame_count": len(frames),
            "recommended_word_count": round(metadata["duration_seconds"] / 60 * 150),
            "recommended_word_count_range": [
                round(metadata["duration_seconds"] / 60 * 150 * .8),
                round(metadata["duration_seconds"] / 60 * 150 * 1.2),
            ],
            "contact_sheet_path": "frames/contact_sheet.jpg",
            "keyframes": [
                {"time_seconds": f["time_seconds"], "path": Path(f["path"]).relative_to(root).as_posix(),
                 "preview_path": Path(f["preview_path"]).relative_to(root).as_posix()}
                for f in frames
            ],
        }
    except Exception:
        # Failed inspections should not leave bulky partial uploads behind.
        from tutorialflow.storage.workspace import delete_project
        delete_project(project_id)
        raise
