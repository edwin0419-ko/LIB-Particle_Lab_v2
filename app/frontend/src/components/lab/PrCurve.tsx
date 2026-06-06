import { SectionLabel } from "./SectionLabel";

export function PrCurve({ auc = 0.901 }: { auc?: number }) {
  // 부드러운 PR curve mock — Bezier
  const path = "M 5 18 C 30 18 60 22 95 70 L 95 95 L 5 95 Z";
  const stroke = "M 5 18 C 30 18 60 22 95 70";
  return (
    <div className="bg-bg1 border border-line rounded p-3">
      <SectionLabel>Precision × Recall</SectionLabel>
      <svg viewBox="0 0 100 100" className="w-full block mt-2">
        <line x1="5"  y1="5"  x2="5"  y2="95" stroke="#cdcdc4" strokeWidth="0.4" />
        <line x1="5"  y1="95" x2="95" y2="95" stroke="#cdcdc4" strokeWidth="0.4" />
        <path d={path}   fill="#1f5fd6" opacity="0.10" />
        <path d={stroke} fill="none" stroke="#1f5fd6" strokeWidth="1" />
        <text x="3"  y="10" fontFamily="JetBrains Mono" fontSize="3.5" fill="#9094a0">P</text>
        <text x="93" y="98" fontFamily="JetBrains Mono" fontSize="3.5" fill="#9094a0">R 1.0</text>
        <text x="3"  y="98" fontFamily="JetBrains Mono" fontSize="3.5" fill="#9094a0">0</text>
        <text x="60" y="50" fontFamily="JetBrains Mono" fontSize="3.5"
              fill="#1c1d22">AUC {auc.toFixed(3)}</text>
      </svg>
    </div>
  );
}
