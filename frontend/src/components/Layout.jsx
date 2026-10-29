import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../services/api.js'
import { useAuth } from './AuthContext.jsx'
import { Spinner } from './ui.jsx'

const NAV = [
  ['/', 'Dashboard'],
  ['/inbox', 'Inbox'],
  ['/tasks', 'Tasks'],
  ['/settings', 'Settings / About'],
]

export function ConnectGmail() {
  const { status } = useAuth()
  return (
    <div className="mx-auto mt-10 max-w-lg rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
      <h2 className="text-xl font-bold text-slate-800">Connect your Gmail account</h2>
      <p className="mt-2 text-sm text-slate-600">
        You'll be sent to Google to sign in and approve <strong>read-only</strong> access. This app never sees your
        password and cannot send, delete or change your emails.
      </p>
      {status && !status.oauth_configured ? (
        <p className="mt-4 rounded bg-amber-50 p-3 text-sm text-amber-800">
          Google OAuth is not configured on the server. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env
          (see README).
        </p>
      ) : (
        <a
          href={api.connectUrl()}
          className="mt-5 inline-block rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Connect Gmail
        </a>
      )}
    </div>
  )
}

export default function Layout() {
  const { status, error } = useAuth()
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="bg-slate-900 text-slate-100 md:w-60 md:shrink-0">
        <div className="px-5 py-5">
          <p className="text-lg font-bold">Smart Email Agent</p>
          <p className="text-xs text-slate-400">Agentic AI for Gmail</p>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col">
          {NAV.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium ${isActive ? 'bg-blue-600 text-white' : 'text-slate-300 hover:bg-slate-800'}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden px-5 py-4 text-xs text-slate-400 md:block">
          {status?.connected ? (
            <>
              <span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-400" />
              {status.email}
            </>
          ) : (
            <>
              <span className="mr-1 inline-block h-2 w-2 rounded-full bg-slate-500" />
              Gmail not connected
            </>
          )}
        </div>
      </aside>
      <main className="flex-1 p-4 md:p-8">
        {error ? (
          <p className="rounded bg-red-50 p-3 text-sm text-red-800">{error.message}</p>
        ) : status === null ? (
          <Spinner />
        ) : (
          <Outlet />
        )}
      </main>
    </div>
  )
}
