import { test } from "node:test";
import assert from "node:assert/strict";
import { relayProduct } from "../src/lib/product-relay";

test("product relay preserves same-origin cookie/CSRF and never forwards unrelated cookies", async () => {
  const old = globalThis.fetch;
  process.env.LOVESTONE_PRODUCT_API_URL = "http://127.0.0.1:8070";
  let called = false;
  globalThis.fetch = async (input, options) => {
    called = true;
    assert.equal(String(input), "http://127.0.0.1:8070/api/account/login");
    const headers = new Headers(options?.headers);
    assert.equal(headers.get("cookie"), "lingyv_session=opaque");
    assert.equal(headers.get("origin"), "https://qsinghua.lingozm.cn");
    assert.equal(headers.get("authorization"), null);
    return Response.json({ user: { id: "fixture", username: "fixture" } }, { headers: { "Set-Cookie": "lingyv_session=new; HttpOnly; Secure; SameSite=Lax; Path=/" } });
  };
  try {
    const response = await relayProduct(new Request("https://qsinghua.lingozm.cn/api/account/login", {
      method: "POST", headers: { Origin: "https://qsinghua.lingozm.cn", Cookie: "unrelated=private; lingyv_session=opaque", Authorization: "unrelated-secret" }, body: "{}",
    }), ["account", "login"]);
    assert.equal(response.status, 200); assert.ok(called);
    assert.match(response.headers.get("set-cookie") ?? "", /HttpOnly/);
    assert.equal(response.headers.get("cache-control"), "no-store");
  } finally { globalThis.fetch = old; delete process.env.LOVESTONE_PRODUCT_API_URL; }
});

test("product relay rejects path/query injections, unsafe origins, and a missing service", async () => {
  const old = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error("must not fetch"); };
  try {
    for (const base of [undefined, "http://public.example", "https://user:password@public.example/", "https://public.example/path"]) {
      if (base) process.env.LOVESTONE_PRODUCT_API_URL = base; else delete process.env.LOVESTONE_PRODUCT_API_URL;
      assert.equal((await relayProduct(new Request("https://site/api/account/me"), ["account", "me"])).status, 503);
    }
    process.env.LOVESTONE_PRODUCT_API_URL = "http://127.0.0.1:8070";
    assert.equal((await relayProduct(new Request("https://site/api/account/me"), ["account", "..", "me"])).status, 404);
    assert.equal((await relayProduct(new Request("https://site/api/product/cards?owner=someone"), ["product", "cards"])).status, 400);
    assert.equal(calls, 0);
  } finally { globalThis.fetch = old; delete process.env.LOVESTONE_PRODUCT_API_URL; }
});

test("chunked oversized credential requests fail without forwarding sensitive content", async () => {
  const old = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; throw new Error("must not fetch"); };
  process.env.LOVESTONE_PRODUCT_API_URL = "http://127.0.0.1:8070";
  try {
    const response = await relayProduct(new Request("https://site/api/account/register", { method: "POST", body: "x".repeat(4*1024*1024+1) }), ["account", "register"]);
    assert.equal(response.status, 413); assert.equal(calls, 0);
  } finally { globalThis.fetch = old; delete process.env.LOVESTONE_PRODUCT_API_URL; }
});
