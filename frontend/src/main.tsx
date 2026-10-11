import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode, Suspense, lazy, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { ADMIN_PATH } from './admin/config.ts'

// Auth0Provider + the admin panel: a separate chunk, downloaded only on /admin.
const AdminRoot = lazy(() => import('./admin/AdminRoot.tsx'))

const queryClient = new QueryClient()

function isAdminPath(path: string): boolean {
  return path === ADMIN_PATH || path.startsWith(`${ADMIN_PATH}/`)
}

// Auth0 sends the admin back to the only allowed callback URL, "/?code=…&state=…" (or "?error=…&state=…").
function isAuth0Callback(): boolean {
  const params = new URLSearchParams(window.location.search)
  return params.has('state') && (params.has('code') || params.has('error'))
}

// The chat (/) and the admin panel (/admin) are two separate apps on one page, chosen by path — no router.
function Root() {
  const [path, setPath] = useState(() => (isAuth0Callback() ? ADMIN_PATH : window.location.pathname))

  useEffect(() => {
    const onPopState = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  if (!isAdminPath(path)) return <App />

  return (
    <Suspense fallback={<p>Loading…</p>}>
      <AdminRoot onNavigate={setPath} />
    </Suspense>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Root />
    </QueryClientProvider>
  </StrictMode>,
)
