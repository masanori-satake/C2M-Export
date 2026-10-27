"""添付参照のリンク書き換え (リンクリゾルバ) のテスト."""

import pytest

from c2m_export.converter import MarkdownConverter
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

    assert "![画像](<_attachments/image (2).png>)" in new_content
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


@pytest.mark.parametrize("filename", ["image space.png", "image(1).png", "image (1).png"])
@pytest.mark.parametrize("tag", ["image", "link"])
@pytest.mark.parametrize("link_mode", ["relative", "original"])
def test_rewrite_converted_attachment_with_special_destination(filename, tag, link_mode):
    attachment = f'<ri:attachment ri:filename="{filename}" />'
    content = MarkdownConverter("https://confluence.example.com").convert(f"<ac:{tag}>{attachment}</ac:{tag}>")
    attachments = [
        AttachmentRef(
            original_filename=filename,
            saved_filename=filename,
            saved=True,
            download_path=f"/download/attachments/123/{filename}",
        )
    ]

    new_content, unresolved = rewrite_attachment_links(
        content, attachments, link_mode=link_mode, base_url="https://confluence.example.com/"
    )

    prefix = "!" if tag == "image" else ""
    destination = (
        f"_attachments/{filename}"
        if link_mode == "relative"
        else f"https://confluence.example.com/download/attachments/123/{filename}"
    )
    assert new_content.strip() == f"{prefix}[{filename}](<{destination}>)"
    assert unresolved == 0


@pytest.mark.parametrize("attachment_dir", ["添付 ファイル", "添付(資料)"])
def test_rewrite_attachment_with_special_directory(attachment_dir):
    attachments = [AttachmentRef(original_filename="doc.pdf", saved_filename="doc.pdf", saved=True)]

    new_content, unresolved = rewrite_attachment_links(
        "[文書](doc.pdf)", attachments, attachment_dir_name=attachment_dir
    )

    assert new_content == f"[文書](<{attachment_dir}/doc.pdf>)"
    assert unresolved == 0


def test_unresolved_angle_destination_is_preserved():
    content = "[文書](<doc (1).pdf>) と [不明](<unknown (2).pdf>)"
    attachments = [AttachmentRef(original_filename="doc (1).pdf", saved_filename="doc (1).pdf", saved=False)]

    new_content, unresolved = rewrite_attachment_links(content, attachments)

    assert new_content == content
    assert unresolved == 2
