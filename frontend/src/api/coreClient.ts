import { ApiError, Holding, InvestigationResult, LoginPayload, RegisterPayload, TokenResponse, User } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL;

const ACCESS_TOKEN_KEY = "risklens_access_token";
const REFRESH_TOKEN_KEY = "risklens_refresh_token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      // FastAPI/Pydantic validation error shape.
      return body.detail.map((item: { msg?: string }) => item.msg).join(", ");
    }
  } catch {
    // Response body wasn't JSON; fall through to the generic message below.
  }
  return `Request failed with status ${response.status}`;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await extractErrorMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// Attaches the stored access token automatically — every authenticated
// endpoint (anything but /auth/register and /auth/login) goes through this
// instead of building the Authorization header by hand each time.
async function authRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getAccessToken();
  return request<T>(path, {
    ...options,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
}

export function register(payload: RegisterPayload): Promise<User> {
  return request<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function login(payload: LoginPayload): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function refresh(refreshToken: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export function me(accessToken: string): Promise<User> {
  return request<User>("/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function getHoldings(): Promise<Holding[]> {
  return authRequest<Holding[]>("/portfolio/holdings");
}

export function addHolding(input: Omit<Holding, "id">): Promise<Holding> {
  return authRequest<Holding>("/portfolio/holdings", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateHolding(id: number, input: Omit<Holding, "id">): Promise<Holding> {
  return authRequest<Holding>(`/portfolio/holdings/${id}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function removeHolding(id: number): Promise<void> {
  return authRequest<void>(`/portfolio/holdings/${id}`, {
    method: "DELETE",
  });
}

export function investigate(question: string): Promise<InvestigationResult> {
  return authRequest<InvestigationResult>("/investigations", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

