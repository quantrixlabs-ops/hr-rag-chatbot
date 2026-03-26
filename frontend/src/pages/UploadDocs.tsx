import { useState, useEffect, useCallback } from 'react'
import {
  getDocuments, uploadDocument, deleteDocument, batchDeleteDocuments,
  reindexDocument, getPendingDocuments, approveDocument,
} from '../services/api'
import {
  FileText, Upload, Trash2, CheckSquare, Square, MinusSquare, RefreshCw,
  CheckCircle2, XCircle, Clock, Shield,
} from 'lucide-react'

interface Props {
  token: string
  role?: string
}

interface DocItem {
  document_id: string
  title: string
  category: string
  chunk_count: number
  access_roles: string[]
  uploaded_at: number
  version: string | null
  approval_status?: string
  approved_by?: string
  uploaded_by?: string
}

interface PendingDoc {
  document_id: string
  title: string
  category: string
  chunk_count: number
  uploaded_at: number
  version: string | null
  source_filename: string
  uploaded_by: string
  uploaded_by_name: string
}

const APPROVAL_BADGES: Record<string, { color: string; icon: typeof Clock; label: string }> = {
  pending: { color: 'bg-yellow-100 text-yellow-700', icon: Clock, label: 'Pending' },
  approved: { color: 'bg-green-100 text-green-700', icon: CheckCircle2, label: 'Approved' },
  rejected: { color: 'bg-red-100 text-red-700', icon: XCircle, label: 'Rejected' },
}

const HR_HEAD_ROLES = new Set(['hr_head', 'hr_admin', 'admin', 'super_admin'])

