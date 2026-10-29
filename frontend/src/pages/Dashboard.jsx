import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../components/AuthContext.jsx'
import { ConnectGmail } from '../components/Layout.jsx'
import { Card, CategoryBadge, EmptyState, ErrorBox, formatDate, PriorityBadge, senderName, Spinner } from '../components/ui.jsx'
import { api } from '../services/api.js'

function Stat({ label, value, tone = 'text-slate-900', to }) {
  const body = (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-bold ${tone}`}>{value ?? '-'}</p>
    </div>
  )
  return to ? <Link to={to}>{body}</Link> : body
}

export default function Dashboard() {
  const { status } = useAuth()
  const [params] = useSearchParams()
  const [stats, setStats] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setStats(await api.dashboard())
    } catch (e) {
      setError(e)
    }
  }, [])

  useEffect(() => {
    if (status?.connected) load()
  }, [status, load])

  if (!status.connected) return <ConnectGmail />

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500">
          Connected to <strong>{status.email}</strong> (real Gmail, read-only). Statistics come from emails you have analyzed.
        </p>
        {params.get('connected') && (
          <p className="mt-2 rounded bg-emerald-50 p-2 text-sm text-emerald-800">Gmail connected successfully.</p>
        )}
      </header>

      <ErrorBox error={error} onRetry={load} />
      {!stats && !error && <Spinner />}

      {stats && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Messages in mailbox" value={stats.mailbox_messages_total?.toLocaleString() ?? 'n/a'} to="/inbox" />
            <Stat label="Emails analyzed" value={stats.analyzed_emails} />
            <Stat label="High priority" value={stats.high_priority_emails} tone="text-red-600" />
            <Stat label="Need a response" value={stats.response_required_emails} tone="text-blue-600" />
            <Stat label="Pending tasks" value={stats.pending_tasks} to="/tasks" />
            <Stat label="Completed tasks" value={stats.completed_tasks} tone="text-emerald-600" to="/tasks" />
            <Stat label="Overdue tasks" value={stats.overdue_tasks} tone={stats.overdue_tasks ? 'text-red-600' : undefined} to="/tasks" />
            <Stat label="Due in 7 days" value={stats.upcoming_deadlines.length} tone="text-amber-600" to="/tasks" />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Recent important emails">
              {stats.recent_important.length === 0 ? (
                <EmptyState title="No high-priority emails analyzed yet">
                  Open an email in the <Link className="text-blue-600 underline" to="/inbox">Inbox</Link> and click Analyze Email.
                </EmptyState>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {stats.recent_important.map((a) => (
                    <li key={a.gmail_message_id} className="py-2">
                      <Link to={`/emails/${a.gmail_message_id}`} className="block hover:bg-slate-50">
                        <div className="flex items-center gap-2">
                          <PriorityBadge priority={a.priority} />
                          <CategoryBadge category={a.category} />
                        </div>
                        <p className="mt-1 text-sm font-medium text-slate-900">{a.subject}</p>
                        <p className="text-xs text-slate-500">{senderName(a.sender)} · {formatDate(a.received_at)}</p>
                        <p className="mt-1 text-sm text-slate-700">{a.summary}</p>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card title="Pending tasks">
              {stats.pending_task_list.length === 0 ? (
                <EmptyState title="No pending tasks">Tasks you create from analyzed emails appear here.</EmptyState>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {stats.pending_task_list.map((t) => (
                    <li key={t.id} className="flex items-start justify-between gap-2 py-2">
                      <div>
                        <p className="text-sm font-medium text-slate-800">{t.title}</p>
                        <p className="text-xs text-slate-500">
                          {t.deadline_text ? `Due: ${t.deadline_text}` : 'No deadline'}
                          {t.is_overdue && <span className="ml-2 font-semibold text-red-600">Overdue</span>}
                        </p>
                      </div>
                      <PriorityBadge priority={t.priority} />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          {stats.upcoming_deadlines.length > 0 && (
            <Card title="Upcoming deadlines (next 7 days)">
              <ul className="space-y-1 text-sm">
                {stats.upcoming_deadlines.map((t) => (
                  <li key={t.id}>
                    <span className="font-medium">{t.title}</span>: {formatDate(t.parsed_deadline)}{' '}
                    <span className="text-slate-500">("{t.deadline_text}")</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

