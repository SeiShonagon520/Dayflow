"""P0 acceptance scenarios with isolated SQLite data, model requests and monitors."""

import asyncio
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from bridge import server
from bridge.stats_service import collect_stats
from core.analysis import AnalysisScheduler
from core.activity_time import ledger_days, summarize_activities
from core.chunk_files import protected_chunk_files
from core.dashboard_exporter import DashboardExporter
from core.llm_provider import DayflowBackendProvider
from core.recorder import ScreenRecorder
from core.types import ActivityCard, ChunkStatus, Observation, VideoChunk
from core.window_tracker import WindowTracker
from database.storage import StorageManager

START = datetime(2026, 11, 25, 9)


@pytest.fixture
def queue(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "CHUNKS_DIR", tmp_path)
    monkeypatch.setattr(config, "AUTO_DELETE_ANALYZED_CHUNKS", True)
    db = StorageManager(tmp_path / "test.db")
    yield db
    db.close()


def make_chunk(db, directory, start=START):
    path = directory / f"chunk_{start:%Y%m%d_%H%M%S}.mp4"
    path.touch()
    metadata = path.with_suffix(".json")
    metadata.write_text("[]", encoding="utf-8")
    chunk = VideoChunk(file_path=str(path), start_time=start,
                       end_time=start + timedelta(minutes=1), duration_seconds=60,
                       status=ChunkStatus.PENDING, window_records_path=str(metadata))
    chunk.id = db.save_chunk(chunk)
    return chunk


def make_card(title, start, minutes, score=80):
    return ActivityCard(category="工作", title=title, summary="", start_time=start,
                        end_time=start + timedelta(minutes=minutes), productivity_score=score)


def read_state(db, chunk):
    with db._get_connection() as conn:
        return dict(conn.execute(
            "SELECT status, retry_count, retry_at, analysis_error FROM chunks WHERE id=?", (chunk.id,),
        ).fetchone())


