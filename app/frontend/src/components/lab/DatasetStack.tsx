import clsx from "clsx";
import { Chip } from "./Chip";
import { SectionLabel } from "./SectionLabel";
import type { InputStackItem, StackStatus } from "@/lib/types";

const dotColor: Record<StackStatus, string> = {
  ready:   "bg-good",
  matched: "bg-ink",
  partial: "bg-amber",
  empty:   "bg-text-faint",
};

const labelText: Record<StackStatus, string> = {
  ready: "READY", matched: "MATCHED", partial: "PARTIAL", empty: "EMPTY",
};

const labelTone: Record<StackStatus, string> = {
  ready: "text-good", matched: "text-ink",
  partial: "text-amber", empty: "text-text-faint",
};

export function DatasetStack({
  items, pairCount, totalCount,
}: {
  items: InputStackItem[];
  pairCount: number;
  totalCount: number;
}) {
  return (
    <div className="bg-bg1 border border-line rounded">
      <div className="px-3 pt-3 pb-2 border-b border-line">
        <SectionLabel index="01">Input Stack</SectionLabel>
        <div className="flex items-baseline gap-3 mt-1">
          <span className="text-[15px] font-bold">Dataset</span>
          <Chip tone="ink">PAIR {pairCount}/{totalCount}</Chip>
        </div>
        <p className="text-[11px] text-text-mute mt-2 leading-snug">
          YOLOv11-seg 모드는 가중치(.pt) + SEM 이미지가 필수입니다. GT
          라벨은 평가 시 필요합니다.
        </p>
      </div>

      <div>
        {items.map((it, i) => (
          <div key={it.id}
               className={clsx(
                 "px-3 py-2.5 cursor-pointer transition-colors",
                 i === 0 ? "bg-bg2 border-l-2 border-ink" : "hover:bg-bg2",
                 i !== items.length - 1 && "border-b border-line",
               )}>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-[10px] text-text-faint w-4">
                {String(it.index).padStart(2, "0")}
              </span>
              <span className="text-[12px] font-semibold flex-1">
                {it.label}
              </span>
              <span className={clsx("w-1.5 h-1.5 rounded-full",
                                    dotColor[it.status])} />
            </div>
            <div className="flex items-center gap-1.5 pl-6">
              <span className="font-mono text-[10px] text-text-mute truncate">
                {it.meta}
              </span>
              <span className="flex-1" />
              <span className={clsx(
                "font-mono text-[9px] tracking-wide2 font-semibold",
                labelTone[it.status],
              )}>
                {labelText[it.status]}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
