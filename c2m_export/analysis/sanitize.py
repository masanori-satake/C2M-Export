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
    # JSON の引用符・エスケープ文字やログの区切りをトークンに含めない
    token_pattern = r"""[^\s"'\\,;{}\[\]]+"""

    def _mask_bearer(m: re.Match) -> str:
        prefix = m.group(1)
        token = m.group(2)
        if token == "***REDACTED***":
            return m.group(0)
        return f"{prefix}***REDACTED***"

    sanitized = re.sub(rf"(Bearer\s+)({token_pattern})", _mask_bearer, sanitized, flags=re.IGNORECASE)

    # Basic の方式名と認証情報、または独自ヘッダの単一トークンをまとめてマスクする
    def _mask_auth_header(m: re.Match) -> str:
        prefix = m.group(1)
        val = m.group(2)
        if val.lower() == "bearer" or val == "***REDACTED***":
            return m.group(0)
        return f"{prefix}***REDACTED***"

    sanitized = re.sub(
        rf"(Authorization[\"\']?\s*[:=]\s*[\"\']?)((?:Basic[ \t]+)?{token_pattern})",
        _mask_auth_header,
        sanitized,
        flags=re.IGNORECASE,
    )

    return sanitized
