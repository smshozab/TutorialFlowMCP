import shutil
import subprocess
from subprocess import CompletedProcess

import pytest
from PIL import Image

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


def test_frame_extraction_converts_png_to_jpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(frames, "detect_scene_times", lambda _video: [])

    def fake_ffmpeg(command, timeout):
        assert "png" in command and "rgb24" in command
        Image.new("RGB", (320, 180), "#176d49").save(command[-1], format="PNG")

    monkeypatch.setattr(frames, "run_media_command", fake_ffmpeg)
    extracted = frames.extract_keyframes(tmp_path / "source.mp4", tmp_path / "frames", 2)
    assert extracted
    assert all((tmp_path / "frames" / f"frame_{index:02d}.jpg").is_file()
               for index in range(1, len(extracted) + 1))
    assert not list((tmp_path / "frames").glob("*.png"))


def test_branded_thumbnail_uses_actual_frame(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from tutorialflow.storage import workspace
    from tutorialflow.video.thumbnail import render_thumbnail

    monkeypatch.setattr(workspace, "settings", SimpleNamespace(
        workspace_path=tmp_path, ttl_hours=24, artifact_secret="",
    ))
    project_id, root, _ = workspace.create_project("video.mp4")
    frame = root / "frames" / "frame_01.jpg"
    Image.new("RGB", (640, 360), "#d1e5fa").save(frame)
    record = workspace.load_project(project_id)
    record["frames"] = [{"time_seconds": 1.0, "path": "frames/frame_01.jpg"}]
    workspace.save_project(project_id, record)

    result = render_thumbnail(project_id, "Generate a Statement of Marks", "Education Global")
    assert result["path"] == "output/thumbnail.png"
    with Image.open(root / result["path"]) as thumbnail:
        assert thumbnail.size == (1280, 720)


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
