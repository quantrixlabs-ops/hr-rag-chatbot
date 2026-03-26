import { useState } from 'react'
import { ThumbsUp, ThumbsDown, FileText, Shield, ExternalLink, AlertCircle, AlertTriangle, Brain, Copy, Check, X, Send } from 'lucide-react'
import type { ChatMessage, Citation } from '../types/chat'

interface Props {
  message: ChatMessage
  onFeedback?: (rating: string) => void
  onDetailedFeedback?: (issueCategory: string, comment: string) => void
  givenFeedback?: string  // 'positive' | 'negative' | undefined
  onSuggestedClick?: (question: string) => void
  onCitationClick?: (citation: Citation) => void
  onEscalate?: (query: string, answer: string) => void
}

function ConfidenceBadge({ score, sourceCount }: { score: number; sourceCount?: number }) {
  const pct = Math.round(score * 100)
  const barColor =
    pct >= 70 ? 'bg-emerald-500' :
    pct >= 40 ? 'bg-amber-500' :
               'bg-red-500'
  const textColor =
    pct >= 70 ? 'text-emerald-700' :
    pct >= 40 ? 'text-amber-700' :
               'text-red-700'
  const label =
    pct >= 70 ? 'High confidence' :
    pct >= 40 ? 'Moderate confidence' :
               'Low confidence'

  return (
    <div className="group relative inline-flex items-center gap-2">
      {/* Mini progress bar */}
      <div className="flex items-center gap-1.5">
        <Shield size={10} className={textColor} />
        <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`text-[11px] font-medium ${textColor}`}>{pct}%</span>
      </div>
      {/* Tooltip on hover */}
      <div className="absolute bottom-full left-0 mb-1.5 hidden group-hover:block z-10">
        <div className="bg-gray-900 text-white text-[10px] rounded-lg px-2.5 py-1.5 whitespace-nowrap shadow-lg">
          <p className="font-medium">{label}</p>
          {sourceCount !== undefined && sourceCount > 0 && (
            <p className="text-gray-400 mt-0.5">Based on {sourceCount} source{sourceCount > 1 ? 's' : ''}</p>
          )}
        </div>
      </div>
    </div>
  )
}

