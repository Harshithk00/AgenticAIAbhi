import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '../components/AuthContext.jsx'
import { Button, Card } from '../components/ui.jsx'
import { api } from '../services/api.js'

const AUTH_ERRORS = {
  access_denied: 'You declined the Gmail permission request. Nothing was connected.',
  invalid_state: 'The sign-in response could not be verified (expired or forged request). Please try connecting again.',
  token_exchange_failed: 'Google sign-in failed while exchanging the authorization code. Check the OAuth client settings and try again.',
  scope_not_granted: 'Read-only Gmail access was not granted. Please approve the Gmail permission.',
  gmail_profile_failed: 'Connected to Google, but the Gmail profile could not be read. Is the Gmail API enabled in your Cloud project?',
  missing_code: 'Google did not return an authorization code. Please try again.',
  oauth_error: 'Google returned an error during sign-in. Please try again.',
}

export default function Settings() {
  const { status, refresh } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const authError = params.get('auth_error')

  const disconnect = async () => {
    if (!window.confirm('Disconnect Gmail? Stored Google tokens will be deleted from this app.')) return
    setBusy(true)
    try {
      await api.disconnect()
      await refresh()
      setMessage('Disconnected. The app no longer has access to your Gmail.')
      navigate('/settings', { replace: true })
    } catch (e) {
      setMessage(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Settings / About</h1>
      {authError && <p className="rounded bg-red-50 p-3 text-sm text-red-800">{AUTH_ERRORS[authError] || 'Sign-in failed.'}</p>}
      {message && <p className="rounded bg-slate-100 p-3 text-sm text-slate-700">{message}</p>}

      <Card title="Gmail connection">
        {status.connected ? (
          <div className="space-y-2 text-sm">
            <p><span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />Connected as <strong>{status.email}</strong></p>
            <p className="text-slate-500">Permission: {status.scopes.join(', ')} (read-only)</p>
            <Button variant="danger" onClick={disconnect} disabled={busy}>Disconnect Gmail</Button>
          </div>
        ) : (
          <div className="space-y-2 text-sm">
            <p>Not connected.</p>
            {status.oauth_configured ? (
              <a href={api.connectUrl()} className="inline-block rounded-lg bg-blue-600 px-3 py-1.5 font-semibold text-white hover:bg-blue-700">
                Connect Gmail
              </a>
            ) : (
              <p className="text-amber-700">Google OAuth is not configured on the server (see README).</p>
            )}
          </div>
        )}
      </Card>

      <Card title="AI configuration">
        <ul className="space-y-1 text-sm">
          <li>Gemini API: {status.gemini_configured ? <span className="text-emerald-700">configured</span> : <span className="text-red-700">not configured (set GEMINI_API_KEY)</span>}</li>
          <li>Automatic task creation: <strong>{status.auto_create_tasks ? 'on' : 'off'}</strong>{' '}
            <span className="text-slate-500">(AUTO_CREATE_TASKS in backend/.env; when off, tasks are created only when you click Create Task)</span>
          </li>
        </ul>
      </Card>

      <Card title="How the AI processes your email">
        <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-700">
          <li>Emails are fetched from Gmail with read-only permission, only when you open the inbox or an email.</li>
          <li>When you click <strong>Analyze Email</strong>, a LangGraph agent loads the message, applies simple rules, and sends the email text to Google Gemini for analysis.</li>
          <li>Gemini's answer is validated (category, priority, summary, task, deadline). Python rules then adjust clear cases and choose the recommended action.</li>
          <li>Only the analysis is stored in the local SQLite database: sender, subject, date, summary, category, priority, task and deadline. Email bodies are not stored.</li>
          <li>Email text is treated as untrusted data: instructions inside an email are never followed.</li>
          <li>Reply suggestions are generated on request and never sent. This app has no permission to send, delete or modify email.</li>
        </ol>
      </Card>
    </div>
  )
}
