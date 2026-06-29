import json
from pathlib import Path
from unittest.mock import patch

from news import crawl_urls


class FakeResponse:
    def __init__(self, text="", status=200):
        self.text = text
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise crawl_urls.requests.HTTPError(f"status {self.status}")


def test_fetch_content_ok():
    extracted = json.dumps({"title": "제목", "date": "2026-06-24", "text": "본문 내용"})
    with patch("news.crawl_urls.requests.get", return_value=FakeResponse("<html></html>")), \
         patch("news.crawl_urls.trafilatura.extract", return_value=extracted):
        result = crawl_urls.fetch_content("https://example.com/a")

    assert result == {
        "url": "https://example.com/a",
        "status": "ok",
        "title": "제목",
        "date": "2026-06-24",
        "text": "본문 내용",
    }


def test_fetch_content_request_failure():
    with patch("news.crawl_urls.requests.get", side_effect=Exception("boom")):
        result = crawl_urls.fetch_content("https://example.com/a")

    assert result["url"] == "https://example.com/a"
    assert result["status"] == "error"
    assert "fetch_failed" in result["error"]


def test_fetch_content_extract_failure():
    with patch("news.crawl_urls.requests.get", return_value=FakeResponse("<html></html>")), \
         patch("news.crawl_urls.trafilatura.extract", side_effect=Exception("boom")):
        result = crawl_urls.fetch_content("https://example.com/a")

    assert result["status"] == "error"
    assert "extract_failed" in result["error"]


def test_fetch_content_no_text_extracted():
    with patch("news.crawl_urls.requests.get", return_value=FakeResponse("<html></html>")), \
         patch("news.crawl_urls.trafilatura.extract", return_value=None):
        result = crawl_urls.fetch_content("https://example.com/a")

    assert result == {"url": "https://example.com/a", "status": "error", "error": "extraction_failed"}


def test_read_url_file_skips_blank_and_comment_lines(tmp_path: Path):
    path = tmp_path / "urls.txt"
    path.write_text(
        "# comment\n"
        "https://example.com/1\n"
        "\n"
        "https://example.com/2\n",
        encoding="utf-8",
    )

    assert crawl_urls.read_url_file(path) == [
        "https://example.com/1",
        "https://example.com/2",
    ]


def test_read_legacy_json_extracts_urls(tmp_path: Path):
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "sensitive_issues": {
                    "records": [
                        {"urls": ["https://example.com/1", "https://example.com/2"]},
                        {"urls": ["https://example.com/3"]},
                        {},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    assert crawl_urls.read_legacy_json(path) == [
        "https://example.com/1",
        "https://example.com/2",
        "https://example.com/3",
    ]


def test_read_legacy_json_missing_records(tmp_path: Path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({}), encoding="utf-8")

    assert crawl_urls.read_legacy_json(path) == []
