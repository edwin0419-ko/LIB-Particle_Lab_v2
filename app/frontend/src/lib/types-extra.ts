// 백엔드 SessionState 와 1:1 매핑. backend/app/schemas.py 와 동일한 모양.

import type {
  CanvasMeta, ConsoleLine, FilmstripItem, InputStackItem, MetricTile,
  ModeId, Particle, PerImageRow, PipelineStage,
} from "./types";

export type { ModeId };

export interface SessionState {
  session_id: string;
  mode: ModeId;
  stack: InputStackItem[];
  console: ConsoleLine[];
  metrics: MetricTile[];
  per_image: PerImageRow[];
  filmstrip: FilmstripItem[];
  pipeline: PipelineStage[];
  canvas_meta: CanvasMeta;
  particles: Particle[];
}
