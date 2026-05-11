from bs4 import BeautifulSoup, Tag
import html
import re

class MarkdownConverter:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.macro_handlers = {
            "conf-macro": self._handle_macro,
            "ac:structured-macro": self._handle_structured_macro
        }

    def convert(self, html_content: str, level: int = 1) -> str:
        soup = BeautifulSoup(html_content, "html.parser")
        return self._walk(soup, level)

    def _walk(self, node, level: int) -> str:
        md = ""
        for child in node.children:
            if isinstance(child, Tag):
                md += self._process_tag(child, level)
            else:
                md += html.unescape(str(child))
        return md

    def _process_tag(self, tag: Tag, level: int) -> str:
        name = tag.name

        # Headings
        if re.match(r'h[1-6]', name):
            h_level = int(name[1]) + level - 1
            return f"\n{'#' * h_level} {self._walk(tag, level)}\n"

        if name == 'p':
            return f"\n{self._walk(tag, level)}\n"

        if name == 'br':
            return "\n"

        if name in ['strong', 'b']:
            return f"**{self._walk(tag, level)}**"

        if name in ['em', 'i']:
            return f"*{self._walk(tag, level)}*"

        if name == 'code':
            return f"`{self._walk(tag, level)}`"

        if name == 'ul':
            return f"\n{self._walk(tag, level)}\n"

        if name == 'ol':
            return f"\n{self._walk(tag, level)}\n"

        if name == 'li':
            parent = tag.parent
            if parent and parent.name == 'ol':
                # Simple implementation, doesn't track index perfectly for nested
                return f"1. {self._walk(tag, level)}\n"
            else:
                return f"- {self._walk(tag, level)}\n"

        if name == 'table':
            return self._handle_table(tag, level)

        if name == 'a':
            href = tag.get('href', '')
            if href.startswith('/'):
                href = self.base_url + href
            return f"[{self._walk(tag, level)}]({href})"

        # Confluence Macros
        if tag.get('class') and 'conf-macro' in tag.get('class'):
            return self._handle_macro(tag)

        if name == 'ac:structured-macro':
            return self._handle_structured_macro(tag)

        # Default: just process children
        return self._walk(tag, level)

    def _handle_table(self, table: Tag, level: int) -> str:
        rows = []
        for tr in table.find_all('tr', recursive=False):
            cols = []
            for cell in tr.find_all(['th', 'td'], recursive=False):
                # Clean up cell content for markdown table
                cell_text = self._walk(cell, level).strip().replace('\n', '<br>')
                cols.append(cell_text)
            rows.append(cols)

        if not rows:
            return ""

        md = "\n"
        # Header
        md += "| " + " | ".join(rows[0]) + " |\n"
        # Separator
        md += "| " + " | ".join(["---"] * len(rows[0])) + " |\n"
        # Body
        for row in rows[1:]:
            # Pad row if it has fewer columns than header
            if len(row) < len(rows[0]):
                row += [""] * (len(rows[0]) - len(row))
            md += "| " + " | ".join(row[:len(rows[0])]) + " |\n"

        return md + "\n"

    def _handle_macro(self, tag: Tag) -> str:
        macro_name = tag.get('data-macro-name')
        if macro_name == 'code':
            content = tag.find('pre')
            if content:
                return f"\n```\n{content.get_text()}\n```\n"
        return f"\n[Macro: {macro_name}]\n"

    def _handle_structured_macro(self, tag: Tag) -> str:
        macro_name = tag.get('ac:name')
        if macro_name == 'code':
            plain_text_body = tag.find('ac:plain-text-body')
            if plain_text_body:
                # Use CDATA if present
                content = plain_text_body.get_text()
                return f"\n```\n{content}\n```\n"
        elif macro_name == 'plantuml':
            plain_text_body = tag.find('ac:plain-text-body')
            if plain_text_body:
                content = plain_text_body.get_text()
                return f"\n```plantuml\n{content}\n```\n"

        return f"\n[Structured Macro: {macro_name}]\n"
