#!/usr/bin/env python3
"""
Confluence Workspace Analysis Skill 補助実行スクリプト

C2M-Export の分析 CLI (c2m_export.analyze) をサブプロセスとして起動します。
トークンは環境変数 (C2M_CONFLUENCE_TOKEN または CONFLUENCE_TOKEN) から自動参照されます。
"""

import subprocess
import sys


def main() -> None:
    """CLI エントリーポイントへ引数をそのまま引き継いで実行します。"""
    cmd = [sys.executable, "-m", "c2m_export.analyze"] + sys.argv[1:]
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