export default function UploadDocs({ token, role = '' }: Props) {
  const isHRHead = HR_HEAD_ROLES.has(role)

  const [docs, setDocs] = useState<DocItem[]>([])
  const [pendingDocs, setPendingDocs] = useState<PendingDoc[]>([])
  const [uploading, setUploading] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('auto')
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number; name: string; results: { name: string; ok: boolean; msg: string }[] }>({ current: 0, total: 0, name: '', results: [] })
  const [deleting, setDeleting] = useState<string | null>(null)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [reindexing, setReindexing] = useState<string | null>(null)
  const [approving, setApproving] = useState<string | null>(null)

  const refreshData = useCallback((clearSelection = false) => {
    getDocuments(token).then(d => {
      setDocs(d.documents || [])
      if (clearSelection) setSelected(new Set())
    }).catch(() => {})
  }, [token])

  const refreshPending = useCallback(() => {
    if (isHRHead) {
      getPendingDocuments(token).then(d => setPendingDocs(d.pending || [])).catch(() => {})
    }
  }, [token, isHRHead])

  useEffect(() => { refreshData(true) }, [refreshData])
  useEffect(() => { refreshPending() }, [refreshPending])

  const toggleSelect = (docId: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selected.size === docs.length) setSelected(new Set())
    else setSelected(new Set(docs.map(d => d.document_id)))
  }

  const isAllSelected = docs.length > 0 && selected.size === docs.length
  const isSomeSelected = selected.size > 0 && selected.size < docs.length

  const handleUpload = async () => {
    if (files.length === 0) return
    setUploading(true)
    const results: { name: string; ok: boolean; msg: string }[] = []

    for (let i = 0; i < files.length; i++) {
      const f = files[i]
      // Use custom title for single file, or filename-based title for multi
      const docTitle = files.length === 1 && title.trim()
        ? title.trim()
        : f.name.replace(/\.[^/.]+$/, '').replace(/[_-]/g, ' ')
      setUploadProgress({ current: i + 1, total: files.length, name: f.name, results })
      try {
        await uploadDocument(token, f, docTitle, category, ['employee', 'manager', 'hr_admin'])
        results.push({ name: f.name, ok: true, msg: 'Uploaded' })
      } catch (err: any) {
        results.push({ name: f.name, ok: false, msg: err.message || 'Failed' })
      }
    }

    setUploadProgress({ current: files.length, total: files.length, name: '', results })
    setFiles([])
    setTitle('')
    refreshData(true)
    refreshPending()
    setUploading(false)

    // Show summary
    const ok = results.filter(r => r.ok).length
    const fail = results.filter(r => !r.ok).length
    if (fail === 0) {
      alert(`All ${ok} document(s) uploaded successfully!`)
    } else {
      alert(`${ok} uploaded, ${fail} failed:\n${results.filter(r => !r.ok).map(r => `  - ${r.name}: ${r.msg}`).join('\n')}`)
    }
    setUploadProgress({ current: 0, total: 0, name: '', results: [] })
  }

  const handleDelete = async (docId: string, docTitle: string) => {
    if (!confirm(`Delete "${docTitle}"?\n\nThis will remove the document and all its indexed chunks.`)) return
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

  const handleBulkDelete = async () => {
    const ids = Array.from(selected)
    const titles = docs.filter(d => selected.has(d.document_id)).map(d => d.title)
    if (!confirm(`Delete ${ids.length} document(s)?\n\n${titles.map(t => `  - ${t}`).join('\n')}`)) return
    setBulkDeleting(true)
    try {
      const result = await batchDeleteDocuments(token, ids)
      refreshData(true)
      alert(`Deleted ${result.deleted_count} document(s) (${result.chunks_removed} chunks removed)`)
    } catch (err: any) {
      alert(err.message || 'Batch delete failed')
    } finally {
      setBulkDeleting(false)
    }
  }

  const handleReindex = async (docId?: string) => {
    const label = docId ? 'this document' : 'ALL documents'
    if (!confirm(`Reindex ${label}?`)) return
    setReindexing(docId || 'all')
    try {
      const result = await reindexDocument(token, docId)
      refreshData(true)
      if (docId) alert(`Reindexed: ${result.chunk_count} chunks`)
      else alert(`Reindexed ${result.reindexed} documents (${result.total_chunks} total chunks)`)
    } catch (err: any) {
      alert(err.message || 'Reindex failed')
    } finally {
      setReindexing(null)
    }
  }

  const handleApproval = async (docId: string, action: 'approve' | 'reject', docTitle: string) => {
    if (action === 'reject' && !confirm(`Reject "${docTitle}"? This will remove it from the search index.`)) return
    setApproving(docId)
    try {
      await approveDocument(token, docId, action)
      refreshData(true)
      refreshPending()
    } catch (err: any) {
      alert(err.message || 'Approval action failed')
    } finally {
      setApproving(null)
    }
  }

  const isBusy = deleting !== null || bulkDeleting || reindexing !== null

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Document Management</h1>
          <p className="text-sm text-gray-500 mt-1">Upload, manage, and reindex HR policy documents</p>
        </div>

        {/* Upload Form */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Upload size={18} /> Upload Documents
          </h2>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {files.length <= 1 && (
                <input type="text" placeholder="Document title (optional for multiple)" value={title} onChange={e => setTitle(e.target.value)}
                  className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
              )}
              <select value={category} onChange={e => setCategory(e.target.value)}
                className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                <option value="auto">Auto-detect category</option>
                <option value="policy">Policy</option>
                <option value="handbook">Handbook</option>
                <option value="benefits">Benefits</option>
                <option value="leave">Leave</option>
                <option value="onboarding">Onboarding</option>
                <option value="legal">Legal</option>
              </select>
              <input type="file" accept=".pdf,.docx,.md,.txt" multiple
                onChange={e => {
                  const selected = Array.from(e.target.files || [])
                  setFiles(selected)
                  if (selected.length > 1) setTitle('')
                }}
                className="text-sm file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100" />
            </div>

            {/* Selected files preview */}
            {files.length > 0 && (
              <div className="bg-gray-50 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-medium text-gray-600">{files.length} file(s) selected</p>
                  <button onClick={() => setFiles([])} className="text-xs text-red-500 hover:text-red-700">Clear all</button>
                </div>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {files.map((f, i) => (
                    <div key={i} className="flex items-center justify-between text-xs bg-white rounded px-3 py-1.5 border border-gray-200">
                      <div className="flex items-center gap-2">
                        <FileText size={12} className="text-blue-500" />
                        <span className="text-gray-700">{f.name}</span>
                      </div>
                      <span className="text-gray-400">{(f.size / 1024 / 1024).toFixed(1)} MB</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Upload progress */}
            {uploading && uploadProgress.total > 0 && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-medium text-blue-700">
                    Uploading {uploadProgress.current} of {uploadProgress.total}...
                  </p>
                  <p className="text-xs text-blue-500">{uploadProgress.name}</p>
                </div>
                <div className="w-full h-2 bg-blue-100 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full transition-all duration-300"
                    style={{ width: `${(uploadProgress.current / uploadProgress.total) * 100}%` }} />
                </div>
                {uploadProgress.results.length > 0 && (
                  <div className="mt-2 space-y-0.5">
                    {uploadProgress.results.map((r, i) => (
                      <p key={i} className={`text-[11px] ${r.ok ? 'text-emerald-600' : 'text-red-600'}`}>
                        {r.ok ? '✓' : '✗'} {r.name}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center justify-between">
              <button onClick={handleUpload} disabled={files.length === 0 || uploading}
                className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-40 text-sm font-medium transition-colors flex items-center gap-2">
                <Upload size={14} />
                {uploading ? `Uploading ${uploadProgress.current}/${uploadProgress.total}...` : files.length > 1 ? `Upload ${files.length} Files` : 'Upload & Index'}
              </button>
              {!isHRHead && (
                <p className="text-xs text-amber-600 flex items-center gap-1">
                  <Clock size={12} /> Uploads require HR Head approval.
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Pending Approvals — HR Head only */}
        {isHRHead && pendingDocs.length > 0 && (
          <div className="bg-white rounded-xl border border-yellow-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-yellow-200 bg-yellow-50 flex items-center gap-2">
              <Shield size={18} className="text-yellow-600" />
              <h2 className="text-lg font-semibold text-yellow-800">
                Pending Approval
                <span className="text-sm font-normal text-yellow-600 ml-2">({pendingDocs.length})</span>
              </h2>
            </div>
            <div className="divide-y divide-gray-100">
              {pendingDocs.map(d => (
                <div key={d.document_id} className="px-6 py-3 flex items-center gap-4 hover:bg-gray-50 transition-colors">
                  <FileText size={20} className="text-yellow-500 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{d.title}</p>
                    <p className="text-xs text-gray-500">
                      Uploaded by {d.uploaded_by_name} &middot; {d.category} &middot; {d.chunk_count} chunks &middot; v{d.version || '1.0'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => handleApproval(d.document_id, 'approve', d.title)}
                      disabled={approving === d.document_id}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
                    >
                      <CheckCircle2 size={13} />
                      {approving === d.document_id ? '...' : 'Approve'}
                    </button>
                    <button
                      onClick={() => handleApproval(d.document_id, 'reject', d.title)}
                      disabled={approving === d.document_id}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100 disabled:opacity-50 transition-colors"
                    >
                      <XCircle size={13} />
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Documents Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              Indexed Documents
              {docs.length > 0 && <span className="text-sm font-normal text-gray-400 ml-2">({docs.length})</span>}
            </h2>
            <div className="flex items-center gap-2">
              <button onClick={() => handleReindex()} disabled={isBusy || docs.length === 0}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-40 transition-colors">
                <RefreshCw size={14} className={reindexing === 'all' ? 'animate-spin' : ''} />
                {reindexing === 'all' ? 'Reindexing...' : 'Reindex All'}
              </button>
              {selected.size > 0 && (
                <button onClick={handleBulkDelete} disabled={isBusy}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-40 transition-colors">
                  <Trash2 size={14} />
                  {bulkDeleting ? 'Deleting...' : `Delete Selected (${selected.size})`}
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
                      <button onClick={toggleSelectAll} className="text-gray-400 hover:text-gray-700 transition-colors">
                        {isAllSelected ? <CheckSquare size={18} className="text-blue-600" />
                          : isSomeSelected ? <MinusSquare size={18} className="text-blue-400" />
                          : <Square size={18} />}
                      </button>
                    )}
                  </th>
                  <th className="text-left px-6 py-3 font-medium">Title</th>
                  <th className="text-left px-6 py-3 font-medium">Category</th>
                  <th className="text-left px-6 py-3 font-medium">Status</th>
                  <th className="text-left px-6 py-3 font-medium">Ver</th>
                  <th className="text-left px-6 py-3 font-medium">Chunks</th>
                  <th className="text-right px-6 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {docs.map(d => {
                  const isSelected = selected.has(d.document_id)
                  const badge = APPROVAL_BADGES[d.approval_status || 'approved'] || APPROVAL_BADGES.approved
                  const BadgeIcon = badge.icon
                  return (
                    <tr key={d.document_id} className={`group transition-colors ${isSelected ? 'bg-blue-50/60' : 'hover:bg-gray-50'}`}>
                      <td className="w-12 px-4 py-3">
                        <button onClick={() => toggleSelect(d.document_id)} className="text-gray-400 hover:text-gray-700 transition-colors">
                          {isSelected ? <CheckSquare size={18} className="text-blue-600" /> : <Square size={18} />}
                        </button>
                      </td>
                      <td className="px-6 py-3 font-medium text-gray-900">{d.title}</td>
                      <td className="px-6 py-3">
                        <span className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full text-xs">{d.category}</span>
                      </td>
                      <td className="px-6 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${badge.color}`}>
                          <BadgeIcon size={11} /> {badge.label}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-gray-500 text-xs">{d.version || '1.0'}</td>
                      <td className="px-6 py-3 text-gray-600">{d.chunk_count}</td>
                      <td className="px-6 py-3 text-right flex items-center justify-end gap-1.5">
                        <button onClick={() => handleReindex(d.document_id)} disabled={isBusy}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-gray-100 disabled:opacity-40 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100">
                          <RefreshCw size={12} className={reindexing === d.document_id ? 'animate-spin' : ''} />
                          {reindexing === d.document_id ? '...' : 'Reindex'}
                        </button>
                        <button onClick={() => handleDelete(d.document_id, d.title)} disabled={isBusy}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 rounded-lg hover:bg-red-100 disabled:opacity-40 transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                          title={`Delete ${d.title}`}>
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

          {selected.size > 0 && (
            <div className="px-6 py-3 bg-blue-50 border-t border-blue-100 flex items-center justify-between text-sm">
              <span className="text-blue-700 font-medium">
                {selected.size} of {docs.length} document{docs.length !== 1 ? 's' : ''} selected
              </span>
              <div className="flex items-center gap-3">
                <button onClick={() => setSelected(new Set())} className="text-blue-600 hover:text-blue-800 font-medium transition-colors">
                  Clear selection
                </button>
                <button onClick={handleBulkDelete} disabled={isBusy}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-40 font-medium transition-colors">
                  <Trash2 size={13} />
                  {bulkDeleting ? 'Deleting...' : 'Delete Selected'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
