from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from common.config import settings


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"JSON으로 직렬화할 수 없는 타입: {type(value)!r}")


def save_jsonl(records: Iterable[Any], collector_name: str, subdir: str = "") -> Path:
    """dataclass 또는 dict 레코드를 `data/<subdir>/<collector_name>_<timestamp>.jsonl`로 저장한다."""
    out_dir = settings.data_dir / subdir if subdir else settings.data_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{collector_name}_{timestamp}.jsonl"

    count = 0
    with out_path.open("w", encoding="utf-8") as f:
        for record in records:
            payload = dataclasses.asdict(record) if dataclasses.is_dataclass(record) else record
            f.write(json.dumps(payload, ensure_ascii=False, default=_json_default))
            f.write("\n")
            count += 1

    return out_path
