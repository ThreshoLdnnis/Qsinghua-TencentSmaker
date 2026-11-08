"use client";

import { ArrowUpRight, Check, Feather, LoaderCircle, LogOut, UserRound, X } from "lucide-react";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { accountClient, type AccountClient, type AccountSession } from "@/lib/account-client";
import "./account-access.css";

type AccountAccessProps = {
  session: AccountSession | null;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
  client?: AccountClient;
  onSessionChange: (session: AccountSession) => void | Promise<void>;
};

export function AccountAccess({ session, loading = false, disabled = false, className, client = accountClient, onSessionChange }: AccountAccessProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const request = useRef<AbortController | null>(null);
  const titleId = useId();
  const usernameId = useId();
  const passwordId = useId();
  const usernameHintId = useId();
  const passwordHintId = useId();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [consent, setConsent] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const user = session?.user;

  useEffect(() => () => request.current?.abort(), []);

  function close() {
    if (request.current) return;
    dialog.current?.close();
    setPassword("");
    setConsent(false);
    setError("");
    trigger.current?.focus();
  }

  function open() {
    setMode("login");
    setPassword("");
    setConsent(false);
    setError("");
    dialog.current?.showModal();
  }

  function switchMode(next: "login" | "register") {
    if (request.current || next === mode) return;
    setMode(next);
    setPassword("");
    setConsent(false);
    setError("");
  }

  async function updateSession(next: AccountSession) {
    setPassword("");
    try {
      await onSessionChange(next);
    } catch {
      throw new Error("账号状态已经更新，请刷新页面以恢复当前旅程。");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (request.current || (mode === "register" && !consent)) return;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError("");
    try {
      const credentials = { username, password, consent: true as const };
      const next = await client[mode](credentials, controller.signal);
      if (request.current !== controller) return;
      await updateSession(next);
      request.current = null;
      close();
    } catch (issue) {
      if (controller.signal.aborted || request.current !== controller) return;
      setError(issue instanceof Error ? issue.message : "暂时无法完成登录，请稍后再试。");
      setPassword("");
    } finally {
      if (request.current === controller) request.current = null;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  async function logout() {
    if (request.current || !session?.user) return;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError("");
    try {
      const next = await client.logout(session, controller.signal);
      if (request.current !== controller) return;
      await updateSession(next);
      request.current = null;
      close();
    } catch (issue) {
      if (controller.signal.aborted || request.current !== controller) return;
      setError(issue instanceof Error ? issue.message : "暂时无法退出登录，请稍后再试。");
    } finally {
      if (request.current === controller) request.current = null;
      if (!controller.signal.aborted) setPending(false);
    }
  }

  return <>
    <button ref={trigger} type="button" className={["account-trigger", className].filter(Boolean).join(" ")}
      disabled={loading || disabled} aria-busy={loading} aria-haspopup="dialog" onClick={open}>
      {loading ? <LoaderCircle className="account-spinner" size={15} aria-hidden="true" /> : <UserRound size={15} aria-hidden="true" />}
      <span>{loading ? "正在连接" : user?.username ?? "登录 / 注册"}</span>
    </button>
    <dialog ref={dialog} className="account-dialog" aria-labelledby={titleId}
      onCancel={(event) => { event.preventDefault(); close(); }}
      onClick={(event) => { if (event.target === event.currentTarget) close(); }}>
      <div className="account-card">
        <button type="button" className="account-close" onClick={close} disabled={pending} aria-label="关闭账号窗口"><X size={19} /></button>
        <div className="account-symbol" aria-hidden="true"><Feather size={25} /></div>
        <p className="account-eyebrow">YOUR LITTLE UNIVERSE</p>
        <h2 id={titleId}>{user ? "属于你的空间" : mode === "login" ? "欢迎回来。" : "留一个自己的位置。"}</h2>
        {user ? <div className="account-profile">
          <p className="account-username"><Check size={15} aria-hidden="true" />{user.username}</p>
          <p>主动保存的经历卡会关联到这个账号。对话不会自动存为卡片，向 AI 发送内容需要每次确认。</p>
          <button type="button" className="account-submit account-logout" onClick={logout} disabled={pending}>
            {pending ? <LoaderCircle size={16} className="account-spinner" aria-hidden="true" /> : <LogOut size={16} aria-hidden="true" />}
            {pending ? "正在退出" : "退出登录"}
          </button>
        </div> : <>
          <p className="account-intro">让你选择留下的理解，在下次回来时仍有位置。</p>
          <div className="account-modes" role="group" aria-label="账号操作">
            <button type="button" aria-pressed={mode === "login"} onClick={() => switchMode("login")} disabled={pending}>登录</button>
            <button type="button" aria-pressed={mode === "register"} onClick={() => switchMode("register")} disabled={pending}>创建账号</button>
          </div>
          <form onSubmit={submit} aria-busy={pending}>
            <label className="account-field" htmlFor={usernameId}>
              <span>用户名</span>
              <input id={usernameId} value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username"
                autoCapitalize="none" spellCheck={false} required minLength={3} maxLength={32} pattern="[A-Za-z0-9_-]{3,32}"
                aria-describedby={usernameHintId} disabled={pending} autoFocus />
            </label>
            <small id={usernameHintId} className="account-field-hint">3–32 位字母、数字、下划线或连字符</small>
            <label className="account-field" htmlFor={passwordId}>
              <span>密码</span>
              <input id={passwordId} type="password" value={password} onChange={(event) => setPassword(event.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={10} maxLength={128}
                aria-describedby={passwordHintId} disabled={pending} />
            </label>
            <small id={passwordHintId} className="account-field-hint">10–128 个字符，请妥善保管</small>
            {mode === "register" && <label className="account-consent">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} disabled={pending} required />
              <span>我同意保存账号信息，主动保存的经历卡会关联到此账号。向 AI 发送文字需要每次确认。</span>
            </label>}
            <button type="submit" className="account-submit" disabled={pending || (mode === "register" && !consent)}>
              <span>{pending ? "正在连接你的空间" : mode === "login" ? "进入我的空间" : "创建我的空间"}</span>
              {pending ? <LoaderCircle size={17} className="account-spinner" aria-hidden="true" /> : <ArrowUpRight size={17} aria-hidden="true" />}
            </button>
          </form>
          <p className="account-footnote">当前为试用框架，请仅用虚构内容测试。账号没有密码找回；服务端经历卡尚未提供端到端加密。</p>
        </>}
        {error && <p className="account-error" role="alert">{error}</p>}
      </div>
    </dialog>
  </>;
}
