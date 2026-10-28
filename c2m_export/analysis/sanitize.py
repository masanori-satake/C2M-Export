import re
from typing import Iterable, Optional


def sanitize_text(text: str, secrets: Optional[Iterable[Optional[str]]] = None) -> str:
    """テキストに含まれる秘匿情報（認証トークン実値、Bearerヘッダ）をマスクする純粋関数.

    Args:
        text: サニタイズ対象のテキスト（JSON文字列またはログテキスト）。
        secrets: マスク対象とするシークレット（トークン文字列等）の集合。

    Returns:
        サニタイズされたテキスト。
    """
    if not text:
        return text

    sanitized = text

    # 1. secrets に含まれる完全一致トークンの置換 (非空文字列のみ対象)
    if secrets:
        for secret in secrets:
            if secret and secret.strip():
                sanitized = sanitized.replace(secret, "***REDACTED***")

    # 2. Authorization ヘッダおよび Bearer トークンのマスク
    # "Authorization": "Bearer xxx" or Authorization: Bearer xxx or Authorization: Basic xxx
    def _mask_bearer(m: re.Match) -> str:
        prefix = m.group(1)
        token = m.group(2)
        if token == "***REDACTED***":
            return m.group(0)
        return f"{prefix}***REDACTED***"

    sanitized = re.sub(r"(Bearer\s+)(\S+)", _mask_bearer, sanitized, flags=re.IGNORECASE)

    # 独自ヘッダ形式 Authorization: <non-bearer-single-word>
    def _mask_auth_header(m: re.Match) -> str:
        prefix = m.group(1)
        val = m.group(2)
        quote = m.group(3) or ""
        if "Bearer" in val or "***REDACTED***" in val:
            return m.group(0)
        return f"{prefix}***REDACTED***{quote}"

    sanitized = re.sub(
        r'(Authorization[\"\']?\s*[:=]\s*[\"\']?)([^\"\'\s,]+)([\"\']?)',
        _mask_auth_header,
        sanitized,
        flags=re.IGNORECASE,
    )

    return sanitized
