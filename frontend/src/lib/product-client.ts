import type { ExperienceCard, SupportChoice } from "./agent";
import { SupportError } from "./support-client";
import type { UnderstandingFields } from "./support-types";

export type ProductCard = {
  card_id: string;
  revision: number;
  created_at: string;
  fields: UnderstandingFields;
  choice: SupportChoice;
  keep_text: string;
  release_text: string;
  next_step: string;
  remember_for_future: boolean;
  session_id: string;
  understanding_id: string;
  understanding_revision: number;
};

export type CreateProductCard = {
  operation_id: string;
  session_id: string;
  understanding_id: string;
  expected_revision: number;
  choice: SupportChoice;
  keep_text: string;
  release_text: string;
  next_step: string;
  remember_for_future: boolean;
};

function cardId(value: string): string {
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(value)) throw new Error("无效的卡片编号。");
  return value;
}

function readCard(value: unknown): ProductCard {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new SupportError("upstream_error", 502);
  const card = value as Partial<ProductCard>;
  const fields = card.fields;
  if (typeof card.card_id !== "string" || !Number.isInteger(card.revision) || typeof card.created_at !== "string"
    || !fields || ![fields.facts, fields.interpretation, fields.emotions, fields.needs].every((field) => typeof field === "string")
    || !["keep", "release", "next"].includes(card.choice ?? "")
    || ![card.keep_text, card.release_text, card.next_step, card.session_id, card.understanding_id].every((field) => typeof field === "string")
    || typeof card.remember_for_future !== "boolean" || !Number.isInteger(card.understanding_revision)) {
    throw new SupportError("upstream_error", 502);
  }
  return card as ProductCard;
}

export function projectProductCard(card: ProductCard): ExperienceCard {
  const { facts, interpretation, emotions, needs } = card.fields;
  return {
    id: card.card_id,
    title: facts.trim().slice(0, 28) || "一段已确认的经历",
    hypotheses: { facts, interpretation, emotion: emotions, needs },
    choice: card.choice,
    action: card.next_step || card.keep_text || card.release_text,
    createdAt: card.created_at,
    reflectionStatus: "confirmed",
    source: "fastapi",
  };
}

export function createProductClient(csrfToken: () => string | undefined, base = "/api/product") {
  if (!/^\/[a-z0-9/_-]+$/i.test(base) || base.startsWith("//") || base.endsWith("/")) {
    throw new Error("卡片接口必须为本站的相对路径。");
  }

  async function request(path: string, method = "GET", body?: unknown, signal?: AbortSignal): Promise<unknown> {
    signal?.throwIfAborted();
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (method !== "GET") {
      const token = csrfToken();
      if (!token) throw new SupportError("authentication_required", 401);
      headers["x-csrf-token"] = token;
    }
    let response: Response;
    try {
      response = await fetch(`${base}${path}`, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "same-origin", cache: "no-store", redirect: "error", signal,
      });
    } catch {
      signal?.throwIfAborted();
      throw new SupportError("upstream_error", 502);
    }
    const result: unknown = response.status === 204 ? undefined : await response.json().catch(() => null);
    signal?.throwIfAborted();
    if (!response.ok) {
      const failure = result && typeof result === "object" ? result as Record<string, unknown> : {};
      const detail = failure.detail && typeof failure.detail === "object" ? failure.detail as Record<string, unknown> : {};
      const code = failure.code ?? detail.code;
      throw new SupportError(typeof code === "string" ? code : "upstream_error", response.status);
    }
    return result;
  }

  return {
    list: async (signal?: AbortSignal): Promise<ProductCard[]> => {
      const value = await request("/cards", "GET", undefined, signal);
      if (!Array.isArray(value)) throw new SupportError("upstream_error", 502);
      return value.map(readCard);
    },
    create: async (body: CreateProductCard): Promise<ProductCard> => readCard(await request("/cards", "POST", body)),
    remember: async (card: ProductCard, remember: boolean): Promise<ProductCard> => readCard(await request(`/cards/${cardId(card.card_id)}`, "PATCH", {
      expected_revision: card.revision, remember_for_future: remember,
    })),
    remove: async (card: ProductCard): Promise<void> => {
      await request(`/cards/${cardId(card.card_id)}?${new URLSearchParams({ expected_revision: String(card.revision) })}`, "DELETE");
    },
  };
}
