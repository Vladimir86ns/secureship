import { Auth0Provider, type AppState } from '@auth0/auth0-react'
import { AdminApp } from './AdminApp'
import { ADMIN_PATH, AUTH0_AUDIENCE, AUTH0_CLIENT_ID, AUTH0_DOMAIN, AUTH0_REDIRECT_URI } from './config'

// Loaded only on /admin (lazy chunk in main.tsx): the chat never loads Auth0 (two separate identity systems, Epic E4).
export default function AdminRoot({ onNavigate }: { onNavigate: (path: string) => void }) {
  // After login: replace "/?code=…&state=…" with the admin URL WITHOUT reloading the page — the access token is
  // kept in memory only, a reload would lose it.
  const onRedirectCallback = (appState?: AppState) => {
    const target = appState?.returnTo ?? ADMIN_PATH
    window.history.replaceState(null, '', target)
    onNavigate(target)
  }

  return (
    <Auth0Provider
      domain={AUTH0_DOMAIN}
      clientId={AUTH0_CLIENT_ID}
      authorizationParams={{ redirect_uri: AUTH0_REDIRECT_URI, audience: AUTH0_AUDIENCE }}
      onRedirectCallback={onRedirectCallback}
    >
      <AdminApp />
    </Auth0Provider>
  )
}
