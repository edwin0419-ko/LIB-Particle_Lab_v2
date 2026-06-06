#!/usr/bin/env bash
# 백엔드/프런트엔드 강제 종료 — 비정상 종료 후 정리 용
G='\033[1;32m'; Y='\033[1;33m'; N='\033[0m'

printf "${Y}▸ Particle Lab 프로세스 종료${N}\n"
for PORT in 8765 3001; do
  PIDS=$(lsof -ti:$PORT 2>/dev/null || true)
  if [ -n "$PIDS" ]; then
    kill -9 $PIDS 2>/dev/null || true
    printf "  ${G}포트 $PORT 정리${N}\n"
  fi
done
printf "${G}끝.${N}\n"
sleep 0.6
