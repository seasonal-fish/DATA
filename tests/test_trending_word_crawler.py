"""
trending_word_crawler 순수 함수 유닛 테스트
외부 의존성(Playwright, OpenAI, boto3, DB) 없이 실행 가능한 함수만 대상으로 함
"""
import json
import sys
from pathlib import Path

import pytest

# trending_word_crawler 패키지를 임포트 가능하도록 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trending_word_crawler.step1_get_word_list import apply_word_limit
from trending_word_crawler.step2_crawl_descriptions import extract_body_text, extract_section_text
from trending_word_crawler.step3_save_final import clean_text
from trending_word_crawler.step4_enrich_with_openai import normalize_sentiment, parse_json_from_text
from trending_word_crawler.step3_save_final import guess_content_type
from trending_word_crawler.step5_load_enriched_to_db import chunked


# ---------------------------------------------------------------------------
# step1: apply_word_limit
# ---------------------------------------------------------------------------

class TestApplyWordLimit:
    def test_no_limit_returns_all(self):
        sections = {"ㄱ": [1, 2, 3], "ㄴ": [4, 5]}
        assert apply_word_limit(sections, 0) == sections

    def test_none_limit_returns_all(self):
        sections = {"ㄱ": [1, 2], "ㄴ": [3]}
        assert apply_word_limit(sections, None) == sections

    def test_limit_trims_across_sections(self):
        sections = {"ㄱ": [1, 2, 3], "ㄴ": [4, 5, 6]}
        result = apply_word_limit(sections, 4)
        total = sum(len(v) for v in result.values())
        assert total == 4

    def test_limit_larger_than_total_returns_all(self):
        sections = {"ㄱ": [1, 2]}
        result = apply_word_limit(sections, 100)
        assert result == sections

    def test_section_order_preserved(self):
        sections = {"숫자": ["1", "2"], "라틴": ["a", "b"], "ㄱ": ["가", "나"]}
        result = apply_word_limit(sections, 3)
        assert list(result.keys()) == ["숫자", "라틴"]

    def test_limit_one(self):
        sections = {"ㄱ": ["가", "나", "다"], "ㄴ": ["라"]}
        result = apply_word_limit(sections, 1)
        assert result == {"ㄱ": ["가"]}

    def test_empty_sections(self):
        assert apply_word_limit({}, 5) == {}


# ---------------------------------------------------------------------------
# step2: extract_body_text, extract_section_text
# ---------------------------------------------------------------------------

SIMPLE_HTML = """
<html><body>
  <div>
    <div><h3><a id="s-1">개요</a></h3></div>
    <div>
      <div>내용 없음</div>
    </div>
  </div>
  <div class="content">
    <p>본문 텍스트입니다.</p>
  </div>
</body></html>
"""

SECTIONED_HTML = """
<html><body>
  <div>
    <div>
      <div><h3><a id="s-1">섹션1</a></h3></div>
    </div>
    <div class="body">
      <p>섹션1 본문 내용</p>
    </div>
  </div>
</body></html>
"""


class TestExtractBodyText:
    def test_returns_string(self):
        result = extract_body_text(SIMPLE_HTML)
        assert isinstance(result, str)

    def test_strips_scripts(self):
        html = "<html><body><script>alert(1)</script><p>텍스트</p></body></html>"
        result = extract_body_text(html)
        assert "alert" not in result
        assert "텍스트" in result

    def test_max_length_12000(self):
        long_text = "가" * 20000
        html = f"<html><body><p>{long_text}</p></body></html>"
        result = extract_body_text(html)
        assert len(result) <= 12000

    def test_empty_html_returns_string(self):
        result = extract_body_text("")
        assert isinstance(result, str)

    def test_collapses_whitespace(self):
        html = "<html><body><p>텍스트   여러   공백</p></body></html>"
        result = extract_body_text(html)
        assert "  " not in result


