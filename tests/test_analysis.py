"""
Unit tests for core/analysis.py
"""
from datetime import datetime, timedelta
import pytest

from core.types import VideoChunk, ChunkStatus
from core.analysis import AnalysisScheduler


def test_create_batches_empty():
    """Test batch creation on empty chunk list."""
    scheduler = AnalysisScheduler(batch_duration_minutes=15)
    batches = scheduler._create_batches([])
    assert batches == []


def test_create_batches_grouping():
    """Test batch creation groups chunks up to batch_duration."""
    scheduler = AnalysisScheduler(batch_duration_minutes=2)  # 2 minutes = 120 seconds

    now = datetime.now()
    # 5 chunks of 60 seconds each -> 300 seconds total
    # Batch 1: chunk 0 + chunk 1 (120s)
    # Batch 2: chunk 2 + chunk 3 (120s)
    # Batch 3: chunk 4 (60s)
    chunks = [
        VideoChunk(
            id=i,
            file_path=f"/fake/chunk_{i}.mp4",
            start_time=now + timedelta(minutes=i),
            end_time=now + timedelta(minutes=i + 1),
            duration_seconds=60.0,
            status=ChunkStatus.PENDING
        )
        for i in range(5)
    ]

    batches = scheduler._create_batches(chunks)
    assert len(batches) == 3
    assert len(batches[0]) == 2
    assert len(batches[1]) == 2
    assert len(batches[2]) == 1
    assert [c.id for c in batches[0]] == [0, 1]
    assert [c.id for c in batches[1]] == [2, 3]
    assert [c.id for c in batches[2]] == [4]
