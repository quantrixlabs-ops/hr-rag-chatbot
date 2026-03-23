import { useState, useEffect, useCallback } from 'react'
import {
  Ticket, FileText, Shield, Users, Clock, AlertTriangle,
  ArrowRight, CheckCircle, XCircle, RefreshCw, Eye,
} from 'lucide-react'
import {
  getTickets, getTicketStats, getPendingDocuments, getComplaints,
  getComplaintStats, getPendingUsers,
} from '../services/api'
import type { Ticket as TicketType, TicketStats, Complaint, ComplaintStats } from '../types/chat'

interface Props {
  token: string
  role: string
  onNavigate: (page: string) => void
}

const HR_HEAD_ROLES = ['hr_head', 'hr_admin', 'admin', 'super_admin']

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const PRIORITY_COLORS: Record<string, string> = {
  urgent: 'bg-red-100 text-red-800',
  high: 'bg-orange-100 text-orange-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-green-100 text-green-800',
}

const STATUS_COLORS: Record<string, string> = {
  raised: 'bg-yellow-100 text-yellow-800',
  assigned: 'bg-blue-100 text-blue-800',
  in_progress: 'bg-purple-100 text-purple-800',
  resolved: 'bg-green-100 text-green-800',
  submitted: 'bg-yellow-100 text-yellow-800',
  under_review: 'bg-blue-100 text-blue-800',
  investigating: 'bg-purple-100 text-purple-800',
}

