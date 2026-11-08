import { handleSupportRequest } from "@/lib/support-relay";
import { relayProduct } from "@/lib/product-relay";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
async function handler(request: Request, context: { params: Promise<{ path?: string[] }> }) {
  if (process.env.LOVESTONE_PRODUCT_API_URL) return relayProduct(request, ["support", ...((await context.params).path ?? [])]);
  return handleSupportRequest(request);
}
export { handler as GET, handler as POST, handler as PUT, handler as DELETE };
