import sys
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from .config import Config
from .confluence import ConfluenceClient
from .converter import MarkdownConverter
from .utils import get_unique_filename, bytes_to_mb, is_within_size_limit, create_zip_file, generate_zip_filename, sanitize_filename

logger = logging.getLogger(__name__)

def export_tree(client: ConfluenceClient, converter: MarkdownConverter, root_page_id: str, stop_threshold_mb: float, initial_page_data: Dict = None):
    """
    指定されたルートページから子孫をDFS(深さ優先探索)で巡回し、Markdownに統合する。
    """
    pages_to_process = [(root_page_id, 1, initial_page_data)] # (page_id, level, pre_fetched_data) のスタック
    processed_md = []
    total_bytes = 0
    page_count = 0

    while pages_to_process:
        page_id, level, pre_fetched_data = pages_to_process.pop()

        try:
            if pre_fetched_data:
                page_data = pre_fetched_data
            else:
                logger.info(f"ページ {page_id} を取得中 (レベル {level})...")
                page_data = client.get_page(page_id)

            title = page_data.get('title')
            space_key = page_data.get('space', {}).get('key')
            body = page_data.get('body', {}).get('storage', {}).get('value', '')
            webui = page_data.get('_links', {}).get('webui', '')
            full_url = f"{client.base_url}{webui}"

            # 統合ファイル内での各ページのヘッダーセクション。メタ情報をAIが参照できるように付与。
            page_md = f"\n---\n# {title}\n"
            page_md += f"- **Page ID**: {page_id}\n"
            page_md += f"- **Space Key**: {space_key}\n"
            page_md += f"- **URL**: {full_url}\n\n"
            page_md += converter.convert(body, level=level)

            md_bytes = len(page_md.encode('utf-8'))

            # サイズ制限のチェック。閾値を超えた場合は、中途半端な取得を避けるためその時点で停止。
            if not is_within_size_limit(total_bytes + md_bytes, stop_threshold_mb):
                logger.warning(f"停止閾値 ({stop_threshold_mb}MB) に達しました（現象）。詳細: 取得予定のデータが制限を超えています（原因）。これ以上のエクスポートを停止します（対処方法）")
                break

            processed_md.append(page_md)
            total_bytes += md_bytes
            page_count += 1

            # 子ページの取得とスタックへの追加。DFSを実現するために reversed で追加。
            children = client.get_child_pages(page_id)
            for child in reversed(children):
                pages_to_process.append((child['id'], level + 1, None))

            logger.info(f"'{title}' を処理しました。現在のサイズ: {bytes_to_mb(total_bytes):.2f}MB, ページ数: {page_count}")

        except Exception as e:
            # 個別ページの失敗はログに記録し、全体の処理は継続。
            logger.error(f"ページ {page_id} の処理に失敗しました（現象）。詳細: {e}（原因）。このページをスキップして継続します（対処方法）")
            continue

    return "".join(processed_md), total_bytes, page_count

