from bs4 import BeautifulSoup, Tag
import html
import re

class MarkdownConverter:
    """
    ConfluenceのStorage Format (XHTML) を Markdownに変換するクラス。
    再帰的なタグ探索と、特定のマクロ（Code, PlantUML）に対するカスタムハンドラを実装。
    """
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.macro_handlers = {
            "conf-macro": self._handle_macro,
            "ac:structured-macro": self._handle_structured_macro
        }

    def convert(self, html_content: str, level: int = 1) -> str:
        """
        HTML文字列をMarkdownに変換するエントリーポイント。
        level引数は、ページツリーの深さに応じて見出しレベルを調整するために使用。
        """
        soup = BeautifulSoup(html_content, "html.parser")
        return self._walk(soup, level)

    def _walk(self, node, level: int) -> str:
        """
        DOMツリーを再帰的に巡回してMarkdown文字列を組み立てる。
        """
        md = ""
        for child in node.children:
            if isinstance(child, Tag):
                md += self._process_tag(child, level)
            else:
                md += html.unescape(str(child))
        return md

    def _process_tag(self, tag: Tag, level: int) -> str:
        """
        タグごとの変換ルールを定義。
        """
        name = tag.name

        # 見出し: ページ階層に応じて#の数を増やす。ただしMarkdownの仕様上、最大6まで。
        if re.match(r'h[1-6]', name):
            h_level = min(6, int(name[1]) + level - 1)
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
                # ネストされたリストでのインデックス制御は簡易実装
                return f"1. {self._walk(tag, level)}\n"
            else:
                return f"- {self._walk(tag, level)}\n"

        if name == 'table':
            return self._handle_table(tag, level)

        if name == 'a':
            href = tag.get('href', '')
            # コンテキストパスを含む絶対URLに変換
            if href.startswith('/'):
                href = self.base_url + href
            return f"[{self._walk(tag, level)}]({href})"

        # クラス名によるマクロ判定
        if tag.get('class') and 'conf-macro' in tag.get('class'):
            return self._handle_macro(tag)

        # 名前空間付きマクロタグの処理
        if name == 'ac:structured-macro':
            return self._handle_structured_macro(tag)

        # 未定義のタグは中身を再帰的に処理
        return self._walk(tag, level)

    def _handle_table(self, table: Tag, level: int) -> str:
        """
        HTMLテーブルをMarkdownテーブルに変換。
        セル内の改行はテーブル構造を壊さないよう<br>に置換。
        """
        rows = []
        for tr in table.find_all('tr', recursive=False):
            cols = []
            for cell in tr.find_all(['th', 'td'], recursive=False):
                cell_text = self._walk(cell, level).strip().replace('\n', '<br>')
                cols.append(cell_text)
            rows.append(cols)

        if not rows:
            return ""

        md = "\n"
        md += "| " + " | ".join(rows[0]) + " |\n"
        md += "| " + " | ".join(["---"] * len(rows[0])) + " |\n"
        for row in rows[1:]:
            # 列数が不足している場合の補正
            if len(row) < len(rows[0]):
                row += [""] * (len(rows[0]) - len(row))
            md += "| " + " | ".join(row[:len(rows[0])]) + " |\n"

        return md + "\n"

    def _handle_macro(self, tag: Tag) -> str:
        """
        旧来の形式のマクロ（conf-macro）を処理。
        """
        macro_name = tag.get('data-macro-name')
        if macro_name == 'code':
            content = tag.find('pre')
            if content:
                return f"\n```\n{content.get_text()}\n```\n"
        return f"\n[Macro: {macro_name}]\n"

    def _handle_structured_macro(self, tag: Tag) -> str:
        """
        名前空間付きの構造化マクロを処理。
        AIナレッジ向けにコードと言語情報を適切に抽出。
        """
        macro_name = tag.get('ac:name')
        if macro_name == 'code':
            # 言語設定の抽出（シンタックスハイライト用）
            lang = ""
            lang_param = tag.find('ac:parameter', attrs={'ac:name': 'language'})
            if lang_param:
                lang = lang_param.get_text().strip()

            plain_text_body = tag.find('ac:plain-text-body')
            if plain_text_body:
                content = plain_text_body.get_text()
                return f"\n```{lang}\n{content}\n```\n"
        elif macro_name == 'plantuml':
            # PlantUML定義をコードブロックとして出力
            plain_text_body = tag.find('ac:plain-text-body')
            if plain_text_body:
                content = plain_text_body.get_text()
                return f"\n```plantuml\n{content}\n```\n"

        return f"\n[Structured Macro: {macro_name}]\n"
