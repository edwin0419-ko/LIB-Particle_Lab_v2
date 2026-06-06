import "./globals.css";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Particle Lab — SEM 입자 분할 콘솔",
  description: "U-Net × YOLO Hybrid 기반 SEM 입자 분할 추론 · 학습 · 민감도 분석 통합 콘솔",
};

export const viewport: Viewport = {
  themeColor: "#f6f6f1",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="font-sans antialiased min-h-screen">{children}</body>
    </html>
  );
}
