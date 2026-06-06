#!/usr/bin/env bash
# Particle Lab v2 — 휴대용 번들 빌더 (macOS 에서 실행)
# 결과:
#   dist/Particle_lab_v2_mac/   — macOS Apple Silicon, 즉시 더블클릭 실행
#   dist/Particle_lab_v2_win/   — Windows x64, 즉시 더블클릭 실행
#
# 두 폴더 모두 Python·Node 가 깔려 있지 않은 컴퓨터에서도 동작합니다.

set -euo pipefail

G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; C='\033[1;36m'; N='\033[0m'

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd -P )"
cd "$ROOT"

CACHE="${CACHE_DIR:-$ROOT/.build_cache}"
# 로컬 스테이징 (HFS+/APFS 에서만 pip 가 안정적으로 동작)
STAGE="${STAGE_DIR:-$ROOT/dist}"
# 최종 위치 — USB 등 외장 가능. 미지정 시 로컬과 동일.
FINAL="${DIST_DIR:-$STAGE}"
MAC_DIR="$STAGE/Particle_lab_v2_mac"
WIN_DIR="$STAGE/Particle_lab_v2_win"
# 플랫폼 선택 — mac / win / both (기본 both)
PLATFORM="${PLATFORM:-both}"

# 로컬→최종 이동 (cross-filesystem 도 안전)
relocate_to_final() {
  local name="$1"  # 예: Particle_lab_v2_mac
  if [ "$STAGE" = "$FINAL" ]; then return; fi
  if [ ! -d "$STAGE/$name" ]; then return; fi
  mkdir -p "$FINAL"
  printf "  ${C}최종 위치로 복사:${N} $FINAL/$name (시간 좀 걸림)\n"
  rm -rf "$FINAL/$name"
  # -L: 심볼릭 링크를 실제 파일로 복사 (ExFAT 는 심볼릭 링크 미지원)
  if cp -RL "$STAGE/$name" "$FINAL/" ; then
    rm -rf "$STAGE/$name"
    printf "  ${G}이동 완료, 로컬 정리됨${N}\n"
  else
    printf "  ${R}복사 실패${N}\n"
    return 1
  fi
}

# ── 버전 ──
PY_VERSION="3.12.7"
PY_TAG="20241016"
NODE_VERSION="20.18.0"

