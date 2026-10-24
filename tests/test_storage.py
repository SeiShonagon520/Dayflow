"""
Unit tests for database/storage.py
"""
from datetime import datetime, timedelta
import pytest

from database.storage import StorageManager
from core.types import VideoChunk, ChunkStatus, AnalysisBatch, BatchStatus, ActivityCard


@pytest.fixture
def storage(tmp_path):
    """Fixture providing a temporary SQLite StorageManager."""
    db_file = tmp_path / "test_dayflow.db"
    mgr = StorageManager(db_path=db_file, use_pool=False)
    yield mgr
    mgr.close()


def test_storage_settings(storage):
    """Test reading and writing settings."""
    assert storage.get_setting("non_existent_key", "default_val") == "default_val"

    storage.set_setting("theme", "dark")
    assert storage.get_setting("theme", "light") == "dark"

    storage.set_setting("theme", "light")
    assert storage.get_setting("theme") == "light"


def test_storage_chunk_lifecycle(storage, tmp_path):
    """Test creating, fetching and updating video chunks."""
    now = datetime.now()
    chunk1 = VideoChunk(
        file_path=str(tmp_path / "chunk_1.mp4"),
        start_time=now - timedelta(minutes=2),
        end_time=now - timedelta(minutes=1),
        duration_seconds=60.0,
        status=ChunkStatus.PENDING,
        window_records_path=str(tmp_path / "chunk_1.json")
    )

    chunk_id = storage.save_chunk(chunk1)
    assert chunk_id is not None
    assert chunk_id > 0

    pending = storage.get_pending_chunks()
    assert len(pending) == 1
    assert pending[0].id == chunk_id
    assert pending[0].duration_seconds == 60.0
    assert pending[0].window_records_path == str(tmp_path / "chunk_1.json")

    # Update chunk status to PROCESSING
    storage.update_chunk_status(chunk_id, ChunkStatus.PROCESSING, batch_id=10)
    assert len(storage.get_pending_chunks()) == 0

    # Update to COMPLETED
    storage.update_chunk_status(chunk_id, ChunkStatus.COMPLETED)
    assert len(storage.get_pending_chunks()) == 0


def test_storage_batch_lifecycle(storage):
    """Test creating and updating analysis batches."""
    now = datetime.now()
    batch = AnalysisBatch(
        chunk_ids=[1, 2, 3],
        start_time=now - timedelta(minutes=15),
        end_time=now,
        status=BatchStatus.PENDING
    )

    batch_id = storage.create_batch(batch)
    assert batch_id is not None
    assert batch_id > 0

    # Update status to completed with observations JSON
    storage.update_batch(batch_id, BatchStatus.COMPLETED, observations_json='[{"text": "coding"}]')

    # Update failed batch with error
    failed_batch = AnalysisBatch(
        chunk_ids=[4],
        start_time=now,
        end_time=now,
        status=BatchStatus.PENDING
    )
    failed_id = storage.create_batch(failed_batch)
    storage.update_batch(failed_id, BatchStatus.FAILED, error_message="API Timeout")


def test_storage_activity_cards(storage):
    """Test saving and querying timeline cards."""
    now = datetime.now()
    card1 = ActivityCard(
        category="编程",
        title="Dayflow 开发",
        summary="编写单元测试",
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(hours=1),
        productivity_score=95.0
    )
    card2 = ActivityCard(
        category="工作",
        title="邮件处理",
        summary="回复客户邮件",
        start_time=now - timedelta(minutes=30),
        end_time=now,
        productivity_score=80.0
    )

    card_id1 = storage.save_card(card1, batch_id=1)
    card_id2 = storage.save_card(card2, batch_id=1)
    assert card_id1 > 0
    assert card_id2 > 0

    # Fetch recent cards
    recent = storage.get_recent_cards(limit=5)
    assert len(recent) == 2
    assert recent[0].title == "邮件处理"  # ordered by start_time DESC

    # Fetch cards for date
    today_cards = storage.get_cards_for_date(now)
    assert len(today_cards) == 2

    # Fetch cards for another date (should be empty)
    yesterday_cards = storage.get_cards_for_date(now - timedelta(days=5))
    assert len(yesterday_cards) == 0
