"""
PIPELINE_ENABLED=true  → cron 스케줄에 맞춰 trending_word_crawler 파이프라인을 반복 실행
PIPELINE_ENABLED=false → 즉시 종료 (스케줄러 미사용 시 컨테이너 기본 동작)

관련 env:
  PIPELINE_ENABLED        true / false (기본 false)
  PIPELINE_SCHEDULE_CRON  cron 표현식  (기본 "0 3 * * *" — 매일 새벽 3시)
  PIPELINE_TIMEZONE       타임존       (기본 Asia/Seoul)
"""
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

_CRAWLER_DIR = Path(__file__).resolve().parent / "trending_word_crawler"
_PYTHON = sys.executable


def run_pipeline():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log.info(f"=== 파이프라인 시작 (run_id={run_id}) ===")

    steps = [
        [_PYTHON, "step1_get_word_list.py"],
        [_PYTHON, "step2_crawl_descriptions.py"],
        [_PYTHON, "step3_save_final.py", "--run-id", run_id],
        [_PYTHON, "step4_enrich_with_openai.py", "--run-id", run_id],
        [_PYTHON, "step5_load_enriched_to_db.py", "--run-id", run_id],
    ]

    for cmd in steps:
        log.info(f"실행: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=str(_CRAWLER_DIR))
        if result.returncode != 0:
            log.error(f"실패: {cmd[1]} (exit={result.returncode}) — 파이프라인 중단")
            return

    log.info(f"=== 파이프라인 완료 (run_id={run_id}) ===")


def main():
    enabled = os.getenv("PIPELINE_ENABLED", "false").strip().lower()
    if enabled != "true":
        log.info("PIPELINE_ENABLED=false — 스케줄러를 시작하지 않습니다.")
        return

    cron = os.getenv("PIPELINE_SCHEDULE_CRON", "0 3 * * *").strip()
    tz = os.getenv("PIPELINE_TIMEZONE", "Asia/Seoul").strip()

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_pipeline,
        CronTrigger.from_crontab(cron, timezone=tz),
        id="trending_word_pipeline",
        max_instances=1,
        misfire_grace_time=3600,
    )

    log.info(f"스케줄러 시작 — cron='{cron}', timezone={tz}")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("스케줄러 종료")


if __name__ == "__main__":
    main()
