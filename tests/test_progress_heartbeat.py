"""ProgressHeartbeat（時間ベース進捗）の単体テスト."""

import logging
import time

import pytest

from c2m_export.analysis.progress import ProgressHeartbeat


def test_heartbeat_rejects_non_positive_interval():
    """間隔が 0 以下なら ValueError を送出する."""
    with pytest.raises(ValueError):
        ProgressHeartbeat(interval_seconds=0)


def test_heartbeat_emits_periodically_with_phase_and_counter(caplog):
    """ハートビートがフェーズ・経過・収集済み件数を含むログを周期的に出す."""
    test_logger = logging.getLogger("test.heartbeat")
    heartbeat = ProgressHeartbeat(target_logger=test_logger, interval_seconds=0.05, phase="ページ収集")
    heartbeat.set_counter(lambda: 42)
    with caplog.at_level(logging.INFO, logger="test.heartbeat"):
        heartbeat.start()
        try:
            time.sleep(0.22)
        finally:
            heartbeat.stop()
    messages = [r.getMessage() for r in caplog.records if "処理継続中" in r.getMessage()]
    assert len(messages) >= 2
    assert any("フェーズ=ページ収集" in m for m in messages)
    assert any("収集済み=42件" in m for m in messages)


def test_heartbeat_stops_after_context_exit(caplog):
    """コンテキスト終了後はハートビートが止まり、追加のログが出ない."""
    test_logger = logging.getLogger("test.heartbeat.stop")
    with caplog.at_level(logging.INFO, logger="test.heartbeat.stop"):
        with ProgressHeartbeat(target_logger=test_logger, interval_seconds=0.05, phase="準備"):
            time.sleep(0.12)
        count_after_exit = len([r for r in caplog.records if "処理継続中" in r.getMessage()])
        time.sleep(0.15)
        count_later = len([r for r in caplog.records if "処理継続中" in r.getMessage()])
    assert count_after_exit >= 1
    assert count_later == count_after_exit


def test_heartbeat_phase_can_be_updated(caplog):
    """set_phase でフェーズ名が切り替わり、以降のログに反映される."""
    test_logger = logging.getLogger("test.heartbeat.phase")
    heartbeat = ProgressHeartbeat(target_logger=test_logger, interval_seconds=0.05, phase="Space 一覧取得")
    with caplog.at_level(logging.INFO, logger="test.heartbeat.phase"):
        heartbeat.start()
        try:
            time.sleep(0.08)
            heartbeat.set_phase("ページ収集")
            time.sleep(0.12)
        finally:
            heartbeat.stop()
    messages = [r.getMessage() for r in caplog.records if "処理継続中" in r.getMessage()]
    assert any("フェーズ=Space 一覧取得" in m for m in messages)
    assert any("フェーズ=ページ収集" in m for m in messages)
