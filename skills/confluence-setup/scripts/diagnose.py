#!/usr/bin/env python3
"""Confluence Setup Support Skill 切り分け（診断）スクリプト.

C2M-Export のスキル／CLI が「使える状態」になるまでのセットアップ要因を、
上流（環境）から下流（API 応答）へ順に検査し、どこで詰まっているかを素早く特定する。

検査項目（上流→下流）:
  1. Python バージョン
  2. 必須依存ライブラリ (requests / bs4 / yaml)
  3. 認証トークン環境変数 (C2M_CONFLUENCE_TOKEN / CONFLUENCE_TOKEN) の有無
  4. 設定ファイル (c2m_config.yaml) の読み込みと必須項目
  5. プロキシ設定の最終解決値（設定ファイル vs 環境変数の優先）
  6. Confluence への素の疎通（/rest/api/space を 1 件取得）
  7. 指定スペースキーの解決（パス直埋め経路。記号を含むキーのエスケープ検証を含む）

秘匿情報は値を出力せず、有無・長さ・ステータスのみ表示する。
終了コード: 全項目 OK なら 0、1 つでも致命的な失敗があれば 1。

使い方:
  python skills/confluence-setup/scripts/diagnose.py
  python skills/confluence-setup/scripts/diagnose.py --space-key "~user@example.com" "DEV"
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote


# c2m_export パッケージを含むリポジトリルートを import パスへ追加する。
# このスクリプトは正本 (skills/) と複製先 (.kiro/skills/, .github/skills/) の
# いずれからも実行されうるため、固定の階層数ではなく、スクリプト位置から
# 上方向へ c2m_export ディレクトリを探索してルートを特定する。
# これにより PYTHONPATH 未設定でも、どこから起動しても c2m_export を解決できる。
def _find_repo_root() -> Path | None:
    """上位ディレクトリを辿り c2m_export パッケージを含むルートを返す。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "c2m_export" / "__init__.py").exists():
            return parent
    return None


_REPO_ROOT = _find_repo_root()
if _REPO_ROOT and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 診断の過程で致命的失敗があったかどうか
_HAS_FATAL = False


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    global _HAS_FATAL
    _HAS_FATAL = True
    print(f"  [NG]   {msg}")


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def check_python() -> None:
    _section("1. Python バージョン")
    major, minor = sys.version_info[:2]
    if (major, minor) >= (3, 11):
        _ok(f"Python {major}.{minor} (>= 3.11)")
    else:
        _fail(f"Python {major}.{minor} は要件 3.11 未満です。3.11 以上を導入してください。")


def check_deps() -> None:
    _section("2. 必須依存ライブラリ")
    for name, mod in (("requests", "requests"), ("beautifulsoup4", "bs4"), ("PyYAML", "yaml")):
        try:
            __import__(mod)
            _ok(f"{name} 導入済み")
        except ImportError:
            _fail(f"{name} が未導入です。`pip install -r requirements.txt` を実行してください。")


