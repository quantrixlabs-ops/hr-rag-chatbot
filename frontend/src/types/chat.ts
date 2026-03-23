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
  // Phase 2: Intelligence fields
  intent?: string
  has_contradictions?: boolean
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
  username?: string
  full_name?: string
  role: string
  department: string | null
  employee_id?: string
  branch_id?: string
  team?: string
}

export interface AuthState {
  token: string | null
  refreshToken: string | null
  user: UserInfo | null
}

// Phase B: Ticket system types
export type TicketStatus = 'raised' | 'assigned' | 'in_progress' | 'resolved' | 'closed' | 'rejected'
export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent'

export interface Ticket {
  ticket_id: string
  title: string
  description: string
  category: string
  priority: TicketPriority
  status: TicketStatus
  raised_by: string
  assigned_to: string
  created_at: number
  updated_at: number
  resolved_at: number | null
  raised_by_name: string
  assigned_to_name: string
  auto_close_at?: number | null
  feedback?: string
  rating?: number
  history?: TicketHistoryEntry[]
}

export interface TicketHistoryEntry {
  action: string
  performed_by: string
  old_value: string
  new_value: string
  comment: string
  timestamp: number
  performed_by_name: string
}

export interface TicketStats {
  total: number
  open: number
  by_status: Record<string, number>
  by_priority: Record<string, number>
}

// Phase D: Notification types
export interface Notification {
  notification_id: string
  title: string
  message: string
  type: string
  is_read: boolean
  link: string
  created_at: number
}

// Phase D: Complaint types
export type ComplaintStatus = 'submitted' | 'under_review' | 'investigating' | 'resolved' | 'dismissed'
export type ComplaintCategory =
  | 'harassment' | 'discrimination' | 'fraud' | 'safety' | 'ethics'
  | 'retaliation' | 'misconduct' | 'policy_violation' | 'other'

export interface Complaint {
  complaint_id: string
  category: ComplaintCategory
  description: string
  status: ComplaintStatus
  submitted_at: number
  reviewed_by: string
  reviewed_at: number | null
  resolution: string
  reviewed_by_name: string
}

export interface ComplaintStats {
  total: number
  by_status: Record<string, number>
  by_category: Record<string, number>
}

// Phase F: Branch types
export interface Branch {
  branch_id: string
  name: string
  location: string
  address: string
  is_active: boolean
  created_at: number
  user_count: number
}

export interface BranchStats {
  branch_id: string
  user_count: number
  ticket_count: number
  open_tickets: number
  hr_contact_count: number
}

// Phase F: HR Contact types
export interface HRContact {
  contact_id: string
  name: string
  role: string
  email: string
  phone: string
  branch_id: string
  is_available: boolean
  branch_name: string
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
  query_success_rate: number
  failed_queries: number
  negative_feedback_count: number
  top_documents?: { source: string; query_count: number }[]
  query_type_distribution?: Record<string, number>
}
