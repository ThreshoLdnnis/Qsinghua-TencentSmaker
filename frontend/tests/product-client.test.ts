import assert from "node:assert/strict";
import { test } from "node:test";
import { createProductClient, projectProductCard, type ProductCard } from "../src/lib/product-client";
import { SupportError } from "../src/lib/support-client";
import { projectReflection } from "../src/lib/support-presentation";

const card: ProductCard = {
  card_id: "11111111-1111-4111-8111-111111111111", revision: 1, created_at: "2026-11-08T00:00:00Z",
  fields: { facts: "虚构会议没有发言", interpretation: "我想再找机会表达", emotions: "遗憾", needs: "被听见" },
  choice: "next", keep_text: "保留准备", release_text: "", next_step: "明天问一个问题", remember_for_future: false,
  session_id: "22222222-2222-4222-8222-222222222222", understanding_id: "u1", understanding_revision: 3,
};

test("owned cards use same-origin cookies and CSRF for saves, memory changes and versioned deletes", async (context) => {
  const fetchMock = context.mock.method(globalThis, "fetch", async (_url: RequestInfo | URL, options?: RequestInit) => options?.method === "DELETE"
    ? new Response(null, { status: 204 }) : Response.json(options?.method === "GET" ? [card] : card));
  const api = createProductClient(() => "csrf-fixture");
  assert.deepEqual(await api.list(), [card]);
  await api.create({ operation_id: "op1", session_id: card.session_id, understanding_id: card.understanding_id,
    expected_revision: 3, choice: "next", keep_text: card.keep_text, release_text: "", next_step: card.next_step, remember_for_future: false });
  await api.remember(card, true);
  await api.remove(card);
  for (const { arguments: [, options] } of fetchMock.mock.calls) assert.equal(options?.credentials, "same-origin");
  for (const { arguments: [, options] } of fetchMock.mock.calls.slice(1)) {
    assert.equal(new Headers(options?.headers).get("x-csrf-token"), "csrf-fixture");
  }
  assert.equal(fetchMock.mock.calls[3].arguments[0], `/api/product/cards/${card.card_id}?expected_revision=1`);
  assert.deepEqual(JSON.parse(String(fetchMock.mock.calls[2].arguments[1]?.body)), { expected_revision: 1, remember_for_future: true });
});

test("missing login, malformed cards and server conflicts stay failures without local card success", async (context) => {
  const fetchMock = context.mock.method(globalThis, "fetch", async () => Response.json({}));
  await assert.rejects(createProductClient(() => undefined).remember(card, true), (error) => error instanceof SupportError && error.code === "authentication_required");
  assert.equal(fetchMock.mock.callCount(), 0);
  await assert.rejects(createProductClient(() => "csrf").list(), (error) => error instanceof SupportError);
  fetchMock.mock.mockImplementation(async () => Response.json({ detail: { code: "stale_revision" } }, { status: 409 }));
  await assert.rejects(createProductClient(() => "csrf").remember(card, true), (error) => error instanceof SupportError && error.code === "stale_revision");
});

test("native understanding fields reach the canvas literally and persisted cards retain user-authored choices", () => {
  const projected = projectReflection({
    understanding: { understanding: {
      schema_version: "understanding.v0.1", understanding_id: "u1", revision: 3, status: "confirmed",
      interpretation: "简短摘要", fields: card.fields, origin: "user_report", evidence_refs: [],
      created_at: card.created_at, updated_at: card.created_at, confirmed_revision: 3, confirmed_at: card.created_at, invalidation_reason: null,
    }, confirmation_token: null },
    currentInput: "", reply: "回应",
  });
  assert.equal(projected?.hypotheses.facts, card.fields.facts);
  assert.equal(projected?.hypotheses.emotion, card.fields.emotions);
  assert.equal(projected?.hypotheses.interpretation, card.fields.interpretation);
  assert.equal(projectProductCard(card).action, card.next_step);
  assert.equal(projectProductCard(card).source, "fastapi");
});
