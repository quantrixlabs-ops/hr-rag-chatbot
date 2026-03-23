import { useState, useEffect, useRef, useMemo } from 'react'
import { X, FileText, ChevronLeft, ChevronRight, BookOpen, Hash, Layers, Tag, Search } from 'lucide-react'
import { getDocumentContent } from '../services/api'
import type { Citation } from '../types/chat'

interface DocumentPage {
  page: number
  text: string
}

interface DocumentData {
  document_id: string
  title: string
  category: string
  version: string
  page_count: number
  chunk_count: number
  pages: DocumentPage[]
}

interface Props {
  token: string
  citation: Citation
  onClose: () => void
}

/**
 * Find the section (1-indexed) whose text best matches the citation excerpt.
 * Returns the page number to navigate to.
 */
function findExcerptPage(pages: DocumentPage[], excerpt: string): number {
  if (!excerpt || excerpt.length < 10 || pages.length === 0) return 1

  const clean = excerpt.replace(/\s+/g, ' ').trim().toLowerCase()

  // Try progressively shorter substrings of the excerpt
  for (const len of [100, 60, 40, 25]) {
    const needle = clean.substring(0, Math.min(len, clean.length))
    for (let i = 0; i < pages.length; i++) {
      if (pages[i].text.toLowerCase().includes(needle)) return i + 1
    }
  }

  // Fallback: score each page by keyword overlap with the excerpt
  const excerptWords = new Set(clean.split(/\s+/).filter(w => w.length > 3))
  if (excerptWords.size === 0) return 1

  let bestPage = 1
  let bestScore = 0
  for (let i = 0; i < pages.length; i++) {
    const pageWords = pages[i].text.toLowerCase()
    let score = 0
    excerptWords.forEach(w => { if (pageWords.includes(w)) score++ })
    if (score > bestScore) { bestScore = score; bestPage = i + 1 }
  }
  return bestPage
}

/** Convert markdown-like text to styled HTML */
function renderMarkdown(text: string, excerpt: string): string {
  let html = text
    // Escape HTML
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Headings
    .replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold text-gray-900 mt-6 mb-2 flex items-center gap-2"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0"></span>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-lg font-bold text-gray-900 mt-8 mb-3 pb-2 border-b border-gray-200">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold text-gray-900 mt-4 mb-4 pb-3 border-b-2 border-emerald-500">$1</h1>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-gray-900">$1</strong>')
    // Numbered lists
    .replace(/^(\d+)\. (.+)$/gm, '<div class="flex gap-3 my-1.5 ml-2"><span class="flex-shrink-0 w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 text-xs font-bold flex items-center justify-center">$1</span><span class="text-gray-700 leading-relaxed pt-0.5">$2</span></div>')
    // Bullet lists
    .replace(/^- (.+)$/gm, '<div class="flex gap-3 my-1.5 ml-4"><span class="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-gray-400 mt-2"></span><span class="text-gray-700 leading-relaxed">$1</span></div>')
    // Paragraphs (double newlines)
    .replace(/\n\n/g, '</p><p class="text-gray-700 leading-relaxed my-3">')
    // Single newlines within content (not after elements)
    .replace(/\n/g, '<br/>')

  // Wrap in paragraph
  html = '<p class="text-gray-700 leading-relaxed my-3">' + html + '</p>'

  // Clean up empty paragraphs
  html = html.replace(/<p class="[^"]*"><\/p>/g, '')
  html = html.replace(/<p class="[^"]*"><br\/><\/p>/g, '')

  // Highlight the excerpt
  if (excerpt && excerpt.length >= 10) {
    const cleanExcerpt = excerpt.replace(/\s+/g, ' ').trim()
    // Try progressively shorter matches
    for (const len of [80, 50, 30, 20]) {
      const search = cleanExcerpt.substring(0, Math.min(len, cleanExcerpt.length))
      const escaped = search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      const regex = new RegExp(`(${escaped})`, 'i')
      if (regex.test(html)) {
        html = html.replace(regex,
          '<mark class="bg-amber-100 border-l-4 border-amber-400 px-1 py-0.5 rounded-r not-italic" id="highlight-target">$1</mark>'
        )
        break
      }
    }
  }

  return html
}

const CATEGORY_COLORS: Record<string, string> = {
  leave: 'bg-violet-100 text-violet-700',
  benefits: 'bg-emerald-100 text-emerald-700',
  handbook: 'bg-blue-100 text-blue-700',
  policy: 'bg-amber-100 text-amber-700',
  onboarding: 'bg-pink-100 text-pink-700',
  legal: 'bg-red-100 text-red-700',
  compensation: 'bg-cyan-100 text-cyan-700',
  performance: 'bg-orange-100 text-orange-700',
}

