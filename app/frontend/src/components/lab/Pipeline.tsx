import clsx from "clsx";
import type { PipelineStage } from "@/lib/types";

export function Pipeline({
  stages,
  onRunAll, onExport,
}: {
  stages: PipelineStage[];
  onRunAll?: () => void;
  onExport?: () => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2 flex-1">
        {stages.map((s, i) => {
          const dotCls =
            s.status === "done" ? "bg-good text-white"
            : s.status === "active" ? "bg-ink text-white"
            : "bg-bg3 text-text-faint border border-line";
          return (
            <div key={s.id} className="flex items-center gap-2">
              <div className={clsx(
                "w-7 h-7 rounded-full grid place-items-center font-mono text-[12px] font-bold",
                dotCls,
              )}>
                {s.status === "done" ? "✓" : s.status === "active" ? "●" : "○"}
              </div>
              <div className="leading-tight">
                <div className="font-mono text-[10px] tracking-wide2 font-semibold text-text">
                  {s.label}
                </div>
                <div className="font-mono text-[9px] text-text-faint">
                  {s.ts ?? "—"}
                </div>
              </div>
              {i < stages.length - 1 && (
                <div className={clsx(
                  "w-10 h-px mx-1",
                  s.status === "done" ? "bg-good" : "bg-line",
                )} />
              )}
            </div>
          );
        })}
      </div>

      <button onClick={onRunAll}
              className="px-4 py-2 rounded font-semibold text-[13px]
                         bg-ink text-white border border-ink
                         hover:bg-[#1853c2] transition-colors
                         shadow-[0_1px_2px_rgba(31,95,214,0.25)]">
        ▶ Run all
      </button>
      <button onClick={onExport}
              className="px-4 py-2 rounded font-semibold text-[13px]
                         bg-bg1 text-text border border-line
                         hover:bg-bg2 transition-colors">
        ↓ Export PPT
      </button>
    </div>
  );
}
