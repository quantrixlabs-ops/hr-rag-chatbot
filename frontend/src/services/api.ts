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
  secret_question?: string
  secret_answer?: string
}

// ── Forgot Password ──────────────────────────────────────────────────────────
export async function forgotPassword(username: string) {
  const res = await fetch(`${BASE}/auth/forgot-password`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

export async function verifySecretAnswer(username: string, secretAnswer: string) {
  const res = await fetch(`${BASE}/auth/verify-secret`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, secret_answer: secretAnswer }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Verification failed')
  }
  return res.json()
}

export async function resetPassword(username: string, secretAnswer: string, newPassword: string) {
  const res = await fetch(`${BASE}/auth/reset-password`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, secret_answer: secretAnswer, new_password: newPassword }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Password reset failed')
  }
  return res.json()
}

export async function changePassword(token: string, currentPassword: string, newPassword: string) {
  const res = await handleResponse(await fetch(`${BASE}/auth/change-password`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Password change failed')
  }
  return res.json()
}

// ── Email OTP Reset (Phase 2) ────────────────────────────────────────────────
export async function checkEmailResetAvailable() {
  const res = await fetch(`${BASE}/auth/email-reset-available`)
  if (!res.ok) return { available: false }
  return res.json()
}

export async function requestOtp(username: string) {
  const res = await fetch(`${BASE}/auth/request-otp`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'OTP request failed')
  }
  return res.json()
}

export async function verifyOtp(username: string, otpCode: string) {
  const res = await fetch(`${BASE}/auth/verify-otp`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, otp_code: otpCode }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'OTP verification failed')
  }
  return res.json()
}

export async function resetWithOtp(username: string, otpCode: string, newPassword: string) {
  const res = await fetch(`${BASE}/auth/reset-with-otp`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, otp_code: otpCode, new_password: newPassword }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Password reset failed')
  }
  return res.json()
}

export async function getSetupStatus(): Promise<{ has_users: boolean; has_admin: boolean; has_hr_head: boolean }> {
  const res = await fetch(`${BASE}/auth/setup-status`)
  if (!res.ok) return { has_users: false, has_admin: false, has_hr_head: false }
  return res.json()
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

export async function deleteSession(token: string, sessionId: string) {
  const res = await handleResponse(await fetch(`${BASE}/chat/sessions/${sessionId}`, {
    method: 'DELETE', headers: headers(token),
  }))
  if (!res.ok) throw new Error('Failed to delete session')
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
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Upload failed (${res.status})`)
  }
  return res.json()
}

export async function getDocumentContent(token: string, documentId: string, page?: number, window?: number) {
  const params = new URLSearchParams()
  if (page && page > 0) params.set('page', String(page))
  if (window && window > 0) params.set('window', String(window))
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await handleResponse(await fetch(`${BASE}/documents/${documentId}/content${qs}`, { headers: headers(token) }))
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

// ── Escalation ─────────────────────────────────────────────────────────────
export async function escalateToHR(token: string, query: string, answer: string, sessionId?: string | null, reason?: string, chatHistory?: {role: string, content: string}[]) {
  const res = await handleResponse(await fetch(`${BASE}/tickets/escalate`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({
      query, answer, session_id: sessionId,
      reason: reason || 'Employee needs further HR assistance',
      chat_history: chatHistory || null,
    }),
  }))
  if (!res.ok) throw new Error('Escalation failed')
  return res.json()
}

export async function getEscalations(token: string, status?: string) {
  const qs = status ? `?status=${status}` : ''
  const res = await handleResponse(await fetch(`${BASE}/tickets/escalations/list${qs}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch escalations')
  return res.json()
}

export async function getEscalationDetail(token: string, ticketId: string) {
  const res = await handleResponse(await fetch(`${BASE}/tickets/${ticketId}/escalation-detail`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch escalation detail')
  return res.json()
}

export async function hrRespondToEscalation(token: string, ticketId: string, hrResponse: string, resolve: boolean = true) {
  const res = await handleResponse(await fetch(`${BASE}/tickets/${ticketId}/hr-respond`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ hr_response: hrResponse, resolve }),
  }))
  if (!res.ok) throw new Error('Failed to submit HR response')
  return res.json()
}

