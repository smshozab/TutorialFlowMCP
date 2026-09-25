from __future__ import annotations

import logging
import math
import re
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from tutorialflow.config import settings
from tutorialflow.utils.subprocess_utils import MediaCommandError, run_media_command

SCENE_TIME_RE = re.compile(r"pts_time:([0-9.]+)")
logger = logging.getLogger(__name__)


def sample_times(duration: float, scene_times: list[float], limit: int = 18) -> list[float]:
    """Combine regular samples and scene changes while preserving first/last states."""
    if duration <= 0 or limit < 1:
        return []
    if limit == 1:
        return [duration / 2]
    regular_count = min(limit, max(2, math.ceil(duration / 4) + 1))
    regular = [duration * i / max(1, regular_count - 1) for i in range(regular_count)]
    candidates = sorted(set([0.0, duration] + regular + [t for t in scene_times if 0 < t < duration]))
    if len(candidates) <= limit:
        return candidates
    # Evenly retain the candidate range; scene and interval candidates share the budget.
    return [candidates[round(i * (len(candidates) - 1) / (limit - 1))] for i in range(limit)]


def detect_scene_times(video: Path) -> list[float]:
    try:
        result = run_media_command([
            "ffmpeg", "-hide_banner", "-i", str(video), "-vf",
            "select='gt(scene,0.30)',showinfo", "-an", "-f", "null", "-",
        ], timeout=600)
    except MediaCommandError:
        # Regular interval frames remain available when scene analysis is unsupported.
        return []
    return [float(value) for value in SCENE_TIME_RE.findall(result.stderr)]


def extract_keyframes(video: Path, out_dir: Path, duration: float) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    times = sample_times(duration, detect_scene_times(video), settings.max_frame_count)
    frames: list[dict] = []
    last_error: str | None = None
    for index, second in enumerate(times, 1):
        target = out_dir / f"frame_{index:02d}.jpg"
        temporary = out_dir / f"frame_{index:02d}.png"
        try:
            # The MJPEG encoder rejects limited-range YUV from some screen recorders.
            # Decode to PNG, then let Pillow convert to the final JPEGs.
            run_media_command([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{second:.3f}",
                "-i", str(video), "-map", "0:v:0", "-frames:v", "1",
                "-an", "-sn", "-dn", "-c:v", "png", "-pix_fmt", "rgb24",
                "-threads", "1", "-y", str(temporary),
            ], timeout=90)
            if not temporary.is_file() or not temporary.stat().st_size:
                continue
            preview = out_dir / f"preview_{index:02d}.jpg"
            with PILImage.open(temporary) as source:
                image = source.convert("RGB")
                image.save(target, format="JPEG", quality=90, optimize=True)
                image.thumbnail((1280, 1280), PILImage.Resampling.LANCZOS)
                image.save(preview, format="JPEG", quality=82, optimize=True)
            frames.append({"time_seconds": round(second, 2), "path": str(target), "preview_path": str(preview)})
        except (MediaCommandError, OSError) as exc:
            last_error = str(exc)
            target.unlink(missing_ok=True)
            logger.warning("Frame extraction skipped time_seconds=%.2f reason=%s", second, last_error[-200:])
        finally:
            temporary.unlink(missing_ok=True)
    if not frames:
        detail = f" Last FFmpeg error: {last_error[-300:]}" if last_error else ""
        raise ValueError(f"No frames could be extracted from the recording.{detail}")
    return frames


def create_contact_sheet(frames: list[dict], target: Path, columns: int = 3) -> None:
    tile_w, tile_h, label_h = 480, 270, 34
    rows = math.ceil(len(frames) / columns)
    sheet = PILImage.new("RGB", (columns * tile_w, rows * (tile_h + label_h)), "#f4f7f5")
    draw = ImageDraw.Draw(sheet)
    for index, frame in enumerate(frames):
        image = PILImage.open(frame["path"]).convert("RGB")
        image.thumbnail((tile_w, tile_h), PILImage.Resampling.LANCZOS)
        x = (index % columns) * tile_w
        y = (index // columns) * (tile_h + label_h)
        sheet.paste(image, (x, y))
        draw.text((x + 8, y + tile_h + 8), f"{frame['time_seconds']:.1f}s", fill="#193b2d", font=ImageFont.load_default())
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, format="JPEG", quality=86, optimize=True)
