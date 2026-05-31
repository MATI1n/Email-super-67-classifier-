// Тонкий клиент REST API MailPilot.
const json = async (r) => {
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${r.status}`)
  }
  return r.json()
}

const post = (url, body) =>
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  }).then(json)

export const api = {
  health: () => fetch('/api/health').then(json),
  folders: () => fetch('/api/folders').then(json),
  stats: () => fetch('/api/stats').then(json),
  emails: (params = {}) =>
    fetch('/api/emails?' + new URLSearchParams(params)).then(json),
  email: (id) => fetch(`/api/emails/${id}`).then(json),
  search: (q) => fetch('/api/search?' + new URLSearchParams({ q })).then(json),
  summarize: (id, scope = 'email') => post(`/api/emails/${id}/summarize`, { scope }),
  action: (id, action) => post(`/api/emails/${id}/action`, { action }),
  reset: () => post('/api/reset'),
}
