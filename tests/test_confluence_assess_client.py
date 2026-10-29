from unittest.mock import MagicMock, patch

from c2m_export.confluence import ConfluenceClient


def test_get_page_default_expand():
    client = ConfluenceClient("https://confluence.example.com", "dummy_token")
    with patch.object(client, "_request", return_value={"id": "123"}) as mock_req:
        res = client.get_page("123")
        assert res == {"id": "123"}
        mock_req.assert_called_once_with("GET", "/rest/api/content/123", params={"expand": "body.storage,space"})


def test_get_page_custom_expand():
    client = ConfluenceClient("https://confluence.example.com", "dummy_token")
    with patch.object(client, "_request", return_value={"id": "123"}) as mock_req:
        res = client.get_page("123", expand="body.storage,space,version")
        assert res == {"id": "123"}
        mock_req.assert_called_once_with(
            "GET", "/rest/api/content/123", params={"expand": "body.storage,space,version"}
        )


def test_get_attachments_pagination():
    client = ConfluenceClient("https://confluence.example.com", "dummy_token")
    page1 = {
        "results": [
            {
                "title": "file1.png",
                "extensions": {"fileSize": 100, "mediaType": "image/png"},
                "version": {"number": 1},
            },
            {
                "title": "file2.pdf",
                "extensions": {"fileSize": 200, "mediaType": "application/pdf"},
                "version": {"number": 2},
            },
        ],
        "_links": {"next": "/rest/api/content/123/child/attachment?start=2&limit=2"},
    }
    page2 = {
        "results": [
            {
                "title": "file3.docx",
                "extensions": {"fileSize": 300, "mediaType": "application/docx"},
                "version": {"number": 1},
            }
        ]
    }

    with patch.object(client, "_request", side_effect=[page1, page2]) as mock_req:
        res = client.get_attachments("123", limit=2)
        assert len(res) == 3
        assert mock_req.call_count == 2


def test_get_restrictions():
    client = ConfluenceClient("https://confluence.example.com", "dummy_token")
    expected = {
        "read": {"restrictions": {"user": {"results": [{"username": "user1"}]}, "group": {"results": []}}},
        "update": {"restrictions": {"user": {"results": []}, "group": {"results": [{"name": "group1"}]}}},
    }
    with patch.object(client, "_request", return_value=expected) as mock_req:
        res = client.get_restrictions("123")
        assert res == expected
        mock_req.assert_called_once_with("GET", "/rest/api/content/123/restriction/byOperation")


def test_get_space_root_pages_pagination():
    client = ConfluenceClient("https://confluence.example.com", "dummy_token")
    page1 = {
        "results": [{"id": "10", "title": "Root1"}, {"id": "20", "title": "Root2"}],
        "_links": {"next": "/rest/api/space/MYSPACE/content/page?depth=root&start=2&limit=2"},
    }
    page2 = {"results": [{"id": "30", "title": "Root3"}]}

    with patch.object(client, "_request", side_effect=[page1, page2]) as mock_req:
        res = client.get_space_root_pages("MYSPACE", limit=2)
        assert len(res) == 3
        assert mock_req.call_count == 2


def test_pagination_exact_limit_no_next_does_not_request_again():
    """limit ちょうどの件数だが _links.next が無い場合に追加リクエストを投げないことを検証."""
    client = ConfluenceClient("https://confluence.example.com", "dummy_token")
    page1 = {"results": [{"id": "1"}, {"id": "2"}]}  # limit=2, next なし

    with patch.object(client, "_request", return_value=page1) as mock_req:
        res = client.get_child_pages("100", limit=2)
        assert len(res) == 2
        assert mock_req.call_count == 1


def test_pagination_less_than_limit_with_next_fetches_next_page():
    """limit 未満の件数（例: 1件）だが _links.next が存在する場合に次ページを取得することを検証."""
    client = ConfluenceClient("https://confluence.example.com", "dummy_token")
    page1 = {
        "results": [{"id": "1"}],
        "_links": {"next": "/rest/api/content/100/child/page?start=1&limit=25"},
    }
    page2 = {"results": [{"id": "2"}]}

    with patch.object(client, "_request", side_effect=[page1, page2]) as mock_req:
        res = client.get_child_pages("100", limit=25)
        assert len(res) == 2
        assert mock_req.call_count == 2


def test_all_pagination_methods_use_links_next():
    """全 8(+1) メソッドで _links.next が正しく解釈されることを検証."""
    client = ConfluenceClient("https://confluence.example.com", "dummy_token")

    # 1. list_spaces
    p1 = {"results": [{"key": "S1"}], "_links": {"next": "/rest/api/space?start=1&limit=1"}}
    p2 = {"results": [{"key": "S2"}]}
    with patch.object(client, "_request", side_effect=[p1, p2]):
        assert len(client.list_spaces(limit=1)) == 2

    # 2. get_descendants
    p1 = {"results": [{"id": "d1"}], "_links": {"next": "/rest/api/content/1/descendant/page?start=1&limit=1"}}
    p2 = {"results": [{"id": "d2"}]}
    with patch.object(client, "_request", side_effect=[p1, p2]):
        assert len(client.get_descendants("1", limit=1)) == 2

    # 3. get_user_memberof
    p1 = {"results": [{"name": "g1"}], "_links": {"next": "/rest/api/user/memberof?start=1&limit=1"}}
    p2 = {"results": [{"name": "g2"}]}
    with patch.object(client, "_request", side_effect=[p1, p2]):
        assert len(client.get_user_memberof(limit=1)) == 2

    # 4. get_labels
    p1 = {"results": [{"name": "l1"}], "_links": {"next": "/rest/api/content/1/label?start=1&limit=1"}}
    p2 = {"results": [{"name": "l2"}]}
    with patch.object(client, "_request", side_effect=[p1, p2]):
        assert len(client.get_labels("1", limit=1)) == 2

    # 5. search_cql
    p1 = {"results": [{"id": "c1"}], "_links": {"next": "/rest/api/content/search?start=1&limit=1"}}
    p2 = {"results": [{"id": "c2"}]}
    with patch.object(client, "_request", side_effect=[p1, p2]):
        assert len(client.search_cql("title ~ 'test'", limit=1)) == 2

    # 6. get_comments
    p1 = {"results": [{"id": "cm1"}], "_links": {"next": "/rest/api/content/1/child/comment?start=1&limit=1"}}
    p2 = {"results": [{"id": "cm2"}]}
    with patch.object(client, "_request", side_effect=[p1, p2]):
        assert len(client.get_comments("1", limit=1)) == 2

    # 7. get_child_pages
    p1 = {"results": [{"id": "cp1"}], "_links": {"next": "/rest/api/content/1/child/page?start=1&limit=1"}}
    p2 = {"results": [{"id": "cp2"}]}
    with patch.object(client, "_request", side_effect=[p1, p2]):
        assert len(client.get_child_pages("1", limit=1)) == 2

    # 8. get_attachments
    p1 = {"results": [{"title": "a1.png"}], "_links": {"next": "/rest/api/content/1/child/attachment?start=1&limit=1"}}
    p2 = {"results": [{"title": "a2.png"}]}
    with patch.object(client, "_request", side_effect=[p1, p2]):
        assert len(client.get_attachments("1", limit=1)) == 2
