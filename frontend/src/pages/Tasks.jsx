import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../components/AuthContext.jsx'
import { ConnectGmail } from '../components/Layout.jsx'
import { Button, EmptyState, ErrorBox, formatDate, PriorityBadge, Spinner } from '../components/ui.jsx'
import { api } from '../services/api.js'

const FILTERS = [
  ['', 'All'],
  ['Pending', 'Pending'],
  ['Completed', 'Completed'],
]

export default function Tasks() {
  const { status } = useAuth()
  const [filter, setFilter] = useState('Pending')
  const [tasks, setTasks] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setTasks(await api.listTasks(filter || undefined))
    } catch (e) {
      setError(e)
    }
  }, [filter])

  useEffect(() => {
    if (status?.connected) load()
  }, [status, load])

  if (!status.connected) return <ConnectGmail />

  const toggle = async (task) => {
    setBusy(task.id)
    try {
      await api.updateTask(task.id, task.status === 'Pending' ? 'Completed' : 'Pending')
      await load()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Tasks</h1>
        <p className="text-sm text-slate-500">Tasks created from your analyzed emails, saved in the local SQLite database.</p>
      </header>

      <div className="flex gap-2">
        {FILTERS.map(([value, label]) => (
          <Button key={label} variant={filter === value ? 'primary' : 'secondary'} onClick={() => setFilter(value)}>
            {label}
          </Button>
        ))}
      </div>

      <ErrorBox error={error} onRetry={load} />
      {tasks === null && !error && <Spinner />}
      {tasks?.length === 0 && (
        <EmptyState title="No tasks here">Open an email, click Analyze Email, then Create Task.</EmptyState>
      )}

      {tasks?.length > 0 && (
        <ul className="space-y-2">
          {tasks.map((t) => (
            <li key={t.id} className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <p className={`font-medium ${t.status === 'Completed' ? 'text-slate-400 line-through' : 'text-slate-900'}`}>{t.title}</p>
                <p className="text-xs text-slate-500">
                  {t.deadline_text ? <>Deadline: "{t.deadline_text}"</> : 'No deadline'}
                  {t.parsed_deadline && <> · {formatDate(t.parsed_deadline)}</>}
                  {' · '}created {formatDate(t.created_at)}
                </p>
                <div className="mt-1 flex gap-2 text-xs">
                  {t.is_overdue && <span className="rounded bg-red-100 px-1.5 py-0.5 font-semibold text-red-700">Overdue</span>}
                  {t.is_upcoming && <span className="rounded bg-amber-100 px-1.5 py-0.5 font-semibold text-amber-700">Due within 7 days</span>}
                  <Link to={`/emails/${t.gmail_message_id}`} className="text-blue-600 hover:underline">Open source email</Link>
                </div>
              </div>
              <PriorityBadge priority={t.priority} />
              <Button variant={t.status === 'Pending' ? 'primary' : 'secondary'} disabled={busy === t.id} onClick={() => toggle(t)}>
                {t.status === 'Pending' ? 'Mark completed' : 'Mark pending'}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
