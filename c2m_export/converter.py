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
        AIナレッジ向けに有用な情報を抽出し、Markdownに変換。
        """
        macro_name = tag.get('ac:name')

        # 1. コードブロック系マクロ
        if macro_name == 'code':
            lang = ""
            lang_param = tag.find('ac:parameter', attrs={'ac:name': 'language'})
            if lang_param:
                lang = lang_param.get_text().strip()
            plain_text_body = tag.find('ac:plain-text-body')
            if plain_text_body:
                content = plain_text_body.get_text()
                return f"\n```{lang}\n{content}\n```\n"

        elif macro_name in ['plantuml', 'plantumlrender']:
            plain_text_body = tag.find('ac:plain-text-body')
            if plain_text_body:
                content = plain_text_body.get_text()
                return f"\n```plantuml\n{content}\n```\n"

        # 2. リッチテキストボディを持つマクロ (再帰的に処理)
        elif macro_name in ['expand', 'note', 'info', 'tip', 'panel', 'details']:
            title = ""
            title_param = tag.find('ac:parameter', attrs={'ac:name': 'title'})
            if title_param:
                title = title_param.get_text().strip()

            body_md = ""
            rich_text_body = tag.find('ac:rich-text-body')
            if rich_text_body:
                # ボディ内を再帰的にMarkdown変換
                body_md = self._walk(rich_text_body, 1).strip()

            # AIへのインプットとして有用な形式で組み立て
            result = "\n"
            if title:
                result += f"**{title}**\n"
            if body_md:
                result += f"{body_md}\n"
            return result

        # 3. 単一のパラメータや単純な情報を抽出するマクロ
        elif macro_name == 'status':
            title_param = tag.find('ac:parameter', attrs={'ac:name': 'title'})
            if title_param:
                return f" [{title_param.get_text().strip()}] "
            return ""

        elif macro_name == 'jira':
            # キーまたはJQLを抽出
            key_param = tag.find('ac:parameter', attrs={'ac:name': 'key'})
            if key_param:
                return f" [{key_param.get_text().strip()}] "
            jql_param = tag.find('ac:parameter', attrs={'ac:name': 'jqlQuery'})
            if jql_param:
                return f" [JIRA: {jql_param.get_text().strip()}] "
            return f" [Macro: {macro_name}] "

        elif macro_name == 'include':
            # 埋め込み先のページタイトルを抽出
            ri_page = tag.find('ri:page')
            if ri_page and ri_page.get('ri:content-title'):
                return f"\n[Include: {ri_page.get('ri:content-title')}]\n"

        # 4. AIインプットとして不要、または動的すぎてStorage Formatから抽出困難なマクロ
        elif macro_name in ['toc', 'anchor', 'pagetree', 'children', 'contentbylabel']:
            return ""

        # 未知のマクロはプレースホルダを返す
        return f"\n[Structured Macro: {macro_name}]\n"
