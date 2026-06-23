"""protego가 구글 확장 문법(`*`, `$`)을 올바르게 해석하는지 확인한다.

stdlib의 urllib.robotparser는 이 문법을 지원하지 않아 fmkorea처럼
`Disallow: /*search_keyword=` 같은 규칙을 쓰는 실제 서비스에서 오판을 일으킨다.
"""

from protego import Protego

FMKOREA_LIKE_ROBOTS_TXT = """
User-agent: *
Disallow: /
Allow: /$
Allow: /best
Allow: /best2
Allow: /humor
Disallow: /*search_keyword=
"""

NATE_PANN_LIKE_ROBOTS_TXT = """
User-agent: *
Disallow: /
"""


def test_listing_pages_are_allowed_for_generic_agent():
    parser = Protego.parse(FMKOREA_LIKE_ROBOTS_TXT)
    assert parser.can_fetch("https://www.fmkorea.com/best", "MyBot/1.0")
    assert parser.can_fetch("https://www.fmkorea.com/humor", "MyBot/1.0")


def test_individual_post_pages_are_disallowed_for_generic_agent():
    parser = Protego.parse(FMKOREA_LIKE_ROBOTS_TXT)
    assert not parser.can_fetch("https://www.fmkorea.com/8167938273", "MyBot/1.0")


def test_wildcard_query_string_is_disallowed():
    parser = Protego.parse(FMKOREA_LIKE_ROBOTS_TXT)
    assert not parser.can_fetch(
        "https://www.fmkorea.com/best?search_keyword=foo", "MyBot/1.0"
    )


def test_full_site_disallow_blocks_generic_agent():
    parser = Protego.parse(NATE_PANN_LIKE_ROBOTS_TXT)
    assert not parser.can_fetch("https://pann.nate.com/talk/123", "MyBot/1.0")
