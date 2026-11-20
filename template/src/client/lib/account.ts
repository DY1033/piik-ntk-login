// NTK unified account via OpenID Connect (Authorization Code + PKCE).
// Optional sign-in: Piik works without it; signing in shows the account's
// display name + avatar in the header and syncs the display name into rooms.

const ACCOUNT_ORIGIN = "https://account.natsuko.online";
const AUTHORIZE_URL = ACCOUNT_ORIGIN + "/oauth/authorize";
const TOKEN_URL = ACCOUNT_ORIGIN + "/oauth/token";
const USERINFO_URL = ACCOUNT_ORIGIN + "/oauth/userinfo";
const END_SESSION_URL = ACCOUNT_ORIGIN + "/oauth/end_session";
const SESSION_STATUS_URL = ACCOUNT_ORIGIN + "/oauth/session_status";

// Public client: Piik is a browser app, no client secret. The platform issues
// this app with client_type=public so the token endpoint accepts PKCE alone.
const CLIENT_ID = "__NATSUKO_CLIENT_ID__";
const REDIRECT_URI = "__NATSUKO_REDIRECT_URI__";
const SCOPES = "openid profile email";
const DISPLAY_NAME_KEY = "piik:display-name:v1";
const ACCOUNT_KEY = "piik:natsuko-account:v1";
const ID_TOKEN_KEY = "piik:oauth:id_token";
const DEFAULT_AVATAR = ACCOUNT_ORIGIN + "/assets/default-avatar.svg";
// 站点策略：
//  - REQUIRE_LOGIN=true 时启用「登录守卫」：访客可以正常浏览 Piik，不会一进站就被踢去登录；
//    只有当他点击站内任意功能时，才在右上角弹出登录提示，用户点提示里的按钮才跳转账号中心。
//    false 时账号登录完全可选、不弹任何提示。
//  - LOCK_DISPLAY_NAME=true 时房间昵称被锁定为账号昵称，用户无法自行修改。
const REQUIRE_LOGIN = __NATSUKO_REQUIRE_LOGIN__;
const LOCK_DISPLAY_NAME = __NATSUKO_LOCK_NAME__;

export interface NatsukoAccount {
  sub: string;
  name: string;
  email?: string;
  picture?: string;
  preferred_username?: string;
}

type Listener = () => void;
const listeners = new Set<Listener>();

