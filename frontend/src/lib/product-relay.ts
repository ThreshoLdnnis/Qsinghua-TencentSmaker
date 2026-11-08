/** Narrow same-origin bridge to the authenticated Python product boundary. */
const route = /^\/(?:account\/(?:me|login|register|logout)|product\/cards(?:\/[0-9a-f-]{36})?|support\/(?:health|support|wearables\/catalog|sessions(?:\/[0-9a-f-]{36}(?:\/(?:support-state|messages|end|workflow\/cancel|wearables\/(?:trends|simulate|consent)|analysis|reports(?:\/[A-Za-z0-9_-]{1,128}\/delete)?|understandings(?:\/control|\/[A-Za-z0-9_-]{1,128}(?:\/(?:confirm|reject))?)?))?)?))$/;
const unavailable = () => Response.json({ detail: { code: "product_service_unavailable", message: "账号与真实模型服务尚未部署，仍可使用独立演示。" } }, { status: 503, headers: { "Cache-Control": "no-store" } });

export async function relayProduct(request: Request, segments: string[]): Promise<Response> {
  const suffix = "/" + segments.join("/");
  if (!route.test(suffix) || segments.some(part => part.includes("..") || /[%?#\\]/.test(part))) return new Response(null, { status: 404 });
  const configured = process.env.LOVESTONE_PRODUCT_API_URL;
  if (!configured) return unavailable();
  let base: URL;
  try { base = new URL(configured); } catch { return unavailable(); }
  if (base.username || base.password || base.search || base.hash || base.pathname !== "/"
    || !(base.protocol === "https:" || (base.protocol === "http:" && ["127.0.0.1", "localhost", "[::1]"].includes(base.hostname)))) return unavailable();
  const target = new URL("/api" + suffix, base);
  const incoming = new URL(request.url);
  for (const [key, value] of incoming.searchParams) {
    if (!["expected_revision", "as_of", "days", "timezone", "scope"].includes(key)) return new Response(null, { status: 400 });
    target.searchParams.append(key, value);
  }
  const headers = new Headers({ Accept: "application/json" });
  for (const name of ["origin", "x-csrf-token", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const cookie = request.headers.get("cookie")?.split(";").map(p => p.trim()).find(p => p.startsWith("lingyv_session="));
  if (cookie) headers.set("cookie", cookie);
  try {
    let body: Uint8Array | undefined;
    if (!["GET", "HEAD"].includes(request.method)) {
      const reader = request.body?.getReader();
      if (reader) {
        const parts: Uint8Array[] = []; let length = 0;
        for (;;) {
          const { done, value } = await reader.read(); if (done) break;
          length += value.length;
          if (length > 4 * 1024 * 1024) { await reader.cancel(); return new Response(null, { status: 413 }); }
          parts.push(value);
        }
        body = new Uint8Array(length); let offset = 0;
        for (const part of parts) { body.set(part, offset); offset += part.length; }
      }
    }
    const response = await fetch(target, { method: request.method, headers, body: body as BodyInit | undefined,
      cache: "no-store", redirect: "error", signal: AbortSignal.timeout(65000) });
    if (response.status !== 204 && !response.headers.get("content-type")?.includes("application/json")) return unavailable();
    const outputHeaders = new Headers({ "Cache-Control": "no-store", "Content-Type": "application/json", "X-Content-Type-Options": "nosniff" });
    for (const value of response.headers.getSetCookie()) outputHeaders.append("set-cookie", value);
    let payload: Uint8Array | null = null;
    if (response.status !== 204) {
      const reader = response.body?.getReader(); const parts: Uint8Array[] = []; let length = 0;
      if (reader) for (;;) {
        const { done, value } = await reader.read(); if (done) break;
        length += value.length;
        if (length > 4 * 1024 * 1024) { await reader.cancel(); return unavailable(); }
        parts.push(value);
      }
      payload = new Uint8Array(length); let offset = 0;
      for (const part of parts) { payload.set(part, offset); offset += part.length; }
    }
    return new Response(payload as BodyInit | null, { status: response.status, headers: outputHeaders });
  } catch { return unavailable(); }
}
