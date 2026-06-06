// 디자인을 즉시 띄우기 위한 mock 데이터. 백엔드 연결 후에는 fetch 결과로 교체.

import type {
  CanvasMeta, ConsoleLine, FilmstripItem, InputStackItem, MetricTile,
  ParamKnob, Particle, PerImageRow, PipelineStage,
} from "./types";

export const stack: InputStackItem[] = [
  { id: "weights",  index: 1, label: "Weights",     meta: "best.pt · 1 file · 142 MB",   status: "ready" },
  { id: "images",   index: 2, label: "SEM Images",  meta: ".tif · 2048×2048 · 23 files · 412 MB", status: "matched" },
  { id: "gt",       index: 3, label: "GT Labels",   meta: ".txt · YOLO poly · 23 files · 86 KB",  status: "matched" },
  { id: "binary",   index: 4, label: "Binary Mask", meta: ".png · 0 files",               status: "empty"   },
];

export const knobs: ParamKnob[] = [
  { id: "conf", label: "CONFIDENCE",   value: 0.25, range: [0, 1],   hint: "낮출수록 검출↑ · 오탐↑" },
  { id: "iou",  label: "IOU THRESHOLD",value: 0.7,  range: [0, 1],   hint: "NMS 엄격도" },
  { id: "size", label: "IMAGE SIZE",   value: 1024, range: [320, 1280], hint: "입력 해상도. 클수록 정확↑·속도↓" },
  { id: "max",  label: "MAX DETECTIONS", value: 300, range: [10, 1000], hint: "이미지당 최대 검출 개수" },
];

export const consoleLines: ConsoleLine[] = [
  { ts: "14:32:01", level: "INFO", msg: "loading weights best.pt" },
  { ts: "14:32:02", level: "INFO", msg: "model: yolov11s-seg · 11.2M params" },
  { ts: "14:32:02", level: "INFO", msg: "staging 23 images" },
  { ts: "14:32:03", level: "OK",   msg: "pair-match: 23/23" },
  { ts: "14:32:04", level: "RUN",  msg: "inference imgsz=1024 conf=0.25" },
  { ts: "14:32:42", level: "OK",   msg: "23/23 done · 38.1s · 1.66s/img" },
  { ts: "14:32:42", level: "EVAL", msg: "mAP@0.5=0.847 · IoU=0.731" },
];

export const metricTiles: MetricTile[] = [
  { id: "map50",   label: "mAP@0.5",    value: "0.847", delta: "0.024", deltaUp: true,
    spark: [14, 12, 13, 9, 10, 6, 5, 4, 3] },
  { id: "map5095", label: "mAP@0.5:0.95", value: "0.612", delta: "0.011", deltaUp: true,
    spark: [12, 11, 12, 9, 10, 8, 7, 6, 5] },
  { id: "miou",    label: "Mask IoU",   value: "0.731", delta: "0.008", deltaUp: true,
    spark: [13, 12, 11, 10, 9, 8, 7, 7, 6] },
  { id: "f1",      label: "F1 Score",   value: "0.882", delta: "0.003", deltaUp: true,
    spark: [11, 10, 9, 9, 8, 7, 6, 6, 5] },
];

export const perImage: PerImageRow[] = [
  { stem: "S03_500x_007", pred: 6,  gt: 6,  iou: 0.842 },
  { stem: "S02_500x_011", pred: 8,  gt: 8,  iou: 0.811 },
  { stem: "S04_500x_003", pred: 5,  gt: 5,  iou: 0.798 },
  { stem: "S01_500x_002", pred: 12, gt: 11, iou: 0.764 },
  { stem: "S05_500x_009", pred: 4,  gt: 6,  iou: 0.612 },
  { stem: "S03_500x_014", pred: 9,  gt: 12, iou: 0.581 },
];

export const filmstrip: FilmstripItem[] = Array.from({ length: 23 }, (_, i) => ({
  index: i + 1,
  label: String(i + 1).padStart(2, "0"),
  ok: i !== 4 && i !== 13,
}));

export const pipeline: PipelineStage[] = [
  { id: "ingest",   label: "INGEST",     ts: "14:32:01", status: "done" },
  { id: "pair",     label: "PAIR-MATCH", ts: "14:32:03", status: "done" },
  { id: "infer",    label: "INFERENCE",  ts: "14:32:42", status: "done" },
  { id: "evaluate", label: "EVALUATE",   ts: "now",      status: "active" },
  { id: "export",   label: "EXPORT",     ts: "—",        status: "pending" },
];

export const particles: Particle[] = [
  { id: "P-001", cx: 28, cy: 32, rx: 9,  ry: 8,  rot: 12,  conf: 0.94 },
  { id: "P-002", cx: 58, cy: 24, rx: 7,  ry: 9,  rot: -20, conf: 0.91 },
  { id: "P-003", cx: 76, cy: 48, rx: 10, ry: 8,  rot: 8,   conf: 0.88 },
  { id: "P-004", cx: 42, cy: 58, rx: 8,  ry: 11, rot: 30,  conf: 0.96 },
  { id: "P-005", cx: 18, cy: 72, rx: 6,  ry: 7,  rot: -10, conf: 0.79 },
  { id: "P-006", cx: 64, cy: 78, rx: 11, ry: 9,  rot: 18,  conf: 0.92 },
  { id: "P-007", cx: 86, cy: 80, rx: 5,  ry: 6,  rot: 0,   conf: 0.83 },
  { id: "P-008", cx: 36, cy: 18, rx: 5,  ry: 4,  rot: 0,   conf: 0.71 },
];

export const canvasMeta: CanvasMeta = {
  file: "S03_500x_007.tif",
  size: "2048 × 2048 · 16-bit",
  mag: "500× · WD 8.2 mm",
  detect: "23 particles",
};
