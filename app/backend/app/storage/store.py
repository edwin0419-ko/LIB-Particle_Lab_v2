"""파일 기반 세션 스토어. Phase 1 에서는 mock 상태 + 업로드 보존만.

각 세션:
    data/sessions/{session_id}/
        state.json       — SessionState 스냅샷
        files/           — 업로드된 weights / images / labels / masks
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Optional

from ..schemas import SessionState

_BASE = Path(os.environ.get("PARTICLE_LAB_DATA",
                             Path(__file__).resolve().parents[3] / "data")).resolve()
SESSIONS_DIR = _BASE / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def session_dir(session_id: str) -> Path:
    p = SESSIONS_DIR / session_id
    (p / "files").mkdir(parents=True, exist_ok=True)
    return p


def save_state(state: SessionState) -> Path:
    p = session_dir(state.session_id) / "state.json"
    p.write_text(state.model_dump_json(indent=2))
    return p


def load_state(session_id: str) -> Optional[SessionState]:
    p = session_dir(session_id) / "state.json"
    if not p.exists():
        return None
    return SessionState.model_validate_json(p.read_text())


def list_sessions() -> list[str]:
    if not SESSIONS_DIR.exists():
        return []
    return sorted(d.name for d in SESSIONS_DIR.iterdir() if d.is_dir())


def save_upload(session_id: str, role: str, filename: str, data: bytes) -> str:
    """role = weights | images | labels | masks. 같은 role 의 파일은 누적."""
    out = session_dir(session_id) / "files" / role
    out.mkdir(parents=True, exist_ok=True)
    safe = Path(filename).name
    target = out / safe
    target.write_bytes(data)
    return str(target)
