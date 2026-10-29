"""次リンクに従った全件取得と、不正なページ位置での停止を検証する."""

from unittest.mock import call, patch
from urllib.parse import urlencode

import pytest

from c2m_export.confluence import ConfluenceClient


@pytest.fixture(
    params=[
        (
            "list_spaces",
            (),
            {"type_": "global", "status": "current", "label": "team", "content_label": "doc", "expand": "description"},
            "/rest/api/space",
            {"type": "global", "status": "current", "label": "team", "contentLabel": "doc", "expand": "description"},
        ),
        (
            "get_descendants",
            ("123",),
            {"type_": "blogpost", "expand": "space"},
            "/rest/api/content/123/descendant/blogpost",
            {"expand": "space"},
        ),
        ("get_user_memberof", (), {}, "/rest/api/user/memberof", {}),
        ("get_labels", ("123",), {"prefix": "global"}, "/rest/api/content/123/label", {"prefix": "global"}),
        (
            "search_cql",
            ('space = "DEV"',),
            {"expand": "space"},
            "/rest/api/content/search",
            {"cql": 'space = "DEV"', "expand": "space"},
        ),
        (
            "get_comments",
            ("123",),
            {"depth": "all", "expand": "extensions.location"},
            "/rest/api/content/123/child/comment",
            {"depth": "all", "expand": "extensions.location"},
        ),
    ],
    ids=lambda case: case[0],
)
def offset_operation(request):
    client = ConfluenceClient("https://confluence.example.com/wiki", "test_token")
    name, args, kwargs, path, params = request.param

    def invoke():
        return getattr(client, name)(*args, limit=2, **kwargs)

    return client, invoke, path, params


@pytest.mark.parametrize("first_results", [[], [{"id": "1"}]])
def test_offset_pagination_follows_next_after_short_or_empty_pages(offset_operation, first_results):
    client, invoke, path, params = offset_operation
    final_results = [{"id": "2"}, {"id": "3"}]
    pages = [
        {"results": first_results, "_links": {"next": f"{path}?start=7&limit=2"}},
        {"results": [], "_links": {"next": f"https://confluence.example.com/wiki{path}?limit=2&start=19"}},
        {"results": final_results},
    ]

    with patch.object(client, "_request", side_effect=pages) as transport:
        assert invoke() == first_results + final_results

    assert transport.call_args_list == [
        call("GET", path, params={**params, "limit": 2, "start": start}) for start in (0, 7, 19)
    ]


@pytest.mark.parametrize("next_query", ["limit=2", "start=bad", "start=0", "start=-1"])
def test_offset_pagination_rejects_invalid_or_repeated_position(offset_operation, next_query):
    client, invoke, path, _ = offset_operation
    page = {"results": [], "_links": {"next": f"{path}?{next_query}"}}

    with patch.object(client, "_request", return_value=page) as transport:
        with pytest.raises(ValueError, match="ページ位置"):
            invoke()
        assert transport.call_count == 1


@pytest.mark.parametrize("first_results", [[], [{"id": "1"}]])
@pytest.mark.parametrize("cursor_source", ["next_link", "nextCursor"])
def test_scan_follows_next_after_short_or_empty_pages(first_results, cursor_source):
    client = ConfluenceClient("https://confluence.example.com/wiki", "test_token")
    path = "/rest/api/content/scan"
    next_cursor = "next+cursor/="
    first_page = {"results": first_results, "_links": {"next": path}}
    if cursor_source == "nextCursor":
        first_page["nextCursor"] = next_cursor
    else:
        first_page["_links"]["next"] += "?" + urlencode({"cursor": next_cursor})
    final_results = [{"id": "2"}, {"id": "3"}]
    pages = [first_page, {"results": final_results, "nextCursor": "unused"}]
    params = {"spaceKey": "DEV", "type": "page", "limit": 2, "status": "current", "expand": "space"}

    with patch.object(client, "_request", side_effect=pages) as transport:
        assert client.scan_content("DEV", status="current", expand="space", cursor="initial", limit=2) == (
            first_results + final_results
        )

    assert transport.call_args_list == [
        call("GET", path, params={**params, "cursor": "initial"}),
        call("GET", path, params={**params, "cursor": next_cursor}),
    ]


@pytest.mark.parametrize("cursor_source", ["next_link", "nextCursor"])
def test_scan_rejects_repeated_cursor_without_retry(cursor_source):
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    page = {"results": [{"id": "1"}], "_links": {"next": "/rest/api/content/scan?cursor=same"}}
    if cursor_source == "nextCursor":
        page["nextCursor"] = "same"

    with patch.object(client, "_request", return_value=page) as transport:
        with pytest.raises(ValueError, match="カーソル.*同じ"):
            client.scan_content("DEV", cursor="same", limit=2)
        assert transport.call_count == 1


def test_scan_rejects_next_link_without_cursor():
    client = ConfluenceClient("https://confluence.example.com", "test_token")
    page = {"results": [], "_links": {"next": "/rest/api/content/scan?limit=2"}}

    with patch.object(client, "_request", return_value=page) as transport:
        with pytest.raises(ValueError, match="カーソル.*取得できません"):
            client.scan_content("DEV", limit=2)
        assert transport.call_count == 1
