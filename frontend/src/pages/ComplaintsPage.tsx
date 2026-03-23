import { useState, useEffect, useCallback } from 'react'
import {
  AlertTriangle, Shield, Eye, ChevronLeft, Clock, CheckCircle, XCircle,
  Search, Filter, Send,
} from 'lucide-react'
import {
  getComplaints, getComplaint, reviewComplaint, getComplaintStats,
  submitComplaint,
} from '../services/api'
import type { Complaint, ComplaintStats, ComplaintCategory } from '../types/chat'

interface Props {
  token: string
  role: string
}

const HR_HEAD_ROLES = ['hr_head', 'hr_admin', 'admin', 'super_admin']

const CATEGORIES: { value: ComplaintCategory; label: string }[] = [
  { value: 'harassment', label: 'Harassment' },
  { value: 'discrimination', label: 'Discrimination' },
  { value: 'fraud', label: 'Fraud' },
  { value: 'safety', label: 'Safety' },
  { value: 'ethics', label: 'Ethics' },
  { value: 'retaliation', label: 'Retaliation' },
  { value: 'misconduct', label: 'Misconduct' },
  { value: 'policy_violation', label: 'Policy Violation' },
  { value: 'other', label: 'Other' },
]

const STATUS_COLORS: Record<string, string> = {
  submitted: 'bg-yellow-100 text-yellow-800',
  under_review: 'bg-blue-100 text-blue-800',
  investigating: 'bg-purple-100 text-purple-800',
  resolved: 'bg-green-100 text-green-800',
  dismissed: 'bg-gray-100 text-gray-800',
}

const STATUS_LABELS: Record<string, string> = {
  submitted: 'Submitted',
  under_review: 'Under Review',
  investigating: 'Investigating',
  resolved: 'Resolved',
  dismissed: 'Dismissed',
}

