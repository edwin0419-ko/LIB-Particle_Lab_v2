"use client";

import { Chip } from "./Chip";
import { SectionLabel } from "./SectionLabel";
import type { ParamKnob } from "@/lib/types";

function Knob({ k }: { k: ParamKnob }) {
  const [min, max] = k.range;
  const pct = ((k.value - min) / (max - min)) * 100;
  const display = k.fmt ? k.fmt(k.value) : String(k.value);
  return (
    <div className="mb-3">
      <div className="flex justify-between items-baseline mb-1.5">
        <span className="font-mono text-[10px] text-text-mute uppercase tracking-wide2">
          {k.label}
        </span>
        <span className="font-mono text-[13px] font-bold text-ink">
          {display}
        </span>
      </div>
      <div className="relative h-[3px] bg-bg3">
        <div className="absolute left-0 top-0 h-full bg-ink"
             style={{ width: `${pct}%` }} />
      </div>
      {k.hint && (
        <div className="text-3xs text-text-faint mt-1">{k.hint}</div>
      )}
    </div>
  );
}

export function TuningPanel({ knobs }: { knobs: ParamKnob[] }) {
  return (
    <div className="bg-bg1 border border-line rounded p-3">
      <SectionLabel index="02">Inference Params</SectionLabel>
      <div className="flex items-baseline gap-3 mt-1 mb-3">
        <span className="text-[15px] font-bold">Tuning</span>
        <Chip tone="good">LIVE</Chip>
      </div>
      {knobs.map((k) => <Knob key={k.id} k={k} />)}
    </div>
  );
}
