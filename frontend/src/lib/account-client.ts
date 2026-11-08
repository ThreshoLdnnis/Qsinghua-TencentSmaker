export type AccountUser = {
  id: string;
  username: string;
};

export type AccountSession = {
  user: AccountUser | null;
  csrf_token?: string;
};

export type AccountCredentials = {
  username: string;
  password: string;
  consent: true;
};

const accountMessages: Record<string, string> = {
  invalid_credentials: "用户名或密码不正确，请再检查一下。",
  username_taken: "这个用户名已被使用，请换一个。",
  invalid_username: "用户名需为 3–32 位字母、数字、下划线或连字符。",
  weak_password: "密码需为 10–128 个字符。",
  rate_limited: "尝试次数较多，请稍后再试。",
  authentication_required: "登录状态已过期，请重新登录。",
  csrf_invalid: "登录状态已更新，请刷新页面后再操作。",
  origin_invalid: "当前网址与账号服务配置不一致，请使用正式网站地址。",
  consent_required: "请先确认账号信息的保存说明。",
  account_storage_error: "暂时无法读取或保存账号，请稍后再试。",
  not_configured: "账号服务尚未连接，请稍后再试。",
  account_unavailable: "暂时无法连接账号服务，请稍后再试。",
};

export class AccountError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, status: number) {
    super(accountMessages[code] ?? accountMessages.account_unavailable);
    this.name = "AccountError";
    this.code = code;
    this.status = status;
  }
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function readSession(value: unknown, requireUser: boolean): AccountSession {
  const entry = record(value);
  if (entry?.user === null && !requireUser) return { user: null };

  const user = record(entry?.user);
  if (!user || typeof user.id !== "string" || !user.id || typeof user.username !== "string"
    || !user.username || typeof entry?.csrf_token !== "string" || !entry.csrf_token) {
    throw new AccountError("account_unavailable", 502);
  }
  return { user: { id: user.id, username: user.username }, csrf_token: entry.csrf_token };
}

export function createAccountClient(base = "/api/account") {
  if (!/^\/[a-z0-9/_-]+$/i.test(base) || base.startsWith("//") || base.endsWith("/")) {
    throw new Error("账号接口必须为本站的相对路径。");
  }

  async function request(path: string, method: "GET" | "POST", body: unknown, signal?: AbortSignal, csrfToken?: string): Promise<unknown> {
    signal?.throwIfAborted();
    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (csrfToken) headers["x-csrf-token"] = csrfToken;

    let response: Response;
    try {
      response = await fetch(`${base}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.any([...(signal ? [signal] : []), AbortSignal.timeout(15000)]),
      });
    } catch {
      signal?.throwIfAborted();
      throw new AccountError("account_unavailable", 502);
    }

    const result: unknown = response.status === 204 ? undefined : await response.json().catch(() => undefined);
    signal?.throwIfAborted();
    if (!response.ok) {
      const failure = record(result);
      const code = failure?.code ?? record(failure?.detail)?.code;
      throw new AccountError(typeof code === "string" ? code : "account_unavailable", response.status);
    }
    return result;
  }

  async function signIn(path: "/register" | "/login", input: AccountCredentials, signal?: AbortSignal): Promise<AccountSession> {
    if (input.consent !== true) throw new AccountError("consent_required", 400);
    return readSession(await request(path, "POST", {
      username: input.username.trim(), password: input.password, consent: true,
    }, signal), true);
  }

  return {
    me: async (signal?: AbortSignal) => readSession(await request("/me", "GET", undefined, signal), false),
    register: (input: AccountCredentials, signal?: AbortSignal) => signIn("/register", input, signal),
    login: (input: AccountCredentials, signal?: AbortSignal) => signIn("/login", input, signal),
    logout: async (session: AccountSession, signal?: AbortSignal): Promise<AccountSession> => {
      if (!session.user || !session.csrf_token) throw new AccountError("authentication_required", 401);
      let result: unknown;
      try {
        result = await request("/logout", "POST", undefined, signal, session.csrf_token);
      } catch (issue) {
        // An expired or already-revoked server session is already signed out.
        if (issue instanceof AccountError && issue.code === "authentication_required" && issue.status === 401) return { user: null };
        throw issue;
      }
      if (result !== undefined && readSession(result, false).user !== null) {
        throw new AccountError("account_unavailable", 502);
      }
      return { user: null };
    },
  };
}

export const accountClient = createAccountClient();
export type AccountClient = ReturnType<typeof createAccountClient>;
