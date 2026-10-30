"""分析 (analyze) CLI エントリーポイントモジュール (python -m c2m_export.analyze)."""

import json
import logging
import signal
import sys
import threading
from typing import Dict

from c2m_export.analysis.api import run_analysis
from c2m_export.analysis.params import AnalysisParams
from c2m_export.analysis.response import (
    CODE_API_ERROR,
    CODE_AUTH_FAILED,
    CODE_INTERNAL_ERROR,
    CODE_INVALID_PARAM,
    CODE_PARTIAL,
    CODE_TARGET_NOT_FOUND,
    AnalysisResponse,
    ErrorObject,
)
from c2m_export.analysis.sanitize import sanitize_text
from c2m_export.config import AnalysisConfig

# エラーコード → 終了コード マッピングテーブル
EXIT_CODES: Dict[str, int] = {
    CODE_INVALID_PARAM: 2,
    CODE_AUTH_FAILED: 3,
    CODE_TARGET_NOT_FOUND: 4,
    CODE_API_ERROR: 5,
    CODE_PARTIAL: 6,
    CODE_INTERNAL_ERROR: 10,
}

_interrupted_event = threading.Event()


def _signal_handler(signum: int, frame: object) -> None:
    """SIGINT / SIGTERM シグナル受信時に協調的中断フラグを立てるハンドラ."""
    _interrupted_event.set()


def main() -> None:
    """CLI メイン関数."""
    # ログ設定: 人間向けの進捗・警告・エラーログをすべて stderr へ出力する
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    _interrupted_event.clear()

    orig_sigint = None
    orig_sigterm = None
    try:
        try:
            orig_sigint = signal.signal(signal.SIGINT, _signal_handler)
        except (ValueError, OSError):
            pass

        if hasattr(signal, "SIGTERM"):
            try:
                orig_sigterm = signal.signal(signal.SIGTERM, _signal_handler)
            except (ValueError, OSError):
                pass

        config = AnalysisConfig()

        try:
            # 設定の読込 (CLI引数, 環境変数, YAML)
            config.load()
            config.validate()
        except Exception as e:
            # 設定ロード・検証エラー時
            msg = str(e)
            err_msg = (
                msg
                if "現象:" in msg
                else f"現象: 設定エラー。原因: {msg}。対処方法: 引数または設定ファイルを確認してください。"
            )
            err_resp = AnalysisResponse(
                schema_version="1.2",
                status="error",
                error=ErrorObject(code=CODE_INVALID_PARAM, message=err_msg),
            )
            json_out = json.dumps(err_resp.to_dict(), ensure_ascii=False, indent=2)
            sanitized_json = sanitize_text(json_out, secrets=[config.token])
            sys.stdout.write(sanitized_json + "\n")

            stderr_msg = sanitize_text(f"エラー: {msg}", secrets=[config.token])
            sys.stderr.write(stderr_msg + "\n")
            sys.exit(EXIT_CODES[CODE_INVALID_PARAM])

        # AnalysisParams 構築
        params = AnalysisParams(
            usecases=config.usecases if config.usecases else AnalysisParams().usecases,
            mode=config.mode,
            limit=config.limit,
            stale_days=config.stale_days,
            min_body_bytes=config.min_body_bytes,
            archive_extensions=config.archive_extensions
            if config.archive_extensions is not None
            else AnalysisParams().archive_extensions,
            analyze_restrictions=config.analyze_restrictions,
            all_spaces=config.all_spaces,
            cql=config.cql,
            deep=config.deep,
            collect_history=config.collect_history,
            collect_labels=config.collect_labels,
            collect_comments=config.collect_comments,
            collect_watchers=config.collect_watchers,
            collect_effective_restrictions=config.collect_effective_restrictions,
            collect_extracted_text=config.collect_extracted_text,
            collect_space_permissions=config.collect_space_permissions,
            checkpoint_enabled=config.checkpoint_enabled,
            resume=config.resume,
            checkpoint_interval=config.checkpoint_interval,
            checkpoint_dir=config.checkpoint_dir,
        )

        # run_analysis 実行
        response = run_analysis(params, config, interrupt_checker=_interrupted_event.is_set)

        # 出力文字列のサニタイズ（全出力に対して1回のみ適用）
        json_out = json.dumps(response.to_dict(), ensure_ascii=False, indent=2)
        sanitized_json = sanitize_text(json_out, secrets=[config.token])

        sys.stdout.write(sanitized_json + "\n")

        if response.status == "partial":
            if config.checkpoint_enabled:
                partial_msg = "部分成功結果 (partial) を出力しました。--resume オプションを指定することで未収集ページから再開できます。"
            else:
                partial_msg = "部分成功結果 (partial) を出力しました。--no-checkpoint が指定されているため、チェックポイントからの再開はできません。"
            stderr_msg = sanitize_text(partial_msg, secrets=[config.token])
            sys.stderr.write(stderr_msg + "\n")
            sys.exit(EXIT_CODES.get(CODE_PARTIAL, 6))
    finally:
        if orig_sigint is not None:
            try:
                signal.signal(signal.SIGINT, orig_sigint)
            except (ValueError, OSError):
                pass
        if orig_sigterm is not None:
            try:
                signal.signal(signal.SIGTERM, orig_sigterm)
            except (ValueError, OSError):
                pass

    if response.status != "ok":
        err_code = response.error.code if response.error else CODE_INTERNAL_ERROR
        err_msg = response.error.message if response.error else "不明なエラーが発生しました"
        stderr_msg = sanitize_text(f"エラー: {err_msg}", secrets=[config.token])
        sys.stderr.write(stderr_msg + "\n")
        exit_code = EXIT_CODES.get(err_code, 1)
        sys.exit(exit_code)

    sys.exit(0)


if __name__ == "__main__":
    main()