export default function DocumentViewer({ token, citation, onClose }: Props) {
  const [doc, setDoc] = useState<DocumentData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [sourcePage, setSourcePage] = useState(1) // the page where the excerpt was actually found
  const contentRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setLoading(true)
    setError('')
    const base = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    fetch(`${base}/documents`, {
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    })
      .then(r => r.json())
      .then(data => {
        const docs = data.documents || []
        const src = (citation.source || '').toLowerCase().trim()
        // Try exact match first, then partial matches
        const match = docs.find((d: any) => d.title.toLowerCase() === src)
          || docs.find((d: any) => d.title.toLowerCase().includes(src) || src.includes(d.title.toLowerCase()))
          || docs.find((d: any) => {
            // Fuzzy: compare words overlap
            const srcWords = src.split(/\s+/)
            const titleWords = d.title.toLowerCase().split(/\s+/)
            const overlap = srcWords.filter((w: string) => titleWords.includes(w)).length
            return overlap >= Math.min(2, srcWords.length)
          })
        if (!match) { setError(`Document "${citation.source}" not found in your documents list`); setLoading(false); return }
        return getDocumentContent(token, match.document_id)
      })
      .then(content => {
        if (content) {
          setDoc(content)
          // Find the actual section containing the cited excerpt — NOT just citation.page
          const found = findExcerptPage(content.pages, citation.excerpt)
          setSourcePage(found)
          setCurrentPage(found)
        }
      })
      .catch(() => setError('Failed to load document'))
      .finally(() => setLoading(false))
  }, [token, citation.source])

  // Scroll to highlight after render
  useEffect(() => {
    if (!loading && doc) {
      setTimeout(() => {
        const el = document.getElementById('highlight-target')
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 150)
    }
  }, [currentPage, loading, doc])

  const page = doc?.pages[currentPage - 1]
  const renderedHTML = useMemo(
    () => page ? renderMarkdown(page.text, citation.excerpt) : '',
    [page, citation.excerpt]
  )

  const catColor = CATEGORY_COLORS[doc?.category || ''] || 'bg-gray-100 text-gray-700'

  // Build section sidebar from page titles
  const sections = useMemo(() => {
    if (!doc) return []
    return doc.pages.map((p, i) => {
      const firstLine = p.text.split('\n').find(l => l.trim())?.replace(/^#+\s*/, '').trim() || `Section ${i + 1}`
      return { page: i + 1, title: firstLine.substring(0, 40) }
    })
  }, [doc])

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden"
           onClick={e => e.stopPropagation()}>

        {/* ── Header ── */}
        <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-gray-50 to-white border-b border-gray-200">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-xl shadow-sm">
              <FileText size={22} className="text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-900">{doc?.title || citation.source}</h2>
              <div className="flex items-center gap-3 mt-1">
                {doc && (
                  <>
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${catColor}`}>
                      <Tag size={10} /> {doc.category}
                    </span>
                    <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                      <Hash size={10} /> v{doc.version}
                    </span>
                    <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                      <Layers size={10} /> {doc.chunk_count} chunks
                    </span>
                    <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                      <BookOpen size={10} /> {doc.page_count} sections
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-xl transition-colors">
            <X size={20} className="text-gray-400" />
          </button>
        </div>

        {/* ── Citation banner ── */}
        <div className="px-6 py-2.5 bg-amber-50 border-b border-amber-100 flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-xs font-medium text-amber-700">
            Answer sourced from Section {sourcePage}
          </span>
          {citation.excerpt && (
            <span className="text-xs text-amber-500 ml-1 truncate max-w-md">
              — "{citation.excerpt.substring(0, 60)}..."
            </span>
          )}
        </div>

        {/* ── Body: sidebar + content ── */}
        <div className="flex flex-1 overflow-hidden">

          {/* Section sidebar */}
          {doc && doc.pages.length > 1 && (
            <div className="w-56 border-r border-gray-100 bg-gray-50/50 overflow-y-auto flex-shrink-0">
              <div className="px-3 py-3">
                <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2 px-2">Sections</p>
                {sections.map(s => (
                  <button key={s.page} onClick={() => setCurrentPage(s.page)}
                    className={`w-full text-left px-3 py-2 rounded-lg text-xs mb-0.5 transition-colors ${
                      currentPage === s.page
                        ? 'bg-emerald-100 text-emerald-800 font-medium'
                        : 'text-gray-600 hover:bg-gray-100'
                    }`}>
                    <span className="text-[10px] text-gray-400 mr-1.5">{s.page}.</span>
                    {s.title}
                    {sourcePage === s.page && (
                      <span className="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-amber-400" title="Source section" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Main content */}
          <div className="flex-1 overflow-y-auto" ref={contentRef}>
            {loading && (
              <div className="flex flex-col items-center justify-center py-24">
                <div className="animate-spin w-10 h-10 border-3 border-emerald-500 border-t-transparent rounded-full mb-4" />
                <p className="text-sm text-gray-400">Loading document...</p>
              </div>
            )}

            {error && (
              <div className="flex flex-col items-center justify-center py-24 text-gray-400">
                <FileText size={48} className="mb-4 text-gray-200" />
                <p className="font-medium text-gray-500">{error}</p>
              </div>
            )}

            {!loading && !error && page && (
              <div className="px-8 py-6 max-w-3xl mx-auto">
                <div dangerouslySetInnerHTML={{ __html: renderedHTML }} />
              </div>
            )}
          </div>
        </div>

        {/* ── Footer navigation ── */}
        {doc && doc.pages.length > 1 && (
          <div className="flex items-center justify-between px-6 py-3 border-t border-gray-200 bg-gray-50/80">
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-30 transition-colors"
            >
              <ChevronLeft size={16} /> Previous
            </button>
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-500">
                Section <strong className="text-gray-700">{currentPage}</strong> of {doc.pages.length}
              </span>
              {sourcePage !== currentPage && (
                <button
                  onClick={() => setCurrentPage(sourcePage)}
                  className="flex items-center gap-1.5 text-xs font-medium bg-amber-100 text-amber-700 px-3 py-1.5 rounded-lg hover:bg-amber-200 transition-colors"
                >
                  <Search size={12} /> Jump to source
                </button>
              )}
            </div>
            <button
              onClick={() => setCurrentPage(p => Math.min(doc.pages.length, p + 1))}
              disabled={currentPage >= doc.pages.length}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-30 transition-colors"
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
