#!/usr/bin/env bash
# Particle Lab v2 — 데스크탑 앱 빌더 (macOS 에서 실행)
#
# 산출물:
#   dist/Particle Lab v2.app/                  ← macOS 더블클릭 한 번에 실행
#   dist/Particle_Lab_v2_Windows/              ← 폴더 → 안의 START.bat 더블클릭
#
# 두 결과물 모두 Python·Node 미설치 PC 에서 동작.
# Next.js export + FastAPI 정적 서빙 + pywebview 데스크탑 창 — 단일 Python 프로세스.

set -euo pipefail

G='\033[1;32m'; Y='\033[1;33m'; R='\033[1;31m'; C='\033[1;36m'; N='\033[0m'

ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd -P )"
cd "$ROOT"

CACHE="${CACHE_DIR:-$ROOT/.build_cache}"
DIST="${DIST_DIR:-$ROOT/dist}"
PLATFORM="${PLATFORM:-both}"   # mac | win | both
MAC_APP="$DIST/Particle Lab v2.app"
WIN_DIR="$DIST/Particle_Lab_v2_Windows"

PY_VERSION="3.12.7"
PY_TAG="20241016"
PY_MAC_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TAG}/cpython-${PY_VERSION}+${PY_TAG}-aarch64-apple-darwin-install_only.tar.gz"
PY_WIN_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_TAG}/cpython-${PY_VERSION}+${PY_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz"

mkdir -p "$CACHE" "$DIST"

printf "${C}┌────────────────────────────────────────────────┐${N}\n"
printf "${C}│   Particle Lab v2 — 데스크탑 앱 빌드             │${N}\n"
printf "${C}└────────────────────────────────────────────────┘${N}\n\n"

# ─────── 0. 휴대용 Python 다운로드 ───────
download() {
  local url="$1" out="$2"
  if [ -f "$out" ] && [ -s "$out" ]; then
    printf "  ${G}cached:${N} %s\n" "$(basename "$out")"; return
  fi
  printf "  ${C}download:${N} %s\n" "$url"
  curl -fL --progress-bar -o "$out.partial" "$url"
  mv "$out.partial" "$out"
}

printf "${C}[0/5] 휴대용 Python 다운로드${N}\n"
[ "$PLATFORM" != "win" ] && download "$PY_MAC_URL" "$CACHE/python_mac_arm64.tar.gz"
[ "$PLATFORM" != "mac" ] && download "$PY_WIN_URL" "$CACHE/python_win_x64.tar.gz"
echo

# ─────── 1. Next.js export 빌드 (Mac/Win 공용) ───────
printf "${C}[1/5] Next.js export 빌드${N}\n"
if [ ! -d "$ROOT/app/frontend/node_modules" ]; then
  printf "  ${Y}node_modules 없음 → npm install (한 번만)${N}\n"
  ( cd "$ROOT/app/frontend" && npm install --no-audit --no-fund --silent )
fi
( cd "$ROOT/app/frontend" && BUILD_TARGET=export npx next build > /dev/null )
[ -d "$ROOT/app/frontend/out" ] || { printf "${R}✗ out/ 생성 실패${N}\n"; exit 1; }
printf "  ${G}OK${N} — $(du -sh "$ROOT/app/frontend/out" | awk '{print $1}')\n\n"

# ─────── 자산 카피 헬퍼 (rsync) ───────
copy_assets() {
  local target="$1"
  mkdir -p "$target"
  rsync -a \
    --exclude='dist/' --exclude='.build_cache/' \
    --exclude='venv/' --exclude='.venv' --exclude='.venv/' \
    --exclude='.next/' --exclude='node_modules/' \
    --exclude='logs/' --exclude='runs/' \
    --exclude='__pycache__/' --exclude='*.pyc' \
    --exclude='.git/' --exclude='.gitignore' \
    --exclude='*.bak' --exclude='.DS_Store' \
    --exclude='build_portable_bundles.sh' \
    --exclude='build_desktop_app.sh' \
    --exclude='start.command' --exclude='setup.command' --exclude='stop.command' \
    --exclude='START.bat' --exclude='SETUP.bat' --exclude='STOP.bat' \
    --exclude='시작하기.md' \
    "$ROOT/" "$target/"
}

# ─────── 2. macOS .app 번들 ───────
if [ "$PLATFORM" = "mac" ] || [ "$PLATFORM" = "both" ]; then
  printf "${C}[2/5] macOS .app 번들 — 구조 만들기${N}\n"
  rm -rf "$MAC_APP"
  RES="$MAC_APP/Contents/Resources"
  mkdir -p "$MAC_APP/Contents/MacOS" "$RES"

  copy_assets "$RES"
  mkdir -p "$RES/runtime"
  # BSD tar 가 공백 들어간 .app 경로(-C)에서 디렉토리 자동 생성을 실패하므로
  # 임시 폴더에 풀고 mv 한다.
  TMPRT="$(mktemp -d)"
  tar -xzC "$TMPRT" -f "$CACHE/python_mac_arm64.tar.gz"
  mv "$TMPRT/python" "$RES/runtime/python"
  rm -rf "$TMPRT"

  printf "${C}      → pip 패키지 설치 (~3~5분)${N}\n"
  # 한 번에 install — 동일 --target 에 여러 번 install 하면 transitive dep 가 충돌함.
  "$RES/runtime/python/bin/python3" -m pip install --no-input --disable-pip-version-check \
    --target="$RES/runtime/site-packages" \
    -r "$RES/app/backend/requirements.txt" \
    torch torchvision
  # 검증 — 핵심 패키지가 깔렸는지 확인 (silent fail 방지)
  for pkg in torch fastapi uvicorn webview ultralytics cv2 numpy scipy PIL; do
    if [ ! -d "$RES/runtime/site-packages/$pkg" ]; then
      printf "${R}✗ 핵심 패키지 누락: $pkg${N}\n"
      exit 1
    fi
  done
  printf "  ${G}OK${N} — site-packages: $(du -sh "$RES/runtime/site-packages" | awk '{print $1}')\n"

  # Info.plist
  cat > "$MAC_APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>ParticleLab</string>
    <key>CFBundleIdentifier</key><string>edu.sejong.particlelab.v2</string>
    <key>CFBundleName</key><string>Particle Lab v2</string>
    <key>CFBundleDisplayName</key><string>Particle Lab v2</string>
    <key>CFBundleVersion</key><string>2.0.0</string>
    <key>CFBundleShortVersionString</key><string>2.0.0</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundleIconName</key><string>AppIcon</string>
    <key>LSMinimumSystemVersion</key><string>11.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>LSUIElement</key><false/>
</dict>
</plist>
PLIST

  # 앱 아이콘 — logo.png → AppIcon.icns (있으면 생성/복사)
  if [ -f "$ROOT/logo.png" ]; then
    if [ ! -f "$ROOT/AppIcon.icns" ] || [ "$ROOT/logo.png" -nt "$ROOT/AppIcon.icns" ]; then
      ICONSET="$(mktemp -d)/AppIcon.iconset"; mkdir -p "$ICONSET"
      for sz in 16 32 128 256 512; do
        sips -z $sz $sz "$ROOT/logo.png" --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null 2>&1
        dbl=$((sz*2))
        sips -z $dbl $dbl "$ROOT/logo.png" --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null 2>&1
      done
      iconutil -c icns "$ICONSET" -o "$ROOT/AppIcon.icns" 2>/dev/null || true
    fi
    [ -f "$ROOT/AppIcon.icns" ] && cp "$ROOT/AppIcon.icns" "$RES/AppIcon.icns"
  fi

  # Entry: Contents/MacOS/ParticleLab → Resources/launcher.py 실행
  cat > "$MAC_APP/Contents/MacOS/ParticleLab" <<'ENTRY'
#!/bin/bash
HERE="$( cd "$(dirname "$0")/../Resources" && pwd -P )"
cd "$HERE"
# stdout/stderr → Resources/logs/launcher.log (디버깅용)
mkdir -p "$HERE/logs"
exec "$HERE/runtime/python/bin/python3" "$HERE/launcher.py" > "$HERE/logs/launcher.log" 2>&1
ENTRY
  chmod +x "$MAC_APP/Contents/MacOS/ParticleLab"

  printf "  ${G}OK${N} — %s\n\n" "$(du -sh "$MAC_APP" | awk '{print $1}')"
fi

# ─────── 3. Windows 폴더 ───────
if [ "$PLATFORM" = "win" ] || [ "$PLATFORM" = "both" ]; then
  printf "${C}[3/5] Windows 폴더 — 구조 만들기${N}\n"
  rm -rf "$WIN_DIR"
  copy_assets "$WIN_DIR"
  mkdir -p "$WIN_DIR/runtime"
  tar -xzC "$WIN_DIR/runtime" -f "$CACHE/python_win_x64.tar.gz"

  printf "${C}      → Windows 휠 cross-install (Mac 측 pip)${N}\n"
  WIN_PY_FOR_PIP="$ROOT/.build_cache/win_pip_helper/python/bin/python3"
  if [ ! -x "$WIN_PY_FOR_PIP" ]; then
    mkdir -p "$ROOT/.build_cache/win_pip_helper"
    tar -xzC "$ROOT/.build_cache/win_pip_helper" -f "$CACHE/python_mac_arm64.tar.gz" 2>/dev/null || true
  fi
  PIP_HOST_PY="${WIN_PY_FOR_PIP:-python3}"
  [ -x "$WIN_PY_FOR_PIP" ] || PIP_HOST_PY="$( [ -x "$MAC_APP/Contents/Resources/runtime/python/bin/python3" ] && echo "$MAC_APP/Contents/Resources/runtime/python/bin/python3" || echo python3 )"

  "$PIP_HOST_PY" -m pip install --quiet \
    --target="$WIN_DIR/runtime/site-packages" \
    --platform=win_amd64 --python-version=3.12 --only-binary=:all: \
    --upgrade pip wheel || true
  "$PIP_HOST_PY" -m pip install --quiet \
    --target="$WIN_DIR/runtime/site-packages" \
    --platform=win_amd64 --python-version=3.12 --only-binary=:all: \
    -r "$WIN_DIR/app/backend/requirements.txt" \
    || printf "${Y}  일부 패키지 cross-install 실패 — 첫 실행 시 자동 보충됩니다${N}\n"
  "$PIP_HOST_PY" -m pip install --quiet \
    --target="$WIN_DIR/runtime/site-packages" \
    --platform=win_amd64 --python-version=3.12 --only-binary=:all: \
    torch torchvision \
    || printf "${Y}  torch cross-install 실패 — 첫 실행 시 자동 보충됩니다${N}\n"

  # Windows 런처 — pythonw.exe 사용 → cmd 창 안 뜸
  cat > "$WIN_DIR/Particle Lab v2.bat" <<'WINBAT'
@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PYW=%~dp0runtime\python\pythonw.exe
set PY=%~dp0runtime\python\python.exe
set PKGS=%~dp0runtime\site-packages

if not exist "%PY%" (
  echo [ERROR] runtime\python\python.exe not found. Bundle corrupt.
  pause & exit /b 1
)

REM 첫 실행 보강 — Windows 휠 cross-install 시 빠졌을 수 있는 패키지
if not exist "%PKGS%\torch" (
  echo [SETUP] 첫 실행 - Python 패키지 보충 중 ^(약 3~5분, 인터넷 필요^)
  "%PY%" -m pip install --target="%PKGS%" --upgrade pip wheel
  "%PY%" -m pip install --target="%PKGS%" -r "app\backend\requirements.txt"
  "%PY%" -m pip install --target="%PKGS%" torch torchvision
  echo [SETUP] 완료
)

REM 백그라운드 실행 (cmd 창 깜빡임만)
start "" "%PYW%" "%~dp0launcher.py"
exit
WINBAT

  # 한국어 안내
  cat > "$WIN_DIR/시작하기.txt" <<'WINREADME'
Particle Lab v2 — Windows

"Particle Lab v2.bat" 더블클릭 → 데스크탑 창 뜸.

첫 실행 시 일부 Python 패키지를 인터넷에서 보충합니다 (3~5분, 1회만).
이후로는 즉시 실행.

SmartScreen 경고가 뜨면: "추가 정보" → "실행" 한 번만 누르세요.
WINREADME

  printf "  ${G}OK${N} — %s\n\n" "$(du -sh "$WIN_DIR" | awk '{print $1}')"
fi

# ─────── 4. 마무리 ───────
printf "${G}════════════════════════════════════════════════${N}\n"
printf "${G}✓ 빌드 완료${N}\n"
printf "${G}════════════════════════════════════════════════${N}\n\n"
[ -d "$MAC_APP" ] && printf "  ${C}macOS:${N}    %s\n" "$MAC_APP"
[ -d "$MAC_APP" ] && printf "             더블클릭 ▶ 데스크탑 창 자동 오픈\n"
[ -d "$WIN_DIR" ] && printf "  ${C}Windows:${N}  %s\n" "$WIN_DIR"
[ -d "$WIN_DIR" ] && printf "             폴더 통째로 옮긴 후 'Particle Lab v2.bat' 더블클릭\n"
printf "\n"
[ -d "$MAC_APP" ] && du -sh "$MAC_APP" 2>/dev/null
[ -d "$WIN_DIR" ] && du -sh "$WIN_DIR" 2>/dev/null
