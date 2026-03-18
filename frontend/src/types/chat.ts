export interface Citation {
  source: string
  page: number | null
  excerpt: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  confidence?: number
  faithfulness_score?: number
  query_type?: string
  latency_ms?: number
  suggested_questions?: string[]
  timestamp: number
}

export interface SessionSummary {
  session_id: string
  created_at: number
  last_active: number
  turn_count: number
  preview: string
}

export interface UserInfo {
  user_id: string
  role: string
  department: string | null
}

export interface AuthState {
  token: string | null
  refreshToken: string | null
  user: UserInfo | null
}

export interface AdminMetrics {
  queries_today: number
  queries_this_week: number
  avg_latency_ms: number
  avg_faithfulness: number
  hallucination_rate: number
  active_sessions: number
  total_documents: number
  total_chunks: number
}
