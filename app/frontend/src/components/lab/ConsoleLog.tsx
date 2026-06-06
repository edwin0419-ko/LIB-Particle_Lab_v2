import clsx from "clsx";
import { SectionLabel } from "./SectionLabel";
import type { ConsoleLine } from "@/lib/types";

const levelColor: Record<ConsoleLine["level"], string> = {
  INFO:  "text-[#5dade2]",
  OK:    "text-good",
  RUN:   "text-amber",
  EVAL:  "text-coral",
  WARN:  "text-amber",
  ERROR: "text-bad",
};

export function ConsoleLog({ lines }: { lines: ConsoleLine[] }) {
  return (
    <div>
      <SectionLabel index="03">Console</SectionLabel>
      <div className="bg-[#0d0f12] border border-line rounded p-3
                      font-mono text-[11px] leading-relaxed
                      text-[#cdcdc4] overflow-auto max-h-[200px]">
        {lines.map((l, i) => (
          <div key={i} className="whitespace-pre">
            <span className="text-text-faint">{l.ts}</span>{" "}
            <span className={clsx("font-semibold", levelColor[l.level])}>
              {l.level}
            </span>{" "}
            <span>{l.msg}</span>
          </div>
        ))}
        <div className="text-ink animate-pulse">▌</div>
      </div>
    </div>
  );
}
