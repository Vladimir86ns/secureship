import { useAuth0 } from '@auth0/auth0-react'
import { useEffect, useState, type ReactNode } from 'react'
import { setAdminTokenGetter } from '../api/adminMutator'
import { ADMIN_PATH, AUTH0_AUDIENCE, AUTH0_CONFIGURED, AUTH0_LOGOUT_RETURN_TO } from './config'
import { CustomersPage } from './CustomersPage'
import { PackagesPage } from './PackagesPage'
import { ShipmentsPage } from './ShipmentsPage'
import './Admin.css'

// Admin panel (Epic E). Hiding this page is NOT the protection — every /admin/* API call is checked by the backend.
export function AdminApp() {
  const { isLoading, isAuthenticated, error, user, loginWithRedirect, logout, getAccessTokenSilently } = useAuth0()
  const [tokenReady, setTokenReady] = useState(false)

  // Give the admin API client a way to get the access token (Bearer). The Auth0 SDK keeps the token in memory and
  // renews it; it is never copied anywhere else. The pages render only after this is registered.
  useEffect(() => {
    if (!isAuthenticated) return
    setAdminTokenGetter(() => getAccessTokenSilently({ authorizationParams: { audience: AUTH0_AUDIENCE } }))
    setTokenReady(true)
    return () => {
      setAdminTokenGetter(null)
      setTokenReady(false)
    }
  }, [isAuthenticated, getAccessTokenSilently])

  if (!AUTH0_CONFIGURED) {
    return (
      <AdminCard>
        <p className="admin-error">
          Admin login is not configured: set VITE_AUTH0_DOMAIN, VITE_AUTH0_CLIENT_ID and VITE_AUTH0_AUDIENCE.
        </p>
      </AdminCard>
    )
  }

  if (isLoading) {
    return (
      <AdminCard>
        <p className="admin-card-loading" aria-live="polite">
          Loading…
        </p>
      </AdminCard>
    )
  }

  const login = () => loginWithRedirect({ appState: { returnTo: ADMIN_PATH } })

  if (!isAuthenticated) {
    return (
      <AdminCard>
        <p className="admin-card-text">Sign in to manage customers, shipments and packages.</p>
        {error && (
          <p className="admin-error" role="alert">
            Login failed: {error.message}
          </p>
        )}
        <button type="button" className="admin-primary admin-card-button" onClick={login}>
          Log in
        </button>
      </AdminCard>
    )
  }

  const logoutAdmin = () => {
    setAdminTokenGetter(null)
    logout({ logoutParams: { returnTo: AUTH0_LOGOUT_RETURN_TO } })
  }

  return (
    <AdminShell
      account={
        <>
          <span className="admin-user">{user?.email ?? user?.name ?? 'Admin'}</span>
          <button type="button" onClick={logoutAdmin}>
            Log out
          </button>
        </>
      }
    >
      {tokenReady ? <AdminPages /> : <p>Loading…</p>}
    </AdminShell>
  )
}

type Tab = 'customers' | 'shipments' | 'packages'

function AdminPages() {
  const [tab, setTab] = useState<Tab>('customers')
  const [customerId, setCustomerId] = useState<string | null>(null)
  const [shipmentId, setShipmentId] = useState<string | null>(null)

  return (
    <>
      <nav className="admin-tabs">
        {(['customers', 'shipments', 'packages'] as const).map((t) => (
          <button key={t} type="button" aria-pressed={tab === t} onClick={() => setTab(t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </nav>
      {tab === 'customers' && (
        <CustomersPage
          onShowShipments={(id) => {
            setCustomerId(id)
            setTab('shipments')
          }}
        />
      )}
      {tab === 'shipments' && (
        <ShipmentsPage
          customerId={customerId}
          onCustomerChange={setCustomerId}
          onShowPackages={(id) => {
            setShipmentId(id)
            setTab('packages')
          }}
        />
      )}
      {tab === 'packages' && <PackagesPage shipmentId={shipmentId} onShipmentChange={setShipmentId} />}
    </>
  )
}

// Centered card for the states before the panel: not configured, loading, signed out.
function AdminCard({ children }: { children: ReactNode }) {
  return (
    <div className="admin admin-card-page">
      <div className="admin-card">
        <h2>SecureShip admin</h2>
        {children}
      </div>
    </div>
  )
}

function AdminShell({ account, children }: { account?: ReactNode; children: ReactNode }) {
  return (
    <div className="admin">
      <header className="admin-header">
        <h2>SecureShip admin</h2>
        <div className="admin-account">{account}</div>
      </header>
      {children}
    </div>
  )
}
