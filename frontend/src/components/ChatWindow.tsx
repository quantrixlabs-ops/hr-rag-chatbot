import { useEffect, useRef, useState } from 'react'
import { Calendar, Heart, BookOpen, HelpCircle } from 'lucide-react'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'
import DocumentViewer from './DocumentViewer'
import type { ChatMessage, Citation } from '../types/chat'

interface Props {
  messages: ChatMessage[]
  loading: boolean
  streamingText?: string
  onSend: (message: string) => void
  onFeedback?: (query: string, answer: string, rating: string) => void
  onEscalate?: (query: string, answer: string) => void
  token: string
  role?: string
  feedbackGiven?: Record<string, string>
}

function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">HR</div>
        <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3">
          <div className="flex gap-1.5">
            <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot" />
            <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot" />
            <div className="w-2 h-2 bg-gray-400 rounded-full typing-dot" />
          </div>
        </div>
      </div>
    </div>
  )
}

export default function ChatWindow({ messages, loading, streamingText, onSend, onFeedback, onEscalate, token, role, feedbackGiven = {} }: Props) {
  const endRef = useRef<HTMLDivElement>(null)
  const [viewingCitation, setViewingCitation] = useState<Citation | null>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 && (
            <div className="text-center py-12">
              <div className="w-16 h-16 bg-emerald-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">💬</span>
              </div>
              <h2 className="text-xl font-semibold text-gray-800 mb-1">HR Assistant</h2>
              <p className="text-gray-500 mb-8 text-sm">Ask me anything about company policies, benefits, leave, and more.</p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl mx-auto">
                {[
                  { icon: <Calendar size={15} className="text-blue-600" />, color: 'bg-blue-50 border-blue-200 hover:bg-blue-100', label: 'Leave & Time Off', q: 'How do I request time off?' },
                  { icon: <Heart size={15} className="text-rose-600" />, color: 'bg-rose-50 border-rose-200 hover:bg-rose-100', label: 'Benefits & Insurance', q: 'What health insurance plans are available?' },
                  { icon: <BookOpen size={15} className="text-amber-600" />, color: 'bg-amber-50 border-amber-200 hover:bg-amber-100', label: 'Onboarding', q: 'What should I know for my first day?' },
                  { icon: <HelpCircle size={15} className="text-purple-600" />, color: 'bg-purple-50 border-purple-200 hover:bg-purple-100', label: 'Policies & Procedures', q: 'What is the remote work policy?' },
                ].map(card => (
                  <button
                    key={card.q}
                    onClick={() => onSend(card.q)}
                    className={`flex items-center gap-3 text-left text-sm bg-white border rounded-xl px-4 py-3.5 transition-all hover:shadow-sm ${card.color}`}
                  >
                    <div className={`p-2 rounded-lg ${card.color.split(' ')[0]}`}>{card.icon}</div>
                    <div>
                      <p className="font-medium text-gray-800 text-[13px]">{card.label}</p>
                      <p className="text-[11px] text-gray-400 mt-0.5">{card.q}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((msg, i) => {
            const userMsg = i > 0 ? messages[i - 1] : null
            const feedbackKey = userMsg ? userMsg.content.slice(0, 50) : ''
            const givenRating = feedbackGiven[feedbackKey]
            return (
              <MessageBubble
                key={msg.id}
                message={msg}
                onFeedback={msg.role === 'assistant' && onFeedback && !givenRating
                  ? (rating) => {
                      if (userMsg) onFeedback(userMsg.content, msg.content, rating)
                    }
                  : undefined}
                givenFeedback={msg.role === 'assistant' ? givenRating : undefined}
                onSuggestedClick={msg.role === 'assistant' && i === messages.length - 1 && !loading
                  ? (q) => onSend(q)
                  : undefined}
                onCitationClick={(citation) => setViewingCitation(citation)}
                onEscalate={msg.role === 'assistant' && onEscalate
                  ? (_query, answer) => {
                      onEscalate(userMsg?.content || answer, answer)
                    }
                  : undefined}
              />
            )
          })}
          {loading && streamingText && (
            <div className="flex justify-start mb-4">
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-emerald-600 flex items-center justify-center text-white text-sm font-semibold flex-shrink-0">HR</div>
                <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3">
                  <p className="text-sm whitespace-pre-wrap leading-relaxed text-gray-800">{streamingText}<span className="animate-pulse">▊</span></p>
                </div>
              </div>
            </div>
          )}
          {loading && !streamingText && <TypingIndicator />}
          <div ref={endRef} />
        </div>
      </div>

      <ChatInput
        onSend={onSend}
        disabled={loading}
        role={role}
        suggestedQuestions={(() => {
          if (loading || messages.length === 0) return undefined
          const assistantMsgs = messages.filter(m => m.role === 'assistant')
          return assistantMsgs[assistantMsgs.length - 1]?.suggested_questions
        })()}
      />

      {/* Document Viewer Modal */}
      {viewingCitation && (
        <DocumentViewer
          token={token}
          citation={viewingCitation}
          onClose={() => setViewingCitation(null)}
        />
      )}
    </div>
  )
}
