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
        ]
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
    page1 = {"results": [{"id": "10", "title": "Root1"}, {"id": "20", "title": "Root2"}]}
    page2 = {"results": [{"id": "30", "title": "Root3"}]}

    with patch.object(client, "_request", side_effect=[page1, page2]) as mock_req:
        res = client.get_space_root_pages("MYSPACE", limit=2)
        assert len(res) == 3
        assert mock_req.call_count == 2
