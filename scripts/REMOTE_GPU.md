# 원격 GPU 빌려서 Particle Lab 돌리기

## 1. 어디서 빌릴까

| 서비스 | 시간당 (RTX 3090) | UX | 추천도 |
|--------|------|-----|--------|
| [vast.ai](https://vast.ai) | $0.20~0.50 | SSH 직접 | 가성비 1위 |
| [RunPod](https://runpod.io) | $0.34~0.70 | 웹 터미널 + Jupyter | 사용성 1위 |
| [Lambda Labs](https://lambdalabs.com) | $0.50~1.10 | 안정적 | 기업용 |
| [Paperspace](https://paperspace.com) | $0.45~0.78 | 무료티어 있음 | 입문용 |
| [Google Colab Pro](https://colab.google) | $10/월 | 노트북 | 시간제한 12h |
| [Kaggle Notebooks](https://kaggle.com) | **무료** (T4 16GB) | 노트북 | 주 30시간 |

## 2. 가장 단순한 워크플로우 (vast.ai / RunPod 기준)

### 2-1. 인스턴스 생성
- GPU: RTX 3090 (24GB) 또는 RTX 4090 (24GB) 권장
- 디스크: 50GB+
- OS: Ubuntu 22.04 (PyTorch CUDA 12.x 사전설치 이미지가 가장 편함)

### 2-2. 프로젝트 업로드
```bash
# 옵션 A: git
git clone <YOUR_REPO_URL> Particle_lab && cd Particle_lab

# 옵션 B: scp (로컬에서)
scp -r Particle_lab user@<INSTANCE_IP>:~

# 옵션 C: zip 업로드 (vast.ai/RunPod 웹 인터페이스)
```

### 2-3. 자동 셋업 (한 줄)
```bash
cd Particle_lab
bash scripts/setup.sh
# CUDA 11.8 인스턴스라면:  CUDA_TAG=cu118 bash scripts/setup.sh
```

이 스크립트가 알아서:
- apt 패키지 (opencv 의존성)
- Node.js 20 설치
- Python venv + requirements.txt
- CUDA torch 재설치
- npm install
- torch + GPU 동작 확인 출력

### 2-4. 실행
```bash
PUBLIC=1 bash scripts/start.sh
```
→ 백엔드 0.0.0.0:8765, 프론트 0.0.0.0:3001 둘 다 외부 노출.

### 2-5. 로컬에서 접속

**옵션 A: SSH 포트포워딩 (가장 안전)**
```bash
# 로컬 터미널에서
ssh -L 8765:localhost:8765 -L 3001:localhost:3001 user@<INSTANCE_IP>
```
→ 로컬 브라우저에서 http://localhost:3001 열기.

**옵션 B: 직접 IP 접속 (vast.ai/RunPod 가 포트 매핑 제공)**
```
http://<INSTANCE_IP>:3001
```
이 경우 프론트를 시작할 때 백엔드 IP 도 같이 넘겨줘야 함:
```bash
API_URL=http://<INSTANCE_IP>:8765 PUBLIC=1 bash scripts/start.sh
```

## 3. Docker 로 실행 (대안)

GPU 없는 인스턴스 / 더 깔끔한 격리 원할 때:
```bash
docker compose up --build
```

GPU 활성화: `docker-compose.yml` 의 `deploy:` 섹션 주석 해제 (nvidia-container-toolkit 설치 필요).

## 4. RunPod 템플릿 빠른 시작

RunPod 의 **PyTorch 2.1 (CUDA 12.1)** 템플릿이 가장 적합:
1. Pod 생성 → GPU 선택 → 위 템플릿 선택
2. "Connect" → SSH 또는 Web Terminal
3. `bash scripts/setup.sh && PUBLIC=1 bash scripts/start.sh`
4. RunPod 의 "HTTP Service" 에 3001 포트 추가 → 발급된 URL 로 접속

## 5. Colab 에서 학습만 빠르게 (UI 없이)

Colab 에서 백엔드 학습 함수만 직접 호출:
```python
!pip install ultralytics opencv-python scikit-image scipy
!git clone <YOUR_REPO> /content/plab
%cd /content/plab

# YOLO 학습
from ultralytics import YOLO
model = YOLO("yolo11n-seg.pt")
model.train(data="dataset.yaml", epochs=100, imgsz=640, batch=16, device=0)

# 또는 U-Net 학습 (이 프로젝트의 unet_trainer 사용)
import sys; sys.path.insert(0, "/content/plab")
from unet_trainer import TrainConfig, train_unet
result = train_unet(pairs, TrainConfig(method="U-Net++", epochs=50))

# 결과 모델 다운로드 → 로컬에서 추론에 사용
from google.colab import files
files.download("/content/plab/runs/segment/train/weights/best.pt")
```

## 6. 비용 가이드

| 시나리오 | 사용 | 비용 |
|---------|------|------|
| 작은 데이터 (50장) U-Net 1회 학습 | RTX 3090 30분 | ~$0.20 |
| YOLO 50 epoch 학습 (100장) | RTX 3090 1시간 | ~$0.40 |
| 큰 데이터 (1000장) 풀 학습 | RTX 4090 5시간 | ~$2.00 |
| 한 달 내내 실험 | RunPod 페르시스턴트 | ~$50~150 |

**팁**: 학습 끝나면 .pt 다운로드 받고 인스턴스 종료 — 데이터 안 깔리도록.

## 7. 보안 팁

- vast.ai/RunPod 는 다른 사람이 같은 호스트 쓰는 케이스 있음. 민감한 데이터는 SSH 포트포워딩 사용 권장 (외부 노출 X)
- 작업 끝나면 인스턴스 즉시 종료 (시간당 과금)
- 학습 결과는 로컬로 다운로드해서 보관
