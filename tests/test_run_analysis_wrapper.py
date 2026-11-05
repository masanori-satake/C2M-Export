"""スキル補助スクリプト run_analysis.py の build_command の単体テスト.

正本（skills/）配下のスクリプトをファイルとして読み込んで検証する。
スクリプトはパッケージ外にあるため importlib でパス指定ロードする。
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "confluence-analysis" / "scripts" / "run_analysis.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_analysis_wrapper", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_command_uses_unbuffered_and_default_timeout():
    """-u で起動し、--timeout-seconds 省略時は既定 300 秒が補われる."""
    module = _load_module()
    cmd = module.build_command(["--space-key", "DEV"])
    assert cmd[0] == sys.executable
    assert cmd[1] == "-u"
    assert cmd[2:4] == ["-m", "c2m_export.analyze"]
    assert cmd[-2:] == ["--timeout-seconds", "300"]
    assert "--space-key" in cmd and "DEV" in cmd


def test_build_command_respects_explicit_timeout():
    """--timeout-seconds の明示指定があれば既定値を補わない."""
    module = _load_module()
    cmd = module.build_command(["--timeout-seconds", "60"])
    assert cmd.count("--timeout-seconds") == 1
    assert "60" in cmd
    assert "300" not in cmd


def test_build_command_respects_equals_style_timeout():
    """--timeout-seconds=<値> 形式の指定も明示指定として扱う."""
    module = _load_module()
    cmd = module.build_command(["--timeout-seconds=120"])
    assert "--timeout-seconds=120" in cmd
    assert cmd.count("--timeout-seconds") == 0
