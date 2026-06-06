#!/usr/bin/env bash
# Particle Lab — 원격 GPU 인스턴스 (RunPod / vast.ai / Lambda / Paperspace) 자동 셋업
#
# 사용법:
#   bash scripts/setup.sh         # 기본 (CUDA 12.1, GPU 자동 감지)
#   CUDA_TAG=cu118 bash scripts/setup.sh
#   CPU_ONLY=1 bash scripts/setup.sh
#
# RunPod / 비슷한 root 컨테이너에서:
#   - sudo 없으면 자동 우회
#   - placeholder nginx 가 3000/8765 잡고 있으면 자동 kill
#   - 호스트 NVIDIA 드라이버에 맞는 torch 강제 설치 (cu121 기본)
#   - 좀비 cudnn 상태 자동 복구
#
# 멱등 (idempotent) — 여러 번 실행해도 안전. Pod 재시작 후에도 동일 명령으로 복구.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/app/backend"
FRONTEND_DIR="$PROJECT_ROOT/app/frontend"
CUDA_TAG="${CUDA_TAG:-cu121}"
CPU_ONLY="${CPU_ONLY:-0}"

echo "==> Particle Lab setup"
echo "    project:   $PROJECT_ROOT"
echo "    cuda tag:  $CUDA_TAG"
echo "    cpu only:  $CPU_ONLY"
echo "    user:      $(id -un) (uid=$(id -u))"

# ---------- root 컨테이너용 가짜 sudo ----------
# RunPod 같은 root 컨테이너엔 sudo 가 없음. 이미 root 면 sudo 가짜로 통과시킴.
if [[ "$(id -u)" == "0" ]] && ! command -v sudo >/dev/null 2>&1; then
    echo "==> root 컨테이너 감지 — 가짜 sudo 생성 (이미 root)"
    cat > /usr/local/bin/sudo <<'SUDO_SHIM'
#!/bin/bash
while [[ "$1" == -* ]]; do
    case "$1" in
        -u|-g|-p) shift 2 ;;
        *) shift ;;
    esac
done
exec "$@"
SUDO_SHIM
    chmod +x /usr/local/bin/sudo
fi

# ---------- placeholder nginx 처리 (RunPod) ----------
# RunPod 가 Expose HTTP Ports 등록된 포트마다 placeholder nginx 띄움.
# 우리 서버가 그 포트 못 쓰니 미리 정리.
if pgrep -x nginx >/dev/null 2>&1; then
    echo "==> placeholder nginx 감지 — 정리"
    nginx -s stop 2>/dev/null || pkill -9 nginx 2>/dev/null || true
    sleep 1
fi

# ---------- 시스템 패키지 ----------
# RunPod 의 PyTorch 이미지엔 대부분 이미 깔려있음 — 빠진 것만 보완.
# PPA (deadsnakes 등) 가 가끔 hang 시키므로 timeout 짧게 + 실패 무시.
echo "==> apt 패키지 (필요시, hang 방지 timeout=15s)"
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    # 깨진 PPA 일시 비활성화 (이번 setup 동안만)
    if ls /etc/apt/sources.list.d/deadsnakes-*.list >/dev/null 2>&1; then
        echo "    deadsnakes PPA 일시 비활성화 (PPA hang 방지)"
        mkdir -p /tmp/plab_disabled_ppa
        mv /etc/apt/sources.list.d/deadsnakes-*.list /tmp/plab_disabled_ppa/ 2>/dev/null || true
    fi
    sudo apt-get -o Acquire::http::Timeout=15 -o Acquire::Retries=1 update -y -qq 2>/dev/null || \
        echo "    (apt update 실패 — 무시하고 계속)"
    sudo apt-get install -y --no-install-recommends \
        ffmpeg libsm6 libxext6 libgl1 \
        curl ca-certificates \
        psmisc lsof net-tools unzip git \
        python3-venv python3-pip 2>/dev/null || \
        echo "    (일부 apt 패키지 스킵 — RunPod 이미지에 이미 깔려있을 가능성, 무시)"
fi

# ---------- Node.js 20 ----------
if ! command -v node >/dev/null 2>&1; then
    echo "==> Node.js 20 설치"
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
else
    echo "==> Node.js 이미 설치됨: $(node -v)"
fi

# ---------- Python venv + 의존성 ----------
echo "==> 백엔드 venv"
cd "$BACKEND_DIR"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel

# 1) GPU 자동 감지
GPU_NAME=""
GPU_CC=""
if [[ "$CPU_ONLY" == "0" ]] && command -v nvidia-smi >/dev/null 2>&1; then
    GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || true)"
    GPU_CC="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' .' || true)"
    echo "    GPU: $GPU_NAME (compute capability sm_$GPU_CC)"
fi