PY_MAC_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TAG}/cpython-${PY_VERSION}+${PY_TAG}-aarch64-apple-darwin-install_only.tar.gz"
PY_WIN_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TAG}/cpython-${PY_VERSION}+${PY_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz"
NODE_MAC_URL="https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-darwin-arm64.tar.xz"
NODE_WIN_URL="https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-win-x64.zip"

mkdir -p "$CACHE" "$STAGE"
[ "$STAGE" != "$FINAL" ] && mkdir -p "$FINAL"

# ─────── 다운로드 헬퍼 ───────
download() {
  local url="$1" out="$2"
  if [ -f "$out" ] && [ -s "$out" ]; then
    printf "  ${G}cached:${N} %s\n" "$(basename "$out")"
    return
  fi
  printf "  ${C}download:${N} %s\n" "$url"
  curl -fL --progress-bar -o "$out.partial" "$url"
  mv "$out.partial" "$out"
}

printf "${C}┌─────────────────────────────────────────────┐${N}\n"
printf "${C}│   Particle Lab v2 — 휴대용 번들 빌드        │${N}\n"
printf "${C}└─────────────────────────────────────────────┘${N}\n\n"

# ─────── 0. 다운로드 ───────
printf "${C}[0/6] 휴대용 Python·Node 다운로드${N}\n"
download "$PY_MAC_URL"   "$CACHE/python_mac_arm64.tar.gz"
download "$PY_WIN_URL"   "$CACHE/python_win_x64.tar.gz"
download "$NODE_MAC_URL" "$CACHE/node_mac.tar.xz"
download "$NODE_WIN_URL" "$CACHE/node_win.zip"
echo

# ─────── 1. 소스 카피 ───────
copy_source() {
  local target="$1"
  rm -rf "$target"
  mkdir -p "$target"
  # 프로젝트 루트 파일 + app/, basic_pt/ 복사 (dist/, .build_cache/, venv/, .next/, node_modules/, logs/, runs/, __pycache__/, .git/ 제외)
  rsync -a \
    --exclude='dist/' \
    --exclude='.build_cache/' \
    --exclude='venv/' \
    --exclude='.venv' \
    --exclude='.venv/' \
    --exclude='.next/' \
    --exclude='node_modules/' \
    --exclude='logs/' \
    --exclude='runs/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.git/' \
    --exclude='.gitignore' \
    --exclude='*.bak' \
    --exclude='start.command' \
    --exclude='setup.command' \
    --exclude='stop.command' \
    --exclude='START.bat' \
    --exclude='SETUP.bat' \
    --exclude='STOP.bat' \
    --exclude='시작하기.md' \
    --exclude='build_portable_bundles.sh' \
    "$ROOT/" "$target/"
}

# ─────── 2. macOS 번들 ───────
if [ "$PLATFORM" = "mac" ] || [ "$PLATFORM" = "both" ]; then
printf "${C}[1/6] macOS 번들 — 폴더 만들기${N}\n"
copy_source "$MAC_DIR"
mkdir -p "$MAC_DIR/runtime"

printf "${C}[2/6] macOS 번들 — Python·Node 풀기${N}\n"
tar -xzC "$MAC_DIR/runtime" -f "$CACHE/python_mac_arm64.tar.gz"   # → runtime/python/
TMP="$(mktemp -d)"
tar -xJC "$TMP" -f "$CACHE/node_mac.tar.xz"
mv "$TMP/node-v${NODE_VERSION}-darwin-arm64" "$MAC_DIR/runtime/node"
rm -rf "$TMP"

printf "${C}[3/6] macOS 번들 — pip 패키지 설치 (~2~3분)${N}\n"
"$MAC_DIR/runtime/python/bin/python3" -m pip install --quiet --upgrade pip wheel \
  --target="$MAC_DIR/runtime/site-packages"
"$MAC_DIR/runtime/python/bin/python3" -m pip install --quiet \
  --target="$MAC_DIR/runtime/site-packages" \
  -r "$MAC_DIR/app/backend/requirements.txt"
"$MAC_DIR/runtime/python/bin/python3" -m pip install --quiet \
  --target="$MAC_DIR/runtime/site-packages" \
  torch torchvision

printf "${C}[4/6] macOS 번들 — Next.js 빌드${N}\n"
(
  cd "$MAC_DIR/app/frontend"
  PATH="$MAC_DIR/runtime/node/bin:$PATH" "$MAC_DIR/runtime/node/bin/npm" install --no-audit --no-fund --silent
  # standalone 은 프런트(3001)·백엔드(8765) 가 별도 포트라 절대 URL 필요.
  # api.ts fallback 이 ""(상대경로)로 바뀌었고 next.config 의 env inline 은 신뢰 불가하므로,
  # 실제 환경변수로 NEXT_PUBLIC_API_BASE 를 주입한다 (Next 표준 빌드타임 치환 → 확실히 박힘).
  PATH="$MAC_DIR/runtime/node/bin:$PATH" NEXT_PUBLIC_API_BASE="http://localhost:8765" "$MAC_DIR/runtime/node/bin/npm" run build
  # standalone 출력 → 정적 자산 + public 을 안으로 복사 (Next.js 권장)
  cp -R .next/static .next/standalone/.next/
  if [ -d public ]; then cp -R public .next/standalone/; fi
  # node_modules 삭제 — standalone 안에 필요한 것만 들어있어서 더 이상 필요 없음
  rm -rf node_modules
)

# Mac 런처
cat > "$MAC_DIR/start.command" <<'MAC_LAUNCHER'
#!/usr/bin/env bash
# Particle Lab v2 — 휴대용 (macOS Apple Silicon)
# Python·Node 가 깔려 있지 않아도 동작. runtime/ 안의 바이너리만 사용.
set -uo pipefail
G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; C='\033[1;36m'; N='\033[0m'

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd -P )"
cd "$SCRIPT_DIR"

