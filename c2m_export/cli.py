import sys
import logging
from pathlib import Path
from typing import List, Dict

from .config import Config
from .confluence import ConfluenceClient
from .converter import MarkdownConverter
from .utils import get_unique_filename, bytes_to_mb, is_within_size_limit

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def export_tree(client: ConfluenceClient, converter: MarkdownConverter, root_page_id: str, stop_threshold_mb: float):
    pages_to_process = [(root_page_id, 1)] # (page_id, level)
    processed_md = []
    total_bytes = 0
    page_count = 0

    while pages_to_process:
        page_id, level = pages_to_process.pop(0)

        try:
            logger.info(f"Fetching page {page_id} (Level {level})...")
            page_data = client.get_page(page_id)
            title = page_data.get('title')
            space_key = page_data.get('space', {}).get('key')
            body = page_data.get('body', {}).get('storage', {}).get('value', '')
            webui = page_data.get('_links', {}).get('webui', '')
            full_url = f"{client.base_url}{webui}"

            # Convert to Markdown
            page_md = f"\n---\n# {title}\n"
            page_md += f"- **Page ID**: {page_id}\n"
            page_md += f"- **Space Key**: {space_key}\n"
            page_md += f"- **URL**: {full_url}\n\n"
            page_md += converter.convert(body, level=level)

            md_bytes = len(page_md.encode('utf-8'))

            if not is_within_size_limit(total_bytes + md_bytes, stop_threshold_mb):
                logger.warning(f"Stop threshold ({stop_threshold_mb}MB) reached. Stopping export.")
                break

            processed_md.append(page_md)
            total_bytes += md_bytes
            page_count += 1

            # Get children and add to the front of pages_to_process for DFS-like (Parent -> Child)
            # Actually, to maintain parent-child order in the file, we should process parent, then its children.
            # Using a list and inserting at the front works for DFS.
            children = client.get_child_pages(page_id)
            # Reverse children to maintain original order when popping from front
            for child in reversed(children):
                pages_to_process.insert(0, (child['id'], level + 1))

            logger.info(f"Processed '{title}'. Current size: {bytes_to_mb(total_bytes):.2f}MB, Pages: {page_count}")

        except Exception as e:
            logger.error(f"Failed to process page {page_id}: {e}")
            # Continue with other pages? Or stop?
            # For a CLI tool, continuing might be better if it's just one page failing.
            continue

    return "".join(processed_md), total_bytes, page_count

def main():
    config = Config()
    try:
        config.load()
        config.validate()
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    client = ConfluenceClient(config.base_url, config.token, config.proxy)
    converter = MarkdownConverter(config.base_url)

    logger.info(f"Starting export from root page ID: {config.root_page_id}")

    # We need root page info first for filename
    try:
        root_page = client.get_page(config.root_page_id)
        root_title = root_page.get('title')
        space_key = root_page.get('space', {}).get('key')
    except Exception as e:
        logger.error(f"Failed to fetch root page: {e}")
        sys.exit(1)

    full_md, total_bytes, page_count = export_tree(client, converter, config.root_page_id, config.stop_threshold_mb)

    if not full_md:
        logger.error("No content exported.")
        sys.exit(1)

    output_path = get_unique_filename(config.output_dir, space_key, root_title, config.root_page_id)

    try:
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_md)
        logger.info(f"Successfully exported {page_count} pages to '{output_path}'")
        logger.info(f"Final file size: {bytes_to_mb(total_bytes):.2f}MB")

        if bytes_to_mb(total_bytes) > config.max_mb:
            logger.warning(f"Final file size ({bytes_to_mb(total_bytes):.2f}MB) exceeds max-mb ({config.max_mb}MB)")

    except Exception as e:
        logger.error(f"Failed to write output file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
