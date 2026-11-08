import { connection } from "next/server";
import { AccountShell } from "@/components/account-shell";

export default async function Page() {
  await connection();
  return <AccountShell liveEnabled={Boolean(process.env.LOVESTONE_PRODUCT_API_URL)} />;
}
