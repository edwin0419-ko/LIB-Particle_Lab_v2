"""Pydantic 스키마 — frontend types.ts 와 1:1 대응.
타입 변경 시 두 파일을 같이 갱신할 것."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

ModeId = Literal["yolo", "unet", "legacy"]
StackStatus = Literal["ready", "matched", "partial", "empty"]
ConsoleLevel = Literal["INFO", "OK", "RUN", "EVAL", "WARN", "ERROR"]


class InputStackItem(BaseModel):
    id: str
    index: int
    label: str
    meta: str
    status: StackStatus


class ConsoleLine(BaseModel):
    ts: str
    level: ConsoleLevel
    msg: str


class MetricTile(BaseModel):
    id: str
    label: str
    value: str
    delta: Optional[str] = None
    deltaUp: Optional[bool] = None
    spark: List[float] = Field(default_factory=list)


class PerImageRow(BaseModel):
    stem: str
    pred: int
    gt: int
    iou: float


class FilmstripItem(BaseModel):
    index: int
    label: str
    ok: bool


class PipelineStage(BaseModel):
    id: str
    label: str
    ts: Optional[str] = None
    status: Literal["done", "active", "pending"]


class CanvasMeta(BaseModel):
    file: str
    size: str
    mag: str
    detect: str


class Particle(BaseModel):
    id: str
    cx: float
    cy: float
    rx: float
    ry: float
    rot: float
    conf: float


class SessionState(BaseModel):
    """한 세션(=하나의 추론 작업) 의 전체 상태 스냅샷."""
    session_id: str
    mode: ModeId
    stack: List[InputStackItem]
    console: List[ConsoleLine]
    metrics: List[MetricTile]
    per_image: List[PerImageRow]
    filmstrip: List[FilmstripItem]
    pipeline: List[PipelineStage]
    canvas_meta: CanvasMeta
    particles: List[Particle]


class CreateSessionRequest(BaseModel):
    mode: ModeId = "yolo"


class CreateSessionResponse(BaseModel):
    session_id: str
