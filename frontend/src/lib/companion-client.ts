export type CompanionId = "shiguang" | "weilan" | "qiyu";

export type CompanionReply = {
  session_id: string;
  companion_id: CompanionId;
  reply: string;
  request_id: string;
  revision: number;
  memory_refs: Array<{ card_id?: string; revision?: number; title?: string }>;
};

export type CompanionSession = {
  session_id: string;
  revision: number;
  status: "ACTIVE" | "ENDED";
  messages: Array<{ role: "user" | "assistant"; content: string }>;
};

type ErrorPayload = { detail?: { code?: unknown; message?: unknown } | string; code?: unknown; message?: unknown };

function errorMessage(value: unknown): string {
  if (!value || typeof value !== "object") return "旅伴暂时没有回应，请稍后再试。";
  const payload = value as ErrorPayload;
  const detail = typeof payload.detail === "object" && payload.detail ? payload.detail : undefined;
  const message = detail && typeof detail.message === "string" ? detail.message : typeof payload.message === "string" ? payload.message : undefined;
  return message ?? "旅伴暂时没有回应，请稍后再试。";
}

async function request<T>(path: string, method: "GET" | "POST", body: unknown, csrfToken: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/companion${path}`, {
    method,
    headers: { "Content-Type": "application/json", "x-csrf-token": csrfToken },
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(payload));
  return payload as T;
}

export async function createCompanionSession(csrfToken: string, signal?: AbortSignal): Promise<{ session_id: string }> {
  return request<{ session_id: string }>("/sessions", "POST", undefined, csrfToken, signal);
}

export async function getCompanionSession(sessionId: string, csrfToken: string, signal?: AbortSignal): Promise<CompanionSession> {
  return request<CompanionSession>(`/sessions/${encodeURIComponent(sessionId)}`, "GET", undefined, csrfToken, signal);
}

export async function sendCompanionMessage(input: {
  sessionId: string;
  csrfToken: string;
  companionId: CompanionId;
  content: string;
  requestId: string;
  useMemories: boolean;
  signal?: AbortSignal;
}): Promise<CompanionReply> {
  return request<CompanionReply>(`/sessions/${encodeURIComponent(input.sessionId)}/messages`, "POST", {
    content: input.content,
    request_id: input.requestId,
    model_consent: true,
    companion_id: input.companionId,
    use_memories: input.useMemories,
  }, input.csrfToken, input.signal);
}
