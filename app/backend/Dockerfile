# Particle Lab — 백엔드 Dockerfile
# nvidia-docker / GPU 지원 환경에서 실행 시 자동으로 CUDA 가속 사용.

FROM python:3.12-slim AS base

# OS 패키지 (opencv 의존성)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsm6 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 캐시 레이어
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel \
    && pip install --no-cache-dir -r requirements.txt

# 호스트에 GPU 있으면 CUDA torch 로 교체 (선택 — build arg 로 활성화)
ARG CUDA_TAG=""
RUN if [ -n "$CUDA_TAG" ]; then \
        pip install --no-cache-dir --upgrade torch torchvision \
            --index-url "https://download.pytorch.org/whl/$CUDA_TAG"; \
    fi

# 프로젝트 루트의 ML 모듈 (legacy_segment.py, evaluate.py, unet_*.py 등) 도 필요.
# 이 파일들은 빌드 컨텍스트의 부모 디렉토리에 있으므로 compose 에서 볼륨 마운트로 처리.

# 백엔드 코드
COPY app /app/app

EXPOSE 8765
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
