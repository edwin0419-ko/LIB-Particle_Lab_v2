"""디자인 검증용 mock 세션 상태. Phase 1 에서 GET /api/sessions/{id}
가 곧바로 그럴듯한 데이터를 돌려주도록 한다. Phase 2 부터 실제 추론 결과로
대체된다."""
from __future__ import annotations

from ..schemas import (
    CanvasMeta, ConsoleLine, FilmstripItem, InputStackItem, MetricTile,
    Particle, PerImageRow, PipelineStage, SessionState,
)


def make_mock_state(session_id: str, mode: str = "yolo") -> SessionState:
    return SessionState(
        session_id=session_id,
        mode=mode,  # type: ignore[arg-type]
        stack=[
            InputStackItem(id="weights", index=1, label="Weights",
                           meta="best.pt · 1 file · 142 MB", status="ready"),
            InputStackItem(id="images", index=2, label="SEM Images",
                           meta=".tif · 2048×2048 · 23 files · 412 MB",
                           status="matched"),
            InputStackItem(id="gt", index=3, label="GT Labels",
                           meta=".txt · YOLO poly · 23 files · 86 KB",
                           status="matched"),
            InputStackItem(id="binary", index=4, label="Binary Mask",
                           meta=".png · 0 files", status="empty"),
        ],
        console=[
            ConsoleLine(ts="14:32:01", level="INFO",
                        msg="loading weights best.pt"),
            ConsoleLine(ts="14:32:02", level="INFO",
                        msg="model: yolov11s-seg · 11.2M params"),
            ConsoleLine(ts="14:32:02", level="INFO",
                        msg="staging 23 images"),
            ConsoleLine(ts="14:32:03", level="OK",
                        msg="pair-match: 23/23"),
            ConsoleLine(ts="14:32:04", level="RUN",
                        msg="inference imgsz=1024 conf=0.25"),
            ConsoleLine(ts="14:32:42", level="OK",
                        msg="23/23 done · 38.1s · 1.66s/img"),
            ConsoleLine(ts="14:32:42", level="EVAL",
                        msg="mAP@0.5=0.847 · IoU=0.731"),
        ],
        metrics=[
            MetricTile(id="map50", label="mAP@0.5", value="0.847",
                       delta="0.024", deltaUp=True,
                       spark=[14, 12, 13, 9, 10, 6, 5, 4, 3]),
            MetricTile(id="map5095", label="mAP@0.5:0.95", value="0.612",
                       delta="0.011", deltaUp=True,
                       spark=[12, 11, 12, 9, 10, 8, 7, 6, 5]),
            MetricTile(id="miou", label="Mask IoU", value="0.731",
                       delta="0.008", deltaUp=True,
                       spark=[13, 12, 11, 10, 9, 8, 7, 7, 6]),
            MetricTile(id="f1", label="F1 Score", value="0.882",
                       delta="0.003", deltaUp=True,
                       spark=[11, 10, 9, 9, 8, 7, 6, 6, 5]),
        ],
        per_image=[
            PerImageRow(stem="S03_500x_007", pred=6, gt=6, iou=0.842),
            PerImageRow(stem="S02_500x_011", pred=8, gt=8, iou=0.811),
            PerImageRow(stem="S04_500x_003", pred=5, gt=5, iou=0.798),
            PerImageRow(stem="S01_500x_002", pred=12, gt=11, iou=0.764),
            PerImageRow(stem="S05_500x_009", pred=4, gt=6, iou=0.612),
            PerImageRow(stem="S03_500x_014", pred=9, gt=12, iou=0.581),
        ],
        filmstrip=[
            FilmstripItem(index=i + 1, label=f"{i + 1:02d}",
                          ok=(i not in (4, 13)))
            for i in range(23)
        ],
        pipeline=[
            PipelineStage(id="ingest", label="INGEST",
                          ts="14:32:01", status="done"),
            PipelineStage(id="pair", label="PAIR-MATCH",
                          ts="14:32:03", status="done"),
            PipelineStage(id="infer", label="INFERENCE",
                          ts="14:32:42", status="done"),
            PipelineStage(id="evaluate", label="EVALUATE",
                          ts="now", status="active"),
            PipelineStage(id="export", label="EXPORT",
                          ts="—", status="pending"),
        ],
        canvas_meta=CanvasMeta(
            file="S03_500x_007.tif",
            size="2048 × 2048 · 16-bit",
            mag="500× · WD 8.2 mm",
            detect="23 particles",
        ),
        particles=[
            Particle(id="P-001", cx=28, cy=32, rx=9,  ry=8,  rot=12,  conf=0.94),
            Particle(id="P-002", cx=58, cy=24, rx=7,  ry=9,  rot=-20, conf=0.91),
            Particle(id="P-003", cx=76, cy=48, rx=10, ry=8,  rot=8,   conf=0.88),
            Particle(id="P-004", cx=42, cy=58, rx=8,  ry=11, rot=30,  conf=0.96),
            Particle(id="P-005", cx=18, cy=72, rx=6,  ry=7,  rot=-10, conf=0.79),
            Particle(id="P-006", cx=64, cy=78, rx=11, ry=9,  rot=18,  conf=0.92),
            Particle(id="P-007", cx=86, cy=80, rx=5,  ry=6,  rot=0,   conf=0.83),
            Particle(id="P-008", cx=36, cy=18, rx=5,  ry=4,  rot=0,   conf=0.71),
        ],
    )
