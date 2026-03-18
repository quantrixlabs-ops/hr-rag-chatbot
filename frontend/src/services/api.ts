const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Global callback for handling auth expiration — set by App component
let onAuthExpired: (() => void) | null = null
export function setAuthExpiredHandler(handler: () => void) {
  onAuthExpired = handler
}

function headers(token: string | null): HeadersInit {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

async function handleResponse(res: Response) {
  if (res.status === 401) {
    // Token expired or invalid — trigger logout
    if (onAuthExpired) onAuthExpired()
    throw new Error('Session expired. Please log in again.')
  }
  return res
}

// ── Auth ────────────────────────────────────────────────────────────────────
export async function login(username: string, password: string) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new Error('Invalid credentials')
  return res.json()
}

export interface RegisterData {
  username: string
  password: string
  full_name?: string
  email?: string
  phone?: string
  role?: string
}

export async function register(data: RegisterData) {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Registration failed')
  }
  return res.json()
}

export async function logout(token: string, refreshToken?: string | null) {
  await fetch(`${BASE}/auth/logout`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken || null }),
  })
}

export async function refreshAccessToken(refreshToken: string) {
  const res = await fetch(`${BASE}/auth/refresh`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!res.ok) throw new Error('Refresh failed')
  return res.json()
}

// ── Chat ────────────────────────────────────────────────────────────────────
export async function sendMessage(token: string, query: string, sessionId?: string | null) {
  const res = await handleResponse(await fetch(`${BASE}/chat/query`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ query, session_id: sessionId, include_sources: true }),
  }))
  if (!res.ok) throw new Error('Chat request failed')
  return res.json()
}

export async function getSessions(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/chat/sessions`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch sessions')
  return res.json()
}

export async function getSessionHistory(token: string, sessionId: string) {
  const res = await handleResponse(await fetch(`${BASE}/chat/sessions/${sessionId}/history`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch history')
  return res.json()
}

export async function sendFeedback(token: string, sessionId: string, query: string, answer: string, rating: string) {
  await handleResponse(await fetch(`${BASE}/chat/feedback`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ session_id: sessionId, query, answer, rating }),
  }))
}

// ── Documents ───────────────────────────────────────────────────────────────
export async function uploadDocument(token: string, file: File, title: string, category: string, accessRoles: string[]) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('title', title)
  fd.append('category', category)
  fd.append('access_roles', JSON.stringify(accessRoles))
  const res = await handleResponse(await fetch(`${BASE}/documents/upload`, {
    method: 'POST', headers: { 'Authorization': `Bearer ${token}` }, body: fd,
  }))
  if (!res.ok) throw new Error('Upload failed')
  return res.json()
}

export async function getDocumentContent(token: string, documentId: string) {
  const res = await handleResponse(await fetch(`${BASE}/documents/${documentId}/content`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch document content')
  return res.json()
}

export async function getDocuments(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/documents`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch documents')
  return res.json()
}

export async function deleteDocument(token: string, documentId: string) {
  const res = await handleResponse(await fetch(`${BASE}/documents/${documentId}`, {
    method: 'DELETE', headers: headers(token),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Delete failed')
  }
  return res.json()
}

export async function batchDeleteDocuments(token: string, documentIds: string[]) {
  const res = await handleResponse(await fetch(`${BASE}/documents/batch-delete`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ document_ids: documentIds }),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Batch delete failed')
  }
  return res.json()
}

export async function reindexDocument(token: string, documentId?: string) {
  const res = await handleResponse(await fetch(`${BASE}/documents/reindex`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify(documentId ? { document_id: documentId } : {}),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Reindex failed')
  }
  return res.json()
}

// ── Admin ───────────────────────────────────────────────────────────────────
export async function getMetrics(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/admin/metrics`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch metrics')
  return res.json()
}

export async function getFailedQueries(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/admin/failed-queries`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch failed queries')
  return res.json()
}

export async function getSecurityEvents(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/admin/security-events`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch security events')
  return res.json()
}

// ── Streaming Chat ─────────────────────────────────────────────────────────
export interface StreamDoneData {
  full_text: string
  session_id?: string
  citations?: { source: string; page: number | null; excerpt: string }[]
  confidence?: number
  faithfulness_score?: number
  suggested_questions?: string[]
}

export async function sendMessageStream(
  token: string, query: string, sessionId: string | null | undefined,
  onToken: (token: string) => void,
  onDone: (data: StreamDoneData) => void,
  onError: (error: string) => void,
) {
  try {
    const res = await fetch(`${BASE}/chat/query/stream`, {
      method: 'POST', headers: headers(token),
      body: JSON.stringify({ query, session_id: sessionId, include_sources: true }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Stream failed' }))
      onError(err.detail || 'Stream request failed')
      return
    }
    const reader = res.body?.getReader()
    if (!reader) { onError('No stream reader'); return }
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6))
          if (data.token) onToken(data.token)
          if (data.done) {
            onDone({
              full_text: data.full_text || '',
              session_id: data.session_id,
              citations: data.citations,
              confidence: data.confidence,
              faithfulness_score: data.faithfulness_score,
              suggested_questions: data.suggested_questions,
            })
          }
        }
      }
    }
  } catch (e: any) {
    onError(e.message || 'Streaming failed')
  }
}

// ── Health ──────────────────────────────────────────────────────────────────
export async function healthCheck() {
  const res = await fetch(`${BASE}/health`)
  return res.json()
}
