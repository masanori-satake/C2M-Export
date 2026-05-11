import os
import yaml
import argparse
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_PATH = Path.home() / ".confluence_exporter.yaml"

class Config:
    def __init__(self):
        self.base_url: Optional[str] = None
        self.root_page_id: Optional[str] = None
        self.output_dir: str = "."
        self.max_mb: float = 100.0
        self.stop_threshold_mb: float = 95.0
        self.proxy: Optional[str] = None
        self.token: Optional[str] = os.environ.get("CONFLUENCE_TOKEN")

    def load(self):
        # Preliminary parse to get config path
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH))
        pre_args, _ = pre_parser.parse_known_args()

        config_path = Path(pre_args.config)

        # 1. Load from Config File (Lower priority than ENV and CLI)
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self.base_url = file_config.get("base_url", self.base_url)
                        self.root_page_id = file_config.get("root_page_id", self.root_page_id)
                        self.output_dir = file_config.get("output_dir", self.output_dir)
                        self.max_mb = float(file_config.get("max_mb", self.max_mb))
                        self.stop_threshold_mb = float(file_config.get("stop_threshold_mb", self.stop_threshold_mb))
                        self.proxy = file_config.get("proxy", self.proxy)
            except Exception as e:
                print(f"Warning: Failed to load config file {config_path}: {e}")

        # 2. Load from Environment Variables
        env_token = os.environ.get("CONFLUENCE_TOKEN")
        if env_token:
            self.token = env_token

        env_https_proxy = os.environ.get("HTTPS_PROXY")
        env_http_proxy = os.environ.get("HTTP_PROXY")
        if env_https_proxy:
            self.proxy = env_https_proxy
        elif env_http_proxy:
            self.proxy = env_http_proxy

        # 3. Load from CLI Arguments (Highest priority)
        parser = argparse.ArgumentParser(description="Confluence to Markdown Exporter")
        parser.add_argument("--base-url", type=str, help="Confluence base URL (e.g. https://host/wiki)")
        parser.add_argument("--root-page-id", type=str, help="Root page ID to start export from")
        parser.add_argument("--output-dir", type=str, help="Directory to save the exported Markdown file")
        parser.add_argument("--max-mb", type=float, help="Maximum allowed size of the output file in MB (default: 100)")
        parser.add_argument("--stop-threshold-mb", type=float, help="Stop processing if size exceeds this MB (default: 95)")
        parser.add_argument("--proxy", type=str, help="HTTP/HTTPS Proxy URL")
        parser.add_argument("--config", type=str, help=f"Path to config file (default: {DEFAULT_CONFIG_PATH})")
        parser.add_argument("--token", type=str, help="Confluence Bearer Token")

        cli_args = parser.parse_args()

        if cli_args.base_url: self.base_url = cli_args.base_url
        if cli_args.root_page_id: self.root_page_id = cli_args.root_page_id
        if cli_args.output_dir: self.output_dir = cli_args.output_dir
        if cli_args.max_mb is not None: self.max_mb = cli_args.max_mb
        if cli_args.stop_threshold_mb is not None: self.stop_threshold_mb = cli_args.stop_threshold_mb
        if cli_args.proxy: self.proxy = cli_args.proxy
        if cli_args.token: self.token = cli_args.token

    def validate(self):
        if not self.base_url:
            raise ValueError("base_url is required (use --base-url or config file)")
        if not self.root_page_id:
            raise ValueError("root_page_id is required (use --root-page-id or config file)")
        if not self.token:
            raise ValueError("token is required (use CONFLUENCE_TOKEN environment variable or --token)")

        # Normalize base_url: remove trailing slash if exists
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]
