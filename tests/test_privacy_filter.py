"""
Unit tests for core/privacy_filter.py
"""
import numpy as np
import pytest

from core.window_tracker import WindowInfo
from core.privacy_filter import PrivacyFilter


def test_privacy_filter_sensitive_app():
    """Test sensitive app detection by process name."""
    pf = PrivacyFilter(enabled=True)

    # Known password managers
    w1 = WindowInfo(app_name="bitwarden.exe", window_title="Vault", process_id=101)
    w2 = WindowInfo(app_name="KeePass.exe", window_title="Database.kdbx", process_id=102)
    w3 = WindowInfo(app_name="1Password.exe", window_title="Logins", process_id=103)

    assert pf.is_sensitive(w1) is True
    assert pf.is_sensitive(w2) is True
    assert pf.is_sensitive(w3) is True


def test_privacy_filter_sensitive_title():
    """Test sensitive title detection with keywords."""
    pf = PrivacyFilter(enabled=True)

    # Sensitive titles in normal apps (e.g. Chrome incognito or bank)
    w1 = WindowInfo(app_name="chrome.exe", window_title="New Incognito Tab - Google Chrome", process_id=201)
    w2 = WindowInfo(app_name="msedge.exe", window_title="InPrivate 浏览 - Microsoft Edge", process_id=202)
    w3 = WindowInfo(app_name="firefox.exe", window_title="招商银行 网上银行 登录", process_id=203)

    assert pf.is_sensitive(w1) is True
    assert pf.is_sensitive(w2) is True
    assert pf.is_sensitive(w3) is True


def test_privacy_filter_non_sensitive():
    """Test that standard work windows are not marked sensitive."""
    pf = PrivacyFilter(enabled=True)

    w1 = WindowInfo(app_name="code.exe", window_title="main.py - Dayflow - Visual Studio Code", process_id=301)
    w2 = WindowInfo(app_name="explorer.exe", window_title="Downloads", process_id=302)

    assert pf.is_sensitive(w1) is False
    assert pf.is_sensitive(w2) is False


def test_privacy_filter_disabled():
    """Test that when disabled, nothing is treated as sensitive."""
    pf = PrivacyFilter(enabled=False)

    w1 = WindowInfo(app_name="bitwarden.exe", window_title="Passwords", process_id=401)
    assert pf.is_sensitive(w1) is False


def test_sanitize_window_title():
    """Test title sanitization for sensitive windows."""
    pf = PrivacyFilter(enabled=True)

    sensitive_w = WindowInfo(app_name="chrome.exe", window_title="Secret Password Manager", process_id=501)
    normal_w = WindowInfo(app_name="code.exe", window_title="main.py - Dayflow", process_id=502)

    assert pf.sanitize_window_title(sensitive_w) == "[隐私保护内容]"
    assert pf.sanitize_window_title(normal_w) == "main.py - Dayflow"
    assert pf.sanitize_window_title(None) == ""


def test_mask_frame_blur():
    """Test frame blurring mask effect."""
    pf = PrivacyFilter(enabled=True, action="blur")

    frame = np.ones((480, 640, 3), dtype=np.uint8) * 200
    masked = pf.mask_frame(frame)

    assert masked is not None
    assert masked.shape == frame.shape
    # Masked frame should not be identical to the plain original due to banner and blurring
    assert not np.array_equal(frame, masked)


def test_mask_frame_blackout():
    """Test blackout frame masking."""
    pf = PrivacyFilter(enabled=True, action="blackout")

    frame = np.ones((480, 640, 3), dtype=np.uint8) * 255
    masked = pf.mask_frame(frame, action="blackout")

    assert masked is not None
    assert masked.shape == frame.shape
    # Corner pixels outside banner should be black (0)
    assert np.all(masked[0, 0] == [0, 0, 0])
