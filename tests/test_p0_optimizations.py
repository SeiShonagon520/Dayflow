"""
Unit tests for P0 optimizations:
1. config.ensure_directories()
2. idle_detector calculate_idle_millis & rollover
3. window_tracker get_process_name caching
4. llm_provider _extract_frames_from_video deduplication
"""
import numpy as np
import cv2
import pytest

import config
from core.idle_detector import calculate_idle_millis
from core.window_tracker import WindowTracker
from core.llm_provider import DayflowBackendProvider


def test_config_ensure_directories(tmp_path, monkeypatch):
    """Test config.ensure_directories creates folders properly without error."""
    test_app_dir = tmp_path / "app_data"
    test_chunks_dir = tmp_path / "chunks"
    monkeypatch.setattr(config, "APP_DATA_DIR", test_app_dir)
    monkeypatch.setattr(config, "CHUNKS_DIR", test_chunks_dir)

    assert not test_app_dir.exists()
    assert not test_chunks_dir.exists()

    config.ensure_directories()

    assert test_app_dir.exists()
    assert test_chunks_dir.exists()


def test_calculate_idle_millis_normal():
    """Test normal idle calculation."""
    # Current tick is 10,000 ms, last input was at 7,000 ms -> 3,000 ms idle
    assert calculate_idle_millis(10000, 7000) == 3000


def test_calculate_idle_millis_32bit_rollover():
    """Test 32-bit tick rollover (~49.7 days)."""
    # Suppose last input was at 0xFFFFFF00 (right before wrap)
    # and current tick wrapped around to 0x00000100 (after wrap)
    last_input = 0xFFFFFF00
    current_tick = 0x00000100
    # Expected diff: (0x100000000 - 0xFFFFFF00) + 0x100 = 0x100 + 0x100 = 512
    assert calculate_idle_millis(current_tick, last_input) == 512


def test_calculate_idle_millis_64bit_input():
    """Test 64-bit current tick count masking."""
    # current_tick is larger than 32-bit, e.g. 0x1_0000_1000
    current_tick = 0x100001000
    last_input = 0x00000800
    assert calculate_idle_millis(current_tick, last_input) == 0x800


def test_window_tracker_pid_cache(monkeypatch):
    """Test WindowTracker PID caching mechanism."""
    tracker = WindowTracker()
    tracker._pid_cache.clear()

    call_count = {"count": 0}

    class DummyProcess:
        def __init__(self, pid):
            call_count["count"] += 1
            self._pid = pid

        def name(self):
            return f"proc_{self._pid}.exe"

    monkeypatch.setattr("psutil.Process", DummyProcess)

    # First call: cache miss, instantiates DummyProcess
    name1 = tracker.get_process_name(1234)
    assert name1 == "proc_1234.exe"
    assert call_count["count"] == 1

    # Second call for same PID: cache hit, no new process instantiation
    name2 = tracker.get_process_name(1234)
    assert name2 == "proc_1234.exe"
    assert call_count["count"] == 1

    # Different PID: cache miss
    name3 = tracker.get_process_name(5678)
    assert name3 == "proc_5678.exe"
    assert call_count["count"] == 2


def test_frame_deduplication_static_video(tmp_path):
    """Test that a completely static video results in only 1 frame extracted."""
    video_file = tmp_path / "static_test.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(video_file), fourcc, 1.0, (320, 240))

    # Write 10 identical frames
    static_frame = np.ones((240, 320, 3), dtype=np.uint8) * 128
    for _ in range(10):
        out.write(static_frame)
    out.release()

    provider = DayflowBackendProvider()
    # With deduplication enabled (default threshold 2.5)
    frames = provider._extract_frames_from_video(str(video_file), max_frames=8, diff_threshold=2.5)
    assert len(frames) == 1

    # Without deduplication (threshold <= 0)
    all_frames = provider._extract_frames_from_video(str(video_file), max_frames=8, diff_threshold=0)
    assert len(all_frames) == 8


def test_frame_deduplication_dynamic_video(tmp_path):
    """Test that a video with significant visual changes preserves multiple frames."""
    video_file = tmp_path / "dynamic_test.mp4"
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(video_file), fourcc, 1.0, (320, 240))

    # Write 10 frames with changing colors/content
    for i in range(10):
        frame = np.ones((240, 320, 3), dtype=np.uint8) * ((i * 25) % 256)
        out.write(frame)
    out.release()

    provider = DayflowBackendProvider()
    frames = provider._extract_frames_from_video(str(video_file), max_frames=8, diff_threshold=2.5)
    # Changing frames should be preserved (more than 1)
    assert len(frames) > 1
