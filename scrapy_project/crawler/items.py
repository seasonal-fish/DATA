import scrapy


class CollectedItem(scrapy.Item):
    """대량 수집 스파이더가 공통으로 채우는 범용 아이템.

    뉴스/게시판처럼 형태가 다른 컨텐츠를 한 파이프라인으로 저장할 수 있도록
    common.models의 필드들을 최소 공통분모로 묶었다.
    """

    source = scrapy.Field()  # 사이트/언론사/커뮤니티 이름
    title = scrapy.Field()
    url = scrapy.Field()
    published_at = scrapy.Field()  # ISO 8601 문자열
    summary = scrapy.Field()