function read(): NatsukoAccount | null {
  try {
    const raw = window.localStorage.getItem(ACCOUNT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as NatsukoAccount;
    return parsed && typeof parsed.sub === "string" && parsed.sub ? parsed : null;
  } catch {
    return null;
  }
}

let cached: NatsukoAccount | null | undefined;
export function getAccount(): NatsukoAccount | null {
  if (cached === undefined) cached = read();
  return cached;
}
export function isSignedIn(): boolean {
  return getAccount() !== null;
}
export function subscribeAccount(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
function emit(): void {
  listeners.forEach((fn) => fn());
}
function store(account: NatsukoAccount | null): void {
  // 无头像的账号统一使用平台默认头像，保证头像位始终有图。
  const normalized = account
    ? { ...account, picture: account.picture || DEFAULT_AVATAR }
    : null;
  cached = normalized;
  try {
    if (normalized) window.localStorage.setItem(ACCOUNT_KEY, JSON.stringify(normalized));
    else window.localStorage.removeItem(ACCOUNT_KEY);
  } catch {
    // restricted storage: keep in-memory value only
  }
  if (normalized && LOCK_DISPLAY_NAME) lockDisplayName(normalized.name);
  if (normalized) hideLoginHint(); // 登录成功后收起右上角提示
  emit();
}

/** 已登录时把房间昵称锁定为账号昵称。用一个受控的 localStorage.setItem 包装，
 *  使任何对 display-name 键的写入（含 Piik 自己的改名 UI）都被强制回账号昵称。 */
let nameLocked = "";
let nameLockInstalled = false;
function lockDisplayName(name: string): void {
  const safe = clampName(name || "").trim();
  nameLocked = safe;
  if (!safe) return;
  try { window.localStorage.setItem(DISPLAY_NAME_KEY, safe); } catch { /* ignore */ }
  if (nameLockInstalled) return;
  nameLockInstalled = true;
  const original = window.localStorage.setItem.bind(window.localStorage);
  try {
    window.localStorage.setItem = function (key: string, value: string): void {
      if (key === DISPLAY_NAME_KEY && nameLocked) value = nameLocked;
      return original(key, value);
    };
  } catch { /* ignore: cannot wrap in restricted env */ }
}

function random(n = 24): string {
  const bytes = new Uint8Array(n);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
function base64url(bytes: ArrayBuffer | Uint8Array): string {
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = "";
  for (const b of arr) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}
async function sha256(text: string): Promise<ArrayBuffer> {
  return crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
}

/** Begin sign-in: redirect the browser to the account center. */
export async function login(): Promise<void> {
  const verifier = random(32);
  const challenge = base64url(await sha256(verifier));
  const state = random(16);
  const nonce = random(16);
  try {
    window.sessionStorage.setItem("piik:oauth:verifier", verifier);
    window.sessionStorage.setItem("piik:oauth:state", state);
    window.sessionStorage.setItem("piik:oauth:nonce", nonce);
  } catch {
    // ignore
  }
  const params = new URLSearchParams({
    response_type: "code",
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: SCOPES,
    state,
    nonce,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  window.location.assign(AUTHORIZE_URL + "?" + params.toString());
}

/** Sign out: clear the local account and end the session at the account center,
 *  returning to this site afterwards. */
export function logout(): void {
  let hint = "";
  try { hint = window.sessionStorage.getItem(ID_TOKEN_KEY) || ""; } catch { /* ignore */ }
  store(null);
  const back = window.location.origin + window.location.pathname;
  const params = new URLSearchParams({ post_logout_redirect_uri: back });
  if (hint) params.set("id_token_hint", hint);
  window.location.assign(END_SESSION_URL + "?" + params.toString());
}

/** Ask the account center whether its session is still valid.
 *  - true  : signed in there
 *  - false : explicitly signed out there -> drop our local account
 *  - unknown: cross-site request carried no cookie -> leave local state alone
 */
export async function checkAccountSession(): Promise<void> {
  if (!getAccount()) return;
  try {
    const res = await fetch(SESSION_STATUS_URL, { credentials: "include", cache: "no-store" });
    if (!res.ok) return;
    const data = (await res.json()) as { authenticated: boolean | string };
    if (data.authenticated === false) store(null);
  } catch {
    // offline / CORS: keep local state
  }
}

// ---- Login gate -----------------------------------------------------------
// 访客先正常浏览 Piik；只有点击站内功能时，才在右上角弹出登录提示。
// 用户点击提示里的「登录」按钮才真正跳转到账号中心（见 login()）。
const GATE_HINT_ID = "nk-login-gate-hint";
let gateInstalled = false;

function hideLoginHint(): void {
  try { document.getElementById(GATE_HINT_ID)?.remove(); } catch { /* ignore */ }
}

function pulseLoginHint(hint: HTMLElement): void {
  try {
    if (typeof hint.animate === "function") {
      hint.animate([{ transform: "translateY(-4px)", opacity: 0.7 }, { transform: "translateY(0)", opacity: 1 }],
        { duration: 240, easing: "ease-out" });
    }
  } catch { /* ignore */ }
}

/** 在右上角显示一条登录提示（纯 DOM + 内联样式，不依赖构建期 CSS）。 */
function showLoginHint(): void {
  if (!REQUIRE_LOGIN || getAccount()) return;
  try { if (!document.body) return; } catch { return; }
  const existing = document.getElementById(GATE_HINT_ID);
  if (existing instanceof HTMLElement) { pulseLoginHint(existing); return; }

  const hint = document.createElement("div");
  hint.id = GATE_HINT_ID;
  hint.setAttribute("role", "status");
  hint.setAttribute("aria-live", "polite");
  const box: Record<string, string> = {
    position: "fixed", top: "82px", right: "16px", zIndex: "2147483000",
    maxWidth: "320px", padding: "14px 16px", borderRadius: "12px",
    background: "rgba(12,18,15,.97)", color: "#e8fff1",
    border: "1px solid rgba(94,242,160,.5)",
    boxShadow: "0 14px 38px rgba(0,0,0,.42)",
    font: "500 13px/1.5 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    display: "flex", flexDirection: "column", gap: "10px",
  };
  Object.entries(box).forEach(([k, v]) => { hint.style.setProperty(k, v); });

  const title = document.createElement("div");
  title.textContent = "请先登录 NTK 账号";
  title.style.fontWeight = "700";
  title.style.fontSize = "14px";
  title.style.color = "#5ef2a0";

  const desc = document.createElement("div");
  desc.textContent = "登录后可解锁完整功能，并同步你的昵称与头像。";
  desc.style.opacity = "0.85";
  desc.style.fontSize = "12px";

  const row = document.createElement("div");
  row.style.display = "flex";
  row.style.gap = "8px";
  row.style.alignItems = "center";

  const go = document.createElement("button");
  go.type = "button";
  go.textContent = "立即登录";
  const goStyle: Record<string, string> = {
    cursor: "pointer", border: "0", borderRadius: "8px",
    padding: "7px 14px", background: "#5ef2a0", color: "#08120c",
    fontWeight: "700", fontSize: "13px",
  };
  Object.entries(goStyle).forEach(([k, v]) => { go.style.setProperty(k, v); });
  go.addEventListener("click", (e) => { e.stopPropagation(); void login(); });

  const later = document.createElement("button");
  later.type = "button";
  later.textContent = "稍后";
  const laterStyle: Record<string, string> = {
    cursor: "pointer", border: "1px solid rgba(255,255,255,.24)", borderRadius: "8px",
    padding: "6px 12px", background: "transparent", color: "inherit", fontSize: "12px",
  };
  Object.entries(laterStyle).forEach(([k, v]) => { later.style.setProperty(k, v); });
  later.addEventListener("click", (e) => { e.stopPropagation(); hideLoginHint(); });

  row.appendChild(go);
  row.appendChild(later);
  hint.appendChild(title);
  hint.appendChild(desc);
  hint.appendChild(row);
  document.body.appendChild(hint);
}

/** 全局捕获点击：未登录访客点功能键 → 弹右上角提示；点账号按钮/提示自身不触发。 */
function installLoginGate(): void {
  if (!REQUIRE_LOGIN || gateInstalled) return;
  gateInstalled = true;
  document.addEventListener("click", (event) => {
    if (getAccount()) { hideLoginHint(); return; }
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest(".nk-account-btn, .nk-account-group, #" + GATE_HINT_ID)) return;
    if (target.closest("button, a[href], [role='button'], input, select, textarea, [contenteditable='true']")) {
      showLoginHint();
    }
  }, true);
}

/** Max display name length accepted by Piik rooms. */
const MAX_NAME_POINTS = 24;
function clampName(name: string): string {
  const points = Array.from(name);
  return points.length <= MAX_NAME_POINTS ? name : points.slice(0, MAX_NAME_POINTS).join("");
}
/** Sync the account display name into Piik's room display-name storage. */
function syncDisplayName(name: string): void {
  const safe = clampName(name).trim();
  if (!safe) return;
  try {
    window.localStorage.setItem(DISPLAY_NAME_KEY, safe);
  } catch {
    // ignore
  }
}

/** Handle the OIDC redirect. Returns false if this page is not a callback. */
export async function handleCallback(): Promise<boolean> {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  const state = params.get("state");
  const error = params.get("error");
  if (!code && !error) return false;

  const clean = () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  };

  if (error) {
    clean();
    throw new Error("sign-in failed: " + error);
  }
  const expectedState = window.sessionStorage.getItem("piik:oauth:state");
  const verifier = window.sessionStorage.getItem("piik:oauth:verifier");
  if (!state || state !== expectedState || !verifier) {
    clean();
    throw new Error("invalid OAuth state");
  }

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: CLIENT_ID,
    code: code ?? "",
    redirect_uri: REDIRECT_URI,
    code_verifier: verifier,
  });
  const tokenRes = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!tokenRes.ok) {
    clean();
    throw new Error("token exchange failed (" + tokenRes.status + ")");
  }
  const tokens = (await tokenRes.json()) as { access_token: string; id_token?: string };
  if (tokens.id_token) {
    try { window.sessionStorage.setItem(ID_TOKEN_KEY, tokens.id_token); } catch { /* ignore */ }
  }
  const infoRes = await fetch(USERINFO_URL, {
    headers: { Authorization: "Bearer " + tokens.access_token },
  });
  if (!infoRes.ok) {
    clean();
    throw new Error("userinfo failed (" + infoRes.status + ")");
  }
  const info = (await infoRes.json()) as NatsukoAccount;
  const name = info.name || info.preferred_username || (info.email ? info.email.split("@")[0] : "NTK");
  const account: NatsukoAccount = { ...info, name };
  store(account);
  syncDisplayName(name);
  clean();
  return true;
}

/** Initialise the account module (call once at startup). Returns a promise
 *  resolving true when this page was an OIDC callback that completed. */
export function initAccount(): Promise<boolean> {
  return handleCallback().catch(() => {
    try { window.history.replaceState({}, document.title, window.location.pathname); } catch { /* ignore */ }
    return false;
  }).then((wasCallback) => {
    if (!wasCallback) {
      // 恢复本地已登录态：补齐默认头像并把昵称重新锁定为账号昵称。
      const existing = getAccount();
      if (existing) {
        if (!existing.picture) store(existing);
        else if (LOCK_DISPLAY_NAME) lockDisplayName(existing.name);
      }
      // 与账号中心保持会话同步。
      void checkAccountSession();
    }
    // 登录守卫：不打断访问；未登录访客点击站内功能时才在右上角提示登录。
    if (REQUIRE_LOGIN) installLoginGate();
    window.addEventListener("focus", () => { void checkAccountSession(); });
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) void checkAccountSession();
    });
    window.setInterval(() => { void checkAccountSession(); }, 30000);
    return wasCallback;
  });
}
