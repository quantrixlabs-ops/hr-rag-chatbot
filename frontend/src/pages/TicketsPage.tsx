import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Filter, ChevronDown, ChevronRight, Clock, AlertCircle,
  CheckCircle2, XCircle, MessageSquare, Send, User, ArrowUpDown,
  ThumbsUp, ThumbsDown, Star, RotateCcw, Timer,
} from 'lucide-react'
import type { Ticket, TicketStatus, TicketPriority, TicketStats, TicketHistoryEntry } from '../types/chat'
import {
  createTicket, getTickets, getTicket, updateTicket, addTicketComment, getTicketStats,
  respondToTicket,
} from '../services/api'

interface Props {
  token: string
  role: string
}

const STATUS_COLORS: Record<TicketStatus, string> = {
  raised: 'bg-blue-100 text-blue-700',
  assigned: 'bg-yellow-100 text-yellow-700',
  in_progress: 'bg-purple-100 text-purple-700',
  resolved: 'bg-green-100 text-green-700',
  closed: 'bg-gray-100 text-gray-500',
  rejected: 'bg-red-100 text-red-700',
}

const PRIORITY_COLORS: Record<TicketPriority, string> = {
  low: 'bg-gray-100 text-gray-600',
  medium: 'bg-blue-100 text-blue-600',
  high: 'bg-orange-100 text-orange-700',
  urgent: 'bg-red-100 text-red-700',
}

const STATUS_ICONS: Record<TicketStatus, typeof Clock> = {
  raised: Clock,
  assigned: User,
  in_progress: ArrowUpDown,
  resolved: CheckCircle2,
  closed: CheckCircle2,
  rejected: XCircle,
}

const CATEGORIES = [
  'general', 'leave', 'payroll', 'benefits', 'onboarding',
  'offboarding', 'policy', 'complaint', 'technical', 'other',
]

const HR_ROLES = new Set(['hr_team', 'hr_head', 'hr_admin', 'admin', 'super_admin'])