export default function HRDashboard({ token, role, onNavigate }: Props) {
  const isHead = HR_HEAD_ROLES.includes(role)
  const [ticketStats, setTicketStats] = useState<TicketStats | null>(null)
  const [recentTickets, setRecentTickets] = useState<TicketType[]>([])
  const [pendingDocs, setPendingDocs] = useState<any[]>([])
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [complaintStats, setComplaintStats] = useState<ComplaintStats | null>(null)
  const [pendingUsers, setPendingUsers] = useState<any[]>([])
  const [refreshing, setRefreshing] = useState(false)

  const loadData = useCallback(() => {
    setRefreshing(true)
    const promises: Promise<any>[] = [
      getTicketStats(token).then(setTicketStats).catch(() => {}),
      getTickets(token, { limit: 5 }).then(d => setRecentTickets(d.tickets || [])).catch(() => {}),
    ]

    if (isHead) {
      promises.push(
        getPendingDocuments(token).then(d => setPendingDocs((d.documents || []).slice(0, 5))).catch(() => {}),
        getComplaints(token, { limit: 5 }).then(d => setComplaints(d.complaints || [])).catch(() => {}),
        getComplaintStats(token).then(setComplaintStats).catch(() => {}),
        getPendingUsers(token).then(d => setPendingUsers(d.pending_users || d.users || [])).catch(() => {}),
      )
    }

    Promise.all(promises).finally(() => setRefreshing(false))
  }, [token, isHead])

  useEffect(() => { loadData() }, [loadData])

  // Auto-refresh every 60s
  useEffect(() => {
    const interval = setInterval(loadData, 60000)
    return () => clearInterval(interval)
  }, [loadData])

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">HR Dashboard</h1>
            <p className="text-sm text-gray-500 mt-1">
              {isHead ? 'HR leadership overview' : 'Team workqueue & activity'}
            </p>
          </div>
          <button onClick={loadData} disabled={refreshing}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40">
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-1">
              <Ticket size={16} className="text-blue-500" />
              <span className="text-xs text-gray-500">Total Tickets</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{ticketStats?.total || 0}</p>
            <p className="text-[10px] text-gray-400">{ticketStats?.open || 0} open</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle size={16} className="text-yellow-500" />
              <span className="text-xs text-gray-500">Raised</span>
            </div>
            <p className="text-2xl font-bold text-yellow-600">{ticketStats?.by_status?.raised || 0}</p>
            <p className="text-[10px] text-gray-400">Awaiting assignment</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-1">
              <Clock size={16} className="text-purple-500" />
              <span className="text-xs text-gray-500">In Progress</span>
            </div>
            <p className="text-2xl font-bold text-purple-600">{ticketStats?.by_status?.in_progress || 0}</p>
            <p className="text-[10px] text-gray-400">Being worked on</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle size={16} className="text-green-500" />
              <span className="text-xs text-gray-500">Resolved</span>
            </div>
            <p className="text-2xl font-bold text-green-600">{ticketStats?.by_status?.resolved || 0}</p>
            <p className="text-[10px] text-gray-400">Completed</p>
          </div>
        </div>

        {/* HR Head: Extra stats row */}
        {isHead && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 mb-1">
                <FileText size={16} className="text-amber-500" />
                <span className="text-xs text-gray-500">Pending Documents</span>
              </div>
              <p className="text-2xl font-bold text-amber-600">{pendingDocs.length}</p>
              <button onClick={() => onNavigate('upload')}
                className="text-[10px] text-blue-600 hover:underline mt-1">Review &rarr;</button>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 mb-1">
                <Shield size={16} className="text-red-500" />
                <span className="text-xs text-gray-500">Active Complaints</span>
              </div>
              <p className="text-2xl font-bold text-red-600">
                {(complaintStats?.by_status?.submitted || 0) +
                 (complaintStats?.by_status?.under_review || 0) +
                 (complaintStats?.by_status?.investigating || 0)}
              </p>
              <button onClick={() => onNavigate('complaints')}
                className="text-[10px] text-blue-600 hover:underline mt-1">Review &rarr;</button>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="flex items-center gap-2 mb-1">
                <Users size={16} className="text-indigo-500" />
                <span className="text-xs text-gray-500">Pending Approvals</span>
              </div>
              <p className="text-2xl font-bold text-indigo-600">{pendingUsers.length}</p>
              <button onClick={() => onNavigate('admin')}
                className="text-[10px] text-blue-600 hover:underline mt-1">Manage &rarr;</button>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Recent tickets */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                <Ticket size={14} className="text-blue-500" /> Recent Tickets
              </h3>
              <button onClick={() => onNavigate('tickets')}
                className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
                View all <ArrowRight size={11} />
              </button>
            </div>
            {recentTickets.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">No tickets</p>
            ) : (
              <div className="divide-y divide-gray-50">
                {recentTickets.map(t => (
                  <div key={t.ticket_id} className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-gray-800 truncate">{t.title}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-gray-400">{t.raised_by_name}</span>
                        <span className="text-[10px] text-gray-300">|</span>
                        <span className="text-[10px] text-gray-400">{timeAgo(t.created_at)}</span>
                      </div>
                    </div>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${PRIORITY_COLORS[t.priority] || ''}`}>
                      {t.priority}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STATUS_COLORS[t.status] || 'bg-gray-100 text-gray-600'}`}>
                      {t.status.replace('_', ' ')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Complaints (HR Head only) / Priority breakdown */}
          {isHead ? (
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
                <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                  <Shield size={14} className="text-red-500" /> Recent Complaints
                </h3>
                <button onClick={() => onNavigate('complaints')}
                  className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
                  View all <ArrowRight size={11} />
                </button>
              </div>
              {complaints.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-6">No complaints</p>
              ) : (
                <div className="divide-y divide-gray-50">
                  {complaints.map(c => (
                    <div key={c.complaint_id} className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-gray-800 truncate capitalize">{c.category.replace('_', ' ')}</p>
                        <p className="text-[10px] text-gray-400 truncate">{c.description.slice(0, 80)}</p>
                      </div>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STATUS_COLORS[c.status] || 'bg-gray-100 text-gray-600'}`}>
                        {c.status.replace('_', ' ')}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-800 mb-4 flex items-center gap-2">
                <Ticket size={14} className="text-blue-500" /> By Priority
              </h3>
              <div className="space-y-3">
                {['urgent', 'high', 'medium', 'low'].map(p => {
                  const count = ticketStats?.by_priority?.[p] || 0
                  const total = ticketStats?.total || 1
                  const pct = Math.round((count / total) * 100)
                  return (
                    <div key={p} className="flex items-center gap-3">
                      <span className="text-xs text-gray-600 capitalize w-14">{p}</span>
                      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${
                          p === 'urgent' ? 'bg-red-500' : p === 'high' ? 'bg-orange-500' : p === 'medium' ? 'bg-yellow-500' : 'bg-green-500'
                        }`} style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-xs text-gray-400 w-8 text-right">{count}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {/* Pending documents (HR Head) */}
        {isHead && pendingDocs.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
                <FileText size={14} className="text-amber-500" /> Documents Awaiting Approval
              </h3>
              <button onClick={() => onNavigate('upload')}
                className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
                Review all <ArrowRight size={11} />
              </button>
            </div>
            <div className="divide-y divide-gray-50">
              {pendingDocs.map((d: any) => (
                <div key={d.document_id} className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50">
                  <FileText size={14} className="text-gray-400 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-800 truncate">{d.title}</p>
                    <p className="text-[10px] text-gray-400">
                      Uploaded by {d.uploaded_by_name || 'unknown'} | {d.category}
                    </p>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-100 text-amber-800">Pending</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