function formatDate(ts: number | null): string {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export default function ComplaintsPage({ token, role }: Props) {
  const isHR = HR_HEAD_ROLES.includes(role)
  const [view, setView] = useState<'list' | 'detail' | 'submit'>('list')
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [stats, setStats] = useState<ComplaintStats | null>(null)
  const [selected, setSelected] = useState<Complaint | null>(null)
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filterStatus, setFilterStatus] = useState('')
  const [filterCategory, setFilterCategory] = useState('')

  // Submit form state
  const [submitCategory, setSubmitCategory] = useState<ComplaintCategory>('other')
  const [submitDescription, setSubmitDescription] = useState('')
  const [submitLoading, setSubmitLoading] = useState(false)
  const [submitSuccess, setSubmitSuccess] = useState(false)

  // Review form state
  const [reviewStatus, setReviewStatus] = useState('')
  const [reviewResolution, setReviewResolution] = useState('')
  const [reviewLoading, setReviewLoading] = useState(false)

  const fetchComplaints = useCallback(() => {
    if (!isHR) return
    setLoading(true)
    getComplaints(token, {
      status: filterStatus || undefined,
      category: filterCategory || undefined,
      page,
      limit: 20,
    })
      .then(d => {
        setComplaints(d.complaints || [])
        setTotal(d.total || 0)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [token, isHR, filterStatus, filterCategory, page])

  const fetchStats = useCallback(() => {
    if (!isHR) return
    getComplaintStats(token).then(setStats).catch(() => {})
  }, [token, isHR])

  useEffect(() => { fetchComplaints() }, [fetchComplaints])
  useEffect(() => { fetchStats() }, [fetchStats])

  const openDetail = async (id: string) => {
    try {
      const data = await getComplaint(token, id)
      setSelected(data)
      setReviewStatus(data.status)
      setReviewResolution(data.resolution || '')
      setView('detail')
    } catch { /* ignore */ }
  }

  const handleReview = async () => {
    if (!selected || !reviewStatus) return
    setReviewLoading(true)
    try {
      await reviewComplaint(token, selected.complaint_id, {
        status: reviewStatus,
        resolution: reviewResolution,
      })
      setView('list')
      setSelected(null)
      fetchComplaints()
      fetchStats()
    } catch { /* ignore */ }
    setReviewLoading(false)
  }

  const handleSubmit = async () => {
    if (submitDescription.trim().length < 10) return
    setSubmitLoading(true)
    try {
      await submitComplaint(token, {
        category: submitCategory,
        description: submitDescription.trim(),
      })
      setSubmitSuccess(true)
      setSubmitDescription('')
      setSubmitCategory('other')
    } catch { /* ignore */ }
    setSubmitLoading(false)
  }

  // ── Submit view (all users) ─────────────────────────────────────────────
  if (view === 'submit' || !isHR) {
    return (
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl mx-auto">
          {isHR && (
            <button onClick={() => setView('list')}
              className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4">
              <ChevronLeft size={16} /> Back to complaints
            </button>
          )}

          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                <Shield size={20} className="text-red-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-800">Anonymous Complaint</h2>
                <p className="text-xs text-gray-500">Your identity will NOT be stored or linked to this complaint.</p>
              </div>
            </div>

            {submitSuccess ? (
              <div className="text-center py-8">
                <CheckCircle size={48} className="mx-auto text-green-500 mb-3" />
                <h3 className="text-lg font-semibold text-gray-800 mb-1">Complaint Submitted</h3>
                <p className="text-sm text-gray-500 mb-4">
                  Your complaint has been submitted anonymously and will be reviewed by HR leadership.
                </p>
                <button onClick={() => setSubmitSuccess(false)}
                  className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm hover:bg-gray-800">
                  Submit Another
                </button>
              </div>
            ) : (
              <>
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                  <select
                    value={submitCategory}
                    onChange={e => setSubmitCategory(e.target.value as ComplaintCategory)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    {CATEGORIES.map(c => (
                      <option key={c.value} value={c.value}>{c.label}</option>
                    ))}
                  </select>
                </div>

                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description <span className="text-gray-400">(min 10 characters)</span>
                  </label>
                  <textarea
                    value={submitDescription}
                    onChange={e => setSubmitDescription(e.target.value)}
                    rows={6}
                    maxLength={5000}
                    placeholder="Describe the issue in detail..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                  />
                  <p className="text-xs text-gray-400 mt-1">{submitDescription.length}/5000</p>
                </div>

                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 mb-4">
                  <p className="text-xs text-amber-700">
                    <AlertTriangle size={12} className="inline mr-1" />
                    This complaint is fully anonymous. No user identity, IP address, or session information will be stored.
                  </p>
                </div>

                <button
                  onClick={handleSubmit}
                  disabled={submitLoading || submitDescription.trim().length < 10}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send size={14} />
                  {submitLoading ? 'Submitting...' : 'Submit Anonymous Complaint'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ── Detail view (HR only) ──────────────────────────────────────────────
  if (view === 'detail' && selected) {
    return (
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl mx-auto">
          <button onClick={() => { setView('list'); setSelected(null) }}
            className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4">
            <ChevronLeft size={16} /> Back to complaints
          </button>

          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <Shield size={20} className="text-red-500" />
                <h2 className="text-lg font-semibold text-gray-800">Complaint Detail</h2>
              </div>
              <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${STATUS_COLORS[selected.status] || ''}`}>
                {STATUS_LABELS[selected.status] || selected.status}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-6 text-sm">
              <div>
                <p className="text-gray-500">ID</p>
                <p className="font-mono text-xs text-gray-700">{selected.complaint_id.slice(0, 8)}...</p>
              </div>
              <div>
                <p className="text-gray-500">Category</p>
                <p className="text-gray-800 capitalize">{selected.category.replace('_', ' ')}</p>
              </div>
              <div>
                <p className="text-gray-500">Submitted</p>
                <p className="text-gray-800">{formatDate(selected.submitted_at)}</p>
              </div>
              <div>
                <p className="text-gray-500">Reviewed By</p>
                <p className="text-gray-800">{selected.reviewed_by_name || '—'}</p>
              </div>
            </div>

            <div className="mb-6">
              <p className="text-sm font-medium text-gray-700 mb-1">Description</p>
              <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap">
                {selected.description}
              </div>
            </div>

            {selected.resolution && (
              <div className="mb-6">
                <p className="text-sm font-medium text-gray-700 mb-1">Resolution</p>
                <div className="bg-green-50 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap">
                  {selected.resolution}
                </div>
              </div>
            )}

            {/* Review form */}
            <div className="border-t border-gray-200 pt-4">
              <h3 className="text-sm font-semibold text-gray-800 mb-3">Update Status</h3>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Status</label>
                  <select
                    value={reviewStatus}
                    onChange={e => setReviewStatus(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="under_review">Under Review</option>
                    <option value="investigating">Investigating</option>
                    <option value="resolved">Resolved</option>
                    <option value="dismissed">Dismissed</option>
                  </select>
                </div>
              </div>
              <div className="mb-4">
                <label className="block text-xs text-gray-500 mb-1">Resolution Notes</label>
                <textarea
                  value={reviewResolution}
                  onChange={e => setReviewResolution(e.target.value)}
                  rows={3}
                  maxLength={2000}
                  placeholder="Add resolution notes..."
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 resize-none"
                />
              </div>
              <button
                onClick={handleReview}
                disabled={reviewLoading || !reviewStatus}
                className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800 disabled:opacity-50"
              >
                {reviewLoading ? 'Updating...' : 'Update Complaint'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ── List view (HR only) ────────────────────────────────────────────────
  const totalPages = Math.ceil(total / 20)

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold text-gray-800">Complaints & Whistleblower</h1>
            <p className="text-sm text-gray-500">Anonymous complaint management</p>
          </div>
          <button
            onClick={() => setView('submit')}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700"
          >
            <AlertTriangle size={14} /> Submit Complaint
          </button>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
              <p className="text-2xl font-bold text-gray-800">{stats.total}</p>
              <p className="text-xs text-gray-500">Total</p>
            </div>
            {['submitted', 'under_review', 'investigating', 'resolved', 'dismissed'].map(s => (
              <div key={s} className="bg-white rounded-xl border border-gray-200 p-4 text-center">
                <p className="text-2xl font-bold text-gray-800">{stats.by_status[s] || 0}</p>
                <p className="text-xs text-gray-500">{STATUS_LABELS[s]}</p>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="flex items-center gap-1 text-sm text-gray-500">
            <Filter size={14} /> Filters:
          </div>
          <select value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setPage(1) }}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm">
            <option value="">All statuses</option>
            {Object.entries(STATUS_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <select value={filterCategory} onChange={e => { setFilterCategory(e.target.value); setPage(1) }}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm">
            <option value="">All categories</option>
            {CATEGORIES.map(c => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>

        {/* List */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {loading ? (
            <p className="text-sm text-gray-400 text-center py-8">Loading...</p>
          ) : complaints.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">No complaints found</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                <tr>
                  <th className="px-4 py-3 text-left">ID</th>
                  <th className="px-4 py-3 text-left">Category</th>
                  <th className="px-4 py-3 text-left">Description</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Submitted</th>
                  <th className="px-4 py-3 text-left">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {complaints.map(c => (
                  <tr key={c.complaint_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">{c.complaint_id.slice(0, 8)}</td>
                    <td className="px-4 py-3 capitalize">{c.category.replace('_', ' ')}</td>
                    <td className="px-4 py-3 text-gray-600 max-w-xs truncate">{c.description}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[c.status] || ''}`}>
                        {STATUS_LABELS[c.status] || c.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{formatDate(c.submitted_at)}</td>
                    <td className="px-4 py-3">
                      <button onClick={() => openDetail(c.complaint_id)}
                        className="flex items-center gap-1 text-blue-600 hover:text-blue-800 text-xs font-medium">
                        <Eye size={13} /> View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2 mt-4">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg disabled:opacity-40">
              Previous
            </button>
            <span className="text-sm text-gray-500">Page {page} of {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg disabled:opacity-40">
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
