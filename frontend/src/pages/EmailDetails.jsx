import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../components/AuthContext.jsx'
import { ConnectGmail } from '../components/Layout.jsx'
import {
  ACTION_LABELS,
  Button,
  Card,
  CategoryBadge,
  ErrorBox,
  formatDate,
  PriorityBadge,
  Spinner,
} from '../components/ui.jsx'
import { api } from '../services/api.js'

function YesNo({ value }) {
  return <span className={value ? 'font-semibold text-blue-700' : 'text-slate-500'}>{value ? 'Yes' : 'No'}</span>
}

function WorkflowSteps({ steps }) {
  if (!steps?.length) return null
  const icon = { ok: '✓', skipped: '-', error: '✗' }
  const color = { ok: 'text-emerald-600', skipped: 'text-slate-400', error: 'text-red-600' }
  return (
    <details className="mt-3 text-xs" open>
      <summary className="cursor-pointer font-semibold text-slate-600">Agent workflow steps (LangGraph)</summary>
      <ol className="mt-2 space-y-1">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-2">
            <span className={`font-bold ${color[s.status]}`}>{icon[s.status]}</span>
            <span className="font-mono text-slate-700">{s.node}</span>
            <span className="text-slate-500">{s.detail}</span>
          </li>
        ))}
      </ol>
    </details>
  )
}

function ReplyPanel({ messageId }) {
  const [tone, setTone] = useState('professional')
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [copied, setCopied] = useState(false)

  const generate = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.generateReply(messageId, { tone })
      setText(data.reply)
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setError({ message: 'Clipboard access was blocked by the browser. Select the text and copy it manually.' })
    }
  }

  return (
    <Card title="Reply suggestion">
      <div className="flex flex-wrap items-center gap-2">
        <select value={tone} onChange={(e) => setTone(e.target.value)} className="rounded-lg border border-slate-300 px-2 py-1.5 text-sm">
          <option value="professional">Professional</option>
          <option value="friendly">Friendly</option>
          <option value="brief">Brief</option>
        </select>
        <Button onClick={generate} disabled={loading}>{text ? 'Regenerate' : 'Generate Reply'}</Button>
        {text && <Button variant="secondary" onClick={copy}>{copied ? 'Copied!' : 'Copy to clipboard'}</Button>}
      </div>
      {loading && <div className="mt-3"><Spinner label="Gemini is drafting a reply..." /></div>}
      <div className="mt-3"><ErrorBox error={error} onRetry={generate} /></div>
      {text && (
        <>
          <p className="mt-3 rounded bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800">
            AI-generated suggestion. Review and edit it before sending it yourself from Gmail. This app never sends email.
          </p>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={10}
            className="mt-2 w-full rounded-lg border border-slate-300 p-3 text-sm"
          />
        </>
      )}
    </Card>
  )
}

