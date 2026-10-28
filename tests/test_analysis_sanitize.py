import os
import pytest
from c2m_export.analysis.sanitize import sanitize_text


def test_sanitize_text_exact_match():
    token = "secret-token-12345"
    text = f"Connecting to Confluence with token {token}..."
    result = sanitize_text(text, secrets=[token])
    assert "secret-token-12345" not in result
    assert "Connecting to Confluence with token ***REDACTED***..." == result


def test_sanitize_bearer_header():
    text = "Authorization: Bearer secret-token-abc"
    result = sanitize_text(text, secrets=[])
    assert "secret-token-abc" not in result
    assert "Authorization: Bearer ***REDACTED***" in result


def test_sanitize_json_authorization_header():
    text = '{"headers": {"Authorization": "Bearer secret-token-abc"}}'
    result = sanitize_text(text, secrets=[])
    assert "secret-token-abc" not in result
    assert '***REDACTED***' in result


def test_sanitize_empty_secrets_noop():
    text = "This is a normal log message."
    result = sanitize_text(text, secrets=[None, ""])
    assert result == text
