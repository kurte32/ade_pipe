import { expect, type Page } from "@playwright/test";

export const PWA_URL = process.env.PWA_URL ?? "http://localhost:5173";
export const ADMIN_URL = process.env.ADMIN_URL ?? "http://localhost:5174";
export const API_URL = process.env.API_URL ?? "http://localhost:8000";
export const DEV_IDP_URL = process.env.DEV_IDP_URL ?? "http://localhost:8001";
export const PWA_CLIENT_ID = "33333333-3333-4333-8333-333333333333";
export const ADMIN_CLIENT_ID = "44444444-4444-4444-8444-444444444444";

/** Sign in through the dev user picker rendered by @pipeline/auth SignIn. */
export async function signInAs(page: Page, baseUrl: string, userCode: string): Promise<void> {
  await page.goto(baseUrl + "/");
  const button = page.getByTestId(`dev-user-${userCode}`);
  await expect(button).toBeVisible();
  await button.click();
  await expect(page.getByTestId(`dev-user-${userCode}`)).toBeHidden();
}

/** Mint a token directly for API-level setup in tests. */
export async function mintToken(userCode: string, clientId = PWA_CLIENT_ID): Promise<string> {
  const res = await fetch(`${DEV_IDP_URL}/token`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ user_code: userCode, client_id: clientId }),
  });
  if (!res.ok) throw new Error(`dev-idp ${res.status}`);
  return ((await res.json()) as { access_token: string }).access_token;
}

export async function api<T>(
  method: string,
  path: string,
  token: string,
  body?: unknown,
  headers: Record<string, string> = {},
): Promise<{ status: number; data: T; etag: string | null }> {
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      authorization: `Bearer ${token}`,
      ...(body instanceof FormData ? {} : { "content-type": "application/json" }),
      ...headers,
    },
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  return { status: res.status, data: data as T, etag: res.headers.get("etag") };
}
