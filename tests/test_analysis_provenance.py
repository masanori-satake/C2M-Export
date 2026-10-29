"""実効閲覧制限の未取得と取得済みの区別を検証する。"""

import pytest

from c2m_export.analysis.provenance import enrich_restricted
from c2m_export.assessment.models import PageMeta, RawInventory, RestrictionMeta


@pytest.mark.parametrize(
    ("restriction", "users", "groups", "present"),
    [
        (None, None, None, None),
        (RestrictionMeta(has_explicit=False), [], [], False),
        (RestrictionMeta(has_explicit=True, read_users=["alice"], read_groups=["staff"]), ["alice"], ["staff"], True),
    ],
)
def test_enrich_restricted_distinguishes_unknown_from_unrestricted(restriction, users, groups, present):
    """取得済みの空制限のみ制限なしとし、未取得・ページ不在は null とする。"""
    page = PageMeta("100", "Page", "TEST", 1, 0, None, [], effective_view_restrictions=restriction)
    records = [{"page_id": "100"}, {"page_id": "missing"}]

    result = enrich_restricted(records, RawInventory(pages=[page]))

    assert result[0]["effective_read_users"] == users
    assert result[0]["effective_read_groups"] == groups
    assert result[0]["effective_restriction_present"] is present
    assert result[1] == {
        "page_id": "missing",
        "effective_read_users": None,
        "effective_read_groups": None,
        "effective_restriction_present": None,
    }
    assert records == [{"page_id": "100"}, {"page_id": "missing"}]
