"""添付参照のリンク書き換え (リンクリゾルバ) のテスト."""

from c2m_export.fs_export.links import rewrite_attachment_links
from c2m_export.fs_export.models import AttachmentRef


def test_rewrite_attachment_links_relative():
    attachments = [
        AttachmentRef(
            original_filename="image.png",
            saved_filename="image (2).png",
            saved=True,
            download_path="/download/1",
        ),
        AttachmentRef(
            original_filename="huge.zip",
            saved_filename="huge.zip",
            saved=False,
            skip_reason="単一ファイルサイズ上限超過",
        ),
    ]

    content = "図1: ![画像](image.png)\n巨大ファイル: [ダウンロード](huge.zip)\n外部: [Google](https://google.com)"

    new_content, unresolved = rewrite_attachment_links(
        content, attachments, attachment_dir_name="_attachments", link_mode="relative"
    )

    assert "![画像](_attachments/image (2).png)" in new_content
    assert "[ダウンロード](huge.zip)" in new_content  # 未保存なので元のまま
    assert "[Google](https://google.com)" in new_content  # 外部URLは保持
    assert unresolved == 1


def test_rewrite_attachment_links_original():
    attachments = [
        AttachmentRef(
            original_filename="doc.pdf",
            saved_filename="doc.pdf",
            saved=False,  # 未保存であっても original モードでは Confluence の絶対 URL に置換
            download_path="/download/attachments/123/doc.pdf",
        )
    ]

    content = "文書: [詳細](doc.pdf)"

    new_content, unresolved = rewrite_attachment_links(
        content,
        attachments,
        link_mode="original",
        base_url="https://confluence.example.com/",
    )

    assert "[詳細](https://confluence.example.com/download/attachments/123/doc.pdf)" in new_content
    assert unresolved == 0
