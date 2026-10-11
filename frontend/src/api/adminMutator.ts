import axios, { type AxiosRequestConfig } from 'axios'

// Admin API client (/admin/*). Separate from the chat's mutator on purpose (Epic E4):
// - it never sends the chat session cookie (withCredentials: false);
// - every request carries the admin's Auth0 access token as a Bearer token.
// Orval wires it to every operation tagged "admin" (orval.config.ts).

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

type TokenGetter = () => Promise<string | undefined>

let getAccessToken: TokenGetter | null = null

// Registered by the admin UI once Auth0 has a signed-in admin; null on logout.
// The token itself is never stored here — the Auth0 SDK keeps it (in memory) and refreshes it.
export function setAdminTokenGetter(getter: TokenGetter | null): void {
  getAccessToken = getter
}

export const adminAxios = axios.create({
  baseURL: API_URL,
  withCredentials: false,
})

adminAxios.interceptors.request.use(async (config) => {
  if (!getAccessToken) {
    throw new Error('Not signed in as admin')
  }
  const token = await getAccessToken()
  if (!token) {
    throw new Error('No admin access token')
  }
  config.headers.set('Authorization', `Bearer ${token}`)
  return config
})

export const adminMutator = <T>(config: AxiosRequestConfig): Promise<T> =>
  adminAxios.request<T>(config).then((res) => res.data)

export default adminMutator
