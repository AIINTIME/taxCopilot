// Shared holder for the current access token, so taxApi.ts (and anything
// else outside React) can attach it to a request without every call site
// threading it through unrelated request/response types. AuthContext.tsx is
// the only writer -- it calls setAccessToken alongside every place it sets
// its own `accessToken` state (login, register, refresh, logout).
let currentAccessToken: string | null = null

export function setAccessToken(token: string | null) {
  currentAccessToken = token
}

export function getAccessToken(): string | null {
  return currentAccessToken
}
