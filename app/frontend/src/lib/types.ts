// 도메인 타입 정의 — backend / frontend 모두 같은 모양 사용.

export type ModeId = "yolo" | "unet" | "legacy";

export type StackStatus = "ready" | "matched" | "partial" | "empty";

export interface InputStackItem {
  id: string;
  index: number;
  label: string;
  meta: string;          // "1 file · 142 MB" 같은 한 줄 메타
  status: StackStatus;
}

export interface ParamKnob {
  id: string;
  label: string;
  value: number;
  range: [number, number];
  hint?: string;
  fmt?: (v: number) => string;
}

export interface ConsoleLine {
  ts: string;
  level: "INFO" | "OK" | "RUN" | "EVAL" | "WARN" | "ERROR";
  msg: string;
}

export interface MetricTile {
  id: string;
  label: string;
  value: string;
  delta?: string;
  deltaUp?: boolean;
  spark?: number[];
}

export interface PerImageRow {
  stem: string;
  pred: number;
  gt: number;
  iou: number;
}

export interface FilmstripItem {
  index: number;
  label: string;
  ok: boolean;
}

export interface PipelineStage {
  id: string;
  label: string;
  ts?: string;
  status: "done" | "active" | "pending";
}

export interface Particle {
  id: string;
  cx: number; // 0~100 (% of canvas)
  cy: number;
  rx: number;
  ry: number;
  rot: number; // degrees
  conf: number;
}

export interface CanvasMeta {
  file: string;
  size: string;
  mag: string;
  detect: string;
}
