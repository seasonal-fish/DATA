import json
from datetime import datetime

from itemadapter import ItemAdapter

from common.config import settings


class JsonlExportPipeline:
    """아이템을 받는 즉시 JSONL로 스트리밍 저장한다.

    대량 수집을 염두에 둔 파이프라인이라 common.storage.save_jsonl처럼
    전체 결과를 메모리에 모았다가 한 번에 쓰지 않고 한 줄씩 바로 기록한다.
    """

    def open_spider(self, spider) -> None:
        out_dir = settings.data_dir / "scrapy"
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        self._file = (out_dir / f"{spider.name}_{timestamp}.jsonl").open("w", encoding="utf-8")

    def close_spider(self, spider) -> None:
        self._file.close()

    def process_item(self, item, spider):
        self._file.write(json.dumps(ItemAdapter(item).asdict(), ensure_ascii=False))
        self._file.write("\n")
        return item
