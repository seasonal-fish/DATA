"""
Step 1: 나무위키 속어·유행어 관련 정보 페이지에서
        섹션별(숫자, 라틴, ㄱ~ㅎ) 유행어 목록과 링크를 추출하여 JSON으로 저장

DOM 구조:
  <div class="RK18kjkh dugaJ16k"> (섹션 헤딩 컨테이너)
    <div ...><h3><a id="s-5.1">...
  <div class="tEf4ex+R s8pb81cx"> (섹션 내용: li 목록)
"""
import asyncio
import json
import os
from playwright.async_api import async_playwright

MAIN_URL = "https://namu.wiki/w/%EC%86%8D%EC%96%B4%C2%B7%EC%9C%A0%ED%96%89%EC%96%B4%20%EA%B4%80%EB%A0%A8%20%EC%A0%95%EB%B3%B4"

SECTION_MAP = {
    "s-3":    "숫자",
    "s-4":    "라틴문자",
    "s-5.1":  "ㄱ",
    "s-5.2":  "ㄴ",
    "s-5.3":  "ㄷ",
    "s-5.4":  "ㄹ",
    "s-5.5":  "ㅁ",
    "s-5.6":  "ㅂ",
    "s-5.7":  "ㅅ",
    "s-5.8":  "ㅇ",
    "s-5.9":  "ㅈ",
    "s-5.10": "ㅊ",
    "s-5.11": "ㅋ",
    "s-5.12": "ㅌ",
    "s-5.13": "ㅍ",
    "s-5.14": "ㅎ",
    "s-6":    "기타",
}


def apply_word_limit(sections, limit):
    """섹션 순서를 유지하면서 전체 단어 수를 limit으로 제한"""
    if limit is None or limit <= 0:
        return sections

    limited = {}
    remaining = limit
    for section, words in sections.items():
        if remaining <= 0:
            break
        take = words[:remaining]
        if take:
            limited[section] = take
            remaining -= len(take)
    return limited

async def get_word_list():
    word_limit = None
    limit_raw = os.getenv("WORD_LIMIT", "").strip()
    if limit_raw.isdigit():
        word_limit = int(limit_raw)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR"
        )
        page = await context.new_page()

        print("메인 페이지 로딩 중...")
        await page.goto(MAIN_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("#s-3", timeout=30000)
        print("로딩 완료!")

        result = await page.evaluate('''(sectionMap) => {
            const sections = {};

            for (const [anchorId, sectionName] of Object.entries(sectionMap)) {
                const anchor = document.getElementById(anchorId);
                if (!anchor) continue;

                // anchor -> h3 -> div(depth1) -> div(depth2) -> nextSibling = content div
                const h3 = anchor.closest("h3") || anchor.parentElement;
                const depth1 = h3 ? h3.parentElement : null;
                const depth2 = depth1 ? depth1.parentElement : null;
                const contentDiv = depth2 ? depth2.nextElementSibling : null;

                if (!contentDiv) continue;

                const words = [];
                const lis = contentDiv.querySelectorAll("li");

                lis.forEach(li => {
                    const links = li.querySelectorAll('a[href^="/w/"]');
                    if (links.length === 0) return;

                    const mainLink = links[0];
                    const word = mainLink.innerText.trim();
                    const href = mainLink.getAttribute("href");
                    const displayText = li.innerText.trim();

                    if (!word || !href) return;
                    if (href.includes("%EB%B6%84%EB%A5%98:")) return;  // 분류: 제외
                    if (href.includes("edit/")) return;
                    if (href.includes(":")) return;  // 나무위키: 등 제외

                    words.push({
                        word: word,
                        href: href,
                        url: "https://namu.wiki" + href,
                        display_text: displayText.substring(0, 200)
                    });
                });

                if (words.length > 0) {
                    sections[sectionName] = words;
                }
            }

            return sections;
        }''', SECTION_MAP)

        await browser.close()

        result = apply_word_limit(result, word_limit)
        total = sum(len(v) for v in result.values())
        print(f"\n=== 추출 결과 ===")
        for section, words in result.items():
            print(f"  [{section}] {len(words)}개  예시: {words[0]['word'] if words else 'N/A'}")
        if word_limit:
            print(f"\n  테스트 제한 적용: 최대 {word_limit}개")
        print(f"\n  총 {total}개 단어 추출")

        output = {
            "main_words": result,
            "total_count": total
        }

        with open("word_list.json", "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print("\nword_list.json 저장 완료!")
        return output

if __name__ == "__main__":
    asyncio.run(get_word_list())