// ── Saved Prompts ──────────────────────────────────────────────────────────
export async function getSavedPrompts(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/chat/saved-prompts`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch saved prompts')
  return res.json()
}

export async function savePrompt(token: string, title: string, promptText: string) {
  const res = await handleResponse(await fetch(`${BASE}/chat/saved-prompts`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ title, prompt_text: promptText }),
  }))
  if (!res.ok) throw new Error('Failed to save prompt')
  return res.json()
}

export async function deleteSavedPrompt(token: string, promptId: number) {
  const res = await handleResponse(await fetch(`${BASE}/chat/saved-prompts/${promptId}`, {
    method: 'DELETE', headers: headers(token),
  }))
  if (!res.ok) throw new Error('Failed to delete prompt')
  return res.json()
}

// ── Admin: Pending Users ───────────────────────────────────────────────────
export async function getUsers(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/admin/users`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch users')
  return res.json()
}

export async function getPendingUsers(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/admin/users/pending`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch pending users')
  return res.json()
}

export async function approveUser(token: string, userId: string, action: 'approve' | 'reject', role: string = 'employee') {
  const res = await handleResponse(await fetch(`${BASE}/admin/users/${userId}/approve`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ action, role }),
  }))
  if (!res.ok) throw new Error('Approval action failed')
  return res.json()
}

export async function suspendUser(token: string, userId: string) {
  const res = await handleResponse(await fetch(`${BASE}/admin/users/${userId}/suspend`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({}),
  }))
  if (!res.ok) throw new Error('Suspend action failed')
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
  // Phase 2 fields
  intent?: string
  has_contradictions?: boolean
  query_type?: string
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

// ── CFLS: Controlled Feedback Learning System ────────────────────────────────

export async function sendDetailedFeedback(
  token: string, sessionId: string, query: string, response: string,
  feedbackType: string, issueCategory: string, customComment: string
) {
  const res = await handleResponse(await fetch(`${BASE}/cfls/feedback`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({
      session_id: sessionId, query, response,
      feedback_type: feedbackType,
      issue_category: issueCategory,
      custom_comment: customComment,
    }),
  }))
  if (!res.ok) throw new Error('Failed to submit feedback')
  return res.json()
}

export async function getCflsFeedback(token: string, status?: string) {
  const qs = status ? `?status=${status}` : ''
  const res = await handleResponse(await fetch(`${BASE}/cfls/feedback${qs}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch feedback')
  return res.json()
}

export async function reviewFeedback(token: string, feedbackId: number, status: string, reviewNotes: string) {
  const res = await handleResponse(await fetch(`${BASE}/cfls/feedback/${feedbackId}`, {
    method: 'PATCH', headers: headers(token),
    body: JSON.stringify({ status, review_notes: reviewNotes }),
  }))
  if (!res.ok) throw new Error('Failed to review feedback')
  return res.json()
}

export async function getCflsCorrections(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/cfls/corrections`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch corrections')
  return res.json()
}

export async function createCorrection(
  token: string, queryPattern: string, correctedResponse: string,
  keywords: string, sourceFeedbackId?: number
) {
  const res = await handleResponse(await fetch(`${BASE}/cfls/corrections`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({
      query_pattern: queryPattern,
      corrected_response: correctedResponse,
      keywords,
      source_feedback_id: sourceFeedbackId || null,
    }),
  }))
  if (!res.ok) throw new Error('Failed to create correction')
  return res.json()
}

export async function deleteCorrection(token: string, correctionId: number) {
  const res = await handleResponse(await fetch(`${BASE}/cfls/corrections/${correctionId}`, {
    method: 'DELETE', headers: headers(token),
  }))
  if (!res.ok) throw new Error('Failed to delete correction')
  return res.json()
}

export async function getCflsAnalytics(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/cfls/analytics`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch analytics')
  return res.json()
}

// ── AI Configuration (Admin only) ────────────────────────────────────────────

export async function getAiMode(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/mode`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch AI mode')
  return res.json()
}

export async function setAiMode(token: string, aiMode: string, activeProvider: string = '') {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/mode`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ ai_mode: aiMode, active_provider: activeProvider }),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to set AI mode')
  }
  return res.json()
}