class TestExtractSectionText:
    def test_missing_anchor_returns_empty(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SIMPLE_HTML, "html.parser")
        result = extract_section_text(soup, "s-999")
        assert result == ""

    def test_returns_string(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(SIMPLE_HTML, "html.parser")
        result = extract_section_text(soup, "s-1")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# step3: clean_text
# ---------------------------------------------------------------------------

class TestCleanText:
    def test_none_returns_empty(self):
        assert clean_text(None) == ""

    def test_empty_string(self):
        assert clean_text("") == ""

    def test_collapses_whitespace(self):
        assert clean_text("hello   world") == "hello world"

    def test_removes_newlines(self):
        assert clean_text("line1\nline2") == "line1 line2"

    def test_removes_carriage_return(self):
        assert clean_text("line1\rline2") == "line1 line2"

    def test_strips_leading_trailing(self):
        assert clean_text("  hello  ") == "hello"

    def test_normal_text_unchanged(self):
        assert clean_text("정상 텍스트") == "정상 텍스트"


# ---------------------------------------------------------------------------
# step4: normalize_sentiment, parse_json_from_text
# ---------------------------------------------------------------------------

class TestNormalizeSentiment:
    @pytest.mark.parametrize("label", ["긍정", "positive", "pos", "+", "plus"])
    def test_positive_variants(self, label):
        assert normalize_sentiment(label) == "긍정"

    @pytest.mark.parametrize("label", ["부정", "negative", "neg", "-", "minus"])
    def test_negative_variants(self, label):
        assert normalize_sentiment(label) == "부정"

    @pytest.mark.parametrize("label", ["중립", "neutral", "neu", "0"])
    def test_neutral_variants(self, label):
        assert normalize_sentiment(label) == "중립"

    def test_none_returns_neutral(self):
        assert normalize_sentiment(None) == "중립"

    def test_empty_string_returns_neutral(self):
        assert normalize_sentiment("") == "중립"

    def test_unknown_label_returns_neutral(self):
        assert normalize_sentiment("모름") == "중립"

    def test_case_insensitive(self):
        assert normalize_sentiment("POSITIVE") == "긍정"
        assert normalize_sentiment("Negative") == "부정"


class TestParseJsonFromText:
    def test_pure_json(self):
        text = '{"meaning": "뜻", "sentiment": "긍정"}'
        result = parse_json_from_text(text)
        assert result["meaning"] == "뜻"

    def test_json_with_surrounding_text(self):
        text = '결과는 다음과 같습니다: {"meaning": "뜻", "sentiment": "중립"} 이상입니다.'
        result = parse_json_from_text(text)
        assert result["sentiment"] == "중립"

    def test_invalid_raises_value_error(self):
        with pytest.raises((ValueError, Exception)):
            parse_json_from_text("JSON이 없는 텍스트")

    def test_confidence_float(self):
        text = '{"meaning": "뜻", "sentiment": "긍정", "confidence": 0.85}'
        result = parse_json_from_text(text)
        assert result["confidence"] == 0.85


# ---------------------------------------------------------------------------
# step5: guess_content_type
# ---------------------------------------------------------------------------

class TestGuessContentType:
    def test_json_file(self):
        result = guess_content_type(Path("data.json"))
        assert result == "application/json"

    def test_csv_file(self):
        result = guess_content_type(Path("data.csv"))
        # Windows: application/vnd.ms-excel, Linux/Mac: text/csv
        assert "csv" in result or "excel" in result or result == "text/csv"

    def test_unknown_extension_returns_octet_stream(self):
        result = guess_content_type(Path("file.unknownxyz"))
        assert result == "application/octet-stream"

    def test_returns_string(self):
        result = guess_content_type(Path("file.json"))
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# step6: chunked
# ---------------------------------------------------------------------------

class TestChunked:
    def test_even_split(self):
        result = list(chunked([1, 2, 3, 4], 2))
        assert result == [[1, 2], [3, 4]]

    def test_uneven_split(self):
        result = list(chunked([1, 2, 3, 4, 5], 2))
        assert result == [[1, 2], [3, 4], [5]]

    def test_size_larger_than_list(self):
        result = list(chunked([1, 2], 10))
        assert result == [[1, 2]]

    def test_empty_list(self):
        result = list(chunked([], 5))
        assert result == []

    def test_size_one(self):
        result = list(chunked([1, 2, 3], 1))
        assert result == [[1], [2], [3]]

    def test_preserves_order(self):
        items = list(range(10))
        flattened = [x for chunk in chunked(items, 3) for x in chunk]
        assert flattened == items
