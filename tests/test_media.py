import shutil
import subprocess
from subprocess import CompletedProcess

import pytest

from tutorialflow.video import ffmpeg, frames, metadata


@pytest.mark.parametrize(("value", "expected"), [("1:02", 62), ("01:02:03.5", 3723.5), ("54.25", 54.25)])
def test_parse_duration(value, expected):
    assert metadata.parse_duration(value) == expected


def test_parse_duration_rejects_bad_value():
    for value in ("tomorrow", "NaN", "-1"):
        with pytest.raises(ValueError):
            metadata.parse_duration(value)


def test_sample_times_caps_frames_and_keeps_endpoints():
    result = frames.sample_times(60, [10.2, 24.5, 51.3], limit=12)
    assert len(result) == 12
    assert result[0] == 0
    assert result[-1] == 60


def test_retiming_factor():
    assert ffmpeg.retiming_factor(60, 50) == pytest.approx(5 / 6)
    assert ffmpeg.retiming_factor(45, 52) == pytest.approx(52 / 45)
    with pytest.raises(ValueError):
        ffmpeg.retiming_factor(0, 5)


def test_ffmpeg_presence_probe(monkeypatch):
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda name: f"/fake/{name}")
    assert ffmpeg.media_tools_status() == {"ffmpeg": True, "ffprobe": True}


def test_render_command_is_argument_array_and_safe():
    command = ffmpeg.render_command("in.mp4", "voice.mp3", "out.mp4", 60, 50)
    assert isinstance(command, list)
    assert "shell=True" not in command
    assert "libx264" in command
    assert "+faststart" in command
    assert "setpts=0.83333333*PTS" in command


def test_render_command_rejects_extreme_ratio():
    with pytest.raises(ValueError):
        ffmpeg.render_command("v", "a", "o", 10, 100)


def test_probe_rejects_invalid_video(tmp_path, monkeypatch):
    source = tmp_path / "bad.mp4"
    source.write_bytes(b"not video")
    monkeypatch.setattr(metadata, "run_media_command", lambda *_a, **_kw: CompletedProcess([], 0, '{"streams": []}', ""))
    with pytest.raises(ValueError, match="no video stream"):
        metadata.probe_video(source)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is installed in Docker/Railway, not required on the dev PC")
def test_tiny_synthetic_video_pipeline(tmp_path):
    """A three-second throwaway clip exercises real ffprobe and frame extraction."""
    video = tmp_path / "tiny.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
        "testsrc2=size=640x360:rate=10:duration=3", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=3", "-shortest", "-c:v", "libx264", "-pix_fmt",
        "yuv420p", "-c:a", "aac", "-y", str(video),
    ], check=True, capture_output=True)
    info = metadata.probe_video(video)
    assert info["duration_seconds"] == pytest.approx(3, abs=.15)
    assert info["has_audio"] is True
    selected = frames.extract_keyframes(video, tmp_path / "frames", info["duration_seconds"])
    sheet = tmp_path / "frames" / "contact_sheet.jpg"
    frames.create_contact_sheet(selected, sheet)
    assert 2 <= len(selected) <= 18
    assert sheet.is_file()
