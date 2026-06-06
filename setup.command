#!/usr/bin/env bash
# Particle Lab v2 — 첫 실행 설정 (macOS)
# venv 생성 + Python 의존성 + Node 의존성 + 프런트 빌드
# start.command 가 자동으로 호출하므로 사용자가 직접 실행할 일은 거의 없음.

set -euo pipefail

G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; N='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd -P )"
cd "$SCRIPT_DIR"

printf "${G}▸ Python 가상환경 만들기${N}\n"
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
# shellcheck disable=SC1091
source "venv/bin/activate"

printf "${G}▸ pip 업그레이드${N}\n"
python -m pip install --upgrade pip wheel --quiet

printf "${G}▸ 백엔드 Python 패키지 설치 (PyTorch 포함, 약 2분)${N}\n"
# requirements.txt 는 torch 를 명시 안 함 — 별도로 설치
pip install --quiet -r app/backend/requirements.txt

# PyTorch — Apple Silicon 은 자동으로 MPS 지원 빌드 받음
printf "${G}▸ PyTorch 설치 (CPU/MPS)${N}\n"
pip install --quiet torch torchvision

printf "${G}▸ Node 패키지 설치${N}\n"
(
  cd app/frontend
  if [ -f "package-lock.json" ]; then
    npm ci --silent --no-audit --no-fund || npm install --silent --no-audit --no-fund
  else
    npm install --silent --no-audit --no-fund
  fi
)

printf "${G}▸ 프런트엔드 프로덕션 빌드 (약 30초)${N}\n"
(
  cd app/frontend
  npm run build
)

printf "\n${G}✓ 설정 완료${N}\n"
