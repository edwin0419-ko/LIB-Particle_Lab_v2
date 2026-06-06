import { SectionLabel } from "./SectionLabel";

const items: { label: string; primary?: boolean }[] = [
  { label: "PPTX", primary: true },
  { label: "CSV" },
  { label: "JSON" },
  { label: "Masks ZIP" },
];

export function ExportPanel() {
  return (
    <div>
      <SectionLabel index="05">Export</SectionLabel>
      <div className="grid grid-cols-2 gap-2 mt-2">
        {items.map((it) => (
          <button key={it.label}
                  className={
                    it.primary
                      ? "px-3 py-2 rounded font-semibold text-[13px] bg-ink text-white border border-ink hover:bg-[#1853c2] shadow-[0_1px_2px_rgba(31,95,214,0.25)] transition-colors"
                      : "px-3 py-2 rounded font-semibold text-[13px] bg-bg1 text-text border border-line hover:bg-bg2 transition-colors"
                  }>
            ↓ {it.label}
          </button>
        ))}
      </div>
      <p className="text-[11px] text-text-mute mt-3 leading-snug">
        논문용 ppt: 입력/예측/GT 4컷 + 지표 표가 슬라이드별로 자동 생성됩니다.
      </p>
    </div>
  );
}