def main():
    """
    CLIのエントリーポイント。設定の読み込み、クライアントの初期化、エクスポートの実行を行う。
    """
    # 外部からインポートされた際の副作用を防ぐため、実行時にのみログ設定を行う
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    config = Config()
    try:
        config.load()
        config.validate()
    except Exception as e:
        logger.error(f"設定エラーが発生しました（現象）。詳細: {e}（原因）。c2m_config.yaml の内容やコマンドライン引数を確認してください（対処方法）")
        sys.exit(1)

    client = ConfluenceClient(config.base_url, config.token, config.proxy)
    converter = MarkdownConverter(config.base_url)

    # ツール実行時点での共通サフィックスを生成
    suffix = ""
    if not config.overwrite:
        suffix = datetime.now().strftime("_%y%m%d_%H%M%S")

    # --- フェイルファスト・チェック (Fail-Fast) ---
    # 大規模な情報収集を開始する前に、出力先ファイルの整合性を確認する。
    plan_list = []
    exported_filenames = set()
    first_root_title = None
    first_space_key = None

    for root_page_id in config.root_page_ids:
        try:
            root_page = client.get_page(root_page_id)
            root_title = root_page.get('title')
            space_key = root_page.get('space', {}).get('key')
            if first_root_title is None:
                first_root_title = root_title
                first_space_key = space_key
        except Exception as e:
            logger.error(f"ルートページ {root_page_id} の取得に失敗しました（現象）。詳細: {e}（原因）。ページIDが正しいか、権限があるかを確認してください（対処方法）")
            sys.exit(1)

        output_path = get_unique_filename(config.output_dir, space_key, root_title, suffix)
        filename = output_path.name

        # 非上書き時の競合チェック（既存ファイルおよび同一実行内での重複）
        if not config.overwrite:
            if filename in exported_filenames:
                logger.error(f"ファイル名の競合が発生しました（現象）。詳細: 同一実行内で '{filename}' が重複しています（原因）。ルートページ名が重複していないか確認してください（対処方法）")
                sys.exit(1)
            if not config.zip_output and output_path.exists():
                logger.error(f"出力ファイルが既に存在します（現象）。詳細: '{output_path}' は既に存在します（原因）。上書きを指定するか、既存ファイルを移動してください（対処方法）")
                sys.exit(1)

        exported_filenames.add(filename)

        if not config.zip_output:
            # 書き込み権限の早期確認（ディレクトリ作成試行）
            try:
                output_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"出力ディレクトリの作成に失敗しました（現象）。詳細: {e}（原因）。書き込み権限を確認してください（対処方法）")
                sys.exit(1)

        plan_list.append((root_page_id, root_page, output_path))

    if config.zip_output and first_root_title:
        zip_filename = generate_zip_filename(first_space_key, first_root_title, suffix)
        zip_path = Path(config.output_dir) / zip_filename
        if not config.overwrite and zip_path.exists():
            logger.error(f"Zipファイルが既に存在します（現象）。詳細: '{zip_path}' は既に存在します（原因）。上書きを指定するか、既存ファイルを移動してください（対処方法）")
            sys.exit(1)
        try:
            zip_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"出力ディレクトリの作成に失敗しました（現象）。詳細: {e}（原因）。書き込み権限を確認してください（対処方法）")
            sys.exit(1)

    # --- 情報収集と書き込み実行 ---
    exported_files = []
    for root_page_id, root_page, output_path in plan_list:
        logger.info("-" * 50)
        logger.info(f"ルートページID: {root_page_id} からのエクスポートを開始します")

        full_md, total_bytes, page_count = export_tree(client, converter, root_page_id, config.stop_threshold_mb, initial_page_data=root_page)

        if not full_md:
            logger.error(f"ページ ID {root_page_id} のコンテンツがエクスポートされませんでした（現象）。詳細: 該当ページが空か、取得に失敗しました（原因）。ページIDと内容を確認してください（対処方法）")
            sys.exit(1)

        if config.zip_output:
            exported_files.append((output_path.name, full_md))
            logger.info(f"{page_count} ページのエクスポートに成功しました (Zip待ち)")
        else:
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(full_md)
                logger.info(f"{page_count} ページを '{output_path}' にエクスポートしました")
                logger.info(f"最終ファイルサイズ: {bytes_to_mb(total_bytes):.2f}MB")

                if bytes_to_mb(total_bytes) > config.max_mb:
                    logger.warning(f"最終ファイルサイズ ({bytes_to_mb(total_bytes):.2f}MB) が最大許容サイズ ({config.max_mb}MB) を超えています（現象）。詳細: ページツリー全体の合計サイズが設定値を超過しました（原因）。--max-mb 設定の調整を検討してください（対処方法）")
            except Exception as e:
                logger.error(f"出力ファイルの書き込みに失敗しました（現象）。詳細: {e}（原因）。書き込み権限、ディスク容量、またはファイルロックを確認してください（対処方法）")
                sys.exit(1)

    # Zip圧縮が指定されている場合、全ファイルをまとめて出力
    if config.zip_output and exported_files:
        zip_filename = generate_zip_filename(first_space_key, first_root_title, suffix)
        zip_path = Path(config.output_dir) / zip_filename
        try:
            create_zip_file(zip_path, exported_files)
            logger.info(f"Zipファイルの作成に成功しました: '{zip_path}'")
        except Exception as e:
            logger.error(f"Zipファイルの作成に失敗しました（現象）。詳細: {e}（原因）。書き込み権限、ディスク容量、またはファイルロックを確認してください（対処方法）")
            sys.exit(1)

if __name__ == "__main__":
    main()
