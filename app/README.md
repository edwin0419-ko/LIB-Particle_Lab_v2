# Particle Lab — Desktop App (Phase 1)

Claude Design 기반 Lab Console 디자인을 그대로 구현한 데스크톱급 앱.
Streamlit 버전(`viewer.py` 등) 과 별개로 동작한다.

## 폴더 구조

```
app/
├── backend/   FastAPI · 세션 / 업로드 / mock 메트릭
└── frontend/  Next.js 14 + TypeScript + Tailwind
```

## 실행

### 1) 백엔드 (FastAPI, 포트 8765)

```bash
cd app/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8765
```

확인: http://localhost:8765/docs

### 2) 프론트엔드 (Next.js, 포트 3001)

```bash
cd app/frontend
npm install
npm run dev
```

확인: http://localhost:3001

기존 Streamlit 앱(8501) 과 포트가 겹치지 않으므로 동시에 띄워둘 수 있다.

## 현재(Phase 1) 동작

- 백엔드는 mock 세션 데이터를 즉시 돌려준다 (`GET /api/sessions/{id}` 가 어떤 id 든 그럴듯한 응답).
- 프론트엔드는 컴포넌트 레벨에서는 mock 을 import 하지만, 곧 `api.getSession(id)` 결과로 교체할 수 있도록 같은 모양의 `SessionState` 타입을 사용한다.
- 디자인 100% 매칭: command bar / 좌측 rail / Input Stack / Tuning / Console / Canvas with overlays / Filmstrip / Pipeline / Metrics / PR curve / Per-image / Export 패널.

## Phase 2 — 다음 응답에서 추가

- `/api/yolo/infer` — Streamlit 의 `predict_one` 로직을 그대로 이식
- `/api/unet/train` & `/api/unet/predict` — 기존 unet_trainer 재사용
- `/api/legacy/segment` — 기존 legacy_segment 재사용
- `/api/export/pptx` — PPT 익스포트
- 프론트에서 mock 대신 실제 fetch로 데이터 교체
- 키보드 단축키 (⌘K, R, E, ?)

## 데스크톱 패키징 (Phase 3)

Tauri 또는 Electron 으로 묶어 단일 앱으로 배포 가능. 백엔드는 sidecar 로 spawn,
프론트는 정적 빌드 (`next export` or `output: "export"`).
