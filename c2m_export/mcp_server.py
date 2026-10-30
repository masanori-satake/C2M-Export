"""
Confluence Workspace Analysis MCP サーバ

Model Context Protocol (MCP) に準拠し、Confluence ワークスペース分析機能を FastMCP ツールとして公開します。
"""

import json
import os
from typing import Any, Dict, List, Optional

from c2m_export.analysis.api import run_analysis
from c2m_export.analysis.params import AnalysisParams
from c2m_export.analysis.sanitize import sanitize_text
from c2m_export.config import AnalysisConfig


def create_mcp_server() -> Any:
    """FastMCP サーバインスタンスを生成して返す関数です。

    mcp パッケージは関数内で遅延 import するため、未導入環境でもモジュール読み込み自体は失敗しません。
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as err:
        raise ImportError(
            "MCP サーバの実行には 'mcp' パッケージが必要です。pip install -r requirements-mcp.txt を実行してください。"
        ) from err

    mcp = FastMCP("c2m-export-analysis")

    @mcp.tool()
    def analyze_confluence(
        base_url: str,
        space_keys: Optional[List[str]] = None,
        root_page_ids: Optional[List[str]] = None,
        usecases: Optional[List[str]] = None,
        mode: str = "summary",
        limit: int = 1000,
        stale_days: int = 365,
        stale_years: Optional[float] = None,
        min_body_bytes: int = 200,
        archive_extensions: Optional[List[str]] = None,
        analyze_restrictions: Optional[bool] = None,
        sort: Optional[str] = None,
        all_spaces: bool = False,
        cql: Optional[str] = None,
        deep: bool = False,
        collect_history: Optional[bool] = None,
        collect_labels: Optional[bool] = None,
        collect_comments: Optional[bool] = None,
        collect_watchers: Optional[bool] = None,
        collect_effective_restrictions: Optional[bool] = None,
        collect_extracted_text: Optional[bool] = None,
        collect_space_permissions: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Confluence ワークスペースの状況（移設リスク、古いページ、アクセス制限、圧縮ファイル、添付あり空ページ、マクロ統計）を分析します。レスポンスは schema_version 1.2 に準拠し、status に ok, partial, error を返します。

        引数:
            base_url: Confluence のベース URL (例: https://confluence.example.com)
            space_keys: 対象 Space キー一覧
            root_page_ids: 対象 ルートページ ID 一覧
            usecases: 実行する分析ユースケース (risk, stale, restricted, archives, empty_with_attachments, macros)
            mode: 出力モード (summary または detail)
            limit: detail モード時の上限取得件数
            stale_days: 古いページの判定基準日数
            stale_years: 古いページの判定基準年数 (--stale-days 優先)
            min_body_bytes: 添付あり空ページの判定基準バイト数
            archive_extensions: 圧縮ファイル拡張子一覧
            analyze_restrictions: アクセス制限情報の収集可否 (3値: True/False/None)
            sort: ソート順指定
            all_spaces: 参照可能な全 Space を起点として分析するかどうか
            cql: 起点検索用または課題抽出用の CQL 文字列
            deep: 詳細調査フェーズの情報を一括で有効化するかどうか
            collect_history: ページ更新履歴の個別収集を有効化するかどうか (3値: True/False/None)
            collect_labels: ラベル情報の個別収集を有効化するかどうか (3値: True/False/None)
            collect_comments: コメント情報の個別収集を有効化するかどうか (3値: True/False/None)
            collect_watchers: ウォッチャー情報の個別収集を有効化するかどうか (3値: True/False/None)
            collect_effective_restrictions: 実効アクセス制限の個別収集を有効化するかどうか (3値: True/False/None)
            collect_extracted_text: 抽出テキストの個別収集を有効化するかどうか (3値: True/False/None)
            collect_space_permissions: Space 権限情報の個別収集を有効化するかどうか (3値: True/False/None)
        """
        token = os.environ.get("C2M_CONFLUENCE_TOKEN") or os.environ.get("CONFLUENCE_TOKEN") or ""

        # パラメータ設定オブジェクト構築
        config = AnalysisConfig()
        config.base_url = base_url
        if token:
            config.token = token
        if space_keys is not None:
            config.space_keys = space_keys
        if root_page_ids is not None:
            config.root_page_ids = root_page_ids
        if analyze_restrictions is not None:
            config.analyze_restrictions = analyze_restrictions
        if all_spaces:
            config.all_spaces = all_spaces
        if cql is not None:
            config.cql = cql
        if deep:
            config.deep = deep
        if collect_history is not None:
            config.collect_history = collect_history
        if collect_labels is not None:
            config.collect_labels = collect_labels
        if collect_comments is not None:
            config.collect_comments = collect_comments
        if collect_watchers is not None:
            config.collect_watchers = collect_watchers
        if collect_effective_restrictions is not None:
            config.collect_effective_restrictions = collect_effective_restrictions
        if collect_extracted_text is not None:
            config.collect_extracted_text = collect_extracted_text
        if collect_space_permissions is not None:
            config.collect_space_permissions = collect_space_permissions

        effective_stale_days = stale_days
        if stale_years is not None and stale_days == 365:
            effective_stale_days = int(stale_years * 365)

        params_kwargs: Dict[str, Any] = {
            "mode": mode,
            "limit": limit,
            "stale_days": effective_stale_days,
            "min_body_bytes": min_body_bytes,
            "all_spaces": all_spaces,
            "cql": cql,
            "deep": deep,
            "collect_history": collect_history,
            "collect_labels": collect_labels,
            "collect_comments": collect_comments,
            "collect_watchers": collect_watchers,
            "collect_effective_restrictions": collect_effective_restrictions,
            "collect_extracted_text": collect_extracted_text,
            "collect_space_permissions": collect_space_permissions,
        }
        if usecases is not None:
            params_kwargs["usecases"] = usecases
        if archive_extensions is not None:
            params_kwargs["archive_extensions"] = set(archive_extensions)
        if analyze_restrictions is not None:
            params_kwargs["analyze_restrictions"] = analyze_restrictions
        if sort is not None:
            params_kwargs["sort"] = sort

        params = AnalysisParams(**params_kwargs)

        response = run_analysis(params=params, config=config)
        raw_dict = response.to_dict()
        sanitized_json = sanitize_text(json.dumps(raw_dict, ensure_ascii=False), secrets=[token])
        return json.loads(sanitized_json)

    return mcp


def main() -> None:
    """MCP サーバエントリーポイント (stdio トランスポート)"""
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
