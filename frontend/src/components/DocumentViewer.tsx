import { useState, useEffect, useRef } from 'react'
import { X, FileText, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { getDocumentContent } from '../services/api'
import type { Citation } from '../types/chat'

interface DocumentPage {
  page: number
  text: string
}

interface DocumentChunk {
  chunk_index: number
  page: number | null
  text_preview: string
  section: string
}

interface DocumentData {
  document_id: string
  title: string
  category: string
  version: string
  page_count: number
  chunk_count: number
  pages: DocumentPage[]
  chunks: DocumentChunk[]
}

interface Props {
  token: string
  citation: Citation
  onClose: () => void
}

export default function DocumentViewer({ token, citation, onClose }: Props) {
  const [doc, setDoc] = useState<DocumentData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const highlightRef = useRef<HTMLSpanElement>(null)

  // Find document_id from citation source by searching documents list
  useEffect(() => {
    setLoading(true)
    setError('')

    // First get the documents list to find the ID
    fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/documents`, {
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    })
      .then(r => r.json())
      .then(data => {
        const match = (data.documents || []).find((d: any) =>
          d.title === citation.source || d.title.includes(citation.source) || citation.source.includes(d.title)
        )
        if (!match) {
          setError(`Document "${citation.source}" not found`)
          setLoading(false)
          return
        }
        return getDocumentContent(token, match.document_id)
      })
      .then(content => {
        if (content) {
          setDoc(content)
          // Jump to the cited page
          if (citation.page) {
            setCurrentPage(Math.min(citation.page, content.pages.length))
          }
        }
      })
      .catch(() => setError('Failed to load document'))
      .finally(() => setLoading(false))
  }, [token, citation.source])

  // Scroll to highlighted text when page changes
  useEffect(() => {
    if (highlightRef.current) {
      highlightRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [currentPage, doc])

  // Highlight the excerpt text within the page content
  const highlightText = (pageText: string, excerpt: string) => {
    if (!excerpt || excerpt.length < 10) return pageText

    // Clean up excerpt for matching
    const cleanExcerpt = excerpt.replace(/\s+/g, ' ').trim().substring(0, 100)
    const idx = pageText.toLowerCase().indexOf(cleanExcerpt.toLowerCase().substring(0, 50))

    if (idx === -1) {
      // Try matching by key phrases (first 30 chars)
      const shortExcerpt = cleanExcerpt.substring(0, 30).toLowerCase()
      const shortIdx = pageText.toLowerCase().indexOf(shortExcerpt)
      if (shortIdx === -1) return pageText

      const before = pageText.substring(0, shortIdx)
      const match = pageText.substring(shortIdx, shortIdx + cleanExcerpt.length)
      const after = pageText.substring(shortIdx + cleanExcerpt.length)
      return { before, match, after }
    }

    const before = pageText.substring(0, idx)
    const match = pageText.substring(idx, idx + cleanExcerpt.length)
    const after = pageText.substring(idx + cleanExcerpt.length)
    return { before, match, after }
  }

  const page = doc?.pages[currentPage - 1]
  const highlighted = page ? highlightText(page.text, citation.excerpt) : null

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-50 rounded-lg">
              <FileText size={20} className="text-blue-600" />
            </div>
            <div>
              <h2 className="font-semibold text-gray-900">{citation.source}</h2>
              <p className="text-xs text-gray-500">
                {doc ? `${doc.category} | Version ${doc.version} | ${doc.page_count} sections | ${doc.chunk_count} chunks` : 'Loading...'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        {/* Citation info bar */}
        <div className="px-6 py-2 bg-amber-50 border-b border-amber-100 flex items-center gap-2">
          <Search size={14} className="text-amber-600" />
          <span className="text-xs text-amber-700">
            Referenced from {citation.page ? `Page/Section ${citation.page}` : 'this document'} — highlighted text was used to generate the answer
          </span>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading && (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin w-8 h-8 border-2 border-blue-600 border-t-transparent rounded-full" />
            </div>
          )}

          {error && (
            <div className="text-center py-20 text-gray-500">
              <FileText size={40} className="mx-auto mb-3 text-gray-300" />
              <p>{error}</p>
            </div>
          )}

          {!loading && !error && page && (
            <div className="prose prose-sm max-w-none">
              {typeof highlighted === 'string' ? (
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-700">{highlighted}</pre>
              ) : highlighted ? (
                <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-700">
                  {highlighted.before}
                  <span ref={highlightRef} className="bg-yellow-200 border-b-2 border-yellow-400 px-0.5 rounded">
                    {highlighted.match}
                  </span>
                  {highlighted.after}
                </pre>
              ) : null}
            </div>
          )}
        </div>

        {/* Page navigation */}
        {doc && doc.pages.length > 1 && (
          <div className="flex items-center justify-between px-6 py-3 border-t border-gray-200 bg-gray-50">
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-200 rounded-lg disabled:opacity-30 transition-colors"
            >
              <ChevronLeft size={16} /> Previous
            </button>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600">Section {currentPage} of {doc.pages.length}</span>
              {citation.page && citation.page !== currentPage && (
                <button
                  onClick={() => setCurrentPage(citation.page!)}
                  className="text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded-lg hover:bg-amber-200 transition-colors"
                >
                  Go to cited section
                </button>
              )}
            </div>
            <button
              onClick={() => setCurrentPage(p => Math.min(doc.pages.length, p + 1))}
              disabled={currentPage >= doc.pages.length}
              className="flex items-center gap-1 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-200 rounded-lg disabled:opacity-30 transition-colors"
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
