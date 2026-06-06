#!/usr/bin/env bash
# Particle Lab v2 — macOS 더블클릭 런처
# USB 에 프로젝트를 넣고 이 파일을 더블클릭하면 자동으로:
#   1) 처음이면 venv + 의존성 설치 + 프런트 빌드 (약 5분)
#   2) 백엔드 (FastAPI, 포트 8765) 시작
#   3) 프런트엔드 (Next.js, 포트 3001) 시작
#   4) Chrome 으로 http://localhost:3001 열기
# 터미널을 닫거나 Ctrl+C 누르면 두 서버가 함께 종료됩니다.

set -uo pipefail

# 색상
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; C='\033[1;36m'; N='\033[0m'

# 이 스크립트가 있는 디렉토리로 이동 (USB 경로 어디든 OK)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd -P )"
cd "$SCRIPT_DIR"

clear
printf "${C}┌─────────────────────────────────────────┐${N}\n"
printf "${C}│   Particle Lab v2 — 자동 실행 중...      │${N}\n"
printf "${C}└─────────────────────────────────────────┘${N}\n\n"

# ── 사전 확인 ──
need() {
  local cmd="$1" name="$2" url="$3"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    printf "${R}✗ $name 이(가) 설치되어 있지 않습니다.${N}\n"
    printf "  설치: $url\n"
    printf "\n엔터를 누르면 종료합니다..."
    read -r _
    exit 1
  fi
}
need python3 "Python 3" "https://www.python.org/downloads/  또는  brew install python"
need node "Node.js"   "https://nodejs.org/  또는  brew install node"
need npm  "npm"       "Node.js 와 함께 설치됩니다"
need curl "curl"      "macOS 기본 포함 (없으면 brew install curl)"

# ── 첫 실행이면 setup 호출 ──
NEED_SETUP=0
[ ! -d "venv" ] && NEED_SETUP=1
[ ! -d "app/frontend/node_modules" ] && NEED_SETUP=1
[ ! -d "app/frontend/.next" ] && NEED_SETUP=1

if [ "$NEED_SETUP" = "1" ]; then
  printf "${Y}▸ 처음 실행 — 환경 설정 (약 5분)${N}\n"
  if [ -x "./setup.command" ]; then
    "./setup.command" || { printf "${R}설정 실패. 위 로그를 확인하세요.${N}\n"; read -r _; exit 1; }
  else
    bash "./setup.command" || { printf "${R}설정 실패.${N}\n"; read -r _; exit 1; }
  fi
  printf "\n"
fi

# venv 활성화
# shellcheck disable=SC1091
source "venv/bin/activate"

# ── 기존 잔여 프로세스 정리 ──
for PORT in 8765 3001; do
  PIDS=$(lsof -ti:$PORT 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    printf "${Y}▸ 포트 $PORT 사용 중인 프로세스 정리...${N}\n"
    kill -9 $PIDS 2>/dev/null || true
    sleep 0.5
  fi
done

# ── 백엔드 시작 ──
printf "${G}▸ 백엔드 시작 (FastAPI, 포트 8765)...${N}\n"
mkdir -p logs
(
  cd app/backend
  # PYTHONPATH 에 프로젝트 루트 추가 → evaluate.py / hybrid_core.py 등 import 가능
  PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/app/backend" \
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
) > "logs/backend.log" 2>&1 &
BACKEND_PID=$!

# 백엔드 준비 대기 (최대 60초)
printf "  대기"
for i in $(seq 1 60); do
  if curl -s -o /dev/null http://127.0.0.1:8765/api/health 2>/dev/null; then
    printf " ${G}OK${N}\n"
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    printf "\n${R}✗ 백엔드가 시작되지 않았습니다. logs/backend.log 확인:${N}\n"
    tail -n 25 logs/backend.log
    read -r _
    exit 1
  fi
  printf "."
  sleep 1
done

# ── 프런트엔드 시작 ──
printf "${G}▸ 프런트엔드 시작 (Next.js, 포트 3001)...${N}\n"
(
  cd app/frontend
  PORT=3001 npm run start -- -p 3001
) > "logs/frontend.log" 2>&1 &
FRONTEND_PID=$!

# 프런트엔드 준비 대기 (최대 30초)
printf "  대기"
for i in $(seq 1 30); do
  if curl -s -o /dev/null http://127.0.0.1:3001 2>/dev/null; then
    printf " ${G}OK${N}\n"
    break
  fi
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    printf "\n${R}✗ 프런트엔드가 시작되지 않았습니다. logs/frontend.log 확인:${N}\n"
    tail -n 25 logs/frontend.log
    kill -9 "$BACKEND_PID" 2>/dev/null || true
    read -r _
    exit 1
  fi
  printf "."
  sleep 1
done

# ── 브라우저 열기 ──
URL="http://localhost:3001"
printf "${G}▸ 브라우저 열기${N}\n"
if open -a "Google Chrome" "$URL" 2>/dev/null; then
  printf "  ${G}Chrome${N} 으로 열림\n"
else
  printf "  Chrome 미설치 — 기본 브라우저로 엽니다\n"
  open "$URL"
fi

printf "\n"
printf "${C}╔══════════════════════════════════════════════╗${N}\n"
printf "${C}║   ✓ Particle Lab 실행 중                      ║${N}\n"
printf "${C}║                                              ║${N}\n"
printf "${C}║   접속 주소:  ${G}http://localhost:3001${C}          ║${N}\n"
printf "${C}║                                              ║${N}\n"
printf "${C}║   종료하려면 이 창을 닫거나 Ctrl+C 누르세요   ║${N}\n"
printf "${C}╚══════════════════════════════════════════════╝${N}\n"
printf "\n  로그: logs/backend.log  logs/frontend.log\n\n"

# ── 종료 핸들러 ──
cleanup() {
  printf "\n${Y}▸ 종료 중...${N}\n"
  kill "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
  sleep 0.3
  for PORT in 8765 3001; do
    PIDS=$(lsof -ti:$PORT 2>/dev/null || true)
    [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null || true
  done
  printf "${G}끝.${N}\n"
}
trap cleanup EXIT INT TERM HUP

# 두 프로세스 대기 (둘 중 하나가 죽으면 같이 종료)
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
cleanup