export default function EmailDetails() {
  const { id } = useParams()
  const { status } = useAuth()
  const [email, setEmail] = useState(null)
  const [error, setError] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState(null)
  const [steps, setSteps] = useState([])
  const [taskMessage, setTaskMessage] = useState(null)
  const [taskError, setTaskError] = useState(null)
  const [creatingTask, setCreatingTask] = useState(false)

  const load = useCallback(async () => {
    setError(null)
    try {
      setEmail(await api.getEmail(id))
    } catch (e) {
      setError(e)
    }
  }, [id])

  useEffect(() => {
    if (status?.connected) load()
  }, [status, load])

  if (!status.connected) return <ConnectGmail />
  if (error) return <ErrorBox error={error} onRetry={load} />
  if (!email) return <Spinner label="Loading email from Gmail..." />

  const analysis = email.analysis?.analysis_status === 'completed' ? email.analysis : null

  const analyze = async () => {
    setAnalyzing(true)
    setAnalysisError(null)
    setSteps([])
    try {
      const result = await api.analyzeEmail(id)
      setSteps(result.steps)
      if (result.auto_created_task) setTaskMessage('Task created automatically (AUTO_CREATE_TASKS is on).')
      await load()
    } catch (e) {
      setAnalysisError(e)
      setSteps(e.steps || [])
    } finally {
      setAnalyzing(false)
    }
  }

  const createTask = async () => {
    setCreatingTask(true)
    setTaskError(null)
    try {
      const result = await api.createTask({
        gmail_message_id: email.id,
        title: analysis.extracted_task,
        deadline_text: analysis.deadline_text,
        parsed_deadline: analysis.parsed_deadline,
        priority: analysis.priority,
      })
      setTaskMessage(result.created ? 'Task created.' : 'This task already exists, so no duplicate was created.')
      await load()
    } catch (e) {
      setTaskError(e)
    } finally {
      setCreatingTask(false)
    }
  }

  return (
    <div className="space-y-4">
      <Link to="/inbox" className="text-sm text-blue-600 hover:underline">← Back to inbox</Link>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-slate-900">{email.subject}</h1>
            <p className="mt-1 text-sm text-slate-600">From: {email.sender}</p>
            <p className="text-sm text-slate-600">To: {email.to}</p>
            <p className="text-xs text-slate-400">{formatDate(email.received_at)}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={analyze} disabled={analyzing}>{analysis ? 'Re-analyze' : 'Analyze Email'}</Button>
            <a href={email.gmail_url} target="_blank" rel="noreferrer noopener"
               className="rounded-lg px-3 py-1.5 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50">
              Open in Gmail
            </a>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          <Card title="Original message">
            {email.body_was_html && (
              <p className="mb-2 text-xs text-slate-500">HTML email shown as plain text for safety (scripts and remote images removed).</p>
            )}
            <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words font-sans text-sm text-slate-800">
              {email.body_text || '(This message has no text content.)'}
            </pre>
          </Card>
          <ReplyPanel messageId={email.id} />
        </div>

        <div className="space-y-4 lg:col-span-2">
          <Card title="AI analysis">
            {analyzing && <Spinner label="Agent is analyzing this email..." />}
            <ErrorBox error={analysisError} onRetry={analyze} />
            {!analysis && !analyzing && !analysisError && (
              <p className="text-sm text-slate-500">Not analyzed yet. Click <strong>Analyze Email</strong> to run the AI agent.</p>
            )}
            {analysis && (
              <div className="space-y-3 text-sm">
                <div className="flex flex-wrap gap-2">
                  <CategoryBadge category={analysis.category} />
                  <PriorityBadge priority={analysis.priority} />
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase text-slate-500">Summary</p>
                  <p className="text-slate-800">{analysis.summary}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase text-slate-500">Why this priority</p>
                  <p className="text-slate-700">{analysis.priority_reason}</p>
                </div>
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
                  <dt className="text-slate-500">Action required</dt><dd><YesNo value={analysis.action_required} /></dd>
                  <dt className="text-slate-500">Response required</dt><dd><YesNo value={analysis.response_required} /></dd>
                  <dt className="text-slate-500">Task</dt><dd>{analysis.extracted_task || '-'}</dd>
                  <dt className="text-slate-500">Deadline</dt>
                  <dd>
                    {analysis.deadline_text ? `"${analysis.deadline_text}"` : '-'}
                    {analysis.parsed_deadline && <span className="block text-xs text-slate-500">{formatDate(analysis.parsed_deadline)}</span>}
                  </dd>
                  {analysis.meeting_details && (<><dt className="text-slate-500">Meeting</dt><dd>{analysis.meeting_details}</dd></>)}
                </dl>
                <div className="rounded-lg bg-blue-50 p-3">
                  <p className="text-xs font-semibold uppercase text-blue-700">Recommended next action</p>
                  <p className="font-medium text-blue-900">{ACTION_LABELS[analysis.recommended_action] || analysis.recommended_action}</p>
                  <p className="text-blue-800">{analysis.recommended_action_reason}</p>
                </div>
                {analysis.extracted_task ? (
                  <div>
                    <Button onClick={createTask} disabled={creatingTask || email.task_ids.length > 0}>
                      {email.task_ids.length > 0 ? 'Task created' : 'Create Task'}
                    </Button>
                    {email.task_ids.length > 0 && (
                      <Link to="/tasks" className="ml-2 text-xs text-blue-600 hover:underline">View tasks</Link>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">No task was found in this email, so there is nothing to create.</p>
                )}
                {taskMessage && <p className="text-xs text-emerald-700">{taskMessage}</p>}
                <ErrorBox error={taskError} onRetry={createTask} />
                <p className="text-xs text-slate-400">Analyzed {formatDate(analysis.analyzed_at)} with Gemini. AI output can be wrong; check important details.</p>
              </div>
            )}
            <WorkflowSteps steps={steps} />
          </Card>
        </div>
      </div>
    </div>
  )
}
