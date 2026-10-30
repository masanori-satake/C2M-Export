"""ページツリーのレンダラ（text / markdown / json）純粋ロジックモジュール."""

import json
from dataclasses import asdict
from typing import Any, Dict, List

from c2m_export.page_tree.annotations import inline_marks
from c2m_export.page_tree.models import TreeNode, TreeResult


def render_text(result: TreeResult, ascii: bool = False) -> str:
    """テキスト（罫線ツリー）形式でツリーを描画する."""
    lines: List[str] = []

    def _render_node(node: TreeNode, prefix: str = "", is_last: bool = True, is_root: bool = False):
        mark = inline_marks(node.annotation, ascii=ascii)
        line_content = f"{node.title}  [id:{node.page_id}]{mark}"

        if is_root:
            lines.append(line_content)
            next_prefix = ""
        else:
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{line_content}")
            next_prefix = prefix + ("    " if is_last else "│   ")

        child_count = len(node.children)
        for idx, child in enumerate(node.children):
            _render_node(child, prefix=next_prefix, is_last=(idx == child_count - 1), is_root=False)

    for idx, root in enumerate(result.roots):
        if idx > 0:
            lines.append("")
        _render_node(root, prefix="", is_last=True, is_root=True)

    return "\n".join(lines)


def render_markdown(result: TreeResult, ascii: bool = False) -> str:
    """Markdown（箇条書きツリー + 付帯情報詳細表）形式でツリーを描画する."""
    lines: List[str] = []

    def _render_node_md(node: TreeNode, indent_level: int):
        indent = "  " * indent_level
        mark = inline_marks(node.annotation, ascii=ascii)
        lines.append(f"{indent}- {node.title} `{node.page_id}`{mark}")
        for child in node.children:
            _render_node_md(child, indent_level + 1)

    for idx, root in enumerate(result.roots):
        if idx > 0:
            lines.append("")
        _render_node_md(root, indent_level=0)

    # 全ノードを平坦に収集（別表生成用）
    all_nodes: List[TreeNode] = []

    def _collect_all(node: TreeNode):
        all_nodes.append(node)
        for child in node.children:
            _collect_all(child)

    for root in result.roots:
        _collect_all(root)

    # 別表: アクセス制限詳細
    if "restriction" in result.included_annotations:
        restricted_nodes = [n for n in all_nodes if n.annotation.has_restriction is True]
        if restricted_nodes:
            lines.append("")
            lines.append("## アクセス制限詳細")
            lines.append("")
            lines.append("| page_id | title | Read | Read+Write |")
            lines.append("|---|---|---|---|")
            for n in restricted_nodes:
                r_subj = ", ".join(n.annotation.read_subjects) if n.annotation.read_subjects else "-"
                rw_subj = ", ".join(n.annotation.readwrite_subjects) if n.annotation.readwrite_subjects else "-"
                lines.append(f"| {n.page_id} | {n.title} | {r_subj} | {rw_subj} |")

    # 別表: マクロ使用
    if "macros" in result.included_annotations:
        macro_nodes = [n for n in all_nodes if n.annotation.macros]
        if macro_nodes:
            lines.append("")
            lines.append("## マクロ使用")
            lines.append("")
            lines.append("| page_id | title | マクロ（回数） |")
            lines.append("|---|---|---|")
            for n in macro_nodes:
                if n.annotation.macros:
                    macro_str = ", ".join([f"{k}({v})" for k, v in sorted(n.annotation.macros.items())])
                else:
                    macro_str = "-"
                lines.append(f"| {n.page_id} | {n.title} | {macro_str} |")

    return "\n".join(lines)


def _node_to_dict(node: TreeNode) -> Dict[str, Any]:
    ann_dict = asdict(node.annotation)
    # 不用な空リスト等はきれいに表現
    return {
        "page_id": node.page_id,
        "title": node.title,
        "annotation": ann_dict,
        "children": [_node_to_dict(c) for c in node.children],
    }


def render_json(result: TreeResult) -> str:
    """構造化 JSON 形式でツリーを描画する."""
    data: Dict[str, Any] = {
        "schema_version": result.schema_version,
        "status": result.status,
    }

    if result.status == "error":
        if result.error:
            data["error"] = result.error
        return json.dumps(data, ensure_ascii=False, indent=2)

    data["scope"] = result.scope
    data["included_annotations"] = result.included_annotations
    data["total_pages"] = result.total_pages
    data["roots"] = [_node_to_dict(r) for r in result.roots]
    data["uncertainties"] = result.uncertainties

    return json.dumps(data, ensure_ascii=False, indent=2)


def render_tree(result: TreeResult, fmt: str = "text", ascii: bool = False) -> str:
    """指定のフォーマット（text | markdown | json）でレンダリングするディスパッチャ."""
    if fmt == "json":
        return render_json(result)
    elif fmt == "markdown":
        return render_markdown(result, ascii=ascii)
    else:
        return render_text(result, ascii=ascii)
