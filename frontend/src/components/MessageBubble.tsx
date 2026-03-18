import { ThumbsUp, ThumbsDown, FileText, Shield, ExternalLink, AlertCircle } from 'lucide-react'
import type { ChatMessage, Citation } from '../types/chat'

interface Props {
  message: ChatMessage
  onFeedback?: (rating: string) => void
  onSuggestedClick?: (question: string) => void
  onCitationClick?: (citation: Citation) => void
  onEscalate?: (query: string, answer: string) => void
}

function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color =
    pct >= 70 ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
    pct >= 40 ? 'bg-amber-50 text-amber-700 border-amber-200' :
               'bg-red-50 text-red-700 border-red-200'

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${color}`}>
      <Shield size={10} />
      {pct}% confident
    </span>
  )
}

/** Render markdown-like LLM output as styled HTML */
function renderAnswer(text: string): string {
  let html = text
    // Remove [Source: ...] tags (already shown in citations below)
    .replace(/\[Source:.*?\]/g, '')
    .replace(/\[Relevance:.*?\]/g, '')
    // Escape HTML
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Bold: **text**
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic: *text*
    .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
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

/** Clean raw markdown from citation excerpt */
function cleanExcerpt(text: string): string {
  return text
    .replace(/^#+\s*/g, '')
    .replace(/\*\*/g, '')
    .replace(/\n/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export default function MessageBubble({ message, onFeedback, onSuggestedClick, onCitationClick, onEscalate }: Props) {
  const isUser = message.role === 'user'

  const confidence = message.confidence ?? message.faithfulness_score ?? 0
  const hasContent = !isUser && message.content && message.content.length > 0
  const showConfidence = hasContent && confidence > 0

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

            {/* Confidence + Latency + Feedback */}
            {!isUser && hasContent && (
              <div className="flex items-center gap-3 text-xs text-gray-400 px-1">
                {showConfidence && <ConfidenceBadge score={confidence} />}
                {message.latency_ms !== undefined && message.latency_ms > 0 && (
                  <span className="text-gray-300">{(message.latency_ms / 1000).toFixed(1)}s</span>
                )}
                <div className="flex gap-0.5 ml-auto">
                  {onFeedback && (
                    <>
                      <button onClick={() => onFeedback('positive')} className="p-1.5 hover:bg-emerald-50 rounded-lg transition-colors" title="Helpful">
                        <ThumbsUp size={13} className="text-gray-300 hover:text-emerald-500" />
                      </button>
                      <button onClick={() => onFeedback('negative')} className="p-1.5 hover:bg-red-50 rounded-lg transition-colors" title="Not helpful">
                        <ThumbsDown size={13} className="text-gray-300 hover:text-red-500" />
                      </button>
                    </>
                  )}
                  {onEscalate && (
                    <button onClick={() => onEscalate(message.content, message.content)}
                      className="ml-1 px-2 py-1 text-[11px] text-orange-600 bg-orange-50 border border-orange-200 rounded-lg hover:bg-orange-100 transition-colors flex items-center gap-1"
                      title="Escalate to HR representative">
                      <AlertCircle size={11} /> Escalate to HR
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
    </div>
  )
}
