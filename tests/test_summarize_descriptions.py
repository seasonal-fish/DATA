from unittest.mock import MagicMock

from news import summarize_descriptions


def test_build_user_prompt_includes_title_description_and_ok_articles():
    record = {
        "title": "이슈 제목",
        "description": "기존 설명",
        "url_contents": [
            {"status": "ok", "title": "기사1", "date": "2026-06-01", "text": "본문1"},
            {"status": "error", "title": "기사2", "date": "2026-06-02", "text": "본문2"},
        ],
    }

    prompt = summarize_descriptions.build_user_prompt(record)

    assert "이슈 제목" in prompt
    assert "기존 설명" in prompt
    assert "기사1" in prompt
    assert "본문1" in prompt
    assert "기사2" not in prompt
    assert "본문2" not in prompt


def test_build_user_prompt_truncates_long_article_text():
    long_text = "가" * (summarize_descriptions.MAX_CHARS_PER_ARTICLE + 100)
    record = {
        "title": "이슈 제목",
        "url_contents": [{"status": "ok", "title": "기사1", "date": "2026-06-01", "text": long_text}],
    }

    prompt = summarize_descriptions.build_user_prompt(record)

    assert "가" * summarize_descriptions.MAX_CHARS_PER_ARTICLE in prompt
    assert "가" * (summarize_descriptions.MAX_CHARS_PER_ARTICLE + 1) not in prompt


def test_build_user_prompt_without_description_or_articles():
    record = {"title": "이슈 제목"}

    prompt = summarize_descriptions.build_user_prompt(record)

    assert "이슈 제목" in prompt
    assert "기존 설명" not in prompt


def test_summarize_record_calls_openai_and_returns_stripped_content():
    client = MagicMock()
    client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="  요약 결과  "))
    ]
    record = {"title": "이슈 제목", "url_contents": []}

    result = summarize_descriptions.summarize_record(client, record, "gpt-4o-mini")

    assert result == "요약 결과"
    client.chat.completions.create.assert_called_once()
    _, kwargs = client.chat.completions.create.call_args
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1]["role"] == "user"
