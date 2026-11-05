#!/usr/bin/env python3
"""
Confluence Workspace Analysis Skill 補助実行スクリプト

C2M-Export の分析 CLI (c2m_export.analyze) をサブプロセスとして起動します。
トークンは環境変数 (C2M_CONFLUENCE_TOKEN または CONFLUENCE_TOKEN) から自動参照されます。

スキル経由の実行では、無応答のまま走り続けることを防ぐため、子プロセスを
無バッファモード (-u) で起動し、実行時間上限がどこからも指定されていない
場合に限り、既定の上限 (300 秒) を CLI 引数として補います。
上限の指定として扱うもの（いずれか1つでもあれば既定値は補いません）:
- CLI の `--timeout-seconds`（argparse の省略形 `--timeout` など一意な前方一致も含む）
- 設定ファイル（`--config` または既定の c2m_config.yaml）の `analysis.timeout_seconds`
上限到達時は収集済みデータで partial 結果が出力され、`--resume` で再開できます。
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

DEFAULT_TIMEOUT_SECONDS = 300
_TIMEOUT_OPTION = "--timeout-seconds"
# analyze の argparse で --timeout-seconds と前方一致が重なる唯一の別オプション
_CONFLICTING_OPTION = "--token"


def _has_explicit_timeout(argv: List[str]) -> bool:
    """CLI 引数に実行時間上限の明示指定があるかを返す.

    argparse (allow_abbrev が既定で有効) と同じ解決規則に合わせ、
    `--timeout-seconds` の一意な前方一致（例: `--timeout`）も明示指定として扱う。
    `--token` とも前方一致する曖昧な短い形（`--t` / `--to`）は明示指定とみなさない
    （その場合は CLI 側の argparse が曖昧エラーにする）。
    """
    for arg in argv:
        token = arg.split("=", 1)[0]
        if token == _TIMEOUT_OPTION:
            return True
        if token.startswith("--") and _TIMEOUT_OPTION.startswith(token) and not _CONFLICTING_OPTION.startswith(token):
            return True
    return False


def _find_repo_root() -> Optional[Path]:
    """上位ディレクトリを辿り c2m_export パッケージを含むルートを返す。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "c2m_export" / "__init__.py").exists():
            return parent
    return None


def _resolve_config_path(argv: List[str]) -> Path:
    """設定ファイルのパスを、c2m_export.config と同じ規則（--config の事前解決）で求める."""
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", type=str, default=None)
    pre_args, _ = pre_parser.parse_known_args(argv)
    if pre_args.config:
        return Path(pre_args.config)
    repo_root = _find_repo_root()
    if repo_root is not None:
        return repo_root / "c2m_config.yaml"
    return Path("c2m_config.yaml")


def _config_timeout_is_set(argv: List[str]) -> bool:
    """設定ファイルの analysis.timeout_seconds が明示されているかを返す."""
    config_path = _resolve_config_path(argv)
    if not config_path.exists():
        return False
    try:
        import yaml

        with open(config_path, encoding="utf-8") as f:
            file_config = yaml.safe_load(f)
    except Exception:
        return False
    if not isinstance(file_config, dict):
        return False
    analysis_sec = file_config.get("analysis")
    if not isinstance(analysis_sec, dict):
        return False
    return analysis_sec.get("timeout_seconds") is not None


def _is_estimate_run(argv: List[str]) -> bool:
    """--estimate（事前見積もりモード）指定の有無を返す."""
    return any(arg == "--estimate" or arg.startswith("--estimate=") for arg in argv)


_JOB_QUERY_OPTIONS = ("--job-status", "--job-result", "--job-cancel")


def _is_job_query(argv: List[str]) -> bool:
    """ジョブ操作コマンド（status / result / cancel）の指定の有無を返す."""
    return any(
        arg in _JOB_QUERY_OPTIONS or any(arg.startswith(opt + "=") for opt in _JOB_QUERY_OPTIONS) for arg in argv
    )


def build_command(argv: List[str]) -> List[str]:
    """子プロセスの起動コマンドを構築する（テスト可能）.

    - 常に無バッファ (-u) で起動し、進捗ログが即時に流れるようにする。
    - 上限が CLI でも設定ファイルでも指定されていない場合にだけ既定値を補う
      （CLI 引数は設定ファイルより優先されるため、無条件に追加すると
      設定ファイルの analysis.timeout_seconds を上書きしてしまう）。
    - --estimate 実行時とジョブ操作コマンド（--job-status 等）には既定値を補わない
      （いずれも短時間で終わる独立モード）。
    """
    args = list(argv)
    if (
        not _is_estimate_run(args)
        and not _is_job_query(args)
        and not _has_explicit_timeout(args)
        and not _config_timeout_is_set(args)
    ):
        args = args + ["--timeout-seconds", str(DEFAULT_TIMEOUT_SECONDS)]
    return [sys.executable, "-u", "-m", "c2m_export.analyze"] + args


def main() -> None:
    """CLI エントリーポイントへ引数を引き継いで実行します。"""
    result = subprocess.run(build_command(sys.argv[1:]))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
