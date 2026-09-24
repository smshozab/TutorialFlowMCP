from __future__ import annotations

import subprocess


class MediaCommandError(RuntimeError):
    pass


def run_media_command(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise MediaCommandError(f"Required media tool not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaCommandError(f"Media command timed out after {timeout} seconds.") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "unknown FFmpeg error").strip()[-1600:]
        raise MediaCommandError(detail)
    return result
