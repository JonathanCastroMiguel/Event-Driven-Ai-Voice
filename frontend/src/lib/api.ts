/** API client for the Voice AI Runtime backend. */

import type { CreateCallResponse, SDPResponse } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }

  return res.json() as Promise<T>;
}

export const api = {
  calls: {
    create: () =>
      apiFetch<CreateCallResponse>("/api/v1/calls", { method: "POST" }),

    offer: (callId: string, sdp: string) =>
      apiFetch<SDPResponse>(`/api/v1/calls/${callId}/offer`, {
        method: "POST",
        body: JSON.stringify({ sdp, type: "offer" }),
      }),

    ice: (callId: string, candidate: string, sdpMid?: string | null) =>
      apiFetch<void>(`/api/v1/calls/${callId}/ice`, {
        method: "POST",
        body: JSON.stringify({ candidate, sdpMid }),
      }),

    end: (callId: string) =>
      apiFetch<void>(`/api/v1/calls/${callId}`, { method: "DELETE" }),
  },
};
