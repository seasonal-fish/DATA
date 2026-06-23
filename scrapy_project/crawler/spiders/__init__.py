# 대량/구조화 수집이 필요한 작업이 생기면 이 디렉터리에 스파이더를 추가한다.
# 예) 게시판 전체 아카이브, 다수 사이트에 걸친 페이지네이션 수집 등.
# 단발성으로 정적 페이지 한두 개만 긁는 작업은 static_html/, news/ (httpx+BeautifulSoup)를 쓴다.
#
# 새 스파이더 작성 시:
# - 응답 파싱 결과는 crawler.items.CollectedItem (또는 새 Item)에 담아 yield한다.
# - settings.py에서 이미 ROBOTSTXT_OBEY=True, AUTOTHROTTLE_ENABLED=True가 켜져 있다.
# - 저장은 crawler.pipelines.JsonlExportPipeline이 자동으로 처리한다(crawling/data/scrapy/).
