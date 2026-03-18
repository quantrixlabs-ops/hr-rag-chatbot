import { useState, useEffect, useCallback } from 'react'
import { getMetrics, getDocuments, uploadDocument, deleteDocument, batchDeleteDocuments, reindexDocument, getFailedQueries, getSecurityEvents } from '../services/api'
import type { AdminMetrics } from '../types/chat'
import { BarChart3, FileText, Upload, AlertTriangle, Clock, Shield, Trash2, CheckSquare, Square, MinusSquare, RefreshCw, ShieldAlert, XCircle, TrendingUp } from 'lucide-react'

interface Props {
  token: string
}

interface DocItem {
  document_id: string
  title: string
  category: string
  chunk_count: number
  access_roles: string[]
  uploaded_at: number
  version: string | null
}

function StatCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-3">
        <div className={`p-2.5 rounded-lg ${color}`}>{icon}</div>
        <div>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          <p className="text-xs text-gray-500">{label}</p>
        </div>
      </div>
    </div>
  )
}

export default function AdminDashboard({ token }: Props) {
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null)
  const [docs, setDocs] = useState<DocItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('policy')
  const [deleting, setDeleting] = useState<string | null>(null)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [reindexing, setReindexing] = useState<string | null>(null)  // doc id or 'all'
  const [tab, setTab] = useState<'docs' | 'failed' | 'security'>('docs')
  const [failedQueries, setFailedQueries] = useState<any[]>([])
  const [securityEvents, setSecurityEvents] = useState<any[]>([])

  const refreshData = useCallback((clearSelection = false) => {
    getDocuments(token).then(d => {
      setDocs(d.documents || [])
      if (clearSelection) setSelected(new Set())
    }).catch(() => {})
    getMetrics(token).then(setMetrics).catch(() => {})
    getFailedQueries(token).then(d => setFailedQueries(d.failed_queries || [])).catch(() => {})
    getSecurityEvents(token).then(d => setSecurityEvents(d.events || [])).catch(() => {})
  }, [token])

  useEffect(() => { refreshData(true) }, [refreshData])

  // ── Selection helpers ──────────────────────────────────────────────
  const toggleSelect = (docId: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selected.size === docs.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(docs.map(d => d.document_id)))
    }
  }

  const isAllSelected = docs.length > 0 && selected.size === docs.length
  const isSomeSelected = selected.size > 0 && selected.size < docs.length

  // ── Upload ─────────────────────────────────────────────────────────
  const handleUpload = async () => {
    if (!file || !title) return
    setUploading(true)
    try {
      await uploadDocument(token, file, title, category, ['employee', 'manager', 'hr_admin'])
      setFile(null)
      setTitle('')
      refreshData(true)
    } catch (err) {
      alert('Upload failed')
    } finally {
      setUploading(false)
    }
  }

  // ── Single delete ──────────────────────────────────────────────────
  const handleDelete = async (docId: string, docTitle: string) => {
    if (!confirm(`Delete "${docTitle}"?\n\nThis will remove the document and all its indexed chunks from the vector store. This action cannot be undone.`)) return
    setDeleting(docId)
    try {
      const result = await deleteDocument(token, docId)
      refreshData(true)
      alert(`Deleted "${docTitle}" (${result.chunks_removed} chunks removed)`)
    } catch (err: any) {
      alert(err.message || 'Delete failed')
    } finally {
      setDeleting(null)
    }
  }

  // ── Bulk delete ────────────────────────────────────────────────────
  const handleBulkDelete = async () => {
    const ids = Array.from(selected)
    const titles = docs.filter(d => selected.has(d.document_id)).map(d => d.title)
    const totalChunks = docs.filter(d => selected.has(d.document_id)).reduce((sum, d) => sum + d.chunk_count, 0)

    if (!confirm(
      `Delete ${ids.length} document${ids.length > 1 ? 's' : ''}?\n\n` +
      titles.map(t => `  - ${t}`).join('\n') +
      `\n\nThis will remove ${totalChunks} chunks from the vector store. This action cannot be undone.`
    )) return

    setBulkDeleting(true)
    try {
      const result = await batchDeleteDocuments(token, ids)
      refreshData(true)
      alert(`Deleted ${result.deleted_count} document${result.deleted_count > 1 ? 's' : ''} (${result.chunks_removed} chunks removed)`)
    } catch (err: any) {
      alert(err.message || 'Batch delete failed')
    } finally {
      setBulkDeleting(false)
    }
  }

  // ── Reindex ────────────────────────────────────────────────────────
  const handleReindex = async (docId?: string) => {
    const label = docId ? 'this document' : 'ALL documents'
    if (!confirm(`Reindex ${label}? This will rebuild the vector index from source files.`)) return
    setReindexing(docId || 'all')
    try {
      const result = await reindexDocument(token, docId)
      refreshData(true)
      if (docId) {
        alert(`Reindexed: ${result.chunk_count} chunks`)
      } else {
        alert(`Reindexed ${result.reindexed} documents (${result.total_chunks} total chunks)${result.errors?.length ? `\n${result.errors.length} errors` : ''}`)
      }
    } catch (err: any) {
      alert(err.message || 'Reindex failed')
    } finally {
      setReindexing(null)
    }
  }

  const isBusy = deleting !== null || bulkDeleting || reindexing !== null

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>

        {/* Metrics Grid */}
        {metrics && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard icon={<BarChart3 size={18} className="text-blue-600" />} label="Queries Today" value={metrics.queries_today} color="bg-blue-50" />
            <StatCard icon={<Clock size={18} className="text-amber-600" />} label="Avg Latency" value={`${metrics.avg_latency_ms}ms`} color="bg-amber-50" />
            <StatCard icon={<Shield size={18} className="text-emerald-600" />} label="Faithfulness" value={`${Math.round(metrics.avg_faithfulness * 100)}%`} color="bg-emerald-50" />
            <StatCard icon={<AlertTriangle size={18} className="text-red-600" />} label="Hallucination Rate" value={`${Math.round(metrics.hallucination_rate * 100)}%`} color="bg-red-50" />
            <StatCard icon={<FileText size={18} className="text-purple-600" />} label="Documents" value={metrics.total_documents} color="bg-purple-50" />
            <StatCard icon={<BarChart3 size={18} className="text-indigo-600" />} label="Total Chunks" value={metrics.total_chunks} color="bg-indigo-50" />
            <StatCard icon={<BarChart3 size={18} className="text-cyan-600" />} label="Active Sessions" value={metrics.active_sessions} color="bg-cyan-50" />
            <StatCard icon={<BarChart3 size={18} className="text-rose-600" />} label="Queries This Week" value={metrics.queries_this_week} color="bg-rose-50" />
          </div>
        )}

        {/* Top Documents */}
        {metrics && (metrics as any).top_documents?.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
              <TrendingUp size={16} /> Top Documents Accessed (7d)
            </h2>
            <div className="space-y-2">
              {(metrics as any).top_documents.slice(0, 5).map((d: any, i: number) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span className="text-gray-700 truncate flex-1">{d.source}</span>
                  <span className="text-gray-400 ml-3">{d.query_count} queries</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="flex gap-1 border-b border-gray-200">
          {([['docs', 'Documents', FileText], ['failed', 'Failed Queries', XCircle], ['security', 'Security Events', ShieldAlert]] as const).map(([key, label, Icon]) => (
            <button key={key} onClick={() => setTab(key as any)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${tab === key ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
              <Icon size={15} /> {label}
              {key === 'failed' && failedQueries.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 text-xs bg-red-100 text-red-600 rounded-full">{failedQueries.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* ── Documents Tab ── */}
        {tab === 'docs' && <>

        {/* Upload Section */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Upload size={18} /> Upload Document
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <input type="text" placeholder="Document title" value={title} onChange={e => setTitle(e.target.value)}
              className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
            <select value={category} onChange={e => setCategory(e.target.value)}
              className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent">
              <option value="policy">Policy</option>
              <option value="handbook">Handbook</option>
              <option value="benefits">Benefits</option>
              <option value="leave">Leave</option>
              <option value="onboarding">Onboarding</option>
              <option value="legal">Legal</option>
            </select>
            <input type="file" accept=".pdf,.docx,.md,.txt" onChange={e => setFile(e.target.files?.[0] || null)}
              className="text-sm file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100" />
          </div>
          <button onClick={handleUpload} disabled={!file || !title || uploading}
            className="mt-4 px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-40 text-sm font-medium transition-colors">
            {uploading ? 'Uploading...' : 'Upload & Index'}
          </button>
        </div>

        {/* Documents Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              Indexed Documents
              {docs.length > 0 && <span className="text-sm font-normal text-gray-400 ml-2">({docs.length})</span>}
            </h2>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleReindex()}
                disabled={isBusy || docs.length === 0}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-40 transition-colors"
              >
                <RefreshCw size={14} className={reindexing === 'all' ? 'animate-spin' : ''} />
                {reindexing === 'all' ? 'Reindexing...' : 'Reindex All'}
              </button>
              {selected.size > 0 && (
              <button
                onClick={handleBulkDelete}
                disabled={isBusy}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-40 transition-colors"
              >
                <Trash2 size={14} />
                {bulkDeleting
                  ? 'Deleting...'
                  : `Delete Selected (${selected.size})`
                }
              </button>
            )}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="w-12 px-4 py-3">
                    {docs.length > 0 && (
                      <button onClick={toggleSelectAll} className="text-gray-400 hover:text-gray-700 transition-colors" title={isAllSelected ? 'Deselect all' : 'Select all'}>
                        {isAllSelected
                          ? <CheckSquare size={18} className="text-blue-600" />
                          : isSomeSelected
                            ? <MinusSquare size={18} className="text-blue-400" />
                            : <Square size={18} />
                        }
                      </button>
                    )}
                  </th>
                  <th className="text-left px-6 py-3 font-medium">Title</th>
                  <th className="text-left px-6 py-3 font-medium">Category</th>
                  <th className="text-left px-6 py-3 font-medium">Ver</th>
                  <th className="text-left px-6 py-3 font-medium">Chunks</th>
                  <th className="text-left px-6 py-3 font-medium">Access</th>
                  <th className="text-right px-6 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {docs.map(d => {
                  const isSelected = selected.has(d.document_id)
                  return (
                    <tr
                      key={d.document_id}
                      className={`group transition-colors ${isSelected ? 'bg-blue-50/60' : 'hover:bg-gray-50'}`}
                    >
                      <td className="w-12 px-4 py-3">
                        <button onClick={() => toggleSelect(d.document_id)} className="text-gray-400 hover:text-gray-700 transition-colors">
                          {isSelected
                            ? <CheckSquare size={18} className="text-blue-600" />
                            : <Square size={18} />
                          }
                        </button>
                      </td>
                      <td className="px-6 py-3 font-medium text-gray-900">{d.title}</td>
                      <td className="px-6 py-3">
                        <span className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full text-xs">{d.category}</span>
                      </td>
                      <td className="px-6 py-3 text-gray-500 text-xs">{d.version || '1.0'}</td>
                      <td className="px-6 py-3 text-gray-600">{d.chunk_count}</td>
                      <td className="px-6 py-3 text-gray-500 text-xs">{d.access_roles?.join(', ')}</td>
                      <td className="px-6 py-3 text-right flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => handleReindex(d.document_id)}
                          disabled={isBusy}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-gray-100 disabled:opacity-40 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                          title={`Reindex ${d.title}`}
                        >
                          <RefreshCw size={12} className={reindexing === d.document_id ? 'animate-spin' : ''} />
                          {reindexing === d.document_id ? '...' : 'Reindex'}
                        </button>
                        <button
                          onClick={() => handleDelete(d.document_id, d.title)}
                          disabled={isBusy}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100 disabled:opacity-40 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                          title={`Delete ${d.title}`}
                        >
                          <Trash2 size={13} />
                          {deleting === d.document_id ? 'Deleting...' : 'Delete'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {docs.length === 0 && (
                  <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-400">No documents indexed yet</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Selection footer */}
          {selected.size > 0 && (
            <div className="px-6 py-3 bg-blue-50 border-t border-blue-100 flex items-center justify-between text-sm">
              <span className="text-blue-700 font-medium">
                {selected.size} of {docs.length} document{docs.length !== 1 ? 's' : ''} selected
                {' '}
                ({docs.filter(d => selected.has(d.document_id)).reduce((s, d) => s + d.chunk_count, 0)} chunks)
              </span>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setSelected(new Set())}
                  className="text-blue-600 hover:text-blue-800 font-medium transition-colors"
                >
                  Clear selection
                </button>
                <button
                  onClick={handleBulkDelete}
                  disabled={isBusy}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-40 font-medium transition-colors"
                >
                  <Trash2 size={13} />
                  {bulkDeleting ? 'Deleting...' : 'Delete Selected'}
                </button>
              </div>
            </div>
          )}
        </div>
        </>}

        {/* ── Failed Queries Tab ── */}
        {tab === 'failed' && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Failed Queries
                {failedQueries.length > 0 && <span className="text-sm font-normal text-gray-400 ml-2">({failedQueries.length})</span>}
              </h2>
              <p className="text-xs text-gray-500 mt-1">Queries with low confidence or negative feedback</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="text-left px-6 py-3 font-medium">Query Hash</th>
                    <th className="text-left px-6 py-3 font-medium">Type</th>
                    <th className="text-left px-6 py-3 font-medium">Faithfulness</th>
                    <th className="text-left px-6 py-3 font-medium">Hallucination</th>
                    <th className="text-left px-6 py-3 font-medium">Reason</th>
                    <th className="text-left px-6 py-3 font-medium">Latency</th>
                    <th className="text-left px-6 py-3 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {failedQueries.map((q: any, i: number) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-6 py-3 font-mono text-xs text-gray-600">{q.query_hash}</td>
                      <td className="px-6 py-3">{q.query_type || '—'}</td>
                      <td className="px-6 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${(q.faithfulness_score || 0) < 0.4 ? 'bg-red-50 text-red-700' : 'bg-yellow-50 text-yellow-700'}`}>
                          {Math.round((q.faithfulness_score || 0) * 100)}%
                        </span>
                      </td>
                      <td className="px-6 py-3 text-gray-600">{Math.round((q.hallucination_risk || 0) * 100)}%</td>
                      <td className="px-6 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs ${q.failure_reason === 'low_faithfulness' ? 'bg-red-50 text-red-600' : 'bg-orange-50 text-orange-600'}`}>
                          {q.failure_reason === 'low_faithfulness' ? 'Low confidence' : 'Negative feedback'}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-gray-500">{Math.round(q.latency_ms || 0)}ms</td>
                      <td className="px-6 py-3 text-gray-400 text-xs">{q.timestamp ? new Date(q.timestamp * 1000).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                  {failedQueries.length === 0 && (
                    <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-400">No failed queries recorded</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Security Events Tab ── */}
        {tab === 'security' && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                Security Events
                {securityEvents.length > 0 && <span className="text-sm font-normal text-gray-400 ml-2">({securityEvents.length})</span>}
              </h2>
              <p className="text-xs text-gray-500 mt-1">Audit trail of security-relevant actions</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="text-left px-6 py-3 font-medium">Event</th>
                    <th className="text-left px-6 py-3 font-medium">User</th>
                    <th className="text-left px-6 py-3 font-medium">IP</th>
                    <th className="text-left px-6 py-3 font-medium">Details</th>
                    <th className="text-left px-6 py-3 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {securityEvents.map((e: any, i: number) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-6 py-3">
                        <span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-mono">{e.event_type}</span>
                      </td>
                      <td className="px-6 py-3 text-gray-600 text-xs font-mono">{e.user_id || '—'}</td>
                      <td className="px-6 py-3 text-gray-500 text-xs">{e.ip_address || '—'}</td>
                      <td className="px-6 py-3 text-gray-500 text-xs max-w-xs truncate">{JSON.stringify(e.details)}</td>
                      <td className="px-6 py-3 text-gray-400 text-xs">{e.timestamp ? new Date(e.timestamp * 1000).toLocaleString() : '—'}</td>
                    </tr>
                  ))}
                  {securityEvents.length === 0 && (
                    <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-400">No security events recorded</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
