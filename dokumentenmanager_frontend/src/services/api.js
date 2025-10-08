const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:5173'

function authHeaders() {
  const token = localStorage.getItem('token')
  return token ? { 'Authorization': `Bearer ${token}` } : {}
}

export async function register(email, password) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  })
  if (!res.ok) throw await res.json()
  return res.json()
}

export async function login(email, password) {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  })
  if (!res.ok) throw await res.json()
  const data = await res.json()
  localStorage.setItem('token', data.token)
  localStorage.setItem('user', JSON.stringify(data.user))
  return data
}

export function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
}

export async function me() {
  const res = await fetch(`${API_BASE}/users/me`, { headers: { ...authHeaders() } })
  if (!res.ok) throw await res.json()
  return res.json()
}

export async function listFiles(q = '', limit = 50, offset = 0) {
  const url = new URL(`${API_BASE}/files`)
  if (q) url.searchParams.set('q', q)
  url.searchParams.set('limit', limit)
  url.searchParams.set('offset', offset)
  const res = await fetch(url, { headers: { ...authHeaders() } })
  if (!res.ok) throw await res.json()
  return res.json()
}

export async function uploadFile(file) {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API_BASE}/files/upload`, {
    method: 'POST',
    headers: { ...authHeaders() },
    body: fd
  })
  if (!res.ok) throw await res.json()
  return res.json()
}

export async function deleteFile(id) {
  const res = await fetch(`${API_BASE}/files/${id}`, {
    method: 'DELETE',
    headers: { ...authHeaders() }
  })
  if (!res.ok) throw await res.json()
  return {}
}
