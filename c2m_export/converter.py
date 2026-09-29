from bs4 import BeautifulSoup, Tag
import html
import re
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)


class MarkdownConverter:
    """
    ConfluenceのStorage Format (XHTML) を Markdownに変換するクラス。
    再帰的なタグ探索と、特定のマクロ（Code, PlantUML）に対するカスタムハンドラを実装。
    """

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.macro_handlers = {"conf-macro": self._handle_macro, "ac:structured-macro": self._handle_structured_macro}

    def convert(self, html_content: str, level: int = 1) -> str:
        """
        HTML文字列をMarkdownに変換するエントリーポイント。
        level引数は、ページツリーの深さに応じて見出しレベルを調整するために使用。
        """
        soup = BeautifulSoup(html_content, "html.parser")
        return self._walk(soup, level)

    def _walk(self, node, level: int, list_depth: int = 0) -> str:
        """
        DOMツリーを再帰的に巡回してMarkdown文字列を組み立てる。

        list_depth はリストのネスト深さ（0 = リスト外）。インデント制御に用いる。
        """
        md = ""
        for child in node.children:
            if isinstance(child, Tag):
                md += self._process_tag(child, level, list_depth)
            else:
                md += html.unescape(str(child))
        return md

    def _process_tag(self, tag: Tag, level: int, list_depth: int = 0) -> str:
        """
        タグごとの変換ルールを定義。

        list_depth はリストのネスト深さ。ネストしたリスト項目のインデント付与に用いる。
        個別の複雑要素（表・画像・リンク・マクロ等）は例外を握り込み、
        変換全体を止めずに近似結果または空文字を返す（堅牢性 / 要件14）。
        """
        name = tag.name

        # 見出し: ページ階層に応じて#の数を増やす。ただしMarkdownの仕様上、最大6まで。
        if re.match(r"h[1-6]", name):
            h_level = min(6, int(name[1]) + level - 1)
            return f"\n{'#' * h_level} {self._walk(tag, level, list_depth)}\n"

        if name == "p":
            return f"\n{self._walk(tag, level, list_depth)}\n"

        if name == "br":
            return "\n"

        if name in ["strong", "b"]:
            return f"**{self._walk(tag, level, list_depth)}**"

        if name in ["em", "i"]:
            return f"*{self._walk(tag, level, list_depth)}*"

        # 打ち消し線（GFM）
        if name in ["del", "s", "strike"]:
            return f"~~{self._walk(tag, level, list_depth)}~~"

        # 下線・上付き・下付きは Markdown に専用構文がないためテキストのみ残す（情報非欠損）
        if name in ["u", "sup", "sub", "ins"]:
            return self._walk(tag, level, list_depth)

        if name == "code":
            return f"`{self._walk(tag, level, list_depth)}`"

        # 水平線
        if name == "hr":
            return "\n---\n"

        # 引用: 内部を変換し、各非空行の先頭に "> " を付与
        if name == "blockquote":
            inner = self._walk(tag, level, list_depth).strip()
            quoted = "\n".join(f"> {line}" if line.strip() else ">" for line in inner.split("\n"))
            return f"\n{quoted}\n"

        # マクロ外の pre 単体はコードブロック化（フェンスは動的伸長）
        if name == "pre":
            return self._wrap_code_block(tag.get_text())

        # 定義リスト: dt を用語、dd を説明として出力
        if name == "dl":
            return self._handle_definition_list(tag, level)

        if name in ["ul", "ol"]:
            # リストコンテナはネスト深さを 1 段深くして子を処理
            return f"\n{self._walk(tag, level, list_depth + 1)}\n"

        if name == "li":
            return self._handle_list_item(tag, level, list_depth)

        if name == "table":
            return self._safe(self._handle_table, tag, level)

        if name == "img":
            return self._safe(self._handle_img, tag, level)

        if name == "a":
            href = tag.get("href", "")
            # コンテキストパスを含む絶対URLに変換
            if href.startswith("/"):
                href = self.base_url + href
            return f"[{self._walk(tag, level, list_depth)}]({href})"

        # Confluence 固有要素
        if name == "ac:image":
            return self._safe(self._handle_ac_image, tag, level)

        if name == "ac:link":
            return self._safe(self._handle_ac_link, tag, level)

        if name == "ac:emoticon":
            return self._handle_emoticon(tag)

        if name == "ac:task-list":
            return self._safe(self._handle_task_list, tag, level)

        # レイアウトは段組みの見た目を捨て、中身を縦積みでテキストとして残す
        if name in ["ac:layout", "ac:layout-section", "ac:layout-cell"]:
            return self._walk(tag, level, list_depth)

        # クラス名によるマクロ判定
        if tag.get("class") and "conf-macro" in tag.get("class"):
            return self._safe(self._handle_macro, tag, level)

        # 名前空間付きマクロタグの処理
        if name == "ac:structured-macro":
            return self._safe(self._handle_structured_macro, tag, level)

        # 未定義のタグは中身を再帰的に処理
        return self._walk(tag, level, list_depth)

    def _safe(self, handler, tag: Tag, level: int) -> str:
        """
        個別ハンドラを例外から保護して実行する（堅牢性 / 要件14）。

        想定外の構造で例外が発生しても変換全体を止めず、空文字を返しつつ
        「現象・原因・対処方法」を日本語ログに残す。
        """
        try:
            return handler(tag, level)
        except Exception as e:
            logger.warning(
                f"要素の変換に失敗しました（現象）。詳細: {handler.__name__} でエラー: {e}（原因）。"
                f"該当要素をスキップして処理を継続します（対処方法）"
            )
            return ""

    def _collect_table_rows(self, table: Tag):
        """
        表から行（tr）を thead → tbody → tfoot → table 直下 の順で収集する。

        Confluence の Storage Format は tr を tbody 等でラップすることが多く、
        table 直下だけを見ると tr が 0 件になり表が消失する。これを防ぐため、
        各セクションコンテナの「直下」の tr のみを対象に収集する。
        ネストした表の tr を親テーブルに取り込まないよう recursive=False を用いる。

        戻り値: (header_rows, body_rows)
        """

        def direct_trs(container):
            return container.find_all("tr", recursive=False)

        header_trs = []
        body_trs = []

        thead = table.find("thead", recursive=False)
        if thead:
            header_trs = direct_trs(thead)

        tbodies = table.find_all("tbody", recursive=False)
        tfoots = table.find_all("tfoot", recursive=False)

        for tbody in tbodies:
            body_trs.extend(direct_trs(tbody))
        for tfoot in tfoots:
            body_trs.extend(direct_trs(tfoot))

        # thead/tbody/tfoot のいずれにも属さない table 直下の tr も拾う
        direct = direct_trs(table)
        if direct:
            body_trs = direct + body_trs if not (thead or tbodies) else body_trs + direct

        # thead が無い場合、先頭行が th を含むならヘッダーとして扱う
        if not header_trs and body_trs:
            first = body_trs[0]
            if first.find("th", recursive=False):
                header_trs = [first]
                body_trs = body_trs[1:]

        return header_trs, body_trs

    def _table_row_cells(self, tr: Tag, level: int):
        """tr から各セルのテキストを取り出す。セル内の | と改行を安全化する。"""
        cols = []
        for cell in tr.find_all(["th", "td"], recursive=False):
            cell_text = self._walk(cell, level).strip()
            # 表構造を壊さないよう、| をエスケープし、改行を <br> に置換
            cell_text = cell_text.replace("|", "\\|").replace("\n", "<br>")
            # colspan があれば、その列数ぶんセルを複製せず空セルで補完し列整合を保つ
            try:
                span = int(cell.get("colspan", 1))
            except (TypeError, ValueError):
                span = 1
            cols.append(cell_text)
            for _ in range(max(0, span - 1)):
                cols.append("")
        return cols

    def _handle_table(self, table: Tag, level: int) -> str:
        """
        HTMLテーブルをMarkdownテーブルに変換。

        thead/tbody/tfoot を考慮して行を収集し、ヘッダー行を決定する。
        ヘッダーが特定できない場合でも、情報欠損を防ぐため空ヘッダー行 + 区切り線を出力する。
        セル内の | はエスケープ、改行は <br> に置換して表の破綻を防ぐ。
        """
        header_trs, body_trs = self._collect_table_rows(table)

        header_rows = [self._table_row_cells(tr, level) for tr in header_trs]
        body_rows = [self._table_row_cells(tr, level) for tr in body_trs]

        if not header_rows and not body_rows:
            return ""

        # 列数は全行の最大値に合わせる（colspan 補完後）
        all_rows = header_rows + body_rows
        col_count = max(len(r) for r in all_rows) if all_rows else 0
        if col_count == 0:
            return ""

        def pad(row):
            return row + [""] * (col_count - len(row))

        md = "\n"
        if header_rows:
            header = pad(header_rows[0])
            md += "| " + " | ".join(header) + " |\n"
        else:
            # ヘッダー不明時は空ヘッダー行で区切り線を成立させる（情報欠損防止）
            md += "| " + " | ".join([""] * col_count) + " |\n"

        md += "| " + " | ".join(["---"] * col_count) + " |\n"

        # thead に複数行がある場合、2 行目以降はボディ扱いにする
        remaining_header = header_rows[1:] if len(header_rows) > 1 else []
        for row in remaining_header + body_rows:
            md += "| " + " | ".join(pad(row)) + " |\n"

        return md + "\n"

    def _handle_list_item(self, tag: Tag, level: int, list_depth: int) -> str:
        """
        リスト項目（li）を、ネスト深さに応じたインデント付きで出力する。

        項目直下のインライン内容と子リスト（ul/ol）を分離し、
        子リストは本文の下に、さらに深いインデントで出力する。
        """
        # 親項目の本文開始位置に揃える（番号リストは3列、箇条書きは2列）。
        parent_lists = tag.find_parents(["ul", "ol"])
        indent = " " * sum(3 if parent.name == "ol" else 2 for parent in parent_lists[1:])
        marker = "1. " if (tag.parent and tag.parent.name == "ol") else "- "

        # 子リストとそれ以外を分離
        child_lists = []
        inline_parts = ""
        for child in tag.children:
            if isinstance(child, Tag) and child.name in ("ul", "ol"):
                # 子リストは現在の深さのまま処理（ul/ol 側で +1 される）
                child_lists.append(self._process_tag(child, level, list_depth))
            elif isinstance(child, Tag):
                inline_parts += self._process_tag(child, level, list_depth)
            else:
                inline_parts += html.unescape(str(child))

        body = inline_parts.strip().replace("\n", " ")
        result = f"{indent}{marker}{body}\n"
        for cl in child_lists:
            # 子リストの各行はそのままのインデントで続ける（ul/ol 側でインデント済み）
            result += cl.strip("\n") + "\n"
        return result

    def _handle_definition_list(self, tag: Tag, level: int) -> str:
        """
        定義リスト（dl/dt/dd）を情報欠損なく出力する。
        Markdown に専用構文がないため、用語を太字、説明を続く行として表現する。
        """
        parts = []
        for child in tag.find_all(["dt", "dd"], recursive=False):
            text = self._walk(child, level).strip()
            if not text:
                continue
            if child.name == "dt":
                parts.append(f"**{text}**")
            else:
                parts.append(text)
        if not parts:
            return ""
        return "\n" + "\n".join(parts) + "\n"

    def _format_destination(self, destination: str) -> str:
        """空白や丸括弧を含む参照先を山括弧で囲み、Markdown 構文を保つ。"""
        if any(char in destination for char in " ()"):
            return f"<{destination}>"
        return destination

    def _handle_img(self, tag: Tag, level: int) -> str:
        """<img> を Markdown 画像記法に変換する。相対 src は絶対 URL 化。"""
        src = tag.get("src", "")
        if src.startswith("/"):
            src = self.base_url + src
        alt = tag.get("alt", "").strip()
        if not src:
            # src が無ければ alt テキストのみ残す（情報非欠損）
            return alt
        return f"![{alt}]({self._format_destination(src)})"

    def _handle_ac_image(self, tag: Tag, level: int) -> str:
        """
        Confluence の <ac:image> を変換する。
        ri:attachment（添付ファイル名）または ri:url（外部URL）を参照として残す。
        """
        alt = tag.get("ac:alt", "").strip()

        attachment = tag.find("ri:attachment")
        if attachment and attachment.get("ri:filename"):
            filename = attachment.get("ri:filename")
            alt_text = alt or filename
            return f"![{alt_text}]({self._format_destination(filename)})"

        ri_url = tag.find("ri:url")
        if ri_url and ri_url.get("ri:value"):
            url = ri_url.get("ri:value")
            return f"![{alt}]({self._format_destination(url)})"

        # 参照が取れない場合でも alt があれば残す
        return alt

    def _build_page_url(self, space_key: str, title: str) -> str:
        """Data Center のページ表示 URL を組み立てる。"""
        return f"{self.base_url}/display/{space_key}/{quote(title)}"

    def _handle_ac_link(self, tag: Tag, level: int) -> str:
        """
        Confluence の <ac:link> を変換する。

        - ri:page: 表示テキスト（あれば優先）とタイトルを残す。space-key が判明する場合のみ URL 付与（A案）。
        - ri:user: @ユーザー名 のテキストで残す。
        - ファイル内アンカー解決・相対パス解決は行わない。
        """
        # 表示テキスト（link-body / plain-text-link-body）
        display = ""
        body = tag.find(["ac:link-body", "ac:plain-text-link-body"])
        if body:
            display = self._walk(body, level).strip() if body.name == "ac:link-body" else body.get_text().strip()

        ri_page = tag.find("ri:page")
        if ri_page:
            title = ri_page.get("ri:content-title", "").strip()
            space_key = ri_page.get("ri:space-key", "").strip()
            text = display or title
            if not text:
                return ""
            if space_key and title:
                return f"[{text}]({self._build_page_url(space_key, title)})"
            # space-key 不明時はタイトル（テキスト）のみ残す（A案・情報非欠損）
            return text

        ri_user = tag.find("ri:user")
        if ri_user:
            name = display or ri_user.get("ri:username", "") or ri_user.get("ri:userkey", "")
            name = name.strip()
            return f"@{name}" if name else ""

        ri_attachment = tag.find("ri:attachment")
        if ri_attachment and ri_attachment.get("ri:filename"):
            filename = ri_attachment.get("ri:filename")
            text = display or filename
            return f"[{text}]({self._format_destination(filename)})"

        # 上記いずれでもない場合、表示テキストがあれば残す
        return display

    def _handle_emoticon(self, tag: Tag) -> str:
        """絵文字（ac:emoticon）を Unicode またはショートコードで残す。"""
        fallback = tag.get("ac:emoji-fallback")
        if fallback:
            return fallback
        name = tag.get("ac:name")
        if name:
            return f":{name}:"
        return ""

    def _handle_task_list(self, tag: Tag, level: int) -> str:
        """
        タスクリスト（ac:task-list / ac:task）をチェックボックスリストに変換する。
        ac:task-status が complete なら [x]、それ以外は [ ]。
        """
        lines = []
        for task in tag.find_all("ac:task", recursive=False):
            status = task.find("ac:task-status")
            checked = status and status.get_text().strip().lower() == "complete"
            body = task.find("ac:task-body")
            body_md = self._walk(body, level).strip().replace("\n", " ") if body else ""
            box = "[x]" if checked else "[ ]"
            lines.append(f"- {box} {body_md}")
        if not lines:
            return ""
        return "\n" + "\n".join(lines) + "\n"

    def _wrap_code_block(self, content: str, lang: str = "") -> str:
        """
        コード文字列をフェンスで囲む。

        中身に含まれる最長の連続バッククォートより 1 つ以上長いフェンスを用いることで、
        フェンスが途中で割れて閉じフェンスが失われ、後続テキスト（同一ページの後続要素や
        次ページの本文）をコードとして巻き込むのを防ぐ（CommonMark 準拠）。
        開きフェンスと閉じフェンスの長さは同一変数から生成するため必ず一致する。
        """
        # 中身に現れる連続バッククォートの最長長を求める
        longest = 0
        for m in re.finditer(r"`+", content):
            longest = max(longest, len(m.group(0)))
        # 標準は 3 連。中身により長いバッククォート列があればそれより 1 つ長くする
        fence_len = max(3, longest + 1)
        fence = "`" * fence_len
        return f"\n{fence}{lang}\n{content}\n{fence}\n"

    def _handle_macro(self, tag: Tag, level: int) -> str:
        """
        旧来の形式のマクロ（conf-macro）を処理。
        """
        macro_name = tag.get("data-macro-name")
        if macro_name in ["code", "noformat"]:
            content = tag.find("pre")
            if content:
                return self._wrap_code_block(content.get_text())

        # 未知の旧マクロはAIナレッジ向けに不要なケースが多いため空文字を返す
        return ""

    def _handle_structured_macro(self, tag: Tag, level: int) -> str:
        """
        名前空間付きの構造化マクロを処理。
        AIナレッジ向けに有用な情報を抽出し、Markdownに変換。
        """
        macro_name = tag.get("ac:name")

        # 1. 特殊な情報抽出が必要なマクロ
        if macro_name == "status":
            title_param = tag.find("ac:parameter", attrs={"ac:name": "title"})
            if title_param:
                return f" 【ステータス: {title_param.get_text().strip()}】 "
            return ""

        if macro_name == "jira":
            key_param = tag.find("ac:parameter", attrs={"ac:name": "key"})
            if key_param:
                return f" 【JIRA課題: {key_param.get_text().strip()}】 "
            jql_param = tag.find("ac:parameter", attrs={"ac:name": "jqlQuery"})
            if jql_param:
                return f" 【JIRAクエリ: {jql_param.get_text().strip()}】 "
            return ""

        if macro_name == "include":
            ri_page = tag.find("ri:page")
            if ri_page and ri_page.get("ri:content-title"):
                return f"\n(他ページからの埋め込み内容: {ri_page.get('ri:content-title')})\n"
            return ""

        # 2. AIインプットとして不要なナビゲーション・動的マクロ
        if macro_name in ["toc", "anchor", "pagetree", "children", "contentbylabel"]:
            return ""

        # 3. 汎用的なボディ処理 (名前を問わず構造に基づいて変換)

        # プレーンテキストボディ (Code, PlantUML等)
        plain_text_body = tag.find("ac:plain-text-body")
        if plain_text_body:
            lang = ""
            if macro_name in ["plantuml", "plantumlrender"]:
                lang = "plantuml"
            else:
                lang_param = tag.find("ac:parameter", attrs={"ac:name": "language"})
                if lang_param:
                    lang = lang_param.get_text().strip()

            content = plain_text_body.get_text()
            return self._wrap_code_block(content, lang)

        # リッチテキストボディ (expand, note, info, panel, details等)
        rich_text_body = tag.find("ac:rich-text-body")
        if rich_text_body:
            title = ""
            title_param = tag.find("ac:parameter", attrs={"ac:name": "title"})
            if title_param:
                title = title_param.get_text().strip()

            body_md = self._walk(rich_text_body, level).strip()

            result = "\n"
            if title:
                result += f"**{title}**\n"
            if body_md:
                result += f"{body_md}\n"
            return result

        # 4. ボディも特殊パラメータもないマクロは空文字を返す
        return ""
