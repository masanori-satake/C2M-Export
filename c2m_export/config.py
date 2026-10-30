import argparse
import os
from pathlib import Path
from typing import List, Optional, Set

import yaml

from c2m_export.assessment.rules import (
    DEFAULT_ATTACHMENT_DIR_NAME,
    DEFAULT_BLOCKED_EXTENSIONS,
    DEFAULT_PATH_LENGTH_LIMIT,
    DEFAULT_SINGLE_FILE_MAX_MB,
)

# デフォルト設定ファイルの保存場所 (ツールと同じディレクトリ)
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "c2m_config.yaml"


class Config:
    """ツールの設定を管理するクラス.

    CLI引数、環境変数、設定ファイルの順で優先順位を制御し、
    企業環境（Proxy等）での実行に必要な設定を保持する。
    """

    def __init__(self):
        self.base_url: Optional[str] = None
        self.root_page_ids: List[str] = []
        self.output_dir: str = "."
        self.max_mb: float = 100.0
        self.stop_threshold_mb: float = 95.0
        self.proxy: Optional[str] = None
        self.token: Optional[str] = None
        self.zip_output: bool = False
        self.overwrite: bool = False

    def load(self):
        """設定を読み込む。優先順位は CLI > 環境変数 > 設定ファイル > デフォルト."""
        # 設定ファイルパスを特定するために一度パース
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
        pre_args, _ = pre_parser.parse_known_args()

        config_path = Path(pre_args.config)

        # 1. 設定ファイルからの読み込み（優先度：低）
        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self.base_url = file_config.get("base_url", self.base_url)
                        root_ids = file_config.get("root_page_ids")
                        if root_ids:
                            if isinstance(root_ids, list):
                                self.root_page_ids = [str(i) for i in root_ids]
                            else:
                                self.root_page_ids = [str(root_ids)]
                        self.output_dir = file_config.get("output_dir", self.output_dir)
                        self.max_mb = float(file_config.get("max_mb", self.max_mb))
                        self.stop_threshold_mb = float(file_config.get("stop_threshold_mb", self.stop_threshold_mb))
                        self.proxy = file_config.get("proxy", self.proxy)
                        self.token = file_config.get("token", self.token)
                        self.zip_output = file_config.get("zip_output", self.zip_output)
                        self.overwrite = file_config.get("overwrite", self.overwrite)
            except Exception as e:
                print(
                    f"設定ファイル {config_path} の読み込みに失敗しました（現象）。詳細: {e}（原因）。ファイル形式や権限を確認してください（対処方法）"
                )

        # 2. 環境変数からの読み込み（Proxyおよび認証トークン）
        env_token = os.environ.get("C2M_CONFLUENCE_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
        if env_token:
            self.token = env_token

        env_https_proxy = os.environ.get("HTTPS_PROXY")
        env_http_proxy = os.environ.get("HTTP_PROXY")
        if env_https_proxy:
            self.proxy = env_https_proxy
        elif env_http_proxy:
            self.proxy = env_http_proxy

        # 3. CLI引数からの読み込み（優先度：最高）
        parser = argparse.ArgumentParser(description="ConfluenceのページツリーをMarkdownとしてエクスポートするツール")
        parser.add_argument("--base-url", type=str, help="ConfluenceのベースURL (例: https://host/wiki)")
        parser.add_argument(
            "--root-page-id", type=str, nargs="+", help="エクスポートを開始するルートページのID（複数指定可能）"
        )
        parser.add_argument("--output-dir", type=str, help="エクスポートされたMarkdownファイルを保存するディレクトリ")
        parser.add_argument("--max-mb", type=float, help="出力ファイルの最大許容サイズ (MB) (既定: 100)")
        parser.add_argument(
            "--stop-threshold-mb", type=float, help="サイズがこの閾値 (MB) を超えた場合に処理を停止する (既定: 95)"
        )
        parser.add_argument("--proxy", type=str, help="HTTP/HTTPS プロキシURL")
        parser.add_argument("--config", type=str, help="設定ファイルのパス (既定: c2m_config.yaml)")
        parser.add_argument("--token", type=str, help="ConfluenceのBearerトークン")
        parser.add_argument("--zip", action="store_true", help="エクスポート結果をZip圧縮する")
        parser.add_argument("--overwrite", action="store_true", help="既存のファイルを上書きする")

        cli_args = parser.parse_args()

        if cli_args.base_url:
            self.base_url = cli_args.base_url
        if cli_args.root_page_id:
            self.root_page_ids = cli_args.root_page_id

        # 重複を除去
        if self.root_page_ids:
            seen = set()
            self.root_page_ids = [x for x in self.root_page_ids if not (x in seen or seen.add(x))]

        if cli_args.output_dir:
            self.output_dir = cli_args.output_dir
        if cli_args.max_mb is not None:
            self.max_mb = cli_args.max_mb
        if cli_args.stop_threshold_mb is not None:
            self.stop_threshold_mb = cli_args.stop_threshold_mb
        if cli_args.proxy:
            self.proxy = cli_args.proxy
        if cli_args.token:
            self.token = cli_args.token
        if cli_args.zip:
            self.zip_output = True
        if cli_args.overwrite:
            self.overwrite = True

    def validate(self):
        """必須設定の有無を確認し、URLの正規化を行う."""
        if not self.base_url:
            raise ValueError("base_url is required (use --base-url or config file)")
        if not self.root_page_ids:
            raise ValueError("At least one root_page_id is required (use --root-page-id or config file)")
        if not self.token:
            raise ValueError("token is required (use --token or config file)")

        # 後続のパス結合時に重複を防ぐための正規化
        self.base_url = self.base_url.rstrip("/")


class AnalysisConfig:
    """分析（analyze）モードの設定を管理するクラス.

    CLI引数、環境変数、設定ファイル (YAML) の順で優先順位を制御し、
    分析モード用の設定パラメーターを保持・検証する。
    """

    def __init__(self):
        self.base_url: Optional[str] = None
        self.root_page_ids: List[str] = []
        self.space_keys: List[str] = []
        self.output_dir: str = "."
        self.proxy: Optional[str] = None
        self.token: Optional[str] = None

        # 分析固有設定
        self.usecases: Optional[List[str]] = None
        self.mode: str = "summary"
        self.limit: int = 1000
        self.stale_days: int = 365
        self.min_body_bytes: int = 200
        self.archive_extensions: Optional[Set[str]] = None
        self.analyze_restrictions: Optional[bool] = None

        # 0008 拡張オプション
        self.all_spaces: bool = False
        self.cql: Optional[str] = None
        self.deep: bool = False
        self.collect_history: Optional[bool] = None
        self.collect_labels: Optional[bool] = None
        self.collect_comments: Optional[bool] = None
        self.collect_watchers: Optional[bool] = None
        self.collect_effective_restrictions: Optional[bool] = None
        self.collect_extracted_text: Optional[bool] = None
        self.collect_space_permissions: Optional[bool] = None

    def load(self):
        """設定を読み込む。優先順位は CLI > 環境変数 > 設定ファイル > デフォルト."""
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
        pre_args, _ = pre_parser.parse_known_args()

        config_path = Path(pre_args.config) if pre_args.config else DEFAULT_CONFIG_PATH

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self.base_url = file_config.get("base_url", self.base_url)
                        root_ids = file_config.get("root_page_ids")
                        if root_ids:
                            if isinstance(root_ids, list):
                                self.root_page_ids = [str(i) for i in root_ids]
                            else:
                                self.root_page_ids = [str(root_ids)]
                        s_keys = file_config.get("space_keys")
                        if s_keys:
                            if isinstance(s_keys, list):
                                self.space_keys = [str(k) for k in s_keys]
                            else:
                                self.space_keys = [str(s_keys)]

                        self.output_dir = file_config.get("output_dir", self.output_dir)
                        self.proxy = file_config.get("proxy", self.proxy)
                        self.token = file_config.get("token", self.token)

                        # analysis セクション
                        analysis_sec = file_config.get("analysis", {})
                        if isinstance(analysis_sec, dict):
                            u_cases = analysis_sec.get("usecases")
                            if u_cases and isinstance(u_cases, list):
                                self.usecases = [str(u) for u in u_cases]
                            self.mode = analysis_sec.get("mode", self.mode)
                            self.limit = analysis_sec.get("limit", self.limit)
                            self.stale_days = analysis_sec.get("stale_days", self.stale_days)
                            self.min_body_bytes = analysis_sec.get("min_body_bytes", self.min_body_bytes)
                            a_exts = analysis_sec.get("archive_extensions")
                            if a_exts and isinstance(a_exts, list):
                                self.archive_extensions = {str(e).lower().lstrip(".") for e in a_exts}
                            if "analyze_restrictions" in analysis_sec:
                                self.analyze_restrictions = bool(analysis_sec["analyze_restrictions"])
                            self.all_spaces = bool(analysis_sec.get("all_spaces", self.all_spaces))
                            self.cql = analysis_sec.get("cql", self.cql)
                            self.deep = bool(analysis_sec.get("deep", self.deep))
                            if "collect_history" in analysis_sec:
                                self.collect_history = bool(analysis_sec["collect_history"])
                            if "collect_labels" in analysis_sec:
                                self.collect_labels = bool(analysis_sec["collect_labels"])
                            if "collect_comments" in analysis_sec:
                                self.collect_comments = bool(analysis_sec["collect_comments"])
                            if "collect_watchers" in analysis_sec:
                                self.collect_watchers = bool(analysis_sec["collect_watchers"])
                            if "collect_effective_restrictions" in analysis_sec:
                                self.collect_effective_restrictions = bool(
                                    analysis_sec["collect_effective_restrictions"]
                                )
                            if "collect_extracted_text" in analysis_sec:
                                self.collect_extracted_text = bool(analysis_sec["collect_extracted_text"])
                            if "collect_space_permissions" in analysis_sec:
                                self.collect_space_permissions = bool(analysis_sec["collect_space_permissions"])
            except Exception as e:
                print(
                    f"設定ファイル {config_path} の読み込みに失敗しました（現象）。詳細: {e}（原因）。ファイル形式を確認してください（対処方法）"
                )

        env_token = os.environ.get("C2M_CONFLUENCE_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
        if env_token:
            self.token = env_token

        env_https_proxy = os.environ.get("HTTPS_PROXY")
        env_http_proxy = os.environ.get("HTTP_PROXY")
        if env_https_proxy:
            self.proxy = env_https_proxy
        elif env_http_proxy:
            self.proxy = env_http_proxy

        parser = argparse.ArgumentParser(description="Confluenceのワークスペース状況を分析するツール")
        parser.add_argument("--base-url", type=str, help="ConfluenceのベースURL (例: https://host/wiki)")
        parser.add_argument(
            "--root-page-id", type=str, nargs="+", help="分析を開始するルートページのID（複数指定可能）"
        )
        parser.add_argument("--space-key", type=str, nargs="+", help="分析を開始するSpaceキー（複数指定可能）")
        parser.add_argument("--proxy", type=str, help="HTTP/HTTPS プロキシURL")
        parser.add_argument("--config", type=str, help="設定ファイルのパス (既定: c2m_config.yaml)")
        parser.add_argument("--token", type=str, help="ConfluenceのBearerトークン")

        parser.add_argument("--usecase", type=str, nargs="+", help="分析ユースケース名（複数指定可能）")
        parser.add_argument("--mode", type=str, choices=["summary", "detail"], help="出力モード (summary | detail)")
        parser.add_argument("--limit", type=int, help="個別一覧取得の上限件数")
        parser.add_argument("--stale-days", type=int, help="長期未更新判定の経過日数")
        parser.add_argument("--stale-years", type=float, help="長期未更新判定の経過年数（×365日で日数換算）")
        parser.add_argument("--min-body-bytes", type=int, help="空/極小ページ判定のバイト数上限")
        parser.add_argument("--archive-ext", type=str, nargs="+", help="圧縮形式カテゴリとして扱う拡張子リスト")
        parser.add_argument("--restrictions", action="store_true", default=None, help="権限分析を有効化する")
        parser.add_argument("--no-restrictions", action="store_false", dest="restrictions", help="権限分析を無効化する")

        # 0008 新オプション
        parser.add_argument("--all-spaces", action="store_true", help="参照可能な全Spaceを起点として分析する")
        parser.add_argument("--cql", type=str, help="起点検索用または課題抽出用のCQL文字列")
        parser.add_argument("--deep", action="store_true", help="詳細調査フェーズの情報を一括で有効化する")

        parser.add_argument("--collect-history", action="store_true", default=None)
        parser.add_argument("--no-collect-history", action="store_false", dest="collect_history")
        parser.add_argument("--collect-labels", action="store_true", default=None)
        parser.add_argument("--no-collect-labels", action="store_false", dest="collect_labels")
        parser.add_argument("--collect-comments", action="store_true", default=None)
        parser.add_argument("--no-collect-comments", action="store_false", dest="collect_comments")
        parser.add_argument("--collect-watchers", action="store_true", default=None)
        parser.add_argument("--no-collect-watchers", action="store_false", dest="collect_watchers")
        parser.add_argument("--collect-effective-restrictions", action="store_true", default=None)
        parser.add_argument(
            "--no-collect-effective-restrictions", action="store_false", dest="collect_effective_restrictions"
        )
        parser.add_argument("--collect-extracted-text", action="store_true", default=None)
        parser.add_argument("--no-collect-extracted-text", action="store_false", dest="collect_extracted_text")
        parser.add_argument("--collect-space-permissions", action="store_true", default=None)
        parser.add_argument("--no-collect-space-permissions", action="store_false", dest="collect_space_permissions")

        try:
            cli_args = parser.parse_args()
        except SystemExit as e:
            if e.code == 0:
                raise e
            raise ValueError(
                "現象: 無効なコマンドライン引数が指定されました。原因: コマンドライン引数の解析に失敗しました。対処方法: 引数の指定内容および構文を確認してください。"
            ) from e

        if cli_args.base_url:
            self.base_url = cli_args.base_url
        if cli_args.root_page_id:
            self.root_page_ids = cli_args.root_page_id
        if cli_args.space_key:
            self.space_keys = cli_args.space_key

        if self.root_page_ids:
            seen = set()
            self.root_page_ids = [x for x in self.root_page_ids if not (x in seen or seen.add(x))]
        if self.space_keys:
            seen_s = set()
            self.space_keys = [x for x in self.space_keys if not (x in seen_s or seen_s.add(x))]

        if cli_args.proxy:
            self.proxy = cli_args.proxy
        if cli_args.token:
            self.token = cli_args.token

        if cli_args.usecase:
            self.usecases = cli_args.usecase
        if cli_args.mode:
            self.mode = cli_args.mode
        if cli_args.limit is not None:
            self.limit = cli_args.limit

        if cli_args.stale_days is not None:
            self.stale_days = cli_args.stale_days
        elif cli_args.stale_years is not None:
            self.stale_days = int(cli_args.stale_years * 365)

        if cli_args.min_body_bytes is not None:
            self.min_body_bytes = cli_args.min_body_bytes
        if cli_args.archive_ext:
            self.archive_extensions = {str(e).lower().lstrip(".") for e in cli_args.archive_ext}
        if cli_args.restrictions is not None:
            self.analyze_restrictions = cli_args.restrictions

        if cli_args.all_spaces:
            self.all_spaces = True
        if cli_args.cql:
            self.cql = cli_args.cql
        if cli_args.deep:
            self.deep = True

        if cli_args.collect_history is not None:
            self.collect_history = cli_args.collect_history
        if cli_args.collect_labels is not None:
            self.collect_labels = cli_args.collect_labels
        if cli_args.collect_comments is not None:
            self.collect_comments = cli_args.collect_comments
        if cli_args.collect_watchers is not None:
            self.collect_watchers = cli_args.collect_watchers
        if cli_args.collect_effective_restrictions is not None:
            self.collect_effective_restrictions = cli_args.collect_effective_restrictions
        if cli_args.collect_extracted_text is not None:
            self.collect_extracted_text = cli_args.collect_extracted_text
        if cli_args.collect_space_permissions is not None:
            self.collect_space_permissions = cli_args.collect_space_permissions

    def validate(self):
        """必須設定の有無を確認し、URLの正規化および矛盾チェックを行う."""
        if not self.base_url:
            raise ValueError(
                "現象: base_url が未指定です。原因: --base-url または設定ファイルに base_url が存在しません。対処方法: --base-url オプションまたは設定ファイルで base_url を指定してください。"
            )
        if not self.root_page_ids and not self.space_keys and not self.all_spaces and not self.cql:
            raise ValueError(
                "現象: ルート指定が存在しません。原因: root_page_id, space_key, all_spaces, cql のいずれも指定されていません。対処方法: --root-page-id, --space-key, --all-spaces, --cql のいずれかを指定してください。"
            )
        if self.cql is not None and not self.cql.strip():
            raise ValueError(
                "現象: cql パラメータが無効です。原因: --cql に空の文字列が指定されました。対処方法: 有効な CQL 文字列を指定してください。"
            )
        if not self.token:
            raise ValueError(
                "現象: token が未指定です。原因: 認証トークンが指定されていません。対処方法: C2M_CONFLUENCE_TOKEN 環境変数または --token オプションでトークンを指定してください。"
            )

        # 矛盾チェック (restricted ユースケースと --no-restrictions の競合)
        if self.usecases and "restricted" in self.usecases and self.analyze_restrictions is False:
            raise ValueError(
                "現象: restricted の分析を実行できません。原因: restricted ユースケースが要求されているにもかかわらず --no-restrictions が指定されています。対処方法: --no-restrictions を外すか --usecase から restricted を除外してください。"
            )

        self.base_url = self.base_url.rstrip("/")


class PermissionExportConfig:
    """権限エクスポート（permission_export）の設定を管理するクラス.

    CLI引数、環境変数、設定ファイル (YAML) の順で優先順位を制御する。
    """

    def __init__(self):
        self.base_url: Optional[str] = None
        self.root_page_ids: List[str] = []
        self.space_keys: List[str] = []
        self.output_dir: str = "."
        self.proxy: Optional[str] = None
        self.token: Optional[str] = None
        self.overwrite: bool = False

        # 権限エクスポート固有設定
        self.report_layout: str = "aggregate"  # "aggregate" | "per_page"
        self.report_formats: str = "md"  # "md" | "json" | "both"
        self.attachment_dir_name: str = DEFAULT_ATTACHMENT_DIR_NAME
        self.page_filename_mode: str = "title"  # "title" | "index"

    def load(self):
        """設定を読み込む。優先順位は CLI > 環境変数 > 設定ファイル > デフォルト."""
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
        pre_args, _ = pre_parser.parse_known_args()

        config_path = Path(pre_args.config) if pre_args.config else DEFAULT_CONFIG_PATH

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self.base_url = file_config.get("base_url", self.base_url)
                        root_ids = file_config.get("root_page_ids")
                        if root_ids:
                            if isinstance(root_ids, list):
                                self.root_page_ids = [str(i) for i in root_ids]
                            else:
                                self.root_page_ids = [str(root_ids)]
                        s_keys = file_config.get("space_keys")
                        if s_keys:
                            if isinstance(s_keys, list):
                                self.space_keys = [str(k) for k in s_keys]
                            else:
                                self.space_keys = [str(s_keys)]

                        self.output_dir = file_config.get("output_dir", self.output_dir)
                        self.proxy = file_config.get("proxy", self.proxy)
                        self.token = file_config.get("token", self.token)
                        self.overwrite = file_config.get("overwrite", self.overwrite)

                        # permission_export セクション
                        perm_sec = file_config.get("permission_export", {})
                        if isinstance(perm_sec, dict):
                            self.report_layout = perm_sec.get("report_layout", self.report_layout)
                            self.report_formats = perm_sec.get("report_formats", self.report_formats)
                            self.attachment_dir_name = perm_sec.get("attachment_dir_name", self.attachment_dir_name)
                            self.page_filename_mode = perm_sec.get("page_filename_mode", self.page_filename_mode)
            except Exception as e:
                print(
                    f"設定ファイル {config_path} の読み込みに失敗しました（現象）。詳細: {e}（原因）。ファイル形式を確認してください（対処方法）"
                )

        env_token = os.environ.get("C2M_CONFLUENCE_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
        if env_token:
            self.token = env_token

        env_https_proxy = os.environ.get("HTTPS_PROXY")
        env_http_proxy = os.environ.get("HTTP_PROXY")
        if env_https_proxy:
            self.proxy = env_https_proxy
        elif env_http_proxy:
            self.proxy = env_http_proxy

        parser = argparse.ArgumentParser(
            description="Confluenceのページアクセス権限（コンテンツ制限）を取得・出力するツール"
        )
        parser.add_argument("--base-url", type=str, help="ConfluenceのベースURL (例: https://host/wiki)")
        parser.add_argument(
            "--root-page-id", type=str, nargs="+", help="対象を開始するルートページのID（複数指定可能）"
        )
        parser.add_argument("--space-key", type=str, nargs="+", help="対象を開始するSpaceキー（複数指定可能）")
        parser.add_argument("--output-dir", type=str, help="権限レポートを保存するディレクトリ")
        parser.add_argument("--proxy", type=str, help="HTTP/HTTPS プロキシURL")
        parser.add_argument("--config", type=str, help="設定ファイルのパス (既定: c2m_config.yaml)")
        parser.add_argument("--token", type=str, help="ConfluenceのBearerトークン")
        parser.add_argument("--overwrite", action="store_true", help="既存のレポートを上書きする")

        parser.add_argument(
            "--report-layout",
            type=str,
            choices=["aggregate", "per_page"],
            help="レポート格納形態 (aggregate | per_page)",
        )
        parser.add_argument(
            "--report-format",
            type=str,
            choices=["md", "json", "both"],
            help="出力形式 (md | json | both)",
        )
        parser.add_argument("--attachment-dir", type=str, help="添付サブディレクトリ名 (既定: _attachments)")
        parser.add_argument(
            "--page-filename-mode",
            type=str,
            choices=["title", "index"],
            help="本文ファイル命名方式 (title | index)",
        )

        cli_args = parser.parse_args()

        if cli_args.base_url:
            self.base_url = cli_args.base_url
        if cli_args.root_page_id:
            self.root_page_ids = cli_args.root_page_id
        if cli_args.space_key:
            self.space_keys = cli_args.space_key

        if self.root_page_ids:
            seen = set()
            self.root_page_ids = [x for x in self.root_page_ids if not (x in seen or seen.add(x))]
        if self.space_keys:
            seen_s = set()
            self.space_keys = [x for x in self.space_keys if not (x in seen_s or seen_s.add(x))]

        if cli_args.output_dir:
            self.output_dir = cli_args.output_dir
        if cli_args.proxy:
            self.proxy = cli_args.proxy
        if cli_args.token:
            self.token = cli_args.token
        if cli_args.overwrite:
            self.overwrite = True

        if cli_args.report_layout:
            self.report_layout = cli_args.report_layout
        if cli_args.report_format:
            self.report_formats = cli_args.report_format
        if cli_args.attachment_dir:
            self.attachment_dir_name = cli_args.attachment_dir
        if cli_args.page_filename_mode:
            self.page_filename_mode = cli_args.page_filename_mode

    def validate(self):
        """必須設定の有無を確認し、URLの正規化を行う."""
        if not self.base_url:
            raise ValueError("base_url is required (use --base-url or config file)")
        if not self.root_page_ids and not self.space_keys:
            raise ValueError(
                "At least one root_page_id or space_key is required (use --root-page-id, --space-key, or config file)"
            )
        if not self.token:
            raise ValueError("token is required (use --token or config file)")

        if self.report_layout not in ["aggregate", "per_page"]:
            raise ValueError("report_layout must be 'aggregate' or 'per_page'")
        if self.report_formats not in ["md", "json", "both"]:
            raise ValueError("report_formats must be 'md', 'json', or 'both'")
        if self.page_filename_mode not in ["title", "index"]:
            raise ValueError("page_filename_mode must be 'title' or 'index'")

        self.base_url = self.base_url.rstrip("/")


class FsExportConfig:
    """ファイルシステムエクスポートモードの設定を管理するクラス.

    CLI引数、環境変数、設定ファイル (YAML) の順で優先順位を制御する。
    """

    def __init__(self):
        self.base_url: Optional[str] = None
        self.root_page_ids: List[str] = []
        self.space_keys: List[str] = []
        self.output_dir: str = "."
        self.proxy: Optional[str] = None
        self.token: Optional[str] = None
        self.overwrite: bool = False

        # ファイルシステムモード固有設定
        self.attachment_dir_name: str = DEFAULT_ATTACHMENT_DIR_NAME
        self.attachment_link_mode: str = "relative"  # "relative" | "original"
        self.page_filename_mode: str = "title"  # "title" | "index"
        self.single_file_max_mb: float = float(DEFAULT_SINGLE_FILE_MAX_MB)
        self.exclude_extensions: List[str] = []
        self.path_length_limit: int = DEFAULT_PATH_LENGTH_LIMIT
        self.frontmatter_fields: Optional[List[str]] = None

        # 0005 差分同期・レジューム設定
        self.sync: bool = False
        self.resume: bool = False
        self.full: bool = False
        self.deletion_policy: str = "quarantine"  # "quarantine" | "delete" | "report"
        self.quarantine_dir_name: str = "_c2m_quarantine"
        self.manifest_name: str = ".c2m_manifest.json"

    def load(self):
        """設定を読み込む。優先順位は CLI > 環境変数 > 設定ファイル > デフォルト."""
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
        pre_args, _ = pre_parser.parse_known_args()

        config_path = Path(pre_args.config) if pre_args.config else DEFAULT_CONFIG_PATH

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self.base_url = file_config.get("base_url", self.base_url)
                        root_ids = file_config.get("root_page_ids")
                        if root_ids:
                            if isinstance(root_ids, list):
                                self.root_page_ids = [str(i) for i in root_ids]
                            else:
                                self.root_page_ids = [str(root_ids)]
                        s_keys = file_config.get("space_keys")
                        if s_keys:
                            if isinstance(s_keys, list):
                                self.space_keys = [str(k) for k in s_keys]
                            else:
                                self.space_keys = [str(s_keys)]

                        self.output_dir = file_config.get("output_dir", self.output_dir)
                        self.proxy = file_config.get("proxy", self.proxy)
                        self.token = file_config.get("token", self.token)
                        self.overwrite = file_config.get("overwrite", self.overwrite)

                        # filesystem_export セクション
                        fs_sec = file_config.get("filesystem_export", {})
                        if isinstance(fs_sec, dict):
                            self.attachment_dir_name = fs_sec.get("attachment_dir_name", self.attachment_dir_name)
                            self.attachment_link_mode = fs_sec.get("attachment_link_mode", self.attachment_link_mode)
                            self.page_filename_mode = fs_sec.get("page_filename_mode", self.page_filename_mode)
                            if "single_file_max_mb" in fs_sec:
                                self.single_file_max_mb = float(fs_sec["single_file_max_mb"])
                            e_exts = fs_sec.get("exclude_extensions")
                            if e_exts and isinstance(e_exts, list):
                                self.exclude_extensions = [str(e) for e in e_exts]
                            if "path_length_limit" in fs_sec:
                                self.path_length_limit = int(fs_sec["path_length_limit"])
                            fm_fields = fs_sec.get("frontmatter_fields")
                            if fm_fields and isinstance(fm_fields, list):
                                self.frontmatter_fields = [str(f) for f in fm_fields]

                            self.sync = bool(fs_sec.get("sync", self.sync))
                            self.resume = bool(fs_sec.get("resume", self.resume))
                            self.full = bool(fs_sec.get("full", self.full))
                            self.deletion_policy = str(fs_sec.get("deletion_policy", self.deletion_policy))
                            self.quarantine_dir_name = str(fs_sec.get("quarantine_dir_name", self.quarantine_dir_name))
                            self.manifest_name = str(fs_sec.get("manifest_name", self.manifest_name))
            except Exception as e:
                print(
                    f"設定ファイル {config_path} の読み込みに失敗しました（現象）。詳細: {e}（原因）。ファイル形式を確認してください（対処方法）"
                )

        env_token = os.environ.get("C2M_CONFLUENCE_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
        if env_token:
            self.token = env_token

        env_https_proxy = os.environ.get("HTTPS_PROXY")
        env_http_proxy = os.environ.get("HTTP_PROXY")
        if env_https_proxy:
            self.proxy = env_https_proxy
        elif env_http_proxy:
            self.proxy = env_http_proxy

        parser = argparse.ArgumentParser(
            description="Confluenceページ階層をディレクトリ/ファイル階層として出力するツール"
        )
        parser.add_argument("--base-url", type=str, help="ConfluenceのベースURL (例: https://host/wiki)")
        parser.add_argument(
            "--root-page-id", type=str, nargs="+", help="エクスポートを開始するルートページのID（複数指定可能）"
        )
        parser.add_argument("--space-key", type=str, nargs="+", help="エクスポートを開始するSpaceキー（複数指定可能）")
        parser.add_argument("--output-dir", type=str, help="出力先ルートディレクトリ")
        parser.add_argument("--proxy", type=str, help="HTTP/HTTPS プロキシURL")
        parser.add_argument("--config", type=str, help="設定ファイルのパス (既定: c2m_config.yaml)")
        parser.add_argument("--token", type=str, help="ConfluenceのBearerトークン")
        parser.add_argument("--overwrite", action="store_true", help="既存の出力先を上書きする")

        parser.add_argument("--attachment-dir", type=str, help="添付サブディレクトリ名 (既定: _attachments)")
        parser.add_argument(
            "--attachment-link-mode",
            type=str,
            choices=["relative", "original"],
            help="本文中の添付参照のリンク先 (relative | original)",
        )
        parser.add_argument(
            "--page-filename-mode",
            type=str,
            choices=["title", "index"],
            help="本文ファイル命名方式 (title | index)",
        )
        parser.add_argument("--single-file-max-mb", type=float, help="単一ファイルサイズ上限 (MB)")
        parser.add_argument("--exclude-ext", type=str, nargs="+", help="除外する添付拡張子のリスト")
        parser.add_argument("--path-length-limit", type=int, help="パス長警告しきい値 (文字数)")

        # 0005 差分同期・レジューム CLI 引数
        parser.add_argument("--sync", action="store_true", help="差分同期を有効化する")
        parser.add_argument("--resume", action="store_true", help="中断からのレジューム再開を有効化する")
        parser.add_argument("--full", action="store_true", help="マニフェストを無視し全件フル再取得する")
        parser.add_argument(
            "--deletion-policy",
            type=str,
            choices=["quarantine", "delete", "report"],
            help="削除同期の方針 (quarantine | delete | report)",
        )
        parser.add_argument("--quarantine-dir", type=str, help="退避ディレクトリ名 (既定: _c2m_quarantine)")

        cli_args = parser.parse_args()

        if cli_args.base_url:
            self.base_url = cli_args.base_url
        if cli_args.root_page_id:
            self.root_page_ids = cli_args.root_page_id
        if cli_args.space_key:
            self.space_keys = cli_args.space_key

        if self.root_page_ids:
            seen = set()
            self.root_page_ids = [x for x in self.root_page_ids if not (x in seen or seen.add(x))]
        if self.space_keys:
            seen_s = set()
            self.space_keys = [x for x in self.space_keys if not (x in seen_s or seen_s.add(x))]

        if cli_args.output_dir:
            self.output_dir = cli_args.output_dir
        if cli_args.proxy:
            self.proxy = cli_args.proxy
        if cli_args.token:
            self.token = cli_args.token
        if cli_args.overwrite:
            self.overwrite = True

        if cli_args.attachment_dir:
            self.attachment_dir_name = cli_args.attachment_dir
        if cli_args.attachment_link_mode:
            self.attachment_link_mode = cli_args.attachment_link_mode
        if cli_args.page_filename_mode:
            self.page_filename_mode = cli_args.page_filename_mode
        if cli_args.single_file_max_mb is not None:
            self.single_file_max_mb = cli_args.single_file_max_mb
        if cli_args.exclude_ext:
            self.exclude_extensions = cli_args.exclude_ext
        if cli_args.path_length_limit is not None:
            self.path_length_limit = cli_args.path_length_limit

        if cli_args.sync:
            self.sync = True
        if cli_args.resume:
            self.resume = True
        if cli_args.full:
            self.full = True
        if cli_args.deletion_policy:
            self.deletion_policy = cli_args.deletion_policy
        if cli_args.quarantine_dir:
            self.quarantine_dir_name = cli_args.quarantine_dir

    def validate(self):
        """必須設定の有無を確認し、URLの正規化を行う."""
        if not self.base_url:
            raise ValueError("base_url is required (use --base-url or config file)")
        if not self.root_page_ids and not self.space_keys:
            raise ValueError(
                "At least one root_page_id or space_key is required (use --root-page-id, --space-key, or config file)"
            )
        if not self.token:
            raise ValueError("token is required (use --token or config file)")

        if self.attachment_link_mode not in ["relative", "original"]:
            raise ValueError("attachment_link_mode must be 'relative' or 'original'")
        if self.page_filename_mode not in ["title", "index"]:
            raise ValueError("page_filename_mode must be 'title' or 'index'")
        if self.deletion_policy not in ["quarantine", "delete", "report"]:
            raise ValueError("deletion_policy must be 'quarantine', 'delete', or 'report'")

        self.base_url = self.base_url.rstrip("/")


class TreeConfig:
    """ページツリー表示（tree）モードの設定を管理するクラス.

    CLI引数、環境変数、設定ファイル (YAML) の順で優先順位を制御し、
    ツリー可視化用の設定パラメーターを保持・検証する。
    """

    ALLOWED_FORMATS = {"text", "markdown", "json"}
    ALLOWED_ANNOTATIONS = {"restriction", "macros", "attachments", "last_modified"}

    def __init__(self):
        self.base_url: Optional[str] = None
        self.root_page_ids: List[str] = []
        self.space_keys: List[str] = []
        self.proxy: Optional[str] = None
        self.token: Optional[str] = None

        # ツリーモード固有設定
        self.format: str = "text"
        self.include: Set[str] = set()
        self.ascii: bool = False
        self.output: Optional[str] = None
        self.overwrite: bool = False
        self.max_depth: Optional[int] = None

    def load(self):
        """設定を読み込む。優先順位は CLI > 環境変数 > 設定ファイル > デフォルト."""
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
        pre_args, _ = pre_parser.parse_known_args()

        config_path = Path(pre_args.config) if pre_args.config else DEFAULT_CONFIG_PATH

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self.base_url = file_config.get("base_url", self.base_url)
                        root_ids = file_config.get("root_page_ids")
                        if root_ids:
                            if isinstance(root_ids, list):
                                self.root_page_ids = [str(i) for i in root_ids]
                            else:
                                self.root_page_ids = [str(root_ids)]
                        s_keys = file_config.get("space_keys")
                        if s_keys:
                            if isinstance(s_keys, list):
                                self.space_keys = [str(k) for k in s_keys]
                            else:
                                self.space_keys = [str(s_keys)]

                        self.proxy = file_config.get("proxy", self.proxy)
                        self.token = file_config.get("token", self.token)
                        self.overwrite = bool(file_config.get("overwrite", self.overwrite))

                        # tree セクション
                        tree_sec = file_config.get("tree", {})
                        if isinstance(tree_sec, dict):
                            if "format" in tree_sec:
                                self.format = str(tree_sec["format"])
                            if "include" in tree_sec:
                                inc = tree_sec["include"]
                                if isinstance(inc, list):
                                    self.include = {str(i) for i in inc}
                                elif isinstance(inc, str):
                                    self.include = {inc}
                            if "ascii" in tree_sec:
                                self.ascii = bool(tree_sec["ascii"])
                            if "output" in tree_sec:
                                self.output = str(tree_sec["output"]) if tree_sec["output"] else None
                            if "max_depth" in tree_sec and tree_sec["max_depth"] is not None:
                                self.max_depth = int(tree_sec["max_depth"])
            except Exception as e:
                print(
                    f"設定ファイル {config_path} の読み込みに失敗しました（現象）。詳細: {e}（原因）。ファイル形式を確認してください（対処方法）"
                )

        env_token = os.environ.get("C2M_CONFLUENCE_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
        if env_token:
            self.token = env_token

        env_https_proxy = os.environ.get("HTTPS_PROXY")
        env_http_proxy = os.environ.get("HTTP_PROXY")
        if env_https_proxy:
            self.proxy = env_https_proxy
        elif env_http_proxy:
            self.proxy = env_http_proxy

        parser = argparse.ArgumentParser(description="Confluenceのページ階層を樹形図として可視化・出力するツール")
        parser.add_argument("--base-url", type=str, help="ConfluenceのベースURL (例: https://host/wiki)")
        parser.add_argument("--root-page-id", type=str, nargs="+", help="起点とするルートページのID（複数指定可能）")
        parser.add_argument("--space-key", type=str, nargs="+", help="起点とするSpaceキー（複数指定可能）")
        parser.add_argument("--proxy", type=str, help="HTTP/HTTPS プロキシURL")
        parser.add_argument("--config", type=str, help="設定ファイルのパス (既定: c2m_config.yaml)")
        parser.add_argument("--token", type=str, help="ConfluenceのBearerトークン")

        parser.add_argument(
            "--format", type=str, choices=["text", "markdown", "json"], help="出力フォーマット (text | markdown | json)"
        )
        parser.add_argument(
            "--include",
            type=str,
            nargs="+",
            help="取得・表示する付帯情報 (restriction | macros | attachments | last_modified | all)",
        )
        parser.add_argument("--ascii", action="store_true", help="文字化け防止用 ASCII 互換マークを使用する")
        parser.add_argument("--output", type=str, help="出力先ファイルパス (省略時 stdout)")
        parser.add_argument("--overwrite", action="store_true", help="出力ファイルが存在する場合に上書き許可")
        parser.add_argument("--max-depth", type=int, help="探索する最大階層深さ (指定なし/0で無制限)")

        try:
            cli_args = parser.parse_args()
        except SystemExit as e:
            if e.code == 0:
                raise e
            raise ValueError(
                "現象: 無効なコマンドライン引数が指定されました。原因: コマンドライン引数の解析に失敗しました。対処方法: 引数の指定内容および構文を確認してください。"
            ) from e

        if cli_args.base_url:
            self.base_url = cli_args.base_url
        if cli_args.root_page_id:
            self.root_page_ids = cli_args.root_page_id
        if cli_args.space_key:
            self.space_keys = cli_args.space_key

        if self.root_page_ids:
            seen = set()
            self.root_page_ids = [x for x in self.root_page_ids if not (x in seen or seen.add(x))]
        if self.space_keys:
            seen_s = set()
            self.space_keys = [x for x in self.space_keys if not (x in seen_s or seen_s.add(x))]

        if cli_args.proxy:
            self.proxy = cli_args.proxy
        if cli_args.token:
            self.token = cli_args.token

        if cli_args.format:
            self.format = cli_args.format
        if cli_args.include:
            inc_items = set()
            for item in cli_args.include:
                if item == "all":
                    inc_items.update(self.ALLOWED_ANNOTATIONS)
                else:
                    inc_items.add(item)
            self.include = inc_items
        else:
            # CLI 引数が無くて YAML 等から all が入った場合の展開補助
            if "all" in self.include:
                self.include.remove("all")
                self.include.update(self.ALLOWED_ANNOTATIONS)

        if cli_args.ascii:
            self.ascii = True
        if cli_args.output:
            self.output = cli_args.output
        if cli_args.overwrite:
            self.overwrite = True
        if cli_args.max_depth is not None:
            self.max_depth = cli_args.max_depth

    def validate(self):
        """必須設定の有無を確認し、URLの正規化および値の妥当性チェックを行う."""
        if not self.base_url:
            raise ValueError(
                "現象: base_url が未指定です。原因: --base-url または設定ファイルに base_url が存在しません。対処方法: --base-url オプションまたは設定ファイルで base_url を指定してください。"
            )
        if not self.root_page_ids and not self.space_keys:
            raise ValueError(
                "現象: 起点（ルートページIDまたはSpaceキー）が指定されていません。原因: --root-page-id および --space-key のいずれも指定されていません。対処方法: --root-page-id または --space-key を指定してください。"
            )
        if not self.token:
            raise ValueError(
                "現象: token が未指定です。原因: 認証トークンが指定されていません。対処方法: C2M_CONFLUENCE_TOKEN 環境変数または --token オプションでトークンを指定してください。"
            )

        if self.format not in self.ALLOWED_FORMATS:
            raise ValueError(
                f"現象: 出力フォーマットが無効です。原因: '{self.format}' はサポートされていないフォーマットです。対処方法: text, markdown, json のいずれかを指定してください。"
            )

        invalid_includes = self.include - self.ALLOWED_ANNOTATIONS
        if invalid_includes:
            invalid_str = ", ".join(sorted(invalid_includes))
            raise ValueError(
                f"現象: 無効な付帯情報指定が含まれています。原因: '{invalid_str}' は対象外の指定です。対処方法: restriction, macros, attachments, last_modified, all のいずれかを指定してください。"
            )

        if self.max_depth is not None and self.max_depth <= 0:
            self.max_depth = None

        self.base_url = self.base_url.rstrip("/")


class AssessConfig:
    """アセスメント（分析モード）の設定を管理するクラス."""

    def __init__(self):
        self.base_url: Optional[str] = None
        self.root_page_ids: List[str] = []
        self.space_keys: List[str] = []
        self.output_dir: str = "."
        self.proxy: Optional[str] = None
        self.token: Optional[str] = None
        self.overwrite: bool = False

        # 分析固有オプション
        self.analyze_restrictions: bool = True
        self.single_file_max_mb: int = DEFAULT_SINGLE_FILE_MAX_MB
        self.path_length_limit: int = DEFAULT_PATH_LENGTH_LIMIT
        self.blocked_extensions: Set[str] = set(DEFAULT_BLOCKED_EXTENSIONS)
        self.attachment_dir_name: str = DEFAULT_ATTACHMENT_DIR_NAME
        self.stale_days: int = 365
        self.min_body_bytes: int = 200
        self.report_format: str = "both"

    def load(self):
        """設定を読み込む。優先順位は CLI > 環境変数 > 設定ファイル > デフォルト."""
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
        pre_args, _ = pre_parser.parse_known_args()

        config_path = Path(pre_args.config) if pre_args.config else DEFAULT_CONFIG_PATH

        if config_path.exists():
            try:
                with open(config_path, encoding="utf-8") as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self.base_url = file_config.get("base_url", self.base_url)
                        root_ids = file_config.get("root_page_ids")
                        if root_ids:
                            if isinstance(root_ids, list):
                                self.root_page_ids = [str(i) for i in root_ids]
                            else:
                                self.root_page_ids = [str(root_ids)]
                        s_keys = file_config.get("space_keys")
                        if s_keys:
                            if isinstance(s_keys, list):
                                self.space_keys = [str(k) for k in s_keys]
                            else:
                                self.space_keys = [str(s_keys)]

                        self.output_dir = file_config.get("output_dir", self.output_dir)
                        self.proxy = file_config.get("proxy", self.proxy)
                        self.token = file_config.get("token", self.token)
                        self.overwrite = file_config.get("overwrite", self.overwrite)

                        # assessment セクション
                        assess_sec = file_config.get("assessment", {})
                        if isinstance(assess_sec, dict):
                            self.analyze_restrictions = assess_sec.get(
                                "analyze_restrictions", self.analyze_restrictions
                            )
                            self.single_file_max_mb = assess_sec.get("single_file_max_mb", self.single_file_max_mb)
                            self.path_length_limit = assess_sec.get("path_length_limit", self.path_length_limit)
                            b_exts = assess_sec.get("blocked_extensions")
                            if b_exts and isinstance(b_exts, list):
                                self.blocked_extensions = {str(e).lower().lstrip(".") for e in b_exts}
                            self.attachment_dir_name = assess_sec.get("attachment_dir_name", self.attachment_dir_name)
                            self.stale_days = assess_sec.get("stale_days", self.stale_days)
                            self.min_body_bytes = assess_sec.get("min_body_bytes", self.min_body_bytes)
                            self.report_format = assess_sec.get("report_format", self.report_format)
            except Exception as e:
                print(
                    f"設定ファイル {config_path} の読み込みに失敗しました（現象）。詳細: {e}（原因）。ファイル形式を確認してください（対処方法）"
                )

        env_token = os.environ.get("C2M_CONFLUENCE_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
        if env_token:
            self.token = env_token

        env_https_proxy = os.environ.get("HTTPS_PROXY")
        env_http_proxy = os.environ.get("HTTP_PROXY")
        if env_https_proxy:
            self.proxy = env_https_proxy
        elif env_http_proxy:
            self.proxy = env_http_proxy

        parser = argparse.ArgumentParser(description="Confluenceのコンテンツ分析（アセスメント）を実行するツール")
        parser.add_argument("--base-url", type=str, help="ConfluenceのベースURL (例: https://host/wiki)")
        parser.add_argument(
            "--root-page-id", type=str, nargs="+", help="分析を開始するルートページのID（複数指定可能）"
        )
        parser.add_argument("--space-key", type=str, nargs="+", help="分析を開始するSpaceキー（複数指定可能）")
        parser.add_argument("--output-dir", type=str, help="レポートを保存するディレクトリ")
        parser.add_argument("--proxy", type=str, help="HTTP/HTTPS プロキシURL")
        parser.add_argument("--config", type=str, help="設定ファイルのパス (既定: c2m_config.yaml)")
        parser.add_argument("--token", type=str, help="ConfluenceのBearerトークン")
        parser.add_argument("--overwrite", action="store_true", help="既存のレポートを上書きする")

        parser.add_argument("--restrictions", action="store_true", default=None, help="権限分析を有効化する")
        parser.add_argument("--no-restrictions", action="store_false", dest="restrictions", help="権限分析を無効化する")
        parser.add_argument("--single-file-max-mb", type=int, help="巨大添付判定の閾値(MB)")
        parser.add_argument("--path-length-limit", type=int, help="パス長リスク判定の文字数上限")
        parser.add_argument("--blocked-ext", type=str, nargs="+", help="ブロック対象の拡張子")
        parser.add_argument("--attachment-dir", type=str, help="パス長計算時の添付フォルダ名")
        parser.add_argument("--stale-days", type=int, help="長期未更新判定の経過日数")
        parser.add_argument("--min-body-bytes", type=int, help="空/極小ページ判定のバイト数上限")
        parser.add_argument("--report-format", type=str, choices=["md", "json", "both"], help="出力フォーマット")

        cli_args = parser.parse_args()

        if cli_args.base_url:
            self.base_url = cli_args.base_url
        if cli_args.root_page_id:
            self.root_page_ids = cli_args.root_page_id
        if cli_args.space_key:
            self.space_keys = cli_args.space_key

        if self.root_page_ids:
            seen = set()
            self.root_page_ids = [x for x in self.root_page_ids if not (x in seen or seen.add(x))]
        if self.space_keys:
            seen_s = set()
            self.space_keys = [x for x in self.space_keys if not (x in seen_s or seen_s.add(x))]

        if cli_args.output_dir:
            self.output_dir = cli_args.output_dir
        if cli_args.proxy:
            self.proxy = cli_args.proxy
        if cli_args.token:
            self.token = cli_args.token
        if cli_args.overwrite:
            self.overwrite = True

        if cli_args.restrictions is not None:
            self.analyze_restrictions = cli_args.restrictions
        if cli_args.single_file_max_mb is not None:
            self.single_file_max_mb = cli_args.single_file_max_mb
        if cli_args.path_length_limit is not None:
            self.path_length_limit = cli_args.path_length_limit
        if cli_args.blocked_ext:
            self.blocked_extensions = {str(e).lower().lstrip(".") for e in cli_args.blocked_ext}
        if cli_args.attachment_dir:
            self.attachment_dir_name = cli_args.attachment_dir
        if cli_args.stale_days is not None:
            self.stale_days = cli_args.stale_days
        if cli_args.min_body_bytes is not None:
            self.min_body_bytes = cli_args.min_body_bytes
        if cli_args.report_format:
            self.report_format = cli_args.report_format

    def validate(self):
        """必須設定の有無を確認し、URLの正規化を行う."""
        if not self.base_url:
            raise ValueError("base_url is required (use --base-url or config file)")
        if not self.root_page_ids and not self.space_keys:
            raise ValueError(
                "At least one root_page_id or space_key is required (use --root-page-id, --space-key, or config file)"
            )
        if not self.token:
            raise ValueError("token is required (use --token or config file)")

        self.base_url = self.base_url.rstrip("/")
