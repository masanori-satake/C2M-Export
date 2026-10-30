"""付帯情報の集約・変換・マーク生成を行う純粋ロジックモジュール."""

from typing import Dict, List, Tuple

from bs4 import BeautifulSoup

from c2m_export.page_tree.models import Annotation


def aggregate_macros(storage_xhtml: str) -> Dict[str, int]:
    """Storage Format (XHTML) 内の structured-macro および conf-macro を集計する.

    Spec 0007 / 0009 共通の集計ロジック。
    `ac:name` および `data-macro-name` をカウントして辞書で返す。
    """
    if not storage_xhtml or not storage_xhtml.strip():
        return {}

    counts: Dict[str, int] = {}
    soup = BeautifulSoup(storage_xhtml, "html.parser")

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

    return counts


def classify_restriction(restrictions_data: dict) -> Tuple[bool, List[str], List[str]]:
    """`get_restrictions` のレスポンスから、個別制限の有無・Read Subjects・Read+Write Subjects を抽出する.

    Returns:
        (has_restriction, read_subjects, readwrite_subjects)
        主体表記例: "user:username", "group:groupname"
    """
    if not isinstance(restrictions_data, dict):
        return False, [], []

    read_subjects: List[str] = []
    readwrite_subjects: List[str] = []

    def _extract_subjects(data_sec: dict) -> List[str]:
        subjects: List[str] = []
        if not isinstance(data_sec, dict):
            return subjects
        restr = data_sec.get("restrictions", {})
        if isinstance(restr, dict):
            # Users
            user_data = restr.get("user", {})
            if isinstance(user_data, dict):
                for u in user_data.get("results", []):
                    if isinstance(u, dict):
                        username = u.get("username", "").strip() or u.get("displayName", "").strip()
                        if username:
                            subjects.append(f"user:{username}")
            # Groups
            group_data = restr.get("group", {})
            if isinstance(group_data, dict):
                for g in group_data.get("results", []):
                    if isinstance(g, dict):
                        gname = g.get("name", "").strip()
                        if gname:
                            subjects.append(f"group:{gname}")
        return subjects

    read_subjects = _extract_subjects(restrictions_data.get("read", {}))
    readwrite_subjects = _extract_subjects(restrictions_data.get("update", {}))

    has_restriction = bool(read_subjects or readwrite_subjects)
    return has_restriction, read_subjects, readwrite_subjects


def inline_marks(annotation: Annotation, ascii: bool = False) -> str:
    """ノードの付帯情報からインライン表記文字列を生成する.

    設計に基づくマーク規則:
      - 個別制限あり: 🔒 (ASCII: [R])、取得失敗時: 🔒? (ASCII: [R]?)
      - 添付: 📎N (ASCII: att:N)、取得失敗時: 📎? (ASCII: att:?)
      - マクロ: ⚙N (ASCII: mac:N)、取得失敗時: ⚙? (ASCII: mac:?)
      - 最終更新日: (YYYY-MM-DD)、取得失敗時: (?)
    """
    parts: List[str] = []

    # 1. 制限マーク
    if "restriction" in annotation.failed_fields:
        parts.append("[R]?" if ascii else "🔒?")
    elif annotation.has_restriction is True:
        parts.append("[R]" if ascii else "🔒")

    # 2. 添付件数
    if "attachments" in annotation.failed_fields:
        parts.append("att:?" if ascii else "📎?")
    elif annotation.attachment_count is not None and annotation.attachment_count > 0:
        parts.append(f"att:{annotation.attachment_count}" if ascii else f"📎{annotation.attachment_count}")

    # 3. マクロ種別数
    if "macros" in annotation.failed_fields:
        parts.append("mac:?" if ascii else "⚙?")
    elif annotation.macros is not None and len(annotation.macros) > 0:
        macro_types = len(annotation.macros)
        parts.append(f"mac:{macro_types}" if ascii else f"⚙{macro_types}")

    # 4. 最終更新日
    if "last_modified" in annotation.failed_fields:
        parts.append("(?)")
    elif annotation.last_modified:
        # ISO 8601 文字列から YYYY-MM-DD 部分を抽出
        lm = annotation.last_modified.split("T")[0] if "T" in annotation.last_modified else annotation.last_modified
        parts.append(f"({lm})")

    if not parts:
        return ""
    return " " + "  ".join(parts)
