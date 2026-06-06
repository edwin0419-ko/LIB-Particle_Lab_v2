#!/usr/bin/env bash
# Particle Lab — 두 서버 (백엔드 + 프론트) 띄우기.
#
# 사용법:
#   bash scripts/start.sh                          # localhost only, foreground
#   PUBLIC=1 bash scripts/start.sh                 # 0.0.0.0 바인딩 (외부 접속)
#   API_URL=https://1.2.3.4:8765 PUBLIC=1 bash scripts/start.sh
#   DETACHED=1 PUBLIC=1 bash scripts/start.sh      # 백그라운드 — 셸 닫혀도 안 죽음
#
# RunPod 호환:
#   - placeholder nginx 가 3000/8765 잡고 있으면 자동 kill
#   - 이전 uvicorn/next 프로세스도 자동 정리
#
# foreground 모드: Ctrl+C 한 번에 둘 다 종료.
# detached 모드: 로그는 /workspace/uvicorn.log, /workspace/front.log (또는 PROJECT_ROOT 의 logs/).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/app/backend"
FRONTEND_DIR="$PROJECT_ROOT/app/frontend"
PUBLIC="${PUBLIC:-0}"
API_URL="${API_URL:-}"
DETACHED="${DETACHED:-0}"

if [[ "$PUBLIC" == "1" ]]; then
    HOST="0.0.0.0"
    NEXT_HOST="-H 0.0.0.0"
else
    HOST="127.0.0.1"
    NEXT_HOST=""
fi

# 로그 위치
if [[ -d "/workspace" ]]; then
    LOG_DIR="/workspace"
else
    LOG_DIR="$PROJECT_ROOT/logs"
    mkdir -p "$LOG_DIR"
fi

# ---------- 포트 점유자 정리 ----------
free_port() {
    local port=$1
    local who=""
    if command -v ss >/dev/null 2>&1; then
        who="$(ss -lntp 2>/dev/null | awk -v p=":$port " '$4 ~ p {print}' | head -1)"
    fi
    if [[ -n "$who" ]]; then
        echo "    포트 $port 점유 중 — 정리"
        if [[ "$who" == *nginx* ]]; then
            nginx -s stop 2>/dev/null || pkill -9 nginx 2>/dev/null || true
        elif command -v lsof >/dev/null 2>&1; then
            lsof -ti ":$port" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
        elif command -v fuser >/dev/null 2>&1; then
            fuser -k "$port/tcp" 2>/dev/null || true
        fi
        sleep 1
    fi
}

echo "==> 포트 정리"
free_port 8765
free_port 3000

# 학습 결과 영구 저장 위치
if [[ -z "${PLAB_RUNS_DIR:-}" ]]; then
    if [[ -d "/workspace" ]]; then
        export PLAB_RUNS_DIR="/workspace/Particle_lab/runs"
    else
        export PLAB_RUNS_DIR="$PROJECT_ROOT/runs"
    fi
fi
mkdir -p "$PLAB_RUNS_DIR"
echo "    학습 결과 저장 위치: $PLAB_RUNS_DIR"

# ---------- DETACHED 모드 — 셸 닫혀도 살아있음 ----------
# setsid 가 있으면 새 session leader 로 (Linux/RunPod), 없으면 nohup fallback (macOS).
if [[ "$DETACHED" == "1" ]]; then
    if command -v setsid >/dev/null 2>&1; then
        DETACH_CMD="setsid"
    else
        DETACH_CMD="nohup"
    fi
    echo "==> 백엔드 시작 ($HOST:8765, detached via $DETACH_CMD)"
    cd "$BACKEND_DIR"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    $DETACH_CMD uvicorn app.main:app --host "$HOST" --port 8765 \
        > "$LOG_DIR/uvicorn.log" 2>&1 < /dev/null &
    disown
    BACKEND_PID=$!
    echo "    backend pid: $BACKEND_PID, log: $LOG_DIR/uvicorn.log"

    sleep 3
    echo "==> 프론트 시작 ($HOST:3000, detached via $DETACH_CMD)"
    cd "$FRONTEND_DIR"
    if [[ -n "$API_URL" ]]; then
        $DETACH_CMD env NEXT_PUBLIC_API_BASE="$API_URL" npm run dev -- $NEXT_HOST -p 3000 \
            > "$LOG_DIR/front.log" 2>&1 < /dev/null &
    else
        $DETACH_CMD npm run dev -- $NEXT_HOST -p 3000 \
            > "$LOG_DIR/front.log" 2>&1 < /dev/null &
    fi
    disown
    FRONT_PID=$!
    echo "    frontend pid: $FRONT_PID, log: $LOG_DIR/front.log"

    sleep 5
    echo ""
    echo "==> 상태 확인"
    if command -v ss >/dev/null 2>&1; then
        ss -lntp 2>/dev/null | grep -E ":(8765|3000) " || echo "    포트 안 잡힘 — 로그 확인:"
    fi
    echo ""
    echo " 로그 보기:"
    echo "    tail -f $LOG_DIR/uvicorn.log"
    echo "    tail -f $LOG_DIR/front.log"
    echo " 종료: pkill -f uvicorn && pkill -f 'next dev'"
    exit 0
fi

# ---------- FOREGROUND 모드 ----------
echo "==> 백엔드 시작 ($HOST:8765)"
cd "$BACKEND_DIR"
# shellcheck disable=SC1091
source .venv/bin/activate
uvicorn app.main:app --host "$HOST" --port 8765 &
BACKEND_PID=$!

trap 'echo; echo "==> 종료 중..."; kill $BACKEND_PID 2>/dev/null || true; exit' INT TERM

sleep 2
echo "==> 프론트 시작 ($HOST:3000)"
cd "$FRONTEND_DIR"
if [[ -n "$API_URL" ]]; then
    NEXT_PUBLIC_API_BASE="$API_URL" npm run dev -- $NEXT_HOST -p 3000
else
    npm run dev -- $NEXT_HOST -p 3000
fi
