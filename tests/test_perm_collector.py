"""権限収集（collector）モジュールのテスト."""

from unittest.mock import MagicMock

from c2m_export.permission.collector import (
    collect_permissions,
    extract_permission_holders,
)


def test_extract_permission_holders():
    data = {
        "restrictions": {
            "user": {
                "results": [
                    {"displayName": "山田太郎", "username": "t.yamada"},
                    {"displayName": "admin", "username": "admin"},
                ]
            },
            "group": {
                "results": [
                    {"name": "dev-team"},
                    {"name": "managers"},
                ]
            },
        }
    }

    users, groups = extract_permission_holders(data)
    assert users == ["山田太郎 (t.yamada)", "admin"]
    assert groups == ["dev-team", "managers"]


def test_collect_permissions_explicit_and_inherited():
    mock_client = MagicMock()

    # Root page 100
    mock_client.get_page.side_effect = lambda pid, expand=None: {
        "id": str(pid),
        "title": f"Page {pid}",
        "space": {"key": "TEST"},
        "_links": {"base": "https://example.com", "webui": f"/pages/{pid}"},
    }
    mock_client.get_child_pages.side_effect = lambda pid: (
        [{"id": "101", "title": "Child 101"}] if str(pid) == "100" else []
    )

    # Restrictions
    def mock_get_restrictions(pid):
        if str(pid) == "100":
            return {
                "read": {
                    "restrictions": {
                        "user": {"results": [{"displayName": "佐藤次郎", "username": "j.sato"}]},
                        "group": {"results": []},
                    }
                },
                "update": {"restrictions": {"user": {"results": []}, "group": {"results": []}}},
            }
        else:
            # Inherited/no restriction for 101
            return {
                "read": {"restrictions": {"user": {"results": []}, "group": {"results": []}}},
                "update": {"restrictions": {"user": {"results": []}, "group": {"results": []}}},
            }

    mock_client.get_restrictions.side_effect = mock_get_restrictions

    res = collect_permissions(
        client=mock_client,
        base_url="https://example.com",
        root_page_ids=["100"],
    )

    assert res.exported_count == 2
    assert res.explicit_count == 1
    assert res.inherited_count == 1
    assert len(res.failed_page_ids) == 0

    p100 = res.report.pages[0]
    assert p100.page_id == "100"
    assert p100.has_explicit is True
    assert p100.read_users == ["佐藤次郎 (j.sato)"]

    p101 = res.report.pages[1]
    assert p101.page_id == "101"
    assert p101.has_explicit is False


def test_collect_permissions_partial_failure():
    mock_client = MagicMock()
    mock_client.get_page.side_effect = lambda pid, expand=None: {
        "id": str(pid),
        "title": f"Page {pid}",
        "space": {"key": "TEST"},
    }
    mock_client.get_child_pages.return_value = []

    def mock_get_restrictions(pid):
        if str(pid) == "200":
            raise Exception("APIエラー (403 Forbidden)")
        return {
            "read": {"restrictions": {"user": {"results": []}, "group": {"results": []}}},
            "update": {"restrictions": {"user": {"results": []}, "group": {"results": []}}},
        }

    mock_client.get_restrictions.side_effect = mock_get_restrictions

    res = collect_permissions(
        client=mock_client,
        base_url="https://example.com",
        root_page_ids=["200"],
    )

    assert res.exported_count == 1
    assert res.explicit_count == 0
    assert res.inherited_count == 0
    assert res.failed_page_ids == ["200"]
    assert res.report.pages[0].fetch_failed is True
