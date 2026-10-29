"""分析 (analyze) CLI エントリーポイントモジュール (python -m c2m_export.analyze)."""

import json
import logging
import sys
from typing import Dict

from c2m_export.analysis.api import run_analysis
from c2m_export.analysis.params import AnalysisParams
from c2m_export.analysis.response import (
    CODE_API_ERROR,
    CODE_AUTH_FAILED,
    CODE_INTERNAL_ERROR,
    CODE_INVALID_PARAM,
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
    CODE_INTERNAL_ERROR: 10,
}


def main() -> None:
    """CLI メイン関数."""
    # ログ設定: 人間向けの進捗・警告・エラーログをすべて stderr へ出力する
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

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
    )

    # run_analysis 実行
    response = run_analysis(params, config)

    # 出力文字列のサニタイズ（全出力に対して1回のみ適用）
    json_out = json.dumps(response.to_dict(), ensure_ascii=False, indent=2)
    sanitized_json = sanitize_text(json_out, secrets=[config.token])

    sys.stdout.write(sanitized_json + "\n")

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
