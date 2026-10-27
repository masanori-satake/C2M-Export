"""FsExportConfig sync 関連拡張の単体テスト."""

import pytest

from c2m_export.config import FsExportConfig


def test_fsexport_config_sync_defaults():
    """FsExportConfig の sync 関連デフォルト値を検証する."""
    config = FsExportConfig()
    assert config.sync is False
    assert config.resume is False
    assert config.full is False
    assert config.deletion_policy == "quarantine"
    assert config.quarantine_dir_name == "_c2m_quarantine"
    assert config.manifest_name == ".c2m_manifest.json"


def test_fsexport_config_deletion_policy_validation():
    """不正な deletion_policy で ValueError が発生することを検証する."""
    config = FsExportConfig()
    config.base_url = "https://confluence.example.com"
    config.token = "token"
    config.root_page_ids = ["123"]
    config.deletion_policy = "invalid_policy"

    with pytest.raises(ValueError, match="deletion_policy"):
        config.validate()
