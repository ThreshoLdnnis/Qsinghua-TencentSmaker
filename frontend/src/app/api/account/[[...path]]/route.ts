import { relayProduct } from "@/lib/product-relay";
export const runtime = "nodejs";
async function handler(request: Request, context: { params: Promise<{ path?: string[] }> }) {
  return relayProduct(request, ["account", ...((await context.params).path ?? [])]);
}
export { handler as GET, handler as POST, handler as DELETE };
