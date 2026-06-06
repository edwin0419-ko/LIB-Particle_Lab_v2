"""Particle Lab v2 — 추론 전용 FastAPI 엔트리.

연구실 실용판: U-Net + YOLO 학습된 가중치를 받아 Hybrid 추론만 수행.
학습/증강/통계 모드는 제외.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.formparsers import MultiPartParser

# starlette multipart 한도 우회 (1000 파일 → 100,000)
MultiPartParser.max_files = 100_000
MultiPartParser.max_fields = 100_000

_orig_mpp_init = MultiPartParser.__init__
def _patched_mpp_init(self, *args, **kwargs):
    kwargs['max_files'] = 100_000
    kwargs['max_fields'] = 100_000
    kwargs.setdefault('max_part_size', 50 * 1024 * 1024 * 1024)
    try:
        return _orig_mpp_init(self, *args, **kwargs)
    except TypeError:
        kwargs.pop('max_part_size', None)
        return _orig_mpp_init(self, *args, **kwargs)
MultiPartParser.__init__ = _patched_mpp_init

# JSON NaN/Inf sanitize
import math as _math
from starlette.responses import JSONResponse as _JR
_orig_render = _JR.render
def _sanitize(o):
    if isinstance(o, float):
        if _math.isnan(o) or _math.isinf(o):
            return None
        return o
    if isinstance(o, dict):
        return {k: _sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_sanitize(v) for v in o]
    return o
def _patched_render(self, content):
    return _orig_render(self, _sanitize(content))
_JR.render = _patched_render

from .api.hybrid import router as hybrid_router

# basic_pt 디렉토리 — 프로젝트 루트의 사전 학습 가중치 모음.
# 프런트가 첫 로드 시 fetch 해서 자동으로 슬롯에 채움.
from pathlib import Path as _Path
from fastapi import HTTPException as _HTTPException
from fastapi.responses import FileResponse as _FileResponse, JSONResponse as _JSONResponse
from fastapi.staticfiles import StaticFiles as _StaticFiles
_PROJECT_ROOT = _Path(__file__).resolve().parents[3]
_BASIC_PT_DIR = _PROJECT_ROOT / "basic_pt"
_BASIC_PT_MAP = {
    # which → (file_name_on_disk, suggested_download_name)
    "unet": ("U-net++", "U-net++.pt"),
    "yolo": ("yolo_11", "yolo_11.pt"),
}

app = FastAPI(
    title="Particle Lab v2 — Inference",
    version="2.0.0",
    description="SEM 입자 분할 추론 (U-Net × YOLO Hybrid)",
)


@app.get("/api/basic_pt")
async def basic_pt_list():
    """프런트가 첫 로드 시 어떤 기본 모델이 사용 가능한지 조회."""
    out: dict = {}
    for which, (fname, _) in _BASIC_PT_MAP.items():
        p = _BASIC_PT_DIR / fname
        out[which] = {
            "available": p.exists(),
            "size_bytes": int(p.stat().st_size) if p.exists() else 0,
            "filename": _BASIC_PT_MAP[which][1],
        }
    return _JSONResponse(out)


@app.get("/api/basic_pt/{which}")
async def basic_pt_get(which: str):
    """기본 가중치 파일 다운로드 — 프런트가 첫 로드 시 슬롯에 자동 장착."""
    info = _BASIC_PT_MAP.get(which)
    if info is None:
        raise _HTTPException(404, f"unknown basic_pt key: {which}")
    fname, dl_name = info
    fp = _BASIC_PT_DIR / fname
    if not fp.exists():
        raise _HTTPException(404, f"basic_pt/{fname} not found on server")
    return _FileResponse(
        str(fp),
        media_type="application/octet-stream",
        filename=dl_name,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hybrid_router)


@app.get("/api/health")
async def health():
    return {"ok": True, "name": "particle-lab-v2", "version": app.version}


# 데스크탑 런처용 정적 프런트 — app/frontend/out (Next.js export 산출물)을 루트에 마운트.
# 존재할 때만. 없으면 기존 /api 전용 모드 (개발 환경).
_FRONT_OUT = _PROJECT_ROOT / "app" / "frontend" / "out"
if _FRONT_OUT.is_dir():
    app.mount("/", _StaticFiles(directory=str(_FRONT_OUT), html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        return {
            "name": "Particle Lab v2 — Inference",
            "endpoints": [
                "/api/health",
                "GET /api/basic_pt",
                "GET /api/basic_pt/{which}",
                "POST /api/run/hybrid",
                "/docs",
            ],
        }