export async function getAiProviders(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/providers`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch AI providers')
  return res.json()
}

export async function getSupportedProviders(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/providers/supported`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch supported providers')
  return res.json()
}

export async function createAiProvider(token: string, data: {
  provider_name: string, api_key: string, model_name?: string,
  priority?: number, status?: string, usage_limit?: number
}) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/providers`, {
    method: 'POST', headers: headers(token), body: JSON.stringify(data),
  }))
  if (!res.ok) throw new Error('Failed to create provider')
  return res.json()
}

export async function updateAiProvider(token: string, providerName: string, data: Record<string, any>) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/providers/${providerName}`, {
    method: 'PUT', headers: headers(token), body: JSON.stringify(data),
  }))
  if (!res.ok) throw new Error('Failed to update provider')
  return res.json()
}

export async function deleteAiProvider(token: string, providerName: string) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/providers/${providerName}`, {
    method: 'DELETE', headers: headers(token),
  }))
  if (!res.ok) throw new Error('Failed to delete provider')
  return res.json()
}

export async function testAiProvider(token: string, providerName: string) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/providers/${providerName}/test`, {
    method: 'POST', headers: headers(token), body: '{}',
  }))
  if (!res.ok) throw new Error('Failed to test provider')
  return res.json()
}

export async function getAiUsage(token: string, days: number = 7) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/usage?days=${days}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch AI usage')
  return res.json()
}

// ── Model Routing Configuration ──────────────────────────────────────────────

export async function getModelRouting(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/routing`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch routing config')
  return res.json()
}

export async function setModelRouting(token: string, tier: string, modelName: string, isEnabled: boolean = true) {
  const res = await handleResponse(await fetch(`${BASE}/ai-config/routing`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ tier, model_name: modelName, is_enabled: isEnabled }),
  }))
  if (!res.ok) throw new Error('Failed to update routing')
  return res.json()
}

// ── Health ──────────────────────────────────────────────────────────────────
export async function healthCheck() {
  const res = await fetch(`${BASE}/health`)
  return res.json()
}

// ── MFA ─────────────────────────────────────────────────────────────────────

/** Called after password login when API returns mfa_required: true */
export async function verifyMfaLogin(mfaToken: string, totpCode: string) {
  const res = await fetch(`${BASE}/auth/mfa/verify-login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mfa_token: mfaToken, code: totpCode }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Invalid MFA code')
  }
  return res.json()
}

/** Begin MFA enrollment — returns {secret, otpauth_url, qr_data_url} */
export async function enrollMfa(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/api/v1/compliance/mfa/enroll`, {
    method: 'POST', headers: headers(token),
  }))
  if (!res.ok) throw new Error('MFA enrollment failed')
  return res.json()
}

/** Confirm MFA enrollment with TOTP code — returns {recovery_codes: string[]} */
export async function confirmMfaEnrollment(token: string, code: string) {
  const res = await handleResponse(await fetch(`${BASE}/api/v1/compliance/mfa/verify`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ code }),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Invalid code')
  }
  return res.json()
}

/** Disable MFA — requires current TOTP code to confirm */
export async function disableMfa(token: string, code: string) {
  const res = await handleResponse(await fetch(`${BASE}/api/v1/compliance/mfa/disable`, {
    method: 'DELETE', headers: headers(token),
    body: JSON.stringify({ code }),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Invalid code')
  }
  return res.json()
}

// ── User Profile ─────────────────────────────────────────────────────────────

export async function getMyProfile(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/user/profile`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch profile')
  return res.json()
}

