// Small shared UI pieces.
import { api } from '../services/api.js'

const PRIORITY_STYLES = {
  High: 'bg-red-100 text-red-800 ring-red-200',
  Medium: 'bg-amber-100 text-amber-800 ring-amber-200',
  Low: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
}
const CATEGORY_STYLES = {
  Academic: 'bg-indigo-100 text-indigo-800',
  Work: 'bg-sky-100 text-sky-800',
  Personal: 'bg-pink-100 text-pink-800',
  Meeting: 'bg-violet-100 text-violet-800',
  Finance: 'bg-teal-100 text-teal-800',
  Promotion: 'bg-orange-100 text-orange-800',
  Other: 'bg-slate-200 text-slate-700',
}

export const CATEGORIES = Object.keys(CATEGORY_STYLES)
export const PRIORITIES = ['High', 'Medium', 'Low']

export const ACTION_LABELS = {
  create_task_and_reply: 'Create a task and reply',
  create_task: 'Create a task / reminder',
  reply: 'Reply to the sender',
  review_meeting: 'Review the meeting details',
  read_later: 'Read later',
  no_action: 'No action needed',
}

export function PriorityBadge({ priority }) {
  if (!priority) return <span className="text-xs text-slate-400">Not analyzed</span>
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${PRIORITY_STYLES[priority]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {priority}
    </span>
  )
}

export function CategoryBadge({ category }) {
  if (!category) return null
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${CATEGORY_STYLES[category] || CATEGORY_STYLES.Other}`}>{category}</span>
}

export function Spinner({ label = 'Loading...' }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" />
      {label}
    </div>
  )
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <p className="font-medium">{error.message}</p>
      {error.code === 'gmail_reauth_required' && (
        <a href={api.connectUrl()} className="mt-1 inline-block font-semibold underline">Reconnect Gmail</a>
      )}
      {onRetry && error.retryable !== false && (
        <button onClick={onRetry} className="mt-2 block rounded bg-red-600 px-3 py-1 text-xs font-semibold text-white hover:bg-red-700">
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, children }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="font-medium text-slate-700">{title}</p>
      {children && <div className="mt-1 text-sm text-slate-500">{children}</div>}
    </div>
  )
}

export function Card({ title, children, actions }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="font-semibold text-slate-800">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

export function Button({ variant = 'primary', className = '', ...props }) {
  const styles = {
    primary: 'bg-blue-600 text-white hover:bg-blue-700 disabled:bg-blue-300',
    secondary: 'bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 disabled:text-slate-400',
    danger: 'bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300',
  }
  return (
    <button
      className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition disabled:cursor-not-allowed ${styles[variant]} ${className}`}
      {...props}
    />
  )
}

export function formatDate(value) {
  if (!value) return ''
  return new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function senderName(sender = '') {
  const match = sender.match(/^\s*"?([^"<]+?)"?\s*<.+>$/)
  return match ? match[1] : sender
}
