"""ProgressHeartbeat（時間ベース進捗）の単体テスト."""

import logging
import time
from typing import Callable, List

import pytest

from c2m_export.analysis.progress import ProgressHeartbeat


def _wait_for(predicate: Callable[[], bool], timeout: float = 2.0, interval: float = 0.01) -> bool:
    """条件が成立するまでタイムアウト付きでポーリング待機する（固定長スリープで待たない）."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _heartbeat_messages(caplog, logger_name: str) -> List[str]:
    return [r.getMessage() for r in caplog.records if r.name == logger_name and "処理継続中" in r.getMessage()]


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
            assert _wait_for(lambda: len(_heartbeat_messages(caplog, "test.heartbeat")) >= 2)
        finally:
            heartbeat.stop()
    messages = _heartbeat_messages(caplog, "test.heartbeat")
    assert any("フェーズ=ページ収集" in m for m in messages)
    assert any("収集済み=42件" in m for m in messages)


def test_heartbeat_stops_after_context_exit(caplog):
    """コンテキスト終了後はハートビートが止まり、追加のログが出ない."""
    test_logger = logging.getLogger("test.heartbeat.stop")
    with caplog.at_level(logging.INFO, logger="test.heartbeat.stop"):
        with ProgressHeartbeat(target_logger=test_logger, interval_seconds=0.05, phase="準備"):
            assert _wait_for(lambda: len(_heartbeat_messages(caplog, "test.heartbeat.stop")) >= 1)
        count_after_exit = len(_heartbeat_messages(caplog, "test.heartbeat.stop"))
        # 停止後に新規ログが出ないことの確認（不在の確認には短い観察時間が必要）
        time.sleep(0.15)
        count_later = len(_heartbeat_messages(caplog, "test.heartbeat.stop"))
    assert count_after_exit >= 1
    assert count_later == count_after_exit


def test_heartbeat_phase_can_be_updated(caplog):
    """set_phase でフェーズ名が切り替わり、以降のログに反映される."""
    test_logger = logging.getLogger("test.heartbeat.phase")
    heartbeat = ProgressHeartbeat(target_logger=test_logger, interval_seconds=0.05, phase="Space 一覧取得")
    with caplog.at_level(logging.INFO, logger="test.heartbeat.phase"):
        heartbeat.start()
        try:
            # 旧フェーズのログが出たことを確認してからフェーズを切り替える
            assert _wait_for(
                lambda: any("フェーズ=Space 一覧取得" in m for m in _heartbeat_messages(caplog, "test.heartbeat.phase"))
            )
            heartbeat.set_phase("ページ収集")
            assert _wait_for(
                lambda: any("フェーズ=ページ収集" in m for m in _heartbeat_messages(caplog, "test.heartbeat.phase"))
            )
        finally:
            heartbeat.stop()
    messages = _heartbeat_messages(caplog, "test.heartbeat.phase")
    assert any("フェーズ=Space 一覧取得" in m for m in messages)
    assert any("フェーズ=ページ収集" in m for m in messages)
