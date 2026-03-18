import { ThumbsUp, ThumbsDown, FileText, Shield } from 'lucide-react'
import type { ChatMessage } from '../types/chat'

interface Props {
  message: ChatMessage
  onFeedback?: (rating: string) => void
  onSuggestedClick?: (question: string) => void
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

export default function MessageBubble({ message, onFeedback, onSuggestedClick }: Props) {
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

            {/* Citations */}
            {!isUser && message.citations && message.citations.length > 0 && (
              <div className="mt-2 space-y-1">
                {message.citations.map((c, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-1.5">
                    <FileText size={12} className="text-blue-500 flex-shrink-0" />
                    <span className="font-medium">{c.source}</span>
                    {c.page && <span className="text-gray-400">p.{c.page}</span>}
                  </div>
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