clear
printf "${C}┌─────────────────────────────────────────┐${N}\n"
printf "${C}│   Particle Lab v2 — 휴대용 (macOS)       │${N}\n"
printf "${C}└─────────────────────────────────────────┘${N}\n\n"

PY="$SCRIPT_DIR/runtime/python/bin/python3"
NODE="$SCRIPT_DIR/runtime/node/bin/node"
PKGS="$SCRIPT_DIR/runtime/site-packages"
[ -x "$PY"   ] || { printf "${R}runtime/python 없음. 번들 손상.${N}\n"; read -r _; exit 1; }
[ -x "$NODE" ] || { printf "${R}runtime/node 없음. 번들 손상.${N}\n";   read -r _; exit 1; }

mkdir -p logs

# 잔여 프로세스 정리
for PORT in 8765 3001; do
  PIDS=$(lsof -ti:$PORT 2>/dev/null || true)
  [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null || true
done

# 백엔드
printf "${G}▸ 백엔드 시작 (8765)${N}\n"
(
  cd app/backend
  PYTHONPATH="$PKGS:$SCRIPT_DIR:$SCRIPT_DIR/app/backend" \
    "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8765
) > "logs/backend.log" 2>&1 &
BACKEND_PID=$!

printf "  대기"
for i in $(seq 1 60); do
  if curl -s -o /dev/null http://127.0.0.1:8765/api/health 2>/dev/null; then
    printf " ${G}OK${N}\n"; break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    printf "\n${R}✗ 백엔드 시작 실패. logs/backend.log:${N}\n"; tail -n 25 logs/backend.log
    read -r _; exit 1
  fi
  printf "."; sleep 1
done

# 프런트엔드 (Next.js standalone)
printf "${G}▸ 프런트엔드 시작 (3001)${N}\n"
(
  cd app/frontend/.next/standalone
  PORT=3001 HOSTNAME=127.0.0.1 "$NODE" server.js
) > "logs/frontend.log" 2>&1 &
FRONTEND_PID=$!

printf "  대기"
for i in $(seq 1 30); do
  if curl -s -o /dev/null http://127.0.0.1:3001 2>/dev/null; then
    printf " ${G}OK${N}\n"; break
  fi
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    printf "\n${R}✗ 프런트엔드 시작 실패. logs/frontend.log:${N}\n"; tail -n 25 logs/frontend.log
    kill -9 "$BACKEND_PID" 2>/dev/null || true
    read -r _; exit 1
  fi
  printf "."; sleep 1
done

# Chrome 열기
URL="http://localhost:3001"
printf "${G}▸ 브라우저 열기${N}\n"
open -a "Google Chrome" "$URL" 2>/dev/null || open "$URL"

printf "\n${C}╔══════════════════════════════════════════════╗${N}\n"
printf "${C}║  ✓ Particle Lab 실행 중                        ║${N}\n"
printf "${C}║  접속:  ${G}http://localhost:3001${C}                   ║${N}\n"
printf "${C}║  종료:  Ctrl+C 또는 이 창 닫기                  ║${N}\n"
printf "${C}╚══════════════════════════════════════════════╝${N}\n\n"

cleanup() {
  printf "\n${Y}▸ 종료 중...${N}\n"
  kill "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
  sleep 0.3
  for PORT in 8765 3001; do
    PIDS=$(lsof -ti:$PORT 2>/dev/null || true)
    [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM HUP
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
cleanup
MAC_LAUNCHER
chmod +x "$MAC_DIR/start.command"

# Mac 안내
cat > "$MAC_DIR/시작하기.txt" <<'MAC_README'
Particle Lab v2 — macOS 휴대용 번들

start.command 를 더블클릭하세요.

처음 더블클릭 시 "확인되지 않은 개발자" 경고가 뜨면:
  start.command 우클릭 → "열기" → 대화창에서 "열기" 한 번만 누르세요.

종료: Terminal 창을 닫거나 Ctrl+C
MAC_README

fi  # end PLATFORM mac

# ─────── 3. Windows 번들 ───────
if [ "$PLATFORM" = "win" ] || [ "$PLATFORM" = "both" ]; then
printf "${C}[5/6] Windows 번들 — 폴더·런타임·소스 준비${N}\n"
copy_source "$WIN_DIR"
mkdir -p "$WIN_DIR/runtime"

tar -xzC "$WIN_DIR/runtime" -f "$CACHE/python_win_x64.tar.gz"   # → runtime/python/
TMP="$(mktemp -d)"
unzip -q "$CACHE/node_win.zip" -d "$TMP"
mv "$TMP/node-v${NODE_VERSION}-win-x64" "$WIN_DIR/runtime/node"
rm -rf "$TMP"

printf "${C}[6/6] Windows 번들 — Python·Next.js 자산 (Mac 측에서 cross-build)${N}\n"
# Windows 용 휠을 Mac 측 pip 으로 받아서 site-packages 에 풀어둠
"$MAC_DIR/runtime/python/bin/python3" -m pip install --quiet \
  --target="$WIN_DIR/runtime/site-packages" \
  --platform=win_amd64 \
  --python-version=3.12 \
  --only-binary=:all: \
  --upgrade pip wheel || true
"$MAC_DIR/runtime/python/bin/python3" -m pip install --quiet \
  --target="$WIN_DIR/runtime/site-packages" \
  --platform=win_amd64 \
  --python-version=3.12 \
  --only-binary=:all: \
  -r "$WIN_DIR/app/backend/requirements.txt" \
  || printf "${Y}  일부 패키지 cross-install 실패 — Windows 에서 첫 실행 시 자동 보충됩니다${N}\n"
"$MAC_DIR/runtime/python/bin/python3" -m pip install --quiet \
  --target="$WIN_DIR/runtime/site-packages" \
  --platform=win_amd64 \
  --python-version=3.12 \
  --only-binary=:all: \
  torch torchvision \
  || printf "${Y}  torch cross-install 실패 — Windows 에서 자동 보충됩니다${N}\n"

# Next.js standalone 출력 — 플랫폼 독립이므로 Mac 빌드 결과 그대로 재사용
mkdir -p "$WIN_DIR/app/frontend"
cp -R "$MAC_DIR/app/frontend/.next" "$WIN_DIR/app/frontend/"

# Windows 런처
cat > "$WIN_DIR/START.bat" <<'WIN_LAUNCHER'
@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

cls
echo ===========================================
echo    Particle Lab v2 - Portable (Windows)
echo ===========================================
echo.

set PY=%~dp0runtime\python\python.exe
set NODE=%~dp0runtime\node\node.exe
set NPM=%~dp0runtime\node\npm.cmd
set PKGS=%~dp0runtime\site-packages

if not exist "%PY%" (
  echo [ERROR] runtime\python\python.exe not found. Bundle corrupt.
  pause & exit /b 1
)
if not exist "%NODE%" (
  echo [ERROR] runtime\node\node.exe not found.
  pause & exit /b 1
)

if not exist "logs" mkdir "logs"

REM 첫 실행 보강 — Windows 휠이 cross-install 시 일부 빠졌을 수 있어 보충
if not exist "%PKGS%\torch" (
  echo [SETUP] 첫 실행 — Python 패키지 보충 중 ^(약 3~5분^)
  "%PY%" -m pip install --target="%PKGS%" --upgrade pip wheel
  "%PY%" -m pip install --target="%PKGS%" -r "app\backend\requirements.txt"
  "%PY%" -m pip install --target="%PKGS%" torch torchvision
)

REM 잔여 프로세스 정리
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3001 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1

echo [START] Backend (port 8765)
set PYTHONPATH=%PKGS%;%CD%;%CD%\app\backend
start "Particle Lab - Backend" /MIN cmd /c "cd app\backend && "%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8765 > ..\..\logs\backend.log 2>&1"

set /a count=0
:wait_backend
timeout /t 1 /nobreak >nul
curl -s -o nul http://127.0.0.1:8765/api/health 2>nul
if not errorlevel 1 goto backend_ready
set /a count+=1
if !count! lss 60 goto wait_backend
echo [ERROR] Backend failed. See logs\backend.log
pause & exit /b 1
:backend_ready

echo [START] Frontend (port 3001)
start "Particle Lab - Frontend" /MIN cmd /c "cd app\frontend\.next\standalone && set PORT=3001 && set HOSTNAME=127.0.0.1 && "%NODE%" server.js > ..\..\..\..\logs\frontend.log 2>&1"

set /a count=0
:wait_frontend
timeout /t 1 /nobreak >nul
curl -s -o nul http://127.0.0.1:3001 2>nul
if not errorlevel 1 goto frontend_ready
set /a count+=1
if !count! lss 30 goto wait_frontend
echo [ERROR] Frontend failed. See logs\frontend.log
pause & exit /b 1
:frontend_ready

set CHROME=""
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set CHROME="%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set CHROME="%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not %CHROME%=="" (
  start "" %CHROME% "http://localhost:3001"
) else (
  start "" "http://localhost:3001"
)

echo.
echo ===========================================
echo    Particle Lab running
echo    URL:  http://localhost:3001
echo    Stop: close this window or run STOP.bat
echo ===========================================
echo.
pause
WIN_LAUNCHER

cat > "$WIN_DIR/STOP.bat" <<'WIN_STOP'
@echo off
chcp 65001 >nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3001 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
echo Stopped.
timeout /t 1 /nobreak >nul
WIN_STOP

cat > "$WIN_DIR/시작하기.txt" <<'WIN_README'
Particle Lab v2 — Windows 휴대용 번들

START.bat 을 더블클릭하세요.

첫 실행 시 일부 Python 패키지가 cross-build 단계에서 빠졌으면
3~5분간 자동으로 보충됩니다 (이후로는 즉시 실행).

종료: 백엔드/프런트엔드 창을 닫거나 STOP.bat 더블클릭

만약 SmartScreen 경고가 뜨면: "추가 정보" → "실행" 한 번만 누르세요.
WIN_README

# ─────── 마무리 ───────
fi  # end PLATFORM win  (close conditional for the entire Win section)

# 빌드 완료 — 이제 최종 위치로 이동
if [ "$STAGE" != "$FINAL" ]; then
  printf "\n${C}▸ 로컬 빌드 결과를 최종 위치(${FINAL})로 이동${N}\n"
  [ "$PLATFORM" = "mac" ] || [ "$PLATFORM" = "both" ] && relocate_to_final "Particle_lab_v2_mac"
  [ "$PLATFORM" = "win" ] || [ "$PLATFORM" = "both" ] && relocate_to_final "Particle_lab_v2_win"
fi

printf "\n${G}════════════════════════════════════════════════${N}\n"
printf "${G}✓ 완료${N}\n"
printf "${G}════════════════════════════════════════════════${N}\n\n"
printf "  ${C}macOS:${N}   $FINAL/Particle_lab_v2_mac\n"
printf "  ${C}Windows:${N} $FINAL/Particle_lab_v2_win\n\n"
printf "  USB 에 들고 다니면서:\n"
printf "  macOS:   start.command 더블클릭\n"
printf "  Windows: START.bat 더블클릭\n\n"
du -sh "$FINAL/Particle_lab_v2_mac" "$FINAL/Particle_lab_v2_win" 2>/dev/null || true
