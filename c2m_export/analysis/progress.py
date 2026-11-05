"""時間ベースの進捗ハートビート.

長時間の分析実行中に「処理が止まっているように見える」状態を避けるため、
一定間隔で生存ログを出力する小さなユーティリティ。件数ベースの進捗ログと
異なり、遅いページや前段フェーズ（Space 一覧取得など）でも無音にならない。
"""

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ProgressHeartbeat:
    """一定間隔で進捗ログを出すバックグラウンドスレッドの管理クラス.

    Args:
        target_logger: ログ出力先ロガー。省略時は本モジュールのロガー。
        interval_seconds: ハートビートの出力間隔（秒）。既定 5 秒。
        phase: 現在のフェーズ名。`set_phase` で随時更新できる。
        on_tick: 各ティックで (フェーズ, 経過秒数, 収集済み件数) を受け取る任意のコールバック。
            非同期ジョブの進捗ファイル書き込みなどに使う。例外は握りつぶす。
    """

    def __init__(
        self,
        target_logger: Optional[logging.Logger] = None,
        interval_seconds: float = 5.0,
        phase: str = "開始",
        on_tick: Optional[Callable[[str, float, Optional[int]], None]] = None,
    ):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds は 0 より大きい値でなければなりません")
        self._logger = target_logger or logger
        self._interval = float(interval_seconds)
        self._phase = phase
        self._on_tick = on_tick
        self._counter: Optional[Callable[[], int]] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._started_at: float = 0.0

    @property
    def phase(self) -> str:
        """現在のフェーズ名を返す."""
        return self._phase

    def set_phase(self, phase: str) -> None:
        """現在のフェーズ名を更新する."""
        self._phase = phase

    def set_counter(self, counter: Optional[Callable[[], int]]) -> None:
        """処理済み件数を返すコールバックを設定する（ハートビートに件数を併記する）."""
        self._counter = counter

    def start(self) -> None:
        """ハートビートスレッドを開始する（二重開始は無視する）."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="c2m-progress-heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """ハートビートスレッドを停止する."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1.0)
            self._thread = None

    def __enter__(self) -> "ProgressHeartbeat":
        """コンテキスト開始時にハートビートを開始する."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """コンテキスト終了時にハートビートを停止する."""
        self.stop()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval):
            elapsed = time.monotonic() - self._started_at
            message = f"処理継続中: フェーズ={self._phase}, 経過={elapsed:.0f}秒"
            count: Optional[int] = None
            if self._counter is not None:
                try:
                    count = self._counter()
                    message += f", 収集済み={count}件"
                except Exception:
                    count = None
            self._logger.info(message)
            if self._on_tick is not None:
                try:
                    self._on_tick(self._phase, elapsed, count)
                except Exception:
                    pass
