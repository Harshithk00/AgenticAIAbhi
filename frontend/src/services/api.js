// All calls go to our own FastAPI backend. The browser never sees Google tokens or the Gemini key.
const BASE = import.meta.env.VITE_API_BASE_URL || ''

export class ApiError extends Error {
  constructor(status, detail) {
    const info = typeof detail === 'object' && detail !== null ? detail : { message: String(detail || '') }
    super(info.message || `Request failed (${status})`)
    this.status = status
    this.code = info.code
    this.retryable = info.retryable
    this.steps = info.steps || []
  }
}

async function request(path, { method = 'GET', body, params } = {}) {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v)
  })
  let response
  try {
    response = await fetch(url, {
      method,
      credentials: 'include',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, { code: 'network', message: 'Cannot reach the backend. Is it running on port 8000?' })
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    let detail = data?.detail
    if (Array.isArray(detail)) detail = { code: 'validation', message: detail.map((d) => d.msg).join('; ') }
    throw new ApiError(response.status, detail || { message: response.statusText })
  }
  return data
}

export const api = {
  connectUrl: () => `${BASE}/api/auth/google`,
  authStatus: () => request('/api/auth/status'),
  disconnect: () => request('/api/auth/disconnect', { method: 'POST' }),
  listEmails: (params) => request('/api/emails', { params }),
  getEmail: (id) => request(`/api/emails/${encodeURIComponent(id)}`),
  analyzeEmail: (id) => request(`/api/emails/${encodeURIComponent(id)}/analyze`, { method: 'POST' }),
  generateReply: (id, body) => request(`/api/emails/${encodeURIComponent(id)}/generate-reply`, { method: 'POST', body }),
  listTasks: (status) => request('/api/tasks', { params: { status } }),
  createTask: (body) => request('/api/tasks', { method: 'POST', body }),
  updateTask: (id, status) => request(`/api/tasks/${id}`, { method: 'PATCH', body: { status } }),
  dashboard: () => request('/api/dashboard/stats'),
}
