#!/usr/bin/env python3
"""
Confluence Page Tree Visualization Skill 補助実行スクリプト.

C2M-Export のページツリー CLI (c2m_export.tree) をサブプロセスとして起動します。
トークンは環境変数 (C2M_CONFLUENCE_TOKEN または CONFLUENCE_TOKEN) から自動参照されます。
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _find_repo_root() -> Optional[Path]:
    """上位ディレクトリを辿り c2m_export パッケージを含むルートを返す。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "c2m_export" / "__init__.py").exists():
            return parent
    return None


def main() -> None:
    """CLI エントリーポイントへ引数をそのまま引き継いで実行します。"""
    repo_root = _find_repo_root()
    cmd = [sys.executable, "-m", "c2m_export.tree"] + sys.argv[1:]
    env = dict(os.environ)
    if repo_root:
        python_path = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(repo_root) + (f"{os.pathsep}{python_path}" if python_path else "")

    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
