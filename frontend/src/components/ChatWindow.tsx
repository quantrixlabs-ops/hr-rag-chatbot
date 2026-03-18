import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'
import ChatInput from './ChatInput'
import type { ChatMessage } from '../types/chat'

interface Props {
  messages: ChatMessage[]
  loading: boolean
  streamingText?: string
  onSend: (message: string) => void
  onFeedback?: (query: string, answer: string, rating: string) => void
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

export default function ChatWindow({ messages, loading, streamingText, onSend, onFeedback }: Props) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 && (
            <div className="text-center py-20">
              <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl">💬</span>
              </div>
              <h2 className="text-xl font-semibold text-gray-800 mb-2">HR Assistant</h2>
              <p className="text-gray-500 mb-8">Ask me anything about company policies, benefits, leave, and more.</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto">
                {['How many vacation days do I get?', 'What health insurance plans are available?', 'How do I request time off?', 'What is the 401k matching policy?'].map(q => (
                  <button key={q} onClick={() => onSend(q)} className="text-left text-sm bg-white border border-gray-200 rounded-xl px-4 py-3 hover:border-blue-300 hover:bg-blue-50 transition-colors text-gray-600">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((msg, i) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onFeedback={msg.role === 'assistant' && onFeedback
                ? (rating) => {
                    const userMsg = messages[i - 1]
                    if (userMsg) onFeedback(userMsg.content, msg.content, rating)
                  }
                : undefined}
            />
          ))}
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

      <ChatInput onSend={onSend} disabled={loading} />
    </div>
  )
}
