"""
Confluence Workspace Analysis MCP サーバ

Model Context Protocol (MCP) に準拠し、Confluence ワークスペース分析機能を FastMCP ツールとして公開します。
"""

from typing import Any, Dict, List, Optional

from c2m_export.analysis.api import run_analysis
from c2m_export.analysis.params import AnalysisParams
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
        mode: Optional[str] = None,
        limit: Optional[int] = None,
        stale_days: Optional[int] = None,
        stale_years: Optional[float] = None,
        min_body_bytes: Optional[int] = None,
        archive_extensions: Optional[List[str]] = None,
        analyze_restrictions: Optional[bool] = None,
        sort: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Confluence ワークスペースの状況（移設リスク、古いページ、アクセス制限、圧縮ファイル、添付あり空ページ、マクロ統計）を分析します。

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
        """
        # パラメータ設定オブジェクト構築
        config = AnalysisConfig()
        config.load_file_and_env()
        config.base_url = base_url.rstrip("/")
        config.space_keys = space_keys or []
        config.root_page_ids = root_page_ids or []
        if analyze_restrictions is not None:
            config.analyze_restrictions = analyze_restrictions

        if stale_days is not None:
            effective_stale_days = stale_days
        elif stale_years is not None:
            effective_stale_days = int(stale_years * 365)
        else:
            effective_stale_days = config.stale_days

        params_kwargs: Dict[str, Any] = {
            "mode": mode if mode is not None else config.mode,
            "limit": limit if limit is not None else config.limit,
            "stale_days": effective_stale_days,
            "min_body_bytes": min_body_bytes if min_body_bytes is not None else config.min_body_bytes,
            "analyze_restrictions": config.analyze_restrictions,
        }
        effective_usecases = usecases if usecases is not None else config.usecases
        if effective_usecases is not None:
            params_kwargs["usecases"] = effective_usecases
        effective_archive_extensions = (
            set(archive_extensions) if archive_extensions is not None else config.archive_extensions
        )
        if effective_archive_extensions is not None:
            params_kwargs["archive_extensions"] = effective_archive_extensions
        if sort is not None:
            params_kwargs["sort"] = sort

        params = AnalysisParams(**params_kwargs)

        response = run_analysis(params=params, config=config)
        return response.to_dict()

    return mcp


def main() -> None:
    """MCP サーバエントリーポイント (stdio トランスポート)"""
    server = create_mcp_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
