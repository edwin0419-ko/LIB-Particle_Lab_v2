import clsx from "clsx";
import { SectionLabel } from "./SectionLabel";
import type { PerImageRow } from "@/lib/types";

function iouColor(v: number) {
  if (v >= 0.8) return "text-good";
  if (v >= 0.7) return "text-text";
  if (v >= 0.6) return "text-amber";
  return "text-bad";
}

export function PerImageTable({ rows }: { rows: PerImageRow[] }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <SectionLabel>Per-image</SectionLabel>
        <span className="font-mono text-[10px] text-text-faint tracking-wide">
          sort: IoU ↓
        </span>
      </div>
      <div className="bg-bg1 border border-line rounded overflow-hidden">
        {rows.map((r, i) => (
          <div key={r.stem}
               className={clsx(
                 "flex items-center gap-2 px-3 py-2 hover:bg-bg2 cursor-pointer",
                 i !== rows.length - 1 && "border-b border-line",
               )}>
            <span className="font-mono text-[12px] text-text flex-1 truncate">
              {r.stem}
            </span>
            <span className="font-mono text-[10px] text-text-faint w-10 text-right">
              {r.pred}/{r.gt}
            </span>
            <span className={clsx(
              "font-mono text-[12px] font-semibold w-12 text-right",
              iouColor(r.iou),
            )}>
              {r.iou.toFixed(3)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
