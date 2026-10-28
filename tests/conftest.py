"""pytest 共通フィクスチャ.

プロキシ系の環境変数がホスト環境に設定されていると、
Config のプロキシ取り込み仕様によりテストの期待値（proxy=None 等）が
崩れるため、全テストで当該環境変数を無効化する。
"""

import pytest


@pytest.fixture(autouse=True)
def _clear_proxy_env(monkeypatch):
    """プロキシ関連の環境変数をテスト実行中は除去する。"""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)
