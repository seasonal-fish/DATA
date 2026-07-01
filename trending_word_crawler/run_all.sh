#!/bin/bash
# 전체 크롤링 파이프라인 실행
# rate limit이 풀린 후 실행하세요 (약 1시간 후)

set -e
cd "$(dirname "$0")"

# Prefer project crawler venv on Windows/Git Bash.
PYTHON_BIN="../venv/Scripts/python.exe"
if [ -x "$PYTHON_BIN" ]; then
    PYTHON="$PYTHON_BIN"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    PYTHON="python"
fi

echo "Python 인터프리터: $PYTHON"

# 전 단계에서 공유할 실행 ID (S3 경로 일관성 유지)
RUN_ID=$(date -u +"%Y%m%dT%H%M%SZ")
echo "RUN_ID: $RUN_ID"

echo "=========================================="
echo "나무위키 유행어 크롤러 시작"
echo "=========================================="

# Step 1: 메인 페이지에서 단어 목록 추출 (이미 있으면 건너뜀)
if [ ! -f "word_list.json" ]; then
    echo "[1/5] 메인 페이지에서 유행어 목록 추출 중..."
    "$PYTHON" step1_get_word_list.py
else
    echo "[1/5] word_list.json 이미 있음 - 건너뜀"
fi

# Step 2: 각 단어 페이지에서 본문 텍스트 추출
echo ""
echo "[2/5] 각 단어 페이지 본문 크롤링 (약 38분 소요)..."
"$PYTHON" step2_crawl_descriptions.py

# Step 3: 최종 병합 및 S3 업로드
echo ""
echo "[3/5] 최종 데이터 저장 및 S3 업로드..."
"$PYTHON" step3_save_final.py --run-id "$RUN_ID"

# Step 4: S3에서 읽어 OpenAI로 뜻/감성 정제 후 S3 저장
echo ""
echo "[4/5] OpenAI 정제 실행 (S3 다운로드 -> 분석 -> S3 업로드)..."
"$PYTHON" step4_enrich_with_openai.py --run-id "$RUN_ID"

# Step 5: S3에서 읽어 DB 적재
echo ""
echo "[5/5] DB 적재 (S3 다운로드 -> DB 업로드)..."
"$PYTHON" step5_load_enriched_to_db.py --run-id "$RUN_ID"

echo ""
echo "=========================================="
echo "완료! 생성된 파일:"
ls -lah *.json *.csv 2>/dev/null
echo "=========================================="
