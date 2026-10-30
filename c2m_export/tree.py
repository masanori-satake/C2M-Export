"""ページツリー表示（tree） CLI エントリーポイントモジュール (python -m c2m_export.tree)."""

import logging
import os
import sys
from pathlib import Path
from typing import Dict

import requests

from c2m_export.analysis.sanitize import sanitize_text
from c2m_export.config import TreeConfig
from c2m_export.confluence import ConfluenceClient
from c2m_export.page_tree import build_tree, render_tree
from c2m_export.page_tree.collector import collect_tree
from c2m_export.page_tree.models import TreeResult

# エラーコード定数
CODE_INVALID_PARAM = "INVALID_PARAM"
CODE_AUTH_FAILED = "AUTH_FAILED"
CODE_TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
CODE_API_ERROR = "API_ERROR"
CODE_INTERNAL_ERROR = "INTERNAL_ERROR"

# エラーコード → 終了コード マッピングテーブル
EXIT_CODES: Dict[str, int] = {
    CODE_INVALID_PARAM: 2,
    CODE_AUTH_FAILED: 3,
    CODE_TARGET_NOT_FOUND: 4,
    CODE_API_ERROR: 5,
    CODE_INTERNAL_ERROR: 10,
}


def _classify_error(e: Exception) -> str:
    """例外から対応するエラーコード文字列を特定する."""
    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        status = e.response.status_code
        if status in (401, 403):
            return CODE_AUTH_FAILED
        elif status == 404:
            return CODE_TARGET_NOT_FOUND
        elif status >= 500:
            return CODE_API_ERROR
    if isinstance(e, (ValueError, FileExistsError)):
        return CODE_INVALID_PARAM
    return CODE_INTERNAL_ERROR


def main() -> None:
    """CLI メイン関数."""
    # 人間向けの進捗・警告・エラーログをすべて stderr へ出力する
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    config = TreeConfig()
    fmt = "text"

    try:
        # 1. 設定の読み込みと検証
        config.load()
        fmt = config.format
        config.validate()

        # 2. 出力先の競合チェック（--output 指定時）
        if config.output:
            out_path = Path(config.output)
            if out_path.exists() and not config.overwrite:
                raise ValueError(
                    f"現象: 出力ファイル {config.output} が既に存在します。原因: --overwrite オプションが指定されていません。対処方法: --overwrite を指定するか、別の出力先を指定してください。"
                )

        # 3. Confluence クライアント初期化
        client = ConfluenceClient(
            base_url=config.base_url,  # type: ignore[arg-type]
            token=config.token,  # type: ignore[arg-type]
            proxy=config.proxy,
        )

        # 4. 階層および付帯情報の収集
        resolved_root_ids, children_map, annotations_map, page_titles_map, uncertainties = collect_tree(
            client=client,
            space_keys=config.space_keys,
            root_page_ids=config.root_page_ids,
            include=config.include,
            max_depth=config.max_depth,
        )

        if not resolved_root_ids:
            raise requests.exceptions.HTTPError(
                "現象: 起点ページまたは Space が見つかりませんでした。原因: 指定された --space-key または --root-page-id に該当するコンテンツが存在しないか権限がありません。対処方法: 指定内容およびアクセス権限を確認してください。",
                response=type("Response", (), {"status_code": 404})(),
            )

        # 5. ツリーの構築 (純粋ロジック)
        roots, total_pages = build_tree(
            root_ids=resolved_root_ids,
            children_map=children_map,
            annotations_map=annotations_map,
            page_titles_map=page_titles_map,
            max_depth=config.max_depth,
        )

        result = TreeResult(
            schema_version="1.0",
            status="ok",
            roots=roots,
            total_pages=total_pages,
            included_annotations=sorted(list(config.include)),
            uncertainties=uncertainties,
            scope={
                "space_keys": config.space_keys,
                "root_page_ids": config.root_page_ids,
                "resolved_root_count": len(resolved_root_ids),
            },
        )

        # 6. レンダリング
        output_content = render_tree(result, fmt=config.format, ascii=config.ascii)
        sanitized_content = sanitize_text(output_content, secrets=[config.token])

        # 7. 出力処理
        if config.output:
            os.makedirs(os.path.dirname(os.path.abspath(config.output)), exist_ok=True)
            with open(config.output, "w", encoding="utf-8") as f:
                f.write(sanitized_content + "\n")
            logging.info(f"ツリーを出力ファイル {config.output} に書き出しました。")
        else:
            sys.stdout.write(sanitized_content + "\n")

        sys.exit(0)

    except Exception as e:
        err_code = _classify_error(e)
        exit_code = EXIT_CODES.get(err_code, 10)
        msg = str(e)
        if "現象:" not in msg:
            msg = f"現象: 処理中にエラーが発生しました。原因: {e}。対処方法: 入力パラメーターおよびネットワーク状態を確認してください。"

        sanitized_msg = sanitize_text(msg, secrets=[config.token])

        if fmt == "json":
            err_result = TreeResult(
                schema_version="1.0",
                status="error",
                error={
                    "code": err_code,
                    "message": sanitized_msg,
                    "exit_code": exit_code,
                },
            )
            err_json = render_tree(err_result, fmt="json")
            sys.stdout.write(sanitize_text(err_json, secrets=[config.token]) + "\n")

        sys.stderr.write(f"エラー: {sanitized_msg}\n")
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
