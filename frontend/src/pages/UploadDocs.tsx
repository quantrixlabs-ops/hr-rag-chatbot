import { useState, useEffect, useCallback } from 'react'
import { getDocuments, uploadDocument, deleteDocument, batchDeleteDocuments, reindexDocument } from '../services/api'
import { FileText, Upload, Trash2, CheckSquare, Square, MinusSquare, RefreshCw } from 'lucide-react'

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

export default function UploadDocs({ token }: Props) {
  const [docs, setDocs] = useState<DocItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('auto')
  const [deleting, setDeleting] = useState<string | null>(null)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [reindexing, setReindexing] = useState<string | null>(null)

  const refreshData = useCallback((clearSelection = false) => {
    getDocuments(token).then(d => {
      setDocs(d.documents || [])
      if (clearSelection) setSelected(new Set())
    }).catch(() => {})
  }, [token])

  useEffect(() => { refreshData(true) }, [refreshData])

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
    if (!file || !title) return
    setUploading(true)
    try {
      await uploadDocument(token, file, title, category, ['employee', 'manager', 'hr_admin'])
      setFile(null)
      setTitle('')
      refreshData(true)
    } catch (err: any) {
      alert(err.message || 'Upload failed')
    } finally {
      setUploading(false)
    }
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
            <Upload size={18} /> Upload Document
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <input type="text" placeholder="Document title" value={title} onChange={e => setTitle(e.target.value)}
              className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
            <select value={category} onChange={e => setCategory(e.target.value)}
              className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent">
              <option value="auto">Auto-detect</option>
              <option value="policy">Policy</option>
              <option value="handbook">Handbook</option>
              <option value="benefits">Benefits</option>
              <option value="leave">Leave</option>
              <option value="onboarding">Onboarding</option>
              <option value="legal">Legal</option>
            </select>
            <input type="file" accept=".pdf,.docx,.md,.txt" onChange={e => setFile(e.target.files?.[0] || null)}
              className="text-sm file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-blue-50 file:text-blue-600 hover:file:bg-blue-100" />
            <button onClick={handleUpload} disabled={!file || !title || uploading}
              className="px-6 py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-40 text-sm font-medium transition-colors">
              {uploading ? 'Uploading...' : 'Upload & Index'}
            </button>
          </div>
        </div>

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
                      <td className="px-6 py-3 text-gray-500 text-xs">{d.version || '1.0'}</td>
                      <td className="px-6 py-3 text-gray-600">{d.chunk_count}</td>
                      <td className="px-6 py-3 text-gray-500 text-xs">{d.access_roles?.join(', ')}</td>
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