function formatTime(ts: number) {
  const d = new Date(ts * 1000)
  const now = Date.now()
  const diff = now - d.getTime()
  if (diff < 60_000) return 'Just now'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3600_000)}h ago`
  if (diff < 604_800_000) return `${Math.floor(diff / 86_400_000)}d ago`
  return d.toLocaleDateString()
}

export default function TicketsPage({ token, role }: Props) {
  const isHR = HR_ROLES.has(role)

  const [tickets, setTickets] = useState<Ticket[]>([])
  const [stats, setStats] = useState<TicketStats | null>(null)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Filters
  const [filterStatus, setFilterStatus] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterPriority, setFilterPriority] = useState('')
  const [currentPage, setCurrentPage] = useState(1)

  // Create ticket modal
  const [showCreate, setShowCreate] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newCategory, setNewCategory] = useState('general')
  const [newPriority, setNewPriority] = useState('medium')
  const [creating, setCreating] = useState(false)

  // Detail view
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [comment, setComment] = useState('')
  const [commenting, setCommenting] = useState(false)

  // Employee response to resolved ticket
  const [showAcceptModal, setShowAcceptModal] = useState(false)
  const [respondRating, setRespondRating] = useState(0)
  const [respondFeedback, setRespondFeedback] = useState('')
  const [responding, setResponding] = useState(false)

  const fetchTickets = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getTickets(token, {
        status: filterStatus || undefined,
        category: filterCategory || undefined,
        priority: filterPriority || undefined,
        page: currentPage,
        limit: 20,
      })
      setTickets(data.tickets || [])
      setTotal(data.total || 0)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [token, filterStatus, filterCategory, filterPriority, currentPage])

  const fetchStats = useCallback(async () => {
    try {
      const data = await getTicketStats(token)
      setStats(data)
    } catch { /* ignore */ }
  }, [token])

  useEffect(() => { fetchTickets() }, [fetchTickets])
  useEffect(() => { fetchStats() }, [fetchStats])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newTitle.trim()) return
    setCreating(true)
    setError('')
    try {
      await createTicket(token, {
        title: newTitle, description: newDesc,
        category: newCategory, priority: newPriority,
      })
      setShowCreate(false)
      setNewTitle(''); setNewDesc(''); setNewCategory('general'); setNewPriority('medium')
      fetchTickets()
      fetchStats()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setCreating(false)
    }
  }

  const openDetail = async (ticketId: string) => {
    setDetailLoading(true)
    try {
      const data = await getTicket(token, ticketId)
      setSelectedTicket(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleStatusChange = async (ticketId: string, newStatus: string) => {
    try {
      await updateTicket(token, ticketId, { status: newStatus })
      fetchTickets()
      fetchStats()
      if (selectedTicket?.ticket_id === ticketId) openDetail(ticketId)
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleComment = async () => {
    if (!comment.trim() || !selectedTicket) return
    setCommenting(true)
    try {
      await addTicketComment(token, selectedTicket.ticket_id, comment)
      setComment('')
      openDetail(selectedTicket.ticket_id)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setCommenting(false)
    }
  }

  const handleAccept = async () => {
    if (!selectedTicket || respondRating === 0) return
    setResponding(true)
    try {
      await respondToTicket(token, selectedTicket.ticket_id, {
        action: 'accept',
        feedback: respondFeedback,
        rating: respondRating,
      })
      setShowAcceptModal(false)
      setRespondRating(0)
      setRespondFeedback('')
      fetchTickets()
      fetchStats()
      openDetail(selectedTicket.ticket_id)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setResponding(false)
    }
  }

  const handleReject = async () => {
    if (!selectedTicket) return
    const reason = prompt('Please explain why you need more details:')
    if (!reason?.trim()) return
    setResponding(true)
    try {
      await respondToTicket(token, selectedTicket.ticket_id, {
        action: 'reject',
        feedback: reason,
      })
      fetchTickets()
      fetchStats()
      openDetail(selectedTicket.ticket_id)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setResponding(false)
    }
  }

  const totalPages = Math.ceil(total / 20)

  // ── Detail Panel ──────────────────────────────────────────────────────────
  if (selectedTicket) {
    const t = selectedTicket
    const StatusIcon = STATUS_ICONS[t.status]
    return (
      <div className="h-full flex flex-col bg-white">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center gap-3">
          <button onClick={() => setSelectedTicket(null)}
            className="text-gray-400 hover:text-gray-600 transition-colors">
            <ChevronRight size={20} className="rotate-180" />
          </button>
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-semibold text-gray-900 truncate">{t.title}</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              #{t.ticket_id.slice(0, 8)} &middot; Created by {t.raised_by_name} &middot; {formatTime(t.created_at)}
            </p>
          </div>
          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[t.status]}`}>
            <StatusIcon size={12} className="inline mr-1 -mt-0.5" />
            {t.status.replace('_', ' ')}
          </span>
          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${PRIORITY_COLORS[t.priority]}`}>
            {t.priority}
          </span>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-5">
          {/* Description */}
          {t.description && (
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-1">Description</h3>
              <p className="text-sm text-gray-600 whitespace-pre-wrap bg-gray-50 rounded-lg p-3">{t.description}</p>
            </div>
          )}

          {/* Info grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Category</p>
              <p className="font-medium text-gray-800 capitalize">{t.category}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Assigned To</p>
              <p className="font-medium text-gray-800">{t.assigned_to_name || 'Unassigned'}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Updated</p>
              <p className="font-medium text-gray-800">{formatTime(t.updated_at)}</p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-500">Resolved</p>
              <p className="font-medium text-gray-800">{t.resolved_at ? formatTime(t.resolved_at) : '—'}</p>
            </div>
          </div>

          {/* HR Actions */}
          {isHR && !['closed', 'rejected'].includes(t.status) && (
            <div>
              <h3 className="text-sm font-medium text-gray-700 mb-2">Actions</h3>
              <div className="flex flex-wrap gap-2">
                {['raised', 'assigned'].includes(t.status) && (
                  <button onClick={() => handleStatusChange(t.ticket_id, 'in_progress')}
                    className="px-3 py-1.5 bg-purple-600 text-white rounded-lg text-xs font-medium hover:bg-purple-700 transition-colors">
                    {t.status === 'raised' ? 'Start Working' : 'Mark In Progress'}
                  </button>
                )}
                {['assigned', 'in_progress'].includes(t.status) && (
                  <button onClick={() => handleStatusChange(t.ticket_id, 'resolved')}
                    className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700 transition-colors">
                    Resolve
                  </button>
                )}
                {t.status === 'resolved' && (
                  <>
                    <button onClick={() => handleStatusChange(t.ticket_id, 'closed')}
                      className="px-3 py-1.5 bg-gray-600 text-white rounded-lg text-xs font-medium hover:bg-gray-700 transition-colors">
                      Close
                    </button>
                    <button onClick={() => handleStatusChange(t.ticket_id, 'in_progress')}
                      className="px-3 py-1.5 bg-orange-600 text-white rounded-lg text-xs font-medium hover:bg-orange-700 transition-colors">
                      Reopen
                    </button>
                  </>
                )}
                {!['closed', 'rejected'].includes(t.status) && (
                  <button onClick={() => handleStatusChange(t.ticket_id, 'rejected')}
                    className="px-3 py-1.5 bg-red-100 text-red-700 rounded-lg text-xs font-medium hover:bg-red-200 transition-colors">
                    Reject
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Employee Response — shown to non-HR users when their ticket is resolved */}
          {t.status === 'resolved' && !isHR && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-2">
                <Timer size={16} className="text-amber-600" />
                <h3 className="text-sm font-semibold text-amber-800">HR has resolved your ticket</h3>
              </div>
              {t.auto_close_at && (
                <p className="text-xs text-amber-600 mb-3">
                  Auto-accepts in {Math.max(0, Math.ceil((t.auto_close_at - Date.now() / 1000) / 3600))} hours if no action taken
                </p>
              )}
              <p className="text-xs text-gray-600 mb-3">Are you satisfied with the resolution?</p>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => setShowAcceptModal(true)} disabled={responding}
                  className="flex items-center gap-1.5 px-4 py-2 bg-green-600 text-white rounded-lg text-xs font-medium hover:bg-green-700 disabled:opacity-50 transition-colors">
                  <ThumbsUp size={14} /> Accept
                </button>
                <button onClick={handleReject} disabled={responding}
                  className="flex items-center gap-1.5 px-4 py-2 bg-orange-600 text-white rounded-lg text-xs font-medium hover:bg-orange-700 disabled:opacity-50 transition-colors">
                  <ThumbsDown size={14} /> Need More Details
                </button>
              </div>
            </div>
          )}

          {/* Feedback display for closed tickets with rating */}
          {t.status === 'closed' && (t.rating || t.feedback) && (
            <div className="bg-green-50 border border-green-200 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-green-800 mb-2">Employee Feedback</h3>
              {!!t.rating && (
                <div className="flex items-center gap-1 mb-1">
                  {[1, 2, 3, 4, 5].map(s => (
                    <Star key={s} size={16}
                      className={s <= t.rating! ? 'text-yellow-500 fill-yellow-500' : 'text-gray-300'} />
                  ))}
                  <span className="text-xs text-gray-500 ml-1">{t.rating}/5</span>
                </div>
              )}
              {t.feedback && <p className="text-sm text-gray-700">{t.feedback}</p>}
            </div>
          )}

          {/* History / Timeline */}
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">Activity</h3>
            <div className="space-y-3">
              {(t.history || []).map((h: TicketHistoryEntry, i: number) => (
                <div key={i} className="flex gap-3 text-sm">
                  <div className="w-8 h-8 bg-gray-100 rounded-full flex items-center justify-center flex-shrink-0">
                    {h.action === 'comment' ? <MessageSquare size={14} className="text-gray-500" /> :
                     h.action === 'status_change' ? <ArrowUpDown size={14} className="text-blue-500" /> :
                     <Clock size={14} className="text-gray-400" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-gray-800">
                      <span className="font-medium">{h.performed_by_name}</span>
                      {h.action === 'created' && ' created this ticket'}
                      {h.action === 'status_change' && (
                        <> changed status from <span className="font-medium">{h.old_value}</span> to <span className="font-medium">{h.new_value}</span></>
                      )}
                      {h.action === 'priority_change' && (
                        <> changed priority from <span className="font-medium">{h.old_value}</span> to <span className="font-medium">{h.new_value}</span></>
                      )}
                      {h.action === 'assigned' && (
                        <> assigned ticket{h.new_value ? ` to ${h.new_value}` : ''}</>
                      )}
                      {h.action === 'comment' && ' added a comment'}
                    </p>
                    {h.comment && (
                      <p className="text-gray-600 mt-1 bg-gray-50 rounded-lg px-3 py-2 whitespace-pre-wrap">{h.comment}</p>
                    )}
                    <p className="text-xs text-gray-400 mt-1">{formatTime(h.timestamp)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Comment input */}
        {!['closed', 'rejected'].includes(t.status) && (
          <div className="px-6 py-3 border-t border-gray-200 flex gap-2">
            <input
              type="text" value={comment} onChange={e => setComment(e.target.value)}
              placeholder="Add a comment..."
              onKeyDown={e => e.key === 'Enter' && handleComment()}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <button onClick={handleComment} disabled={commenting || !comment.trim()}
              className="px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              <Send size={16} />
            </button>
          </div>
        )}

        {/* Accept Modal — rating + feedback */}
        {showAcceptModal && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowAcceptModal(false)}>
            <div className="bg-white rounded-2xl w-full max-w-md p-6 shadow-xl" onClick={e => e.stopPropagation()}>
              <h2 className="text-lg font-bold text-gray-900 mb-1">Accept Resolution</h2>
              <p className="text-sm text-gray-500 mb-4">Rate your experience and leave optional feedback.</p>

              {/* Star rating */}
              <div className="mb-4">
                <label className="block text-xs font-medium text-gray-700 mb-2">Rating <span className="text-red-500">*</span></label>
                <div className="flex items-center gap-1">
                  {[1, 2, 3, 4, 5].map(s => (
                    <button key={s} type="button" onClick={() => setRespondRating(s)}
                      className="p-1 transition-transform hover:scale-110">
                      <Star size={28}
                        className={s <= respondRating ? 'text-yellow-500 fill-yellow-500' : 'text-gray-300 hover:text-yellow-400'} />
                    </button>
                  ))}
                  {respondRating > 0 && (
                    <span className="text-sm text-gray-500 ml-2">{respondRating}/5</span>
                  )}
                </div>
              </div>

              {/* Feedback */}
              <div className="mb-4">
                <label className="block text-xs font-medium text-gray-700 mb-1">Feedback (optional)</label>
                <textarea value={respondFeedback} onChange={e => setRespondFeedback(e.target.value)} rows={3}
                  placeholder="Any additional comments about the resolution..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none" />
              </div>

              <div className="flex gap-2">
                <button type="button" onClick={() => setShowAcceptModal(false)}
                  className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-sm hover:bg-gray-50 transition-colors">
                  Cancel
                </button>
                <button onClick={handleAccept} disabled={responding || respondRating === 0}
                  className="flex-1 px-4 py-2.5 bg-green-600 text-white rounded-xl text-sm font-medium hover:bg-green-700 disabled:opacity-50 transition-colors">
                  {responding ? 'Submitting...' : respondRating === 0 ? 'Select a rating' : 'Accept & Close'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // ── List View ─────────────────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Tickets</h1>
            <p className="text-sm text-gray-500">
              {isHR ? 'Manage all support tickets' : 'Track your requests'}
            </p>
          </div>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
            <Plus size={16} /> New Ticket
          </button>
        </div>

        {/* Stats cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div className="bg-blue-50 rounded-lg px-3 py-2">
              <p className="text-xs text-blue-600 font-medium">Open</p>
              <p className="text-lg font-bold text-blue-700">{stats.open}</p>
            </div>
            <div className="bg-gray-50 rounded-lg px-3 py-2">
              <p className="text-xs text-gray-500 font-medium">Total</p>
              <p className="text-lg font-bold text-gray-700">{stats.total}</p>
            </div>
            <div className="bg-orange-50 rounded-lg px-3 py-2">
              <p className="text-xs text-orange-600 font-medium">High/Urgent</p>
              <p className="text-lg font-bold text-orange-700">
                {(stats.by_priority.high || 0) + (stats.by_priority.urgent || 0)}
              </p>
            </div>
            <div className="bg-green-50 rounded-lg px-3 py-2">
              <p className="text-xs text-green-600 font-medium">Resolved</p>
              <p className="text-lg font-bold text-green-700">
                {(stats.by_status.resolved || 0) + (stats.by_status.closed || 0)}
              </p>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap gap-2">
          <div className="flex items-center gap-1 text-xs text-gray-500">
            <Filter size={13} /> Filters:
          </div>
          <select value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setCurrentPage(1) }}
            className="px-2 py-1 border border-gray-300 rounded-lg text-xs bg-white">
            <option value="">All Statuses</option>
            <option value="raised">Raised</option>
            <option value="assigned">Assigned</option>
            <option value="in_progress">In Progress</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
            <option value="rejected">Rejected</option>
          </select>
          <select value={filterCategory} onChange={e => { setFilterCategory(e.target.value); setCurrentPage(1) }}
            className="px-2 py-1 border border-gray-300 rounded-lg text-xs bg-white">
            <option value="">All Categories</option>
            {CATEGORIES.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
          </select>
          <select value={filterPriority} onChange={e => { setFilterPriority(e.target.value); setCurrentPage(1) }}
            className="px-2 py-1 border border-gray-300 rounded-lg text-xs bg-white">
            <option value="">All Priorities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="urgent">Urgent</option>
          </select>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mx-6 mt-3 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex items-center gap-2">
          <AlertCircle size={14} /> {error}
          <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-600">&times;</button>
        </div>
      )}

      {/* Ticket list */}
      <div className="flex-1 overflow-y-auto px-6 py-3">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin w-6 h-6 border-2 border-blue-600 border-t-transparent rounded-full" />
          </div>
        ) : tickets.length === 0 ? (
          <div className="text-center py-12">
            <AlertCircle size={32} className="mx-auto text-gray-300 mb-2" />
            <p className="text-gray-500 text-sm">No tickets found</p>
            <button onClick={() => setShowCreate(true)}
              className="mt-3 text-blue-600 text-sm hover:underline">Create your first ticket</button>
          </div>
        ) : (
          <div className="space-y-2">
            {tickets.map(t => {
              const StatusIcon = STATUS_ICONS[t.status]
              return (
                <button key={t.ticket_id} onClick={() => openDetail(t.ticket_id)}
                  className="w-full text-left bg-white rounded-lg border border-gray-200 px-4 py-3 hover:border-blue-300 hover:shadow-sm transition-all">
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-sm font-medium text-gray-900 truncate">{t.title}</h3>
                      </div>
                      <p className="text-xs text-gray-500 truncate">
                        #{t.ticket_id.slice(0, 8)} &middot; {t.raised_by_name} &middot; {t.category} &middot; {formatTime(t.updated_at)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${PRIORITY_COLORS[t.priority]}`}>
                        {t.priority}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium flex items-center gap-1 ${STATUS_COLORS[t.status]}`}>
                        <StatusIcon size={11} />
                        {t.status.replace('_', ' ')}
                      </span>
                      <ChevronRight size={14} className="text-gray-300" />
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-4 pb-4">
            <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage === 1}
              className="px-3 py-1.5 text-xs border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50">
              Previous
            </button>
            <span className="text-xs text-gray-500">Page {currentPage} of {totalPages}</span>
            <button onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages}
              className="px-3 py-1.5 text-xs border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50">
              Next
            </button>
          </div>
        )}
      </div>

      {/* Create Ticket Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => setShowCreate(false)}>
          <div className="bg-white rounded-2xl w-full max-w-lg p-6 shadow-xl" onClick={e => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-gray-900 mb-4">Create New Ticket</h2>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Title *</label>
                <input type="text" value={newTitle} onChange={e => setNewTitle(e.target.value)} required
                  placeholder="Brief summary of your request"
                  className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Description</label>
                <textarea value={newDesc} onChange={e => setNewDesc(e.target.value)} rows={3}
                  placeholder="Provide details about your request..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Category</label>
                  <select value={newCategory} onChange={e => setNewCategory(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm bg-white">
                    {CATEGORIES.map(c => <option key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Priority</label>
                  <select value={newPriority} onChange={e => setNewPriority(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm bg-white">
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
              </div>

              {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}

              <div className="flex gap-2 pt-2">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-sm hover:bg-gray-50 transition-colors">
                  Cancel
                </button>
                <button type="submit" disabled={creating || !newTitle.trim()}
                  className="flex-1 px-4 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
                  {creating ? 'Creating...' : 'Create Ticket'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
