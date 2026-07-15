import type { Role } from "../data/mock";

const useCognito = import.meta.env.VITE_USE_COGNITO === "true";
const domain = import.meta.env.VITE_COGNITO_DOMAIN?.replace(/\/$/, "") ?? "";
const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID ?? "";
const redirectUri = import.meta.env.VITE_REDIRECT_URI ?? "";
const verifierKey = "policy-intelligence.cognito.pkce-verifier";
const stateKey = "policy-intelligence.cognito.oauth-state";
const tokensKey = "policy-intelligence.cognito.tokens";

export const cognitoSessionExpiredEvent = "policy-intelligence.cognito-session-expired";

export const cognitoEnabled = useCognito && Boolean(domain && clientId && redirectUri);

const base64Url = (bytes: Uint8Array): string => {
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};

const randomValue = (): string => base64Url(crypto.getRandomValues(new Uint8Array(32)));

const sha256 = async (value: string): Promise<string> => {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return base64Url(new Uint8Array(digest));
};

export async function startCognitoLogin(): Promise<void> {
  if (!cognitoEnabled) throw new Error("Cognito sign-in is not fully configured.");
  const verifier = randomValue();
  const state = randomValue();
  window.sessionStorage.setItem(verifierKey, verifier);
  window.sessionStorage.setItem(stateKey, state);
  const query = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: "openid profile email",
    state,
    code_challenge: await sha256(verifier),
    code_challenge_method: "S256",
  });
  window.location.assign(`${domain}/oauth2/authorize?${query.toString()}`);
}

interface CognitoTokens {
  access_token: string;
  id_token: string;
  refresh_token?: string;
  expires_in?: number;
  token_type?: string;
}

export class CognitoSessionExpiredError extends Error {
  constructor() {
    super("Your CSUB SSO session has expired. Please sign in again.");
    this.name = "CognitoSessionExpiredError";
  }
}

const isTokens = (value: unknown): value is CognitoTokens => typeof value === "object" && value !== null
  && "access_token" in value && typeof value.access_token === "string"
  && "id_token" in value && typeof value.id_token === "string";

const storedTokens = (): CognitoTokens | null => {
  try {
    const stored = window.localStorage.getItem(tokensKey);
    if (stored === null) return null;
    const parsed: unknown = JSON.parse(stored);
    return isTokens(parsed) ? parsed : null;
  } catch {
    return null;
  }
};

const isExpired = (token: string): boolean => {
  const payload = decodeJwtPayload(token);
  if (typeof payload !== "object" || payload === null || !("exp" in payload) || typeof payload.exp !== "number") return true;
  return payload.exp <= Math.floor(Date.now() / 1_000) + 30;
};

const clearStoredSession = (): void => {
  window.localStorage.removeItem(tokensKey);
  window.dispatchEvent(new Event(cognitoSessionExpiredEvent));
};

/** Clears the local tokens and ends the Cognito Hosted UI session. */
export function signOutCognito(): void {
  window.localStorage.removeItem(tokensKey);
  window.sessionStorage.removeItem(verifierKey);
  window.sessionStorage.removeItem(stateKey);
  if (!cognitoEnabled) {
    window.location.assign("/login");
    return;
  }
  const logoutUri = `${new URL(redirectUri).origin}/`;
  const query = new URLSearchParams({ client_id: clientId, logout_uri: logoutUri });
  window.location.assign(`${domain}/logout?${query.toString()}`);
}

const refreshCognitoSession = async (tokens: CognitoTokens): Promise<CognitoTokens | null> => {
  if (!tokens.refresh_token) return null;
  const body = new URLSearchParams({ grant_type: "refresh_token", client_id: clientId, refresh_token: tokens.refresh_token });
  try {
    const response = await fetch(`${domain}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok || !isTokens(payload)) return null;
    const refreshed = { ...payload, refresh_token: payload.refresh_token ?? tokens.refresh_token };
    window.localStorage.setItem(tokensKey, JSON.stringify(refreshed));
    return refreshed;
  } catch {
    return null;
  }
};

let refreshInFlight: Promise<CognitoTokens | null> | null = null;

/** Returns an unexpired ID token, refreshing the Cognito session when possible. */
export async function getCognitoAuthorizationToken(): Promise<string | null> {
  if (!cognitoEnabled) return null;
  const tokens = storedTokens();
  if (tokens === null) return null;
  if (!isExpired(tokens.id_token)) return tokens.id_token;

  refreshInFlight ??= refreshCognitoSession(tokens).finally(() => { refreshInFlight = null; });
  const refreshed = await refreshInFlight;
  if (refreshed !== null && !isExpired(refreshed.id_token)) return refreshed.id_token;

  clearStoredSession();
  throw new CognitoSessionExpiredError();
}

export async function completeCognitoLogin(code: string, returnedState: string | null): Promise<Role> {
  if (!cognitoEnabled) throw new Error("Cognito sign-in is not enabled.");
  const verifier = window.sessionStorage.getItem(verifierKey);
  const expectedState = window.sessionStorage.getItem(stateKey);
  if (!verifier || !expectedState || returnedState !== expectedState) throw new Error("The sign-in response could not be verified. Please try again.");
  const body = new URLSearchParams({ grant_type: "authorization_code", client_id: clientId, code, redirect_uri: redirectUri, code_verifier: verifier });
  const response = await fetch(`${domain}/oauth2/token`, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok || !isTokens(payload)) throw new Error("CSUB SSO did not return a valid sign-in token.");
  window.sessionStorage.removeItem(verifierKey);
  window.sessionStorage.removeItem(stateKey);
  window.localStorage.setItem(tokensKey, JSON.stringify(payload));
  return roleFromIdToken(payload.id_token);
}

const decodeJwtPayload = (token: string): unknown => {
  const encoded = token.split(".")[1];
  if (!encoded) return null;
  try {
    const base64 = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes)) as unknown;
  } catch { return null; }
};

export function roleFromIdToken(idToken: string): Role {
  const payload = decodeJwtPayload(idToken);
  if (typeof payload !== "object" || payload === null || !("cognito:groups" in payload)) return "employee";
  const groups = payload["cognito:groups"];
  if (!Array.isArray(groups) || !groups.every((group): group is string => typeof group === "string")) return "employee";
  return groups.includes("makers") ? "reviewer" : "employee";
}
