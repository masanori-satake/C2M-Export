import streamlit as st
import logging
import threading
import tempfile
import os
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

from c2m_export.config import Config
from c2m_export.confluence import ConfluenceClient
from c2m_export.converter import MarkdownConverter
from c2m_export.cli import export_tree
from c2m_export.utils import create_zip_file, sanitize_filename, bytes_to_mb, get_unique_in_memory_filename

# グローバルロック
export_lock = threading.Lock()

class StreamlitLogHandler(logging.Handler):
    def __init__(self, placeholder):
        super().__init__()
        self.placeholder = placeholder
        self.log_content = ""

    def emit(self, record):
        msg = self.format(record)
        self.log_content += msg + "\n"
        self.placeholder.code(self.log_content)

def main():
    st.set_page_config(page_title="C2M-Export Web", layout="wide")

    # パスワードの伏字表示から「目」のアイコン（表示切替）を隠すためのCSS
    st.markdown("""
        <style>
        div[data-testid="stTextInput"] button {
            display: none;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("Confluence to Markdown Exporter")

    # 設定の読み込み
    config = Config()
    try:
        config.load()
    except Exception:
        pass

    # セッション状態の初期化
    if "root_page_ids" not in st.session_state:
        st.session_state.root_page_ids = config.root_page_ids if config.root_page_ids else [""]

    # サイドバー：基本設定
    st.sidebar.header("Confluence 設定")
    base_url = st.sidebar.text_input("Base URL", value=config.base_url if config.base_url else "")
    token = st.sidebar.text_input("Token", value=config.token if config.token else "", type="password")

    st.sidebar.header("エクスポート設定")
    max_mb = st.sidebar.number_input("Max MB", value=config.max_mb, min_value=1.0)
    stop_threshold_mb = st.sidebar.number_input("Stop Threshold MB", value=config.stop_threshold_mb, min_value=1.0)
    zip_output = st.sidebar.checkbox("Zip圧縮してダウンロード", value=True)

    # メインエリア：Root Page IDs
    st.subheader("エクスポート対象のページID")

    new_ids = []
    ids_to_remove = []

    for i, pid in enumerate(st.session_state.root_page_ids):
        cols = st.columns([0.8, 0.2])
        val = cols[0].text_input(f"Root Page ID #{i+1}", value=pid, key=f"pid_{i}")
        new_ids.append(val)
        if cols[1].button("削除", key=f"del_{i}"):
            ids_to_remove.append(i)

    # 削除処理
    if ids_to_remove:
        for i in sorted(ids_to_remove, reverse=True):
            st.session_state.root_page_ids.pop(i)
        if not st.session_state.root_page_ids:
            st.session_state.root_page_ids = [""]
        st.rerun()

    st.session_state.root_page_ids = new_ids

    if st.button("フィールドを追加"):
        st.session_state.root_page_ids.append("")
        st.rerun()

    # 実行ボタン
    is_locked = export_lock.locked()
    if is_locked:
        st.warning("現在、別のエクスポート処理が実行中です。少々お待ちください。")

    start_button = st.button("エクスポート開始", disabled=is_locked)

    if start_button:
        # 入力チェック
        active_ids = [pid.strip() for pid in st.session_state.root_page_ids if pid.strip()]
        if not active_ids:
            st.error("少なくとも1つのRoot Page IDを入力してください。")
            return
        if not base_url or not token:
            st.error("Base URLとTokenを入力してください。")
            return

        # 複数ID指定時はZip必須
        if len(active_ids) > 1 and not zip_output:
            st.info("複数IDが指定されたため、Zip圧縮を有効にします。")
            zip_output = True

        # ログ表示エリア
        st.subheader("実行ログ")
        log_container = st.container(height=300)
        log_placeholder = log_container.empty()

        # ロギング設定
        handler = StreamlitLogHandler(log_placeholder)
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%H:%M:%S'))
        logger = logging.getLogger("c2m_export")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        try:
            with export_lock:
                with tempfile.TemporaryDirectory() as tmp_dir:
                    client = ConfluenceClient(base_url, token, config.proxy)
                    converter = MarkdownConverter(base_url)

                    exported_files = []
                    first_root_title = None
                    first_space_key = None

                    for root_page_id in active_ids:
                        logger.info(f"Starting export from root page ID: {root_page_id}")
                        try:
                            root_page = client.get_page(root_page_id)
                            root_title = root_page.get('title')
                            space_key = root_page.get('space', {}).get('key')
                            if first_root_title is None:
                                first_root_title = root_title
                                first_space_key = space_key
                        except Exception as e:
                            logger.error(f"Failed to fetch root page {root_page_id}: {e}")
                            continue

                        full_md, total_bytes, page_count = export_tree(
                            client, converter, root_page_id, stop_threshold_mb, initial_page_data=root_page
                        )

                        if not full_md:
                            logger.error(f"No content exported for page ID {root_page_id}.")
                            continue

                        # ファイル名生成（ここではtmp_dir内なので、重複はあまり気にしなくて良いが、一応一意にする）
                        safe_title = sanitize_filename(root_title or "untitled")
                        display_space = space_key if space_key else "UNKNOWN"
                        filename = f"【{display_space}】 {safe_title}.md"

                        # 同一名称の回避
                        existing_names = [f[0] for f in exported_files]
                        filename = get_unique_in_memory_filename(existing_names, filename, root_page_id)

                        exported_files.append((filename, full_md))
                        logger.info(f"Successfully processed {page_count} pages.")

                    if not exported_files:
                        st.error("エクスポートされたコンテンツがありません。")
                        return

                    # ダウンロードファイルの作成
                    if zip_output:
                        timestamp = datetime.now().strftime("%y%m%d_%H%M")
                        display_space = first_space_key if first_space_key else "UNKNOWN"
                        safe_title = sanitize_filename(first_root_title or "untitled")
                        zip_filename = f"【{display_space}】 {safe_title}_{timestamp}.zip"
                        zip_path = Path(tmp_dir) / zip_filename
                        create_zip_file(zip_path, exported_files)

                        with open(zip_path, "rb") as f:
                            st.download_button(
                                label="Zipファイルをダウンロード",
                                data=f,
                                file_name=zip_filename,
                                mime="application/zip"
                            )
                    else:
                        # 単一ファイルの場合
                        filename, content = exported_files[0]
                        st.download_button(
                            label="Markdownファイルをダウンロード",
                            data=content,
                            file_name=filename,
                            mime="text/markdown"
                        )
                    st.success("エクスポートが完了しました。上記のボタンからダウンロードしてください。")

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            logger.exception(e)
        finally:
            logger.removeHandler(handler)

if __name__ == "__main__":
    import sys
    from streamlit.web import cli as stcli

    if "--run-internal" in sys.argv:
        sys.argv.remove("--run-internal")
        main()
    else:
        # 自身を streamlit run で再起動する
        sys.argv = ["streamlit", "run", sys.argv[0], "--", "--run-internal"] + sys.argv[1:]
        sys.exit(stcli.main())