function IntentBadge({ intent }: { intent: string }) {
  const labels: Record<string, { label: string; color: string }> = {
    compound: { label: 'Multi-part', color: 'bg-purple-50 text-purple-700 border-purple-200' },
    sensitive: { label: 'Sensitive', color: 'bg-orange-50 text-orange-700 border-orange-200' },
    calculation: { label: 'Calculation', color: 'bg-blue-50 text-blue-700 border-blue-200' },
    comparative: { label: 'Comparison', color: 'bg-indigo-50 text-indigo-700 border-indigo-200' },
    procedural: { label: 'How-to', color: 'bg-teal-50 text-teal-700 border-teal-200' },
  }
  const info = labels[intent]
  if (!info) return null

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${info.color}`}>
      <Brain size={10} />
      {info.label}
    </span>
  )
}

/** Render markdown-like LLM output as styled HTML */
function renderAnswer(text: string): string {
  // Phase 3: Pre-process tables before general rendering
  let html = renderTables(text)

  html = html
    // Remove [Source: ...] tags (already shown in citations below)
    .replace(/\[Source:.*?\]/g, '')
    .replace(/\[Relevance:.*?\]/g, '')
    // Escape HTML (skip already-rendered table HTML)
    .replace(/&(?!amp;|lt;|gt;|#)/g, '&amp;')
    .replace(/<(?!\/?(?:table|thead|tbody|tr|th|td|div|span)\b)/g, '&lt;')
    .replace(/(?<!["=\w])>/g, '&gt;')
    // Bold: **text**
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic: *text*
    .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
    // Phase 3: Horizontal dividers --- → styled separator
    .replace(/^---+$/gm, '<div class="my-3 border-t border-gray-200"></div>')
    // Phase 3: Next Steps / Important / Note callout blocks
    .replace(/^\*\*(?:Next Steps?|Action Required|What to do next)[:\s]*\*\*/gim,
      '<div class="mt-3 mb-1 flex items-center gap-1.5 text-emerald-700 font-semibold text-[13px]"><span class="inline-block w-4 h-4 rounded bg-emerald-100 text-center text-[10px] leading-4">→</span>Next Steps</div>')
    .replace(/^\*\*Important[:\s]*\*\*/gim,
      '<div class="mt-3 mb-1 flex items-center gap-1.5 text-orange-700 font-semibold text-[13px]"><span class="inline-block w-4 h-4 rounded bg-orange-100 text-center text-[10px] leading-4">!</span>Important</div>')
    .replace(/^\*\*Note[:\s]*\*\*/gim,
      '<div class="mt-2 mb-1 flex items-center gap-1.5 text-blue-700 font-semibold text-[13px]"><span class="inline-block w-4 h-4 rounded bg-blue-100 text-center text-[10px] leading-4">i</span>Note</div>')
    // Numbered lists: "1. text"
    .replace(/^(\d+)\.\s+(.+)$/gm,
      '<li class="flex gap-2 my-1"><span class="flex-shrink-0 min-w-[20px] h-5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-bold flex items-center justify-center">$1</span><span>$2</span></li>')
    // Bullet lists: "- text" or "* text"
    .replace(/^[\-\*]\s+(.+)$/gm,
      '<li class="flex gap-2 my-1"><span class="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-gray-400 mt-[7px]"></span><span>$1</span></li>')
    // Headers
    .replace(/^###\s+(.+)$/gm, '<h4 class="font-semibold text-gray-900 mt-3 mb-1">$1</h4>')
    .replace(/^##\s+(.+)$/gm, '<h3 class="font-semibold text-gray-900 mt-3 mb-1">$1</h3>')
    .replace(/^#\s+(.+)$/gm, '<h3 class="font-bold text-gray-900 mt-3 mb-1">$1</h3>')
    // Double newlines → paragraph break
    .replace(/\n\n+/g, '<br/><br/>')
    // Single newlines (keep as line breaks only within non-list content)
    .replace(/\n/g, '<br/>')
    // Clean up excess breaks
    .replace(/(<br\/>){3,}/g, '<br/><br/>')

  // Trim trailing breaks
  html = html.replace(/^(<br\/>)+/, '').replace(/(<br\/>)+$/, '')

  return html
}

/** Phase 3: Convert markdown tables to styled HTML tables */
function renderTables(text: string): string {
  // Match markdown table blocks: header | separator | rows
  return text.replace(
    /^(\|.+\|)\n(\|[\s\-:|]+\|)\n((?:\|.+\|\n?)+)/gm,
    (_match, headerLine: string, _sepLine: string, bodyBlock: string) => {
      const headers = headerLine.split('|').filter((c: string) => c.trim())
      const rows = bodyBlock.trim().split('\n').map((row: string) =>
        row.split('|').filter((c: string) => c.trim())
      )
      const ths = headers.map((h: string) =>
        `<th class="px-3 py-1.5 text-left text-[11px] font-semibold text-gray-600 bg-gray-50 border-b border-gray-200">${h.trim()}</th>`
      ).join('')
      const trs = rows.map((cells: string[]) =>
        '<tr class="border-b border-gray-100 last:border-0">' +
        cells.map((c: string) =>
          `<td class="px-3 py-1.5 text-[12px] text-gray-700">${c.trim()}</td>`
        ).join('') + '</tr>'
      ).join('')
      return `<div class="my-2 overflow-x-auto rounded-lg border border-gray-200"><table class="w-full"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`
    }
  )
}

/** Clean raw markdown from citation excerpt */
function cleanExcerpt(text: string): string {
  return text
    .replace(/^#+\s*/g, '')
    .replace(/\*\*/g, '')
    .replace(/\n/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export default function MessageBubble({ message, onFeedback, onDetailedFeedback, givenFeedback, onSuggestedClick, onCitationClick, onEscalate }: Props) {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)
  const [showFeedbackModal, setShowFeedbackModal] = useState(false)
  const [feedbackCategory, setFeedbackCategory] = useState('')
  const [feedbackComment, setFeedbackComment] = useState('')

  const confidence = message.confidence ?? message.faithfulness_score ?? 0
  const hasContent = !isUser && message.content && message.content.length > 0

  const handleNegativeFeedback = () => {
    // Show detailed feedback modal instead of immediate submit
    setShowFeedbackModal(true)
  }

  const handleSubmitDetailedFeedback = () => {
    if (onDetailedFeedback) {
      onDetailedFeedback(feedbackCategory, feedbackComment)
    }
    if (onFeedback) {
      onFeedback('negative')
    }
    setShowFeedbackModal(false)
    setFeedbackCategory('')
    setFeedbackComment('')
  }

  const handleCopy = () => {
    // Strip markdown formatting for clipboard
    const plain = message.content
      .replace(/\*\*(.+?)\*\*/g, '$1')
      .replace(/\[Source:.*?\]/g, '')
      .replace(/---+/g, '')
      .trim()
    navigator.clipboard.writeText(plain).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-5`}>
      <div className={`max-w-[78%] ${isUser ? 'order-1' : ''}`}>
        <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
          {/* Avatar */}
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0 shadow-sm ${isUser ? 'bg-blue-600' : 'bg-emerald-600'}`}>
            {isUser ? 'U' : 'HR'}
          </div>

          <div className="space-y-2">
            {/* Message Bubble */}
            <div className={`rounded-2xl px-4 py-3 ${
              isUser
                ? 'bg-blue-600 text-white'
                : 'bg-white border border-gray-200 text-gray-800 shadow-sm'
            }`}>
              {isUser ? (
                <p className="text-sm leading-relaxed">{message.content}</p>
              ) : (
                <div
                  className="text-sm leading-relaxed prose-sm"
                  dangerouslySetInnerHTML={{ __html: renderAnswer(message.content) }}
                />
              )}
            </div>

            {/* Citations */}
            {!isUser && message.citations && message.citations.length > 0 && (
              <div className="space-y-1.5">
                {message.citations.map((c, i) => (
                  <button
                    key={i}
                    onClick={() => onCitationClick?.(c)}
                    className="w-full flex items-center gap-3 text-left bg-gradient-to-r from-slate-50 to-white border border-gray-200 rounded-xl px-3.5 py-2.5 transition-all hover:border-blue-300 hover:shadow-sm group"
                  >
                    <div className="p-1.5 bg-blue-100 rounded-lg flex-shrink-0 group-hover:bg-blue-200 transition-colors">
                      <FileText size={14} className="text-blue-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-blue-700">{c.source}</span>
                        {c.page && (
                          <span className="text-[10px] font-medium px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">
                            Page {c.page}
                          </span>
                        )}
                      </div>
                      {c.excerpt && (
                        <p className="text-[11px] text-gray-400 truncate mt-0.5 leading-snug">
                          {cleanExcerpt(c.excerpt).substring(0, 90)}...
                        </p>
                      )}
                    </div>
                    <ExternalLink size={13} className="text-gray-300 group-hover:text-blue-400 flex-shrink-0 transition-colors" />
                  </button>
                ))}
              </div>
            )}

            {/* Contradiction Warning */}
            {!isUser && message.has_contradictions && (
              <div className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-700">
                <AlertTriangle size={13} className="flex-shrink-0" />
                <span>Some sources may contain conflicting information. Check the details above.</span>
              </div>
            )}

            {/* Confidence + Intent + Latency + Feedback */}
            {!isUser && hasContent && (
              <div className="flex items-center gap-3 text-xs text-gray-400 px-1">
                {/* Confidence badge hidden — not needed for employee view */}
                {message.intent && <IntentBadge intent={message.query_type === 'compound' ? 'compound' : message.intent} />}
                {/* Source count */}
                {message.citations && message.citations.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                    <FileText size={10} />
                    {message.citations.length} source{message.citations.length > 1 ? 's' : ''}
                  </span>
                )}
                {message.latency_ms !== undefined && message.latency_ms > 0 && (
                  <span className="text-[11px] text-gray-300">{(message.latency_ms / 1000).toFixed(1)}s</span>
                )}
                <div className="flex gap-0.5 ml-auto">
                  {/* Copy button */}
                  <button onClick={handleCopy} className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors" title={copied ? 'Copied!' : 'Copy response'}>
                    {copied
                      ? <Check size={13} className="text-emerald-500" />
                      : <Copy size={13} className="text-gray-300 hover:text-gray-500" />
                    }
                  </button>
                  {/* Feedback: show clickable thumbs or confirmed state */}
                  {onFeedback && (
                    <>
                      <button onClick={() => onFeedback('positive')} className="p-1.5 hover:bg-emerald-50 rounded-lg transition-colors" title="Helpful">
                        <ThumbsUp size={13} className="text-gray-300 hover:text-emerald-500" />
                      </button>
                      <button onClick={handleNegativeFeedback} className="p-1.5 hover:bg-red-50 rounded-lg transition-colors" title="Not helpful">
                        <ThumbsDown size={13} className="text-gray-300 hover:text-red-500" />
                      </button>
                    </>
                  )}
                  {givenFeedback && !onFeedback && (
                    <span className="flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px]">
                      {givenFeedback === 'positive'
                        ? <><ThumbsUp size={12} className="text-emerald-500" /> <span className="text-emerald-600">Thanks!</span></>
                        : <><ThumbsDown size={12} className="text-red-400" /> <span className="text-red-500">Feedback sent</span></>
                      }
                    </span>
                  )}
                  {onEscalate && (
                    <button onClick={() => onEscalate(message.content, message.content)}
                      className="ml-1 px-2 py-1 text-[11px] text-orange-600 bg-orange-50 border border-orange-200 rounded-lg hover:bg-orange-100 transition-colors flex items-center gap-1"
                      title="Raise a ticket for HR assistance">
                      <AlertCircle size={11} /> Raise Ticket
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Suggested follow-up questions */}
            {!isUser && message.suggested_questions && message.suggested_questions.length > 0 && onSuggestedClick && (
              <div className="flex flex-wrap gap-1.5 px-1">
                {message.suggested_questions.map((q, i) => (
                  <button key={i} onClick={() => onSuggestedClick(q)}
                    className="text-[11px] bg-gray-50 text-gray-600 border border-gray-200 rounded-lg px-2.5 py-1 hover:bg-blue-50 hover:text-blue-600 hover:border-blue-200 transition-colors">
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Detailed Feedback Modal ── */}
      {showFeedbackModal && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
             onClick={() => setShowFeedbackModal(false)}>
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5"
               onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-gray-900">What went wrong?</h3>
              <button onClick={() => setShowFeedbackModal(false)} className="p-1 hover:bg-gray-100 rounded-lg">
                <X size={16} className="text-gray-400" />
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 mb-4">
              {[
                { value: 'incorrect', label: 'Incorrect answer' },
                { value: 'incomplete', label: 'Incomplete answer' },
                { value: 'not_relevant', label: 'Not relevant' },
                { value: 'other', label: 'Other issue' },
              ].map(opt => (
                <button key={opt.value}
                  onClick={() => setFeedbackCategory(opt.value)}
                  className={`text-xs px-3 py-2 rounded-lg border transition-colors ${
                    feedbackCategory === opt.value
                      ? 'bg-red-50 border-red-300 text-red-700 font-medium'
                      : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'
                  }`}>
                  {opt.label}
                </button>
              ))}
            </div>

            <textarea
              value={feedbackComment}
              onChange={e => setFeedbackComment(e.target.value)}
              placeholder="Tell us more (optional)..."
              className="w-full text-sm border border-gray-200 rounded-lg p-3 resize-none focus:ring-2 focus:ring-red-200 focus:border-red-300 outline-none"
              rows={3}
            />

            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setShowFeedbackModal(false)}
                className="text-xs px-4 py-2 text-gray-500 hover:bg-gray-100 rounded-lg transition-colors">
                Cancel
              </button>
              <button onClick={handleSubmitDetailedFeedback}
                disabled={!feedbackCategory}
                className="text-xs px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5">
                <Send size={12} /> Submit Feedback
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
