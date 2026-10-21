#!/bin/bash
# 매주 월요일 오전 9시 자동 실행: 광고 수집 → GitHub push → Streamlit Cloud 자동 배포

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

TODAY=$(date +%Y-%m-%d)
LOG_DIR="$PROJECT_ROOT/data/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${TODAY}_cron.log"

echo "================================" >> "$LOG_FILE"
echo "시작: $(date)" >> "$LOG_FILE"
echo "================================" >> "$LOG_FILE"

if [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# 전체 경쟁사 수집
python scraper/main.py >> "$LOG_FILE" 2>&1

# 웹사이트용 썸네일 (원본 data/media는 용량 때문에 GitHub 제외)
python scripts/make_thumbs.py >> "$LOG_FILE" 2>&1

# DB·썸네일 변경 있으면 커밋 + push
git add data/ads.db data/thumbs
if ! git diff --cached --quiet; then
    git commit -m "자동 수집: ${TODAY}" >> "$LOG_FILE" 2>&1
    git push origin main >> "$LOG_FILE" 2>&1
    echo "✅ GitHub push 완료" >> "$LOG_FILE"
else
    echo "새 광고 없음 — push 생략" >> "$LOG_FILE"
fi

echo "================================" >> "$LOG_FILE"
echo "끝: $(date)" >> "$LOG_FILE"
echo "================================" >> "$LOG_FILE"
