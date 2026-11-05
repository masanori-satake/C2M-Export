#!/usr/bin/env python3
"""
Confluence Workspace Analysis Skill 補助実行スクリプト

C2M-Export の分析 CLI (c2m_export.analyze) をサブプロセスとして起動します。
トークンは環境変数 (C2M_CONFLUENCE_TOKEN または CONFLUENCE_TOKEN) から自動参照されます。

スキル経由の実行では、無応答のまま走り続けることを防ぐため、子プロセスを
無バッファモード (-u) で起動し、`--timeout-seconds` が明示されなければ
既定の実行時間上限 (300 秒) を補います。明示指定が常に優先されます。
上限到達時は収集済みデータで partial 結果が出力され、`--resume` で再開できます。
"""

import subprocess
import sys
from typing import List

DEFAULT_TIMEOUT_SECONDS = 300


def build_command(argv: List[str]) -> List[str]:
    """子プロセスの起動コマンドを構築する（純粋関数・テスト可能）.

    - 常に無バッファ (-u) で起動し、進捗ログが即時に流れるようにする。
    - --timeout-seconds / --timeout-seconds=<値> のいずれも無ければ既定値を補う。
    """
    args = list(argv)
    has_timeout = any(a == "--timeout-seconds" or a.startswith("--timeout-seconds=") for a in args)
    if not has_timeout:
        args = args + ["--timeout-seconds", str(DEFAULT_TIMEOUT_SECONDS)]
    return [sys.executable, "-u", "-m", "c2m_export.analyze"] + args


def main() -> None:
    """CLI エントリーポイントへ引数を引き継いで実行します。"""
    result = subprocess.run(build_command(sys.argv[1:]))
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
