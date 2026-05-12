import os
import yaml
import argparse
from pathlib import Path
from typing import Optional, List, Union

# デフォルト設定ファイルの保存場所 (ツールと同じディレクトリ)
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "c2m_config.yaml"

class Config:
    """
    ツールの設定を管理するクラス。
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

    def load(self):
        """
        設定を読み込む。優先順位は CLI > 設定ファイル > デフォルト。
        """
        # 設定ファイルパスを特定するために一度パース
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
        pre_args, _ = pre_parser.parse_known_args()

        config_path = Path(pre_args.config)

        # 1. 設定ファイルからの読み込み（優先度：低）
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self.base_url = file_config.get("base_url", self.base_url)
                        root_id = file_config.get("root_page_id")
                        if root_id:
                            if isinstance(root_id, list):
                                self.root_page_ids = [str(i) for i in root_id]
                            else:
                                self.root_page_ids = [str(root_id)]
                        self.output_dir = file_config.get("output_dir", self.output_dir)
                        self.max_mb = float(file_config.get("max_mb", self.max_mb))
                        self.stop_threshold_mb = float(file_config.get("stop_threshold_mb", self.stop_threshold_mb))
                        self.proxy = file_config.get("proxy", self.proxy)
                        self.token = file_config.get("token", self.token)
            except Exception as e:
                print(f"Warning: Failed to load config file {config_path}: {e}")

        # 2. 環境変数からの読み込み（Proxyなど環境依存性の高いもの）
        env_https_proxy = os.environ.get("HTTPS_PROXY")
        env_http_proxy = os.environ.get("HTTP_PROXY")
        if env_https_proxy:
            self.proxy = env_https_proxy
        elif env_http_proxy:
            self.proxy = env_http_proxy

        # 3. CLI引数からの読み込み（優先度：最高）
        parser = argparse.ArgumentParser(description="ConfluenceのページツリーをMarkdownとしてエクスポートするツール")
        parser.add_argument("--base-url", type=str, help="ConfluenceのベースURL (例: https://host/wiki)")
        parser.add_argument("--root-page-id", type=str, nargs="+", help="エクスポートを開始するルートページのID（複数指定可能）")
        parser.add_argument("--output-dir", type=str, help="エクスポートされたMarkdownファイルを保存するディレクトリ")
        parser.add_argument("--max-mb", type=float, help="出力ファイルの最大許容サイズ (MB) (既定: 100)")
        parser.add_argument("--stop-threshold-mb", type=float, help="サイズがこの閾値 (MB) を超えた場合に処理を停止する (既定: 95)")
        parser.add_argument("--proxy", type=str, help="HTTP/HTTPS プロキシURL")
        parser.add_argument("--config", type=str, help=f"設定ファイルのパス (既定: c2m_config.yaml)")
        parser.add_argument("--token", type=str, help="ConfluenceのBearerトークン")

        cli_args = parser.parse_args()

        if cli_args.base_url: self.base_url = cli_args.base_url
        if cli_args.root_page_id: self.root_page_ids = cli_args.root_page_id
        if cli_args.output_dir: self.output_dir = cli_args.output_dir
        if cli_args.max_mb is not None: self.max_mb = cli_args.max_mb
        if cli_args.stop_threshold_mb is not None: self.stop_threshold_mb = cli_args.stop_threshold_mb
        if cli_args.proxy: self.proxy = cli_args.proxy
        if cli_args.token: self.token = cli_args.token

    def validate(self):
        """
        必須設定の有無を確認し、URLの正規化を行う。
        """
        if not self.base_url:
            raise ValueError("base_url is required (use --base-url or config file)")
        if not self.root_page_ids:
            raise ValueError("root_page_id is required (use --root-page-id or config file)")
        if not self.token:
            raise ValueError("token is required (use --token or config file)")

        # 後続のパス結合時に重複を防ぐための正規化
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]
