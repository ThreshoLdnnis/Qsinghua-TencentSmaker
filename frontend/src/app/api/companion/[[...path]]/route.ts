import { relayProduct } from "@/lib/product-relay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handler(request: Request, context: { params: Promise<{ path?: string[] }> }) {
  return relayProduct(request, ["companion", ...((await context.params).path ?? [])]);
}

export { handler as GET, handler as POST };
