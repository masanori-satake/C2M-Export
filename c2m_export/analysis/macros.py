"""マクロ統計および手作業修復候補判定の純粋関数 (UC6).

converter (c2m_export/converter.py) の Markdown 変換方針と密接に対応し、
変換時に手作業での確認や補完が必要となるマクロを分析・分類する。
"""

from typing import Any, Dict, List

from bs4 import BeautifulSoup

# converter の変換方針に基づく修復区分・定型理由のマッピングテーブル
MACRO_REPAIR_RULES: Dict[str, Dict[str, str]] = {
    "toc": {
        "repair_category": "content_loss",
        "repair_reason": "目次マクロは空文字化されます。必要に応じて手動で目次を補完してください。",
    },
    "anchor": {
        "repair_category": "content_loss",
        "repair_reason": "アンカーマクロは空文字化されます。",
    },
    "pagetree": {
        "repair_category": "content_loss",
        "repair_reason": "ページツリーマクロは空文字化されます。",
    },
    "children": {
        "repair_category": "content_loss",
        "repair_reason": "子ページ一覧マクロは空文字化されます。",
    },
    "contentbylabel": {
        "repair_category": "content_loss",
        "repair_reason": "ラベル別コンテンツ一覧マクロは空文字化されます。",
    },
    "jira": {
        "repair_category": "external_dependency",
        "repair_reason": "Jira 課題埋め込みマクロです。必要に応じてリンクまたはテキスト表記の調整を行ってください。",
    },
    "include": {
        "repair_category": "external_dependency",
        "repair_reason": "他ページ埋め込みマクロです。参照先ページのタイトルが挿入されます。",
    },
    "excerpt-include": {
        "repair_category": "external_dependency",
        "repair_reason": "抜粋埋め込みマクロです。外部参照箇所の確認が必要です。",
    },
    "gliffy": {
        "repair_category": "external_dependency",
        "repair_reason": "Gliffy 図形描画マクロです。画像等としての手動再エクスポートが必要な場合があります。",
    },
    "drawio": {
        "repair_category": "external_dependency",
        "repair_reason": "Draw.io ダイヤグラムマクロです。画像等としての手動再エクスポートが必要な場合があります。",
    },
    "code": {
        "repair_category": "approximation",
        "repair_reason": "コードブロックに変換されます。構文ハイライト言語の確認を推奨します。",
    },
    "plantuml": {
        "repair_category": "approximation",
        "repair_reason": "PlantUML コードブロックに変換されます。",
    },
    "plantumlrender": {
        "repair_category": "approximation",
        "repair_reason": "PlantUML コードブロックに変換されます。",
    },
    "expand": {
        "repair_category": "approximation",
        "repair_reason": "折りたたみブロックに変換されます。",
    },
    "panel": {
        "repair_category": "approximation",
        "repair_reason": "パネル枠囲みに変換されます。",
    },
    "info": {
        "repair_category": "approximation",
        "repair_reason": "情報コールアウト枠囲みに変換されます。",
    },
    "tip": {
        "repair_category": "approximation",
        "repair_reason": "ヒントコールアウト枠囲みに変換されます。",
    },
    "note": {
        "repair_category": "approximation",
        "repair_reason": "ノートコールアウト枠囲みに変換されます。",
    },
    "warning": {
        "repair_category": "approximation",
        "repair_reason": "警告コールアウト枠囲みに変換されます。",
    },
    "status": {
        "repair_category": "safe",
        "repair_reason": "ステータスバッジ（テキスト）として標準変換されます。",
    },
    "format-block": {
        "repair_category": "safe",
        "repair_reason": "標準的なブロック装飾として変換されます。",
    },
    "section": {
        "repair_category": "safe",
        "repair_reason": "レイアウトセクションとして内包コンテンツがそのまま展開されます。",
    },
    "column": {
        "repair_category": "safe",
        "repair_reason": "レイアウトカラムとして内包コンテンツがそのまま展開されます。",
    },
}

UNKNOWN_REPAIR_RULE: Dict[str, str] = {
    "repair_category": "unknown",
    "repair_reason": "未定義のマクロです。手作業での変換結果確認を推奨します。",
}


def count_macros(body_storage: str) -> Dict[str, int]:
    """body_storage (XHTML) 内の structured-macro および conf-macro を集計する."""
    if not body_storage or not body_storage.strip():
        return {}

    counts: Dict[str, int] = {}
    try:
        soup = BeautifulSoup(body_storage, "html.parser")

        # 1. ac:structured-macro
        for macro in soup.find_all("ac:structured-macro"):
            name = macro.get("ac:name")
            if name:
                name_str = str(name).strip().lower()
                counts[name_str] = counts.get(name_str, 0) + 1

        # 2. conf-macro (旧互換要素)
        for macro in soup.find_all(class_=lambda c: c and "conf-macro" in c.split()):
            name = macro.get("data-macro-name")
            if name:
                name_str = str(name).strip().lower()
                counts[name_str] = counts.get(name_str, 0) + 1
    except Exception:
        # 例外発生時は破綻させず集計途中または空のdictを返す
        pass

    return counts


def summarize_macros(pages: List[Any]) -> List[Dict[str, Any]]:
    """全ページの macro_counts を合算し、修復区分情報を付与した全件レコード列を返す."""
    aggregated: Dict[str, int] = {}
    for page in pages:
        macro_counts = getattr(page, "macro_counts", {})
        if isinstance(macro_counts, dict):
            for m_name, count in macro_counts.items():
                m_key = str(m_name).lower()
                aggregated[m_key] = aggregated.get(m_key, 0) + count

    results: List[Dict[str, Any]] = []
    for m_name, count in aggregated.items():
        rule = MACRO_REPAIR_RULES.get(m_name, UNKNOWN_REPAIR_RULE)
        results.append(
            {
                "name": m_name,
                "count": count,
                "repair_category": rule["repair_category"],
                "repair_reason": rule["repair_reason"],
            }
        )

    return results