export async function updateMyProfile(token: string, data: { full_name?: string; email?: string; phone?: string; department?: string; team?: string }) {
  const res = await handleResponse(await fetch(`${BASE}/user/profile`, {
    method: 'PATCH', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Update failed')
  }
  return res.json()
}

// ── GDPR ─────────────────────────────────────────────────────────────────────

/** Article 15 — download full user data export as JSON */
export async function exportGdprData(token: string, userId: string) {
  const res = await handleResponse(await fetch(`${BASE}/api/v1/users/${userId}/gdpr-export`, { headers: headers(token) }))
  if (!res.ok) throw new Error('GDPR export failed')
  return res.json()
}

/** Article 17 — request account erasure */
export async function requestGdprErasure(token: string, userId: string) {
  const res = await handleResponse(await fetch(`${BASE}/api/v1/users/${userId}/gdpr-erase`, {
    method: 'DELETE', headers: headers(token),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Erasure request failed')
  }
  return res.json()
}

// ── Tenant Branding ──────────────────────────────────────────────────────────

export interface TenantBranding {
  company_name: string
  primary_color?: string
  logo_url?: string
}

export async function getTenantBranding(token: string): Promise<TenantBranding> {
  try {
    const res = await fetch(`${BASE}/api/v1/tenants/me/branding`, { headers: headers(token) })
    if (!res.ok) return { company_name: 'HR Chatbot' }
    return res.json()
  } catch {
    return { company_name: 'HR Chatbot' }
  }
}

// ── Phase C: Document Approval ────────────────────────────────────────────────

export async function getPendingDocuments(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/documents/pending`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch pending documents')
  return res.json()
}

export async function approveDocument(token: string, documentId: string, action: 'approve' | 'reject', comment: string = '') {
  const res = await handleResponse(await fetch(`${BASE}/documents/${documentId}/approve`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ action, comment }),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Approval action failed')
  }
  return res.json()
}

// ── Phase B: Tickets ─────────────────────────────────────────────────────────

export async function createTicket(token: string, data: { title: string; description?: string; category?: string; priority?: string }) {
  const res = await handleResponse(await fetch(`${BASE}/tickets`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create ticket')
  }
  return res.json()
}

export async function getTickets(token: string, params?: { status?: string; category?: string; priority?: string; page?: number; limit?: number }) {
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  if (params?.category) query.set('category', params.category)
  if (params?.priority) query.set('priority', params.priority)
  if (params?.page) query.set('page', String(params.page))
  if (params?.limit) query.set('limit', String(params.limit))
  const qs = query.toString()
  const res = await handleResponse(await fetch(`${BASE}/tickets${qs ? '?' + qs : ''}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch tickets')
  return res.json()
}

export async function getTicket(token: string, ticketId: string) {
  const res = await handleResponse(await fetch(`${BASE}/tickets/${ticketId}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch ticket')
  return res.json()
}

export async function updateTicket(token: string, ticketId: string, data: { status?: string; priority?: string; assigned_to?: string; comment?: string }) {
  const res = await handleResponse(await fetch(`${BASE}/tickets/${ticketId}`, {
    method: 'PATCH', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to update ticket')
  }
  return res.json()
}

export async function addTicketComment(token: string, ticketId: string, comment: string) {
  const res = await handleResponse(await fetch(`${BASE}/tickets/${ticketId}/comment`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify({ comment }),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to add comment')
  }
  return res.json()
}

export async function respondToTicket(token: string, ticketId: string, data: { action: 'accept' | 'reject'; feedback?: string; rating?: number }) {
  const res = await handleResponse(await fetch(`${BASE}/tickets/${ticketId}/respond`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to respond to ticket')
  }
  return res.json()
}

export async function getTicketStats(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/tickets/stats/summary`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch ticket stats')
  return res.json()
}

// ── Phase D: Notifications ──────────────────────────────────────────────────

export async function getNotifications(token: string, unreadOnly = false) {
  const qs = unreadOnly ? '?unread_only=true' : ''
  const res = await handleResponse(await fetch(`${BASE}/notifications${qs}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch notifications')
  return res.json()
}

export async function getUnreadCount(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/notifications/unread-count`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch unread count')
  return res.json()
}

export async function markNotificationRead(token: string, notificationId: string) {
  const res = await handleResponse(await fetch(`${BASE}/notifications/${notificationId}/read`, {
    method: 'POST', headers: headers(token),
  }))
  if (!res.ok) throw new Error('Failed to mark notification read')
  return res.json()
}

export async function markAllNotificationsRead(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/notifications/read-all`, {
    method: 'POST', headers: headers(token),
  }))
  if (!res.ok) throw new Error('Failed to mark all read')
  return res.json()
}

export async function sendNotification(token: string, data: { user_id: string; title: string; message?: string; notification_type?: string; link?: string }) {
  const res = await handleResponse(await fetch(`${BASE}/notifications/send`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to send notification')
  }
  return res.json()
}

// ── Phase D: Complaints ─────────────────────────────────────────────────────

export async function submitComplaint(token: string, data: { category?: string; description: string }) {
  const res = await handleResponse(await fetch(`${BASE}/complaints`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to submit complaint')
  }
  return res.json()
}

export async function getComplaints(token: string, params?: { status?: string; category?: string; page?: number; limit?: number }) {
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  if (params?.category) query.set('category', params.category)
  if (params?.page) query.set('page', String(params.page))
  if (params?.limit) query.set('limit', String(params.limit))
  const qs = query.toString()
  const res = await handleResponse(await fetch(`${BASE}/complaints${qs ? '?' + qs : ''}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch complaints')
  return res.json()
}

export async function getComplaint(token: string, complaintId: string) {
  const res = await handleResponse(await fetch(`${BASE}/complaints/${complaintId}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch complaint')
  return res.json()
}

export async function reviewComplaint(token: string, complaintId: string, data: { status: string; resolution?: string }) {
  const res = await handleResponse(await fetch(`${BASE}/complaints/${complaintId}`, {
    method: 'PATCH', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to review complaint')
  }
  return res.json()
}

export async function getComplaintStats(token: string) {
  const res = await handleResponse(await fetch(`${BASE}/complaints/stats/summary`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch complaint stats')
  return res.json()
}

// ── Phase F: Branches ───────────────────────────────────────────────────────

export async function getBranches(token: string, activeOnly = true) {
  const qs = activeOnly ? '?active_only=true' : '?active_only=false'
  const res = await handleResponse(await fetch(`${BASE}/branches${qs}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch branches')
  return res.json()
}

export async function getBranch(token: string, branchId: string) {
  const res = await handleResponse(await fetch(`${BASE}/branches/${branchId}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch branch')
  return res.json()
}

export async function createBranch(token: string, data: { name: string; location?: string; address?: string }) {
  const res = await handleResponse(await fetch(`${BASE}/branches`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create branch')
  }
  return res.json()
}

export async function updateBranch(token: string, branchId: string, data: { name?: string; location?: string; address?: string; is_active?: boolean }) {
  const res = await handleResponse(await fetch(`${BASE}/branches/${branchId}`, {
    method: 'PATCH', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to update branch')
  }
  return res.json()
}

export async function deleteBranch(token: string, branchId: string) {
  const res = await handleResponse(await fetch(`${BASE}/branches/${branchId}`, {
    method: 'DELETE', headers: headers(token),
  }))
  if (!res.ok) throw new Error('Failed to delete branch')
  return res.json()
}

export async function getBranchStats(token: string, branchId: string) {
  const res = await handleResponse(await fetch(`${BASE}/branches/${branchId}/stats`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch branch stats')
  return res.json()
}

// ── Phase F: HR Contacts ────────────────────────────────────────────────────

export async function getHRContacts(token: string, branchId?: string) {
  const params = new URLSearchParams()
  if (branchId) params.set('branch_id', branchId)
  const qs = params.toString()
  const res = await handleResponse(await fetch(`${BASE}/hr-contacts${qs ? '?' + qs : ''}`, { headers: headers(token) }))
  if (!res.ok) throw new Error('Failed to fetch HR contacts')
  return res.json()
}

export async function createHRContact(token: string, data: { name: string; role?: string; email?: string; phone?: string; branch_id?: string }) {
  const res = await handleResponse(await fetch(`${BASE}/hr-contacts`, {
    method: 'POST', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create contact')
  }
  return res.json()
}

export async function updateHRContact(token: string, contactId: string, data: { name?: string; role?: string; email?: string; phone?: string; branch_id?: string; is_available?: boolean }) {
  const res = await handleResponse(await fetch(`${BASE}/hr-contacts/${contactId}`, {
    method: 'PATCH', headers: headers(token),
    body: JSON.stringify(data),
  }))
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to update contact')
  }
  return res.json()
}

export async function deleteHRContact(token: string, contactId: string) {
  const res = await handleResponse(await fetch(`${BASE}/hr-contacts/${contactId}`, {
    method: 'DELETE', headers: headers(token),
  }))
  if (!res.ok) throw new Error('Failed to delete contact')
  return res.json()
}