# 2) torch 먼저 설치 — requirements.txt 의 ultralytics 가 자동으로 cu13 1.5GB+ 끌어오는 걸 차단.
#    또한 Blackwell 의 경우 cu13 vs cu128 NVIDIA 라이브러리 충돌도 회피.
if [[ "$CPU_ONLY" == "0" ]]; then
    if [[ "$GPU_CC" == "120" || "$GPU_CC" == "100" ]]; then
        echo "==> Blackwell GPU — cu128 nightly torch + cu12 deps 선설치 (충돌 방지)"
        # --no-deps 안 써야 cu128 의 cu12 NVIDIA 라이브러리들이 같이 깔림
        pip install --pre torch torchvision \
            --index-url "https://download.pytorch.org/whl/nightly/cu128" \
            || pip install torch torchvision \
                --index-url "https://download.pytorch.org/whl/cu126"
    else
        echo "==> $CUDA_TAG torch + 의존성 선설치"
        pip install torch torchvision \
            --index-url "https://download.pytorch.org/whl/$CUDA_TAG"
    fi
fi

# 3) requirements.txt 설치 — torch 이미 있으니 ultralytics 가 cu13 NVIDIA 라이브러리 안 끌어옴
echo "==> requirements.txt 설치"
pip install -r requirements.txt

# 3-1) Blackwell 의 경우: ultralytics 가 그래도 cu13 NVIDIA 라이브러리 일부 끌어왔을 수 있음 → 제거.
#      cu128 torch 는 cu12 라이브러리 expect 하므로 cu13 잔재가 있으면 libcupti.so.12 못 찾음.
if [[ "$GPU_CC" == "120" || "$GPU_CC" == "100" ]]; then
    echo "==> Blackwell — cu13 잔재 제거 (cu128 torch 와 호환되는 cu12 라이브러리만 유지)"
    pip uninstall -y \
        nvidia-cublas nvidia-cuda-cupti nvidia-cuda-nvrtc nvidia-cuda-runtime \
        nvidia-cufft nvidia-cufile nvidia-curand \
        nvidia-cusolver nvidia-cusparse \
        nvidia-nvjitlink nvidia-nvtx \
        cuda-toolkit cuda-bindings cuda-pathfinder \
        2>/dev/null || true
    # cu128 torch 가 import 시 deps 자동 import 하면서 cu12 .so 들 정상 동작.
fi

# 4) cudnn 좀비 방지 — sm_89 이하 (4090/H100/A100 등) 만 cu12 NVIDIA 라이브러리 force-reinstall
if [[ "$CPU_ONLY" == "0" ]] && [[ "$GPU_CC" != "120" && "$GPU_CC" != "100" ]]; then
    echo "==> NVIDIA cu12 라이브러리 force-reinstall (cudnn 좀비 방지)"
    pip install --force-reinstall --no-deps \
        nvidia-cublas-cu12==12.1.3.1 \
        nvidia-cuda-cupti-cu12==12.1.105 \
        nvidia-cuda-nvrtc-cu12==12.1.105 \
        nvidia-cuda-runtime-cu12==12.1.105 \
        nvidia-cudnn-cu12==9.1.0.70 \
        nvidia-cufft-cu12==11.0.2.54 \
        nvidia-curand-cu12==10.3.2.106 \
        nvidia-cusolver-cu12==11.4.5.107 \
        nvidia-cusparse-cu12==12.1.0.106 \
        nvidia-nccl-cu12==2.21.5 \
        nvidia-nvtx-cu12==12.1.105 \
        2>/dev/null || echo "    (일부 NVIDIA 라이브러리 스킵 — torch deps 가 자동 처리)"
fi

echo "==> torch 동작 확인 (실제 GPU 연산 테스트)"
python - <<'PY'
import torch, sys
print(f"  torch        : {torch.__version__}")
print(f"  cuda available: {torch.cuda.is_available()}")
if not torch.cuda.is_available():
    print("  ⚠️  CUDA 안 잡힘. 드라이버 버전 vs torch 빌드 확인 필요.")
    sys.exit(0)

print(f"  device 0     : {torch.cuda.get_device_name(0)}")
print(f"  vram (MB)    : {torch.cuda.get_device_properties(0).total_memory // 1024 // 1024}")
cc = torch.cuda.get_device_capability(0)
print(f"  compute cap. : sm_{cc[0]}{cc[1]}")

# 실제 행렬 곱으로 호환성 검증 — Blackwell 에 cu121 인 경우 여기서 RuntimeError 남
try:
    x = torch.randn(64, 64, device='cuda')
    y = x @ x.T
    torch.cuda.synchronize()
    print("  ✅ GPU 연산 OK")
except Exception as e:
    print(f"  ❌ GPU 연산 실패: {e}")
    print("     → Blackwell GPU 에 cu121 torch 깔린 상태일 수 있음.")
    print("     → 해결: 다음 명령으로 nightly cu128 재설치")
    print("       pip install --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cu128 --force-reinstall --no-deps")
PY

# ---------- 프론트엔드 ----------
echo "==> 프론트엔드 npm install"
cd "$FRONTEND_DIR"
npm install --no-audit --no-fund

echo ""
echo "================================================================"
echo " ✅ 셋업 완료. 다음 한 줄로 시작:"
echo "    PUBLIC=1 bash scripts/start.sh"
echo ""
echo " RunPod / 외부 접속:"
echo "   - Pod 의 HTTP Service 에 포트 3000, 8765 노출 추가"
echo "   - API_URL=https://<8765-URL> PUBLIC=1 bash scripts/start.sh"
echo "================================================================"
