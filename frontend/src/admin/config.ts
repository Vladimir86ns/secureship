// Admin login (Auth0) configuration — public values from the environment (.env / docker-compose), no secrets.
export const AUTH0_DOMAIN: string = import.meta.env.VITE_AUTH0_DOMAIN ?? ''
export const AUTH0_CLIENT_ID: string = import.meta.env.VITE_AUTH0_CLIENT_ID ?? ''
export const AUTH0_AUDIENCE: string = import.meta.env.VITE_AUTH0_AUDIENCE ?? ''

export const ADMIN_PATH = '/admin'

// Must match the Auth0 application's Allowed Callback / Logout URLs exactly — they are registered WITH the
// trailing slash ("http://localhost:5173/"), so window.location.origin alone would not match.
export const AUTH0_REDIRECT_URI = `${window.location.origin}/`
export const AUTH0_LOGOUT_RETURN_TO = `${window.location.origin}/`

export const AUTH0_CONFIGURED = Boolean(AUTH0_DOMAIN && AUTH0_CLIENT_ID && AUTH0_AUDIENCE)
