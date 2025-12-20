"""
Property-Based Tests for ConfigManager

Feature: infrastructure-improvements
Tests for Properties 9, 10, 11
Validates: Requirements 3.2, 3.4, 3.5
"""
import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, List, Tuple
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings, strategies as st
from PySide6.QtCore import QCoreApplication

# Ensure Qt application exists for signal testing
import sys
if not QCoreApplication.instance():
    app = QCoreApplication(sys.argv)


class MockStorage:
    """Mock StorageManager for testing ConfigManager in isolation"""
    
    def __init__(self, db_path: str = None):
        self._settings = {}
        self._db_path = db_path or ":memory:"
        self._conn = None
        if db_path:
            self._init_db()
    
    def _init_db(self):
        """Initialize real SQLite database for round-trip tests"""
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._conn.commit()
    
    def get_setting(self, key: str, default: str = "") -> str:
        if self._conn:
            cursor = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            return row[0] if row else default
        return self._settings.get(key, default)
    
    def set_setting(self, key: str, value: str):
        if self._conn:
            self._conn.execute(
                """
                INSERT INTO settings (key, value, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
                """,
                (key, value, value)
            )
            self._conn.commit()
        else:
            self._settings[key] = value
    
    def close(self):
        if self._conn:
            self._conn.close()


# Import ConfigManager after mock is defined
from core.config_manager import ConfigManager, ConfigKey, DEFAULT_VALUES


# ============================================================================
# Property 9: Config Fallback to Defaults
# *For any* configuration key that has no database entry, the ConfigManager 
# should return the default value from config.py.
# **Validates: Requirements 3.2**
# ============================================================================

# Strategy for generating valid config keys
config_keys = st.sampled_from([
    ConfigKey.EMAIL_SEND_TIMES,
    ConfigKey.VIDEO_MAX_FRAMES,
    ConfigKey.API_TIMEOUT,
    ConfigKey.BATCH_DURATION_MINUTES,
    ConfigKey.LOG_MAX_SIZE_MB,
    ConfigKey.LOG_BACKUP_COUNT,
    ConfigKey.LOG_RETENTION_DAYS,
    ConfigKey.DB_POOL_SIZE,
    ConfigKey.DB_POOL_TIMEOUT,
    ConfigKey.DB_IDLE_TIMEOUT,
])


@settings(max_examples=100)
@given(key=config_keys)
def test_property_9_config_fallback_to_defaults(key: str):
    """
    Feature: infrastructure-improvements, Property 9: Config Fallback to Defaults
    
    For any configuration key that has no database entry, the ConfigManager 
    should return the default value from DEFAULT_VALUES.
    
    **Validates: Requirements 3.2**
    """
    # Create ConfigManager with empty storage (no database entries)
    storage = MockStorage()
    config_manager = ConfigManager(storage)
    
    # Get value - should fall back to default
    value = config_manager.get(key)
    
    # Verify it matches the expected default
    expected_default_str = DEFAULT_VALUES.get(key, "")
    
    # Parse expected default based on key type
    if key == ConfigKey.EMAIL_SEND_TIMES:
        expected = json.loads(expected_default_str)
    elif key in {ConfigKey.VIDEO_MAX_FRAMES, ConfigKey.BATCH_DURATION_MINUTES,
                 ConfigKey.LOG_MAX_SIZE_MB, ConfigKey.LOG_BACKUP_COUNT,
                 ConfigKey.LOG_RETENTION_DAYS, ConfigKey.DB_POOL_SIZE}:
        expected = int(expected_default_str)
    elif key in {ConfigKey.API_TIMEOUT, ConfigKey.DB_POOL_TIMEOUT, ConfigKey.DB_IDLE_TIMEOUT}:
        expected = float(expected_default_str)
    else:
        expected = expected_default_str
    
    assert value == expected, f"Key {key}: expected {expected}, got {value}"


# ============================================================================
# Property 10: Config Persistence Round-Trip
# *For any* valid configuration value set via ConfigManager.set(), a subsequent 
# ConfigManager.get() should return an equivalent value.
# **Validates: Requirements 3.4**
# ============================================================================

# Strategies for different value types
int_values = st.integers(min_value=1, max_value=1000)
float_values = st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False)
time_strings = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=23),
        st.integers(min_value=0, max_value=59)
    ).map(lambda t: f"{t[0]:02d}:{t[1]:02d}"),
    min_size=1,
    max_size=5
)


@settings(max_examples=100)
@given(value=int_values)
def test_property_10_round_trip_int_values(value: int):
    """
    Feature: infrastructure-improvements, Property 10: Config Persistence Round-Trip (int)
    
    For any valid integer configuration value set via ConfigManager.set(), 
    a subsequent ConfigManager.get() should return an equivalent value.
    
    **Validates: Requirements 3.4**
    """
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        storage = MockStorage(db_path)
        config_manager = ConfigManager(storage)
        
        key = ConfigKey.VIDEO_MAX_FRAMES
        config_manager.set(key, value)
        
        # Clear cache to force database read
        config_manager.clear_cache()
        
        retrieved = config_manager.get(key)
        assert retrieved == value, f"Round-trip failed: set {value}, got {retrieved}"
    finally:
        storage.close()
        Path(db_path).unlink(missing_ok=True)


