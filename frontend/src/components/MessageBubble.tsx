import { ThumbsUp, ThumbsDown, FileText, Shield, ExternalLink } from 'lucide-react'
import type { ChatMessage, Citation } from '../types/chat'

interface Props {
  message: ChatMessage
  onFeedback?: (rating: string) => void
  onSuggestedClick?: (question: string) => void
  onCitationClick?: (citation: Citation) => void
}

function ConfidenceBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color =
    pct >= 70 ? 'bg-green-50 text-green-700 border-green-200' :
    pct >= 40 ? 'bg-yellow-50 text-yellow-700 border-yellow-200' :
               'bg-red-50 text-red-700 border-red-200'

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${color}`}>
      <Shield size={10} />
      {pct}% confident
    </span>
  )
}

export default function MessageBubble({ message, onFeedback, onSuggestedClick, onCitationClick }: Props) {
  const isUser = message.role === 'user'

  // Resolve confidence: prefer explicit field, never show 0% when we have citations
  const confidence = message.confidence ?? message.faithfulness_score ?? 0
  const hasContent = !isUser && message.content && message.content.length > 0
  const showConfidence = hasContent && confidence > 0

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`max-w-[75%] ${isUser ? 'order-1' : ''}`}>
        {/* Avatar */}
        <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-semibold flex-shrink-0 ${isUser ? 'bg-blue-600' : 'bg-emerald-600'}`}>
            {isUser ? 'U' : 'HR'}
          </div>
          <div>
            {/* Bubble */}
            <div className={`rounded-2xl px-4 py-3 ${isUser ? 'bg-blue-600 text-white' : 'bg-white border border-gray-200 text-gray-800'}`}>
              <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
            </div>

            {/* Clickable Citations */}
            {!isUser && message.citations && message.citations.length > 0 && (
              <div className="mt-2 space-y-1">
                {message.citations.map((c, i) => (
                  <button
                    key={i}
                    onClick={() => onCitationClick?.(c)}
                    className="w-full flex items-center gap-2 text-xs text-left bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg px-3 py-2 transition-colors group"
                  >
                    <FileText size={14} className="text-blue-500 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <span className="font-semibold text-blue-700">{c.source}</span>
                      {c.page && <span className="text-blue-400 ml-1.5">Page {c.page}</span>}
                      {c.excerpt && (
                        <p className="text-gray-500 truncate mt-0.5 text-[11px] leading-tight">
                          "{c.excerpt.substring(0, 80)}..."
                        </p>
                      )}
                    </div>
                    <ExternalLink size={12} className="text-blue-400 opacity-0 group-hover:opacity-100 flex-shrink-0 transition-opacity" />
                  </button>
                ))}
              </div>
            )}

            {/* Confidence + Latency + Feedback */}
            {!isUser && hasContent && (
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                {showConfidence && <ConfidenceBadge score={confidence} />}
                {message.latency_ms !== undefined && message.latency_ms > 0 && (
                  <span>{(message.latency_ms / 1000).toFixed(1)}s</span>
                )}
                {onFeedback && (
                  <div className="flex gap-1 ml-auto">
                    <button onClick={() => onFeedback('positive')} className="p-1 hover:bg-green-50 rounded transition-colors" title="Helpful">
                      <ThumbsUp size={14} />
                    </button>
                    <button onClick={() => onFeedback('negative')} className="p-1 hover:bg-red-50 rounded transition-colors" title="Not helpful">
                      <ThumbsDown size={14} />
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Suggested follow-up questions */}
            {!isUser && message.suggested_questions && message.suggested_questions.length > 0 && onSuggestedClick && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {message.suggested_questions.map((q, i) => (
                  <button key={i} onClick={() => onSuggestedClick(q)}
                    className="text-xs bg-blue-50 text-blue-600 border border-blue-200 rounded-lg px-2.5 py-1 hover:bg-blue-100 transition-colors">
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