def check_token() -> str | None:
    _section("3. 認証トークン環境変数")
    token = os.environ.get("C2M_CONFLUENCE_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
    if os.environ.get("C2M_CONFLUENCE_TOKEN"):
        _ok(f"C2M_CONFLUENCE_TOKEN 設定あり (長さ {len(os.environ['C2M_CONFLUENCE_TOKEN'])})")
    elif os.environ.get("CONFLUENCE_TOKEN"):
        _warn(
            f"CONFLUENCE_TOKEN 設定あり (長さ {len(os.environ['CONFLUENCE_TOKEN'])})。推奨は C2M_CONFLUENCE_TOKEN です。"
        )
    else:
        _fail(
            "トークン環境変数が未設定です。ユーザー環境変数 C2M_CONFLUENCE_TOKEN に PAT を登録し、"
            "登録後は Kiro / ターミナルを再起動してください（既存プロセスには反映されません）。"
        )
    return token


def load_config():
    """AnalysisConfig を検証なしで読み込む。失敗時は None。"""
    _section("4. 設定ファイル読み込み (c2m_config.yaml)")
    try:
        from c2m_export.config import AnalysisConfig
    except Exception as e:  # noqa: BLE001
        _fail(f"c2m_export を import できません: {type(e).__name__}: {e}。リポジトリ直下で実行してください。")
        return None

    saved_argv = sys.argv
    try:
        sys.argv = [saved_argv[0]]  # CLI 引数解析が設定ファイル読込を阻害しないよう退避
        cfg = AnalysisConfig()
        cfg.load()
    except Exception as e:  # noqa: BLE001
        _fail(f"設定の読み込みに失敗しました: {type(e).__name__}: {e}")
        return None
    finally:
        sys.argv = saved_argv

    if cfg.base_url:
        _ok(f"base_url: {cfg.base_url}")
    else:
        _fail("base_url が未設定です。c2m_config.yaml に base_url を記載してください。")
    if cfg.space_keys:
        _ok(f"space_keys: {cfg.space_keys}")
    else:
        _warn("space_keys が未設定です（root_page_ids / cql / all_spaces で指定する運用なら問題ありません）。")
    _ok(f"token (設定反映): {'あり' if cfg.token else 'なし'}")
    return cfg


def check_proxy(cfg) -> None:
    _section("5. プロキシ設定の最終解決値")
    env_https = os.environ.get("HTTPS_PROXY")
    env_http = os.environ.get("HTTP_PROXY")
    if env_https or env_http:
        _warn(
            f"環境変数プロキシが設定されています (HTTPS_PROXY={env_https}, HTTP_PROXY={env_http})。"
            "C2M-Export はこれを設定ファイルの proxy より優先します。"
        )
    final = getattr(cfg, "proxy", None) if cfg else None
    if final:
        _ok(f"ツールへ渡る最終 proxy: {final}")
    else:
        _warn("proxy は未設定です。社内環境でプロキシ必須の場合は c2m_config.yaml に proxy を記載してください。")


def check_connectivity(cfg) -> None:
    _section("6. Confluence への素の疎通")
    if not cfg or not cfg.base_url or not cfg.token:
        _fail("base_url または token が揃っていないため疎通を検査できません。")
        return
    try:
        from c2m_export.confluence import ConfluenceClient
    except Exception as e:  # noqa: BLE001
        _fail(f"ConfluenceClient を import できません: {e}")
        return

    client = ConfluenceClient(cfg.base_url.rstrip("/"), cfg.token, proxy=cfg.proxy)
    t = time.time()
    try:
        spaces = client.list_spaces(limit=1)
        elapsed = time.time() - t
        _ok(
            f"/rest/api/space 応答あり ({elapsed:.1f}s, 取得 {len(spaces)} 件)。認証・エンドポイント・プロキシは正常です。"
        )
    except Exception as e:  # noqa: BLE001
        elapsed = time.time() - t
        _fail(
            f"疎通に失敗しました ({elapsed:.1f}s): {type(e).__name__}: {e}。"
            "長時間ハングする場合はプロキシ経路、401/403 は認証、404 は base_url を疑ってください。"
        )


def check_space_keys(cfg, override_keys: list[str] | None) -> None:
    _section("7. スペースキーの解決（記号キーのエスケープ検証）")
    if not cfg or not cfg.base_url or not cfg.token:
        _warn("base_url / token が揃っていないためスキップします。")
        return
    keys = override_keys if override_keys else list(getattr(cfg, "space_keys", []) or [])
    if not keys:
        _warn("検査対象のスペースキーがありません。")
        return

    from c2m_export.confluence import ConfluenceClient

    client = ConfluenceClient(cfg.base_url.rstrip("/"), cfg.token, proxy=cfg.proxy)
    for key in keys:
        has_symbol = any(c in key for c in "~@/ %?#")
        label = f"'{key}'" + ("（記号を含む）" if has_symbol else "")
        # (a) 現状コード経路: パス直埋め（get_space_root_pages と同じ組み立て）
        try:
            pages = client.get_space_root_pages(key, limit=1)
            _ok(f"{label} パス直埋め経路: 成功 (ルート {len(pages)} 件)")
            continue
        except Exception as e:  # noqa: BLE001
            _warn(f"{label} パス直埋め経路: 失敗 {type(e).__name__}: {e}")

        # (b) エスケープ版で再試行し、エスケープ不足が原因かを切り分け
        if has_symbol:
            try:
                r = client._request(
                    "GET",
                    f"/rest/api/space/{quote(key, safe='')}/content/page",
                    params={"depth": "root", "limit": 1},
                )
                n = len(r.get("results", [])) if isinstance(r, dict) else 0
                _fail(
                    f"{label} エスケープ版なら成功 (ルート {n} 件)。"
                    "→ 原因は C2M-Export がスペースキーを URL エスケープしていないことです（要修正）。"
                )
            except Exception as e:  # noqa: BLE001
                _warn(f"{label} エスケープ版も失敗 {type(e).__name__}: {e}（キー自体の権限・存在を確認してください）。")
        else:
            _warn(f"{label} は記号を含まないため、エスケープ以外の原因（権限・存在）を疑ってください。")


def main() -> int:
    parser = argparse.ArgumentParser(description="C2M-Export セットアップ切り分け診断")
    parser.add_argument("--space-key", nargs="+", help="検査するスペースキー（省略時は設定ファイルの値）")
    parser.add_argument("--skip-network", action="store_true", help="ネットワーク疎通検査をスキップ")
    args = parser.parse_args()

    print("C2M-Export セットアップ診断を開始します。")
    check_python()
    check_deps()
    check_token()
    cfg = load_config()
    check_proxy(cfg)
    if not args.skip_network:
        check_connectivity(cfg)
        check_space_keys(cfg, args.space_key)
    else:
        _section("6-7. ネットワーク検査")
        print("  (--skip-network によりスキップ)")

    print("\n=== 診断結果 ===")
    if _HAS_FATAL:
        print("  致命的な問題が検出されました。上記 [NG] の対処方法に従ってください。")
        return 1
    print("  致命的な問題は検出されませんでした。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
