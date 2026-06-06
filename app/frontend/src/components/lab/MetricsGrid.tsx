import clsx from "clsx";
import { Chip } from "./Chip";
import { SectionLabel } from "./SectionLabel";
import type { MetricTile } from "@/lib/types";

function Sparkline({ data }: { data: number[] }) {
  // 0-20 (lower = better in our mock)
  if (data.length === 0) return null;
  const stepX = 80 / (data.length - 1);
  const path = data
    .map((y, i) => `${i === 0 ? "M" : "L"} ${(i * stepX).toFixed(1)} ${y}`)
    .join(" ");
  return (
    <svg width="100%" height={20} viewBox="0 0 80 20" className="mt-1.5 block">
      <path d={path} fill="none" stroke="#1f5fd6" strokeWidth="1.2" />
      <path d={`${path} L 80 20 L 0 20 Z`} fill="#1f5fd6" opacity="0.08" />
    </svg>
  );
}

function Tile({ t }: { t: MetricTile }) {
  return (
    <div className="bg-bg1 border border-line rounded p-3.5 relative overflow-hidden">
      <div className="font-mono text-[9px] text-text-faint
                      tracking-wide2 uppercase font-medium">
        {t.label}
      </div>
      <div className="font-mono text-[26px] font-semibold text-text leading-none tracking-tight mt-1">
        {t.value}
      </div>
      {t.delta && (
        <div className={clsx(
          "font-mono text-[10px] mt-1",
          t.deltaUp ? "text-good" : "text-bad",
        )}>
          {t.deltaUp ? "↑" : "↓"} {t.delta}
        </div>
      )}
      {t.spark && <Sparkline data={t.spark} />}
    </div>
  );
}

export function MetricsGrid({
  tiles, fresh = true, totalImages, gtKind,
}: {
  tiles: MetricTile[];
  fresh?: boolean;
  totalImages: number;
  gtKind: string;
}) {
  return (
    <div>
      <SectionLabel index="04">Metrics</SectionLabel>
      <div className="flex items-baseline gap-3 mb-2">
        <span className="text-[15px] font-bold">Evaluation</span>
        {fresh
          ? <Chip tone="good">FRESH</Chip>
          : <Chip tone="amber">STALE</Chip>}
      </div>
      <div className="text-[11px] text-text-mute mb-3">
        {totalImages} imgs · GT: {gtKind}
      </div>
      <div className="grid grid-cols-2 gap-2">
        {tiles.map((t) => <Tile key={t.id} t={t} />)}
      </div>
    </div>
  );
}