def test_network_retry_uses_persisted_backoff_and_only_cleans_after_success(queue, tmp_path, monkeypatch):
    chunk = make_chunk(queue, tmp_path)
    clock = [1000.0]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    payloads = [
        {"observations": [{"start_ts": 0, "end_ts": 60, "text": "测试活动"}]},
        {"cards": [{"title": "恢复后的活动", "start_time": START.isoformat(),
                    "end_time": chunk.end_time.isoformat(), "productivity_score": 80}]},
    ]
    class ModelHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            reply = json.dumps({"choices": [{"message": {"content": json.dumps(payloads.pop(0))}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    http_server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler, bind_and_activate=False)
    http_server.server_bind()  # Reserve the address; connections are refused until listen().
    serving_thread = None

    async def exercise():
        nonlocal serving_thread
        port = http_server.server_address[1]
        provider = DayflowBackendProvider(f"http://127.0.0.1:{port}/ollama/v1", "", "test", timeout=3)
        calls = []
        complete = provider._chat_completion

        async def record_request(*args, **kwargs):
            calls.append(1)
            return await complete(*args, **kwargs)

        monkeypatch.setattr(provider, "_chat_completion", record_request)
        monkeypatch.setattr(provider, "_extract_frames_from_video", lambda *args, **kwargs: ["synthetic-frame"])
        scheduler = AnalysisScheduler(storage=queue, provider=provider)
        try:
            await scheduler._scan_and_process()
            assert read_state(queue, chunk) == {
                "status": "pending", "retry_count": 1, "retry_at": 1015.0, "analysis_error": "network",
            }
            assert Path(chunk.file_path).exists() and Path(chunk.window_records_path).exists()
            assert not queue.get_cards_for_date(START)
            http_server.server_activate()
            serving_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
            serving_thread.start()
            clock[0] = 1014
            await scheduler._scan_and_process()
            assert len(calls) == 1
            clock[0] = 1015
            await scheduler._scan_and_process()
            assert len(calls) == 3
            assert [card.title for card in queue.get_cards_for_date(START)] == ["恢复后的活动"]
            assert read_state(queue, chunk)["status"] == "completed"
            assert not Path(chunk.file_path).exists() and not Path(chunk.window_records_path).exists()
            await scheduler._scan_and_process()
            assert len(calls) == 3
        finally:
            await provider.close()

    try:
        asyncio.run(exercise())
    finally:
        if serving_thread:
            http_server.shutdown()
            serving_thread.join(timeout=3)
        http_server.server_close()


@pytest.mark.parametrize("stage", ["transcript", "cards"])
def test_empty_result_keeps_original_files_and_never_marks_success(queue, tmp_path, stage):
    chunk = make_chunk(queue, tmp_path)

    async def transcript(*args, **kwargs):
        return [] if stage == "transcript" else [Observation(0, 60, "测试活动")]

    async def empty_cards(*args, **kwargs):
        return []

    scheduler = AnalysisScheduler(
        storage=queue, provider=SimpleNamespace(transcribe_video=transcript, generate_activity_cards=empty_cards),
    )
    asyncio.run(scheduler._process_batch([chunk]))
    assert read_state(queue, chunk)["status"] == "pending"
    assert read_state(queue, chunk)["analysis_error"] == ("empty_observations" if stage == "transcript" else "empty_cards")
    assert Path(chunk.file_path).is_file() and Path(chunk.window_records_path).is_file()
    assert Path(chunk.file_path).resolve() in protected_chunk_files(queue)
    assert not queue.get_cards_for_date(START)
    with queue._get_connection() as conn:
        assert conn.execute("SELECT status FROM analysis_batches").fetchone()[0] == "failed"


_WORKER = r"""
import asyncio
import config
from bridge import server
from datetime import timedelta
from pathlib import Path
import sys
import time
from core.analysis import AnalysisScheduler
from types import SimpleNamespace
from core.types import ActivityCard, Observation
from database.storage import StorageManager

db_path, marker, phase = sys.argv[1:]
marker = Path(marker)
db = StorageManager(Path(db_path))

async def transcribe(*args, **kwargs):
    if phase == 'claimed':
        marker.write_text('claimed')
        await asyncio.sleep(60)
    return [Observation(0, 60, 'synthetic')]

async def cards(observations, context, *, start_time):
    return [ActivityCard(category='work', title=f'card-{i}', summary='',
                         start_time=start_time+timedelta(seconds=30*i),
                         end_time=start_time+timedelta(seconds=30*n))
            for i,n in [(0,1),(1,2)]]

if phase == 'in-transaction':
    insert_card = db._insert_card
    def interrupt(*args, **kwargs):
        result = insert_card(*args, **kwargs)
        marker.write_text('inserted')
        time.sleep(60)
        return result
    db._insert_card = interrupt

class Provider:
    transcribe_video = staticmethod(transcribe)
    generate_activity_cards = staticmethod(cards)

try:
    scheduler = AnalysisScheduler(storage=db, provider=Provider())
    if phase == 'complete':
        config.API_BASE_URL = 'http://127.0.0.1:11434/v1'
        config.API_MODEL = 'isolated'
        db.set_setting("recording_mode", "visual")
        server._storage = db
        server._analysis = SimpleNamespace(start_scheduler=scheduler.start)
        server._resume_analysis_queue()
        deadline = time.monotonic() + 8
        while db.analysis_queue_size() and time.monotonic() < deadline:
            time.sleep(0.04)
        assert not db.analysis_queue_size()
        assert scheduler.stop()
    else:
        asyncio.run(scheduler.process_immediately())
finally:
    db.close()
"""


@pytest.mark.parametrize("phase", ["claimed", "in-transaction"])
def test_force_terminated_worker_recovers_without_duplicate_cards(queue, tmp_path, phase):
    chunk = make_chunk(queue, tmp_path)
    marker = tmp_path / "worker-ready"
    args = [sys.executable, "-c", _WORKER, str(queue.db_path), str(marker)]
    proc = subprocess.Popen([*args, phase], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 20
        while not marker.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.04)
        if proc.poll() is not None:
            pytest.fail(proc.stderr.read().decode(errors="replace"))
        assert marker.exists(), "worker failed to reach the intended interruption point"
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=8)
        proc.stderr.close()

    assert read_state(queue, chunk)["status"] == "processing"
    assert not queue.get_cards_for_date(START)
    assert Path(chunk.file_path).is_file()
    subprocess.run([*args, "complete"], check=True, timeout=20)
    assert read_state(queue, chunk)["status"] == "completed"
    assert not Path(chunk.file_path).exists()
    assert sorted(card.title for card in queue.get_cards_for_date(START)) == ["card-0", "card-1"]
    subprocess.run([*args, "complete"], check=True, timeout=20)
    assert len(queue.get_cards_for_date(START)) == 2


def test_cross_day_hour_and_overlaps_agree_across_outputs(queue, monkeypatch):
    from core.email_service import ReportGenerator
    day = START.date()
    tomorrow = day + timedelta(days=1)
    queue.save_card(make_card("short", START.replace(minute=45), 5, 50))
    queue.save_card(make_card("long", START.replace(minute=50), 55, 90))
    queue.save_card(make_card("overlap", START.replace(hour=10, minute=5), 15, 20))
    fetches = []
    read_cards = queue.get_cards_in_range

    def count_reads(start, end):
        fetches.append((start, end))
        return read_cards(start, end)

    monkeypatch.setattr(queue, "get_cards_in_range", count_reads)
    stats = collect_stats(queue, days=30, today=START)
    assert len(fetches) == 1
    dashboard = DashboardExporter(queue)._collect_data(day, day)
    assert stats["metrics"]["totalMinutes"] == dashboard.total_duration_minutes == 60
    assert stats["metrics"]["avgScore"] == dashboard.avg_productivity_score == 86.7
    assert sum(row["minutes"] for row in stats["hourly"][9]) == dashboard.hourly_efficiency[9]["duration"] == 15
    assert sum(row["minutes"] for row in stats["hourly"][10]) == dashboard.hourly_efficiency[10]["duration"] == 45
    mail = ReportGenerator(queue)
    monkeypatch.setattr(mail.ai_generator, "generate_comment", lambda *_: "")
    monkeypatch.setattr(mail.ai_generator, "generate_deep_analysis", lambda *_: "")
    monkeypatch.setattr(mail, "_build_html", lambda _, categories, minutes, score, *_args: (minutes, score))
    assert mail.generate_daily_report(START) == (60, 86.7)

    start = START.replace(hour=23, minute=50)
    original_id = queue.save_card(make_card("night", start, 20, 75))
    ledger = ledger_days(queue, day, tomorrow)
    assert summarize_activities(ledger[day])["minutes"] == 70
    assert summarize_activities(ledger[tomorrow])["minutes"] == 10
    assert DashboardExporter(queue)._collect_data(tomorrow, tomorrow).total_duration_minutes == 10
    monkeypatch.setattr(server, "_storage", queue)
    rows = server.get_cards(tomorrow.isoformat())["cards"]
    assert rows[0]["id"] == original_id
    assert rows[0]["startTime"] == start.isoformat()  # Undo retains the original interval.
    assert rows[0]["displayStartTime"] == datetime.combine(tomorrow, datetime.min.time()).isoformat()
    assert rows[0]["durationMinutes"] == 10
    csv = server._csv(day, tomorrow)
    assert f"{day},23:50,24:00,10.0" in csv
    assert f"{tomorrow},00:00,00:10,10.0" in csv


def test_dual_screen_capture_blocks_background_sensitive_window_and_changes_during_grab(tmp_path, monkeypatch):
    from core import window_tracker

    left, right = (-4, 0, 0, 2), (0, 0, 4, 2)
    windows = {1: right, 2: left, 3: (-12, 0, -8, 2)}
    handles = [1, 2, 3]
    names = {1: "editor.exe", 2: "keepass.exe", 3: "keepass.exe"}
    tracker = WindowTracker()
    monkeypatch.setattr(tracker, "capture_monitor_bounds", lambda: {left, right})
    monkeypatch.setattr(window_tracker.win32gui, "GetDesktopWindow", lambda: 1000)
    monkeypatch.setattr(window_tracker.win32gui, "IsWindowVisible", lambda _: True)
    monkeypatch.setattr(window_tracker.win32gui, "IsIconic", lambda _: False)
    monkeypatch.setattr(window_tracker.win32gui, "EnumWindows", lambda fn, _: [fn(hwnd, None) for hwnd in handles])
    monkeypatch.setattr(window_tracker.win32gui, "GetWindowText", lambda hwnd: names[hwnd])
    monkeypatch.setattr(window_tracker.win32process, "GetWindowThreadProcessId", lambda hwnd: (0, hwnd))
    monkeypatch.setattr(window_tracker.psutil, "Process", lambda pid: SimpleNamespace(name=lambda: names[pid]))

    def read_attribute(hwnd, attribute, output, length):
        if attribute == 14:
            ctypes.cast(output, ctypes.POINTER(wintypes.DWORD)).contents.value = 0
        else:
            rect = ctypes.cast(output, ctypes.POINTER(wintypes.RECT)).contents
            rect.left, rect.top, rect.right, rect.bottom = windows[hwnd]
        return 0

    monkeypatch.setattr(ctypes.windll, "user32", SimpleNamespace(GetShellWindow=lambda: 1001))
    monkeypatch.setattr(ctypes.windll, "dwmapi", SimpleNamespace(DwmGetWindowAttribute=read_attribute))
    recorder = ScreenRecorder(output_dir=tmp_path, output_idx=-1)
    recorder._window_tracker = tracker
    recorder._privacy_filter.app_blacklist = {"keepass"}
    recorder._output_geometries = [
        {"left": -4, "top": 0, "width": 4, "height": 2},
        {"left": 0, "top": 0, "width": 4, "height": 2},
    ]
    recorder._canvas_offset_x = -4
    recorder._canvas_shape = (2, 8, 3)
    grabs = []

    def grab(value):
        grabs.append(value)
        return np.full((2, 4, 3), value, np.uint8)

    recorder._cameras = [SimpleNamespace(grab=lambda: grab(77)), SimpleNamespace(grab=lambda: grab(42))]
    assert recorder._grab_composite_safely() is None
    assert recorder.is_privacy_paused and not grabs
    recorder._camera = SimpleNamespace(grab=lambda: grab(77))
    recorder._privacy_filter.action = "pause"
    assert recorder._grab_single_safely() is None
    assert recorder.is_privacy_paused and not grabs
    recorder._privacy_filter.action = "blackout"
    original = np.full((2, 4, 3), 77, np.uint8)
    np.testing.assert_array_equal(recorder._grab_single_safely(), recorder._privacy_filter.mask_frame(original))
    assert not np.array_equal(original, recorder._privacy_filter.mask_frame(original))
    grabs.clear()
    # A sensitive window outside both capture bounds does not stop the recording.
    handles.remove(2)
    frame = recorder._grab_composite_safely()
    assert not recorder.is_privacy_paused
    assert frame[0, 0, 0] == 77 and frame[0, 6, 0] == 42

    def opens_during_grab():
        handles.append(2)
        return grab(77)

    recorder._cameras[0].grab = opens_during_grab
    assert recorder._grab_composite_safely() is None
    assert recorder.is_privacy_paused
    assert list(tmp_path.iterdir()) == []

    monkeypatch.setattr(recorder, "_finalize_current_chunk", recorder._stop_event.set)
    monkeypatch.setattr(recorder, "_create_new_chunk", lambda *args: pytest.fail("private frame reached the writer"))
    recorder._recording_loop()
    assert list(tmp_path.iterdir()) == []

    # Fail closed when a monitor disappears or the window inventory is unavailable.
    monkeypatch.setattr(tracker, "capture_monitor_bounds", lambda: {right})
    assert recorder._grab_composite_safely() is None
    monkeypatch.setattr(tracker, "capture_monitor_bounds", lambda: {left, right})
    monkeypatch.setattr(tracker, "visible_windows", lambda _: None)
    assert recorder._grab_composite_safely() is None


def test_paused_gap_does_not_extend_written_slice(tmp_path):
    saved = []
    recorder = ScreenRecorder(output_dir=tmp_path, on_chunk_saved=saved.append)
    path = tmp_path / "synthetic.mp4"
    path.touch()
    recorder._current_chunk_path = path
    recorder._current_writer = SimpleNamespace(release=lambda: None)
    start = datetime.now() - timedelta(minutes=5)
    recorder._current_chunk_start = start
    recorder._last_frame_at = start + timedelta(seconds=4)
    recorder._finalize_current_chunk()
    assert saved[0].duration_seconds == 5
    assert saved[0].end_time == start + timedelta(seconds=5)


def test_visual_stop_keeps_uncommitted_chunk_for_retry(tmp_path):
    saved = []

    def save(chunk):
        if not saved:
            saved.append(chunk)
            raise OSError("temporary database failure")
        assert chunk is saved[0]

    recorder = ScreenRecorder(output_dir=tmp_path, on_chunk_saved=save)
    path = tmp_path / "synthetic.mp4"
    path.touch()
    recorder._current_chunk_path = path
    recorder._current_writer = SimpleNamespace(release=lambda: None)
    recorder._current_chunk_start = datetime.now() - timedelta(seconds=2)
    recorder._last_frame_at = datetime.now() - timedelta(seconds=1)

    assert not recorder.stop()[0]
    assert path.is_file()
    assert recorder.stop() == (True, None)
    assert recorder._pending_chunk is None


def test_shutdown_never_closes_storage_after_failed_final_save(monkeypatch):
    import threading

    results = iter([(False, "尚未保存"), (False, "尚未保存"), (True, None)])
    closed = []
    recorder = SimpleNamespace(is_recording=False, stop_recording=lambda **_: next(results))
    monkeypatch.setattr(server, "_recorder", recorder)
    monkeypatch.setattr(server, "_storage", SimpleNamespace(close=lambda: closed.append(True)))
    for name in ("_analysis", "_refiner", "_provider", "_log_manager", "_mail_thread"):
        monkeypatch.setattr(server, name, None)
    monkeypatch.setattr(server, "_shutting_down", False)
    monkeypatch.setattr(server, "_mail_stop", threading.Event())

    for _ in range(2):
        ok, failures = server._graceful_shutdown()
        assert not ok and "尚未保存" in failures
        assert not closed
    assert server._graceful_shutdown() == (True, [])
    assert closed == [True]