@settings(max_examples=100)
@given(value=float_values)
def test_property_10_round_trip_float_values(value: float):
    """
    Feature: infrastructure-improvements, Property 10: Config Persistence Round-Trip (float)
    
    For any valid float configuration value set via ConfigManager.set(), 
    a subsequent ConfigManager.get() should return an equivalent value.
    
    **Validates: Requirements 3.4**
    """
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        storage = MockStorage(db_path)
        config_manager = ConfigManager(storage)
        
        key = ConfigKey.API_TIMEOUT
        config_manager.set(key, value)
        
        # Clear cache to force database read
        config_manager.clear_cache()
        
        retrieved = config_manager.get(key)
        # Use approximate comparison for floats
        assert abs(retrieved - value) < 0.001, f"Round-trip failed: set {value}, got {retrieved}"
    finally:
        storage.close()
        Path(db_path).unlink(missing_ok=True)


@settings(max_examples=100)
@given(times=time_strings)
def test_property_10_round_trip_email_times(times: List[str]):
    """
    Feature: infrastructure-improvements, Property 10: Config Persistence Round-Trip (email times)
    
    For any valid list of time strings set via ConfigManager.set(), 
    a subsequent ConfigManager.get() should return an equivalent value.
    
    **Validates: Requirements 3.4**
    """
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    
    try:
        storage = MockStorage(db_path)
        config_manager = ConfigManager(storage)
        
        key = ConfigKey.EMAIL_SEND_TIMES
        config_manager.set(key, times)
        
        # Clear cache to force database read
        config_manager.clear_cache()
        
        retrieved = config_manager.get(key)
        assert retrieved == times, f"Round-trip failed: set {times}, got {retrieved}"
    finally:
        storage.close()
        Path(db_path).unlink(missing_ok=True)


# ============================================================================
# Property 11: Config Change Signal Emission
# *For any* configuration value change via ConfigManager.set(), the config_changed 
# signal should be emitted with the correct key and new value.
# **Validates: Requirements 3.5**
# ============================================================================

@settings(max_examples=100)
@given(value=int_values)
def test_property_11_signal_emission_int(value: int):
    """
    Feature: infrastructure-improvements, Property 11: Config Change Signal Emission (int)
    
    For any configuration value change via ConfigManager.set(), the config_changed 
    signal should be emitted with the correct key and new value.
    
    **Validates: Requirements 3.5**
    """
    storage = MockStorage()
    config_manager = ConfigManager(storage)
    
    # Track signal emissions
    received_signals = []
    
    def on_config_changed(key: str, new_value: Any):
        received_signals.append((key, new_value))
    
    config_manager.config_changed.connect(on_config_changed)
    
    key = ConfigKey.VIDEO_MAX_FRAMES
    config_manager.set(key, value)
    
    # Verify signal was emitted with correct parameters
    assert len(received_signals) == 1, f"Expected 1 signal, got {len(received_signals)}"
    emitted_key, emitted_value = received_signals[0]
    assert emitted_key == key, f"Signal key mismatch: expected {key}, got {emitted_key}"
    assert emitted_value == value, f"Signal value mismatch: expected {value}, got {emitted_value}"


@settings(max_examples=100)
@given(value=float_values)
def test_property_11_signal_emission_float(value: float):
    """
    Feature: infrastructure-improvements, Property 11: Config Change Signal Emission (float)
    
    For any configuration value change via ConfigManager.set(), the config_changed 
    signal should be emitted with the correct key and new value.
    
    **Validates: Requirements 3.5**
    """
    storage = MockStorage()
    config_manager = ConfigManager(storage)
    
    # Track signal emissions
    received_signals = []
    
    def on_config_changed(key: str, new_value: Any):
        received_signals.append((key, new_value))
    
    config_manager.config_changed.connect(on_config_changed)
    
    key = ConfigKey.API_TIMEOUT
    config_manager.set(key, value)
    
    # Verify signal was emitted with correct parameters
    assert len(received_signals) == 1, f"Expected 1 signal, got {len(received_signals)}"
    emitted_key, emitted_value = received_signals[0]
    assert emitted_key == key, f"Signal key mismatch: expected {key}, got {emitted_key}"
    assert abs(emitted_value - value) < 0.001, f"Signal value mismatch: expected {value}, got {emitted_value}"


@settings(max_examples=100)
@given(times=time_strings)
def test_property_11_signal_emission_list(times: List[str]):
    """
    Feature: infrastructure-improvements, Property 11: Config Change Signal Emission (list)
    
    For any configuration value change via ConfigManager.set(), the config_changed 
    signal should be emitted with the correct key and new value.
    
    **Validates: Requirements 3.5**
    """
    storage = MockStorage()
    config_manager = ConfigManager(storage)
    
    # Track signal emissions
    received_signals = []
    
    def on_config_changed(key: str, new_value: Any):
        received_signals.append((key, new_value))
    
    config_manager.config_changed.connect(on_config_changed)
    
    key = ConfigKey.EMAIL_SEND_TIMES
    config_manager.set(key, times)
    
    # Verify signal was emitted with correct parameters
    assert len(received_signals) == 1, f"Expected 1 signal, got {len(received_signals)}"
    emitted_key, emitted_value = received_signals[0]
    assert emitted_key == key, f"Signal key mismatch: expected {key}, got {emitted_key}"
    assert emitted_value == times, f"Signal value mismatch: expected {times}, got {emitted_value}"
