import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../components/AuthContext.jsx'
import { ConnectGmail } from '../components/Layout.jsx'
import {
  Button,
  CATEGORIES,
  CategoryBadge,
  EmptyState,
  ErrorBox,
  formatDate,
  PRIORITIES,
  PriorityBadge,
  senderName,
  Spinner,
} from '../components/ui.jsx'
import { api } from '../services/api.js'

const PAGE_SIZE = 15

export default function Inbox() {
  const { status } = useAuth()
  const [emails, setEmails] = useState([])
  const [nextPage, setNextPage] = useState(null)
  const [estimate, setEstimate] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [searchInput, setSearchInput] = useState('')
  const [query, setQuery] = useState('')
  const [label, setLabel] = useState('INBOX')
  const [category, setCategory] = useState('')
  const [priority, setPriority] = useState('')

  const load = useCallback(
    async (pageToken = null) => {
      setLoading(true)
      setError(null)
      try {
        const data = await api.listEmails({ q: query, label, page_token: pageToken, max_results: PAGE_SIZE })
        setEmails((prev) => (pageToken ? [...prev, ...data.emails] : data.emails))
        setNextPage(data.next_page_token)
        setEstimate(data.result_size_estimate)
      } catch (e) {
        setError(e)
      } finally {
        setLoading(false)
      }
    },
    [query, label],
  )

  useEffect(() => {
    if (status?.connected) load()
  }, [status, load])

  if (!status.connected) return <ConnectGmail />

  const visible = emails.filter(
    (e) => (!category || e.category === category) && (!priority || e.priority === priority),
  )

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Inbox</h1>
          <p className="text-sm text-slate-500">
            <span className="mr-1 rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-semibold text-emerald-800">Live Gmail</span>
            Showing {emails.length} fetched message{emails.length === 1 ? '' : 's'} (Gmail estimates about {estimate}).
          </p>
        </div>
        <Button variant="secondary" onClick={() => load()} disabled={loading}>Refresh</Button>
      </header>

      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setQuery(searchInput.trim())
        }}
      >
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder='Search Gmail, e.g. "report" or from:prof@uni.edu'
          className="min-w-60 flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
        <Button type="submit">Search</Button>
        <select value={label} onChange={(e) => setLabel(e.target.value)} className="rounded-lg border border-slate-300 px-2 text-sm">
          <option value="INBOX">Inbox</option>
          <option value="UNREAD">Unread</option>
          <option value="STARRED">Starred</option>
          <option value="IMPORTANT">Important</option>
          <option value="ALL">All mail</option>
        </select>
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="rounded-lg border border-slate-300 px-2 text-sm">
          <option value="">All categories</option>
          {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
        </select>
        <select value={priority} onChange={(e) => setPriority(e.target.value)} className="rounded-lg border border-slate-300 px-2 text-sm">
          <option value="">All priorities</option>
          {PRIORITIES.map((p) => <option key={p}>{p}</option>)}
        </select>
      </form>
      {(category || priority) && (
        <p className="text-xs text-slate-500">
          Category and priority filters apply to the messages loaded so far, and only analyzed emails have a category.
        </p>
      )}

      <ErrorBox error={error} onRetry={() => load()} />

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {visible.length === 0 && !loading ? (
          <div className="p-4">
            <EmptyState title="No emails to show">
              {emails.length ? 'No loaded emails match these filters.' : 'Gmail returned no messages for this view.'}
            </EmptyState>
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {visible.map((e) => (
              <li key={e.id}>
                <Link to={`/emails/${e.id}`} className="flex flex-col gap-1 px-4 py-3 hover:bg-slate-50 sm:flex-row sm:items-center">
                  <div className="flex w-full min-w-0 flex-col sm:w-56 sm:shrink-0">
                    <span className={`truncate text-sm ${e.unread ? 'font-bold text-slate-900' : 'text-slate-700'}`}>
                      {e.unread && <span className="mr-1 inline-block h-2 w-2 rounded-full bg-blue-600" />}
                      {senderName(e.sender)}
                    </span>
                    <span className="text-xs text-slate-400">{formatDate(e.received_at)}</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className={`truncate text-sm ${e.unread ? 'font-semibold' : ''}`}>{e.subject}</p>
                    <p className="truncate text-xs text-slate-500">{e.snippet}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <CategoryBadge category={e.category} />
                    <PriorityBadge priority={e.priority} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
        {loading && <div className="p-4"><Spinner label="Fetching from Gmail..." /></div>}
      </div>

      {nextPage && !loading && (
        <div className="text-center">
          <Button variant="secondary" onClick={() => load(nextPage)}>Load more</Button>
        </div>
      )}
    </div>
  )
}
