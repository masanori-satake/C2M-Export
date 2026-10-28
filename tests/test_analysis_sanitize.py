import json

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
    assert json.loads(result) == {"headers": {"Authorization": "Bearer ***REDACTED***"}}


def test_sanitize_empty_secrets_noop():
    text = "This is a normal log message."
    result = sanitize_text(text, secrets=[None, ""])
    assert result == text


@pytest.mark.parametrize("delimiter", ['"', "'", "\\", ",", ";", "}", "]", "\n"])
def test_sanitize_bearer_preserves_delimiters(delimiter):
    text = f"Bearer secret-token{delimiter}"

    assert sanitize_text(text) == f"Bearer ***REDACTED***{delimiter}"


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "Basic", "basic"])
@pytest.mark.parametrize("secrets", [[], ["dXNlcjpwYXNz"]])
def test_sanitize_json_authentication(scheme, secrets):
    text = json.dumps({"headers": {"Authorization": f"{scheme} dXNlcjpwYXNz", "Accept": "application/json"}})

    result = sanitize_text(text, secrets=secrets)

    expected = f"{scheme} ***REDACTED***" if scheme.lower() == "bearer" else "***REDACTED***"
    assert json.loads(result) == {"headers": {"Authorization": expected, "Accept": "application/json"}}
    assert sanitize_text(result, secrets=secrets) == result


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Authorization: Basic dXNlcjpwYXNz", "Authorization: ***REDACTED***"),
        ("'Authorization': 'Basic dXNlcjpwYXNz', 'next': 1", "'Authorization': '***REDACTED***', 'next': 1"),
        ("authorization=basic dXNlcjpwYXNz; next=1", "authorization=***REDACTED***; next=1"),
        ("Authorization: secret-token, next=1", "Authorization: ***REDACTED***, next=1"),
    ],
)
def test_sanitize_authorization_preserves_delimiters(text, expected):
    assert sanitize_text(text) == expected


@pytest.mark.parametrize("scheme", ["Bearer", "Basic"])
def test_sanitize_authentication_inside_json_message(scheme):
    text = json.dumps({"message": f'Authorization: {scheme} dXNlcjpwYXNz", next=1'})

    result = sanitize_text(text)

    expected = f"{scheme} ***REDACTED***" if scheme == "Bearer" else "***REDACTED***"
    assert json.loads(result) == {"message": f'Authorization: {expected}", next=1'}
