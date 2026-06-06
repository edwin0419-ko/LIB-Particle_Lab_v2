// Backend HTTP client. NEXT_PUBLIC_API_BASE 환경변수로 base URL 지정.

import type { ModeId, SessionState } from "./types-extra";

// 기본값 = 빈 문자열(같은 origin 상대 경로). FastAPI 가 정적 프런트 + API 를
// 같은 포트에서 서빙하므로, 런처 포트가 8765→8766 으로 밀려도 자동으로 맞는다.
// (예전엔 fallback 이 절대 URL "http://localhost:8765" 라서, 빌드타임 env 주입이
//  번들에 inline 안 되면 런타임에 죽은 8765 로 요청 → 모든 API 실패했었다.)
// 별도 백엔드(standalone/dev)를 쓸 때만 NEXT_PUBLIC_API_BASE 로 절대 URL 지정.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

async function jsonOrThrow(res: Response) {
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export const api = {
  async health() {
    return jsonOrThrow(await fetch(`${API_BASE}/api/health`));
  },
  async createSession(mode: ModeId = "yolo"): Promise<{ session_id: string }> {
    return jsonOrThrow(
      await fetch(`${API_BASE}/api/sessions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ mode }),
      }),
    );
  },
  async listSessions(): Promise<string[]> {
    return jsonOrThrow(await fetch(`${API_BASE}/api/sessions`));
  },
  async getSession(id: string): Promise<SessionState> {
    return jsonOrThrow(await fetch(`${API_BASE}/api/sessions/${id}`));
  },
  async uploadFile(id: string, role: string, file: File) {
    const fd = new FormData();
    fd.append("role", role);
    fd.append("file", file);
    return jsonOrThrow(
      await fetch(`${API_BASE}/api/sessions/${id}/upload`, {
        method: "POST",
        body: fd,
      }),
    );
  },
};
