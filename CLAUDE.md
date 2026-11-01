# Particle Lab v2 — Claude Code 안내

SEM 입자 이미지를 U-Net × YOLO Hybrid 로 분할하고 입자 형상·입도 지표(ECD, D50, 원형도 …)를
엑셀로 내보내는 로컬 웹 앱. 백엔드 FastAPI(포트 8765) + 프런트 Next.js(포트 3001).

## 이 저장소를 받은 사람에게

대부분 **코딩을 모르는 연구실 동료**가 "이 프로그램 실행해줘" 라고 요청한다.

- 목표: 앱을 띄우고 브라우저에서 `http://localhost:3001` 을 열어주는 것.
- 소스 코드는 수정하지 않는다. 실행이 안 되면 원인을 쉬운 말로 설명한다.
- 설명은 한국어로, 전문용어 없이. 명령어 출력은 요약해서 전달한다.
- 프로그램(Python, Node.js 등)을 새로 설치하기 전에는 사용자에게 먼저 묻는다.

## 실행 순서

### 1. 필요한 프로그램 확인

| 필요 | 확인 명령 | 없으면 (사용자 동의 후) |
|---|---|---|
| Python 3.10 ~ 3.13 (3.12 권장) | `python3 --version` (Windows: `python --version`) | Mac: `brew install python@3.12` 또는 python.org 설치 파일 / Windows: `winget install -e --id Python.Python.3.12` |
| Node.js 18 이상 | `node --version` | Mac: `brew install node` 또는 nodejs.org / Windows: `winget install -e --id OpenJS.NodeJS.LTS` |
| curl | `curl --version` | macOS·Windows 10+ 기본 포함 |

- Python 3.14 이상은 PyTorch 미지원일 수 있으니 3.12 를 설치한다.
- Windows 에서 새로 설치한 뒤에는 새 터미널을 열어야 PATH 가 반영된다.
- Windows 의 Microsoft Store 가짜 `python` (설치 안내만 띄우는 것) 에 주의.

### 2. 실행

- **Mac**: 저장소 폴더에서 `./start.command`
- **Windows**: 저장소 폴더에서 `START.bat` (PowerShell: `cmd /c START.bat`)

스크립트가 알아서 하는 일:
1. 처음이면 `venv/` 생성 + Python 패키지(PyTorch 포함) + Node 패키지 설치 + 프런트 빌드 — **5~10분**
2. 기본 모델 가중치가 없으면 GitHub Release v2.0.0 에서 다운로드 (약 90MB)
3. 백엔드·프런트 실행 후 Chrome(없으면 기본 브라우저)으로 앱을 연다

두 스크립트 모두 서버를 띄운 뒤 끝나지 않고 대기한다 (Mac: 서버 종료 대기, Windows: 마지막 `pause`).
따라서 **백그라운드로 실행**하고, 아래 확인 명령으로 준비됐는지 확인한다.
첫 실행은 설치 때문에 오래 걸리니 충분히 기다린다 (진행 상황은 스크립트 출력 / `logs/` 확인).

### 3. 준비 확인

```bash
curl -s http://127.0.0.1:8765/api/health      # {"ok":true,...}
curl -s http://127.0.0.1:8765/api/basic_pt    # unet / yolo 둘 다 "available": true
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3001   # 200
```

세 개 모두 정상이면 사용자에게 브라우저에서 `http://localhost:3001` 을 열라고 안내한다
(자동으로 안 열렸으면 Mac: `open http://localhost:3001`, Windows: `start http://localhost:3001`).

### 4. 사용법 (사용자에게 이렇게 안내)

1. **추론할 이미지**에 SEM 이미지를 끌어다 놓는다 (여러 장 가능). 모델은 자동으로 들어가 있다.
2. 오른쪽 **전처리 · 스케일**:
   - 하단 스케일바 영역: 보통 **자동 감지**
   - **스케일바 길이(px)** 와 **실제 길이(µm)** 입력 → 결과가 µm 단위로 나온다
   - 모서리에 닿은 입자 제거: 켜두는 것을 권장
3. **분석 실행** → 결과 이미지와 형상·입도 지표 카드가 나온다.
4. 오른쪽 **다운로드** → **지표 엑셀** (형상요약·입자별·크기구간·지표정의, 한/영 병기) 또는
   **입자별 지표 엑셀**. 스케일을 안 넣었으면 다운로드할 때 입력 창이 뜬다.

### 5. 종료

- Mac: `./stop.command` (또는 start.command 를 실행한 터미널에서 Ctrl+C)
- Windows: `STOP.bat`

## 문제 해결

| 증상 | 확인 / 조치 |
|---|---|
| 백엔드가 안 뜸 | `logs/backend.log` 마지막 부분 확인. 패키지 문제면 `venv/` 삭제 후 다시 실행 |
| 프런트가 안 뜸 | `logs/frontend.log` 확인. `app/frontend/.next/` 삭제 후 다시 실행하면 재빌드 |
| 화면 상단 "백엔드 끊김" | 백엔드 로그 확인. 포트 8765 를 다른 프로그램이 쓰는지 확인 |
| 모델이 자동으로 안 들어감 | `basic_pt/U-net++`, `basic_pt/yolo_11` 파일이 있는지 확인 (**확장자 없음**). 없으면 아래 주소에서 받아 이 이름으로 저장: `https://github.com/edwin0419-ko/LIB-Particle_Lab_v2/releases/download/v2.0.0/U-net++.pt`, `.../v2.0.0/yolo_11.pt` |
| 첫 실행이 오래 걸림 | 정상. PyTorch 다운로드가 수백 MB |
| Windows 에서 느림 | PyPI 기본 PyTorch 는 CPU 전용이라 정상. 결과는 같다 |

## 업데이트 받기

```bash
git pull
```

그 다음 프런트를 다시 빌드해야 새 화면이 반영된다: `app/frontend/.next/` 폴더를 지우고 실행 스크립트를 다시 실행
(Python 패키지가 바뀐 경우 `venv/` 도 지운다).

## 코드 구조 (수정이 필요할 때만)

- `app/backend/app/api/hybrid.py` — 추론 API `/api/run/hybrid`, 스케일 재환산 엑셀 `/api/run/hybrid/excel`
- `app/backend/app/api/_excel_export.py` — 엑셀 시트 생성
- `hybrid_core.py` — U-Net × YOLO 융합 알고리즘
- `particle_morphology.py` — 형상·입도 지표, 스케일바 자동 감지, 모서리 입자 제거
- `app/frontend/src/app/page.tsx` — 화면 전체 (단일 파일)
