"use client";

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { accountClient, type AccountClient, type AccountSession } from "@/lib/account-client";
import { AccountAccess } from "./account-access";
import { LoveStone } from "./lovestone";

type AccountShellProps = {
  liveEnabled?: boolean;
  client?: AccountClient;
};

/** A missing account service leaves a usable, explicitly labelled local demo. */
export function AccountShell({ liveEnabled = true, client = accountClient }: AccountShellProps) {
  const [session, setSession] = useState<AccountSession>({ user: null });
  const [status, setStatus] = useState<"loading" | "available" | "unavailable" | "disabled">(
    liveEnabled ? "loading" : "disabled",
  );
  const request = useRef<AbortController | null>(null);

  const refreshAccount = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setStatus("loading");
    let timedOut = false;
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 12000);
    try {
      const next = await client.me(controller.signal);
      if (request.current !== controller || controller.signal.aborted) return;
      setSession(next);
      setStatus("available");
    } catch {
      if (request.current !== controller || (controller.signal.aborted && !timedOut)) return;
      setSession({ user: null });
      setStatus("unavailable");
    } finally {
      window.clearTimeout(timeout);
      if (request.current === controller) request.current = null;
    }
  }, [client]);

  useEffect(() => {
    if (liveEnabled) {
      void refreshAccount();
    } else {
      setSession({ user: null });
      setStatus("disabled");
    }
    return () => { request.current?.abort(); request.current = null; };
  }, [liveEnabled, refreshAccount]);

  const connected = liveEnabled && status === "available";
  const control = <div className="account-controls">
    {status === "unavailable" && <button type="button" className="account-service-notice" onClick={() => void refreshAccount()}
      title="账号服务暂不可用，当前为本地演示；点击重新连接。" aria-label="账号服务暂不可用，当前为本地演示，重新连接账号服务">
      <span>本地演示 · 账号服务未连接</span><RefreshCw size={13} aria-hidden="true" />
    </button>}
    {status === "disabled" ? <span className="account-offline-note">本地演示 · 未连接账号服务</span> : <AccountAccess
      session={session} client={client} loading={status === "loading"} disabled={!connected}
      onSessionChange={(next) => { setSession(next); setStatus("available"); }} />}
    <span className="account-status" role="status" aria-live="polite">
      {status === "loading" ? "正在检查账号服务，本地演示仍可使用。" : status === "unavailable"
        ? "账号服务暂不可用，当前使用本地演示。演示内容刷新即清除。"
        : status === "available" ? session.user ? `已登录：${session.user.username}` : "账号服务已连接，可以登录或使用本地演示。" : "当前使用本地演示，未连接账号服务。"}
    </span>
  </div>;

  // Changing connection mode or user remounts the workspace: no previous account's
  // drafts, cards, or pending request state can carry into the next account.
  return <LoveStone key={`${connected ? "connected" : "local-demo"}:${session.user?.id ?? "guest"}`} liveEnabled={connected}
    account={session} accountControl={control} />;
}
