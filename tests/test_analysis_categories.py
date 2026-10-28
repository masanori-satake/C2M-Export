from c2m_export.analysis.categories import summarize_archives
from c2m_export.assessment.models import AttachmentMeta, PageMeta, RawInventory


def test_summarize_archives_default():
    att1 = AttachmentMeta("100", "archive.zip", "zip", "application/zip", 1024)
    att2 = AttachmentMeta("100", "backup.tar.gz", "gz", "application/gzip", 2048)
    att3 = AttachmentMeta("100", "doc.pdf", "pdf", "application/pdf", 512)
    att4 = AttachmentMeta("100", "broken.zip", "zip", "application/zip", None)

    page = PageMeta("100", "Page", "SPACE", 1, 100, None, [], attachments=[att1, att2, att3, att4])
    raw = RawInventory(pages=[page])

    res = summarize_archives(raw)
    assert res["file_count"] == 3
    assert res["total_size_bytes"] == 3072
    assert res["size_meta_missing_count"] == 1

    ext_dict = {item["extension"]: item for item in res["extensions"]}
    assert "zip" in ext_dict
    assert ext_dict["zip"]["count"] == 2
    assert ext_dict["zip"]["total_size_bytes"] == 1024
    assert ext_dict["zip"]["max_size_bytes"] == 1024
    assert "gz" in ext_dict


def test_summarize_archives_custom_extensions():
    att1 = AttachmentMeta("100", "data.7z", "7z", "application/x-7z-compressed", 100)
    page = PageMeta("100", "Page", "SPACE", 1, 100, None, [], attachments=[att1])
    raw = RawInventory(pages=[page])

    res = summarize_archives(raw, archive_extensions={"rar"})
    assert res["file_count"] == 0
    assert res["total_size_bytes"] == 0
