import ChatWindow from '../components/ChatWindow'
import { useChat } from '../hooks/useChat'
import { sendFeedback, getSessionHistory, createTicket } from '../services/api'
import { useEffect, useState } from 'react'
import type { ChatMessage } from '../types/chat'

interface Props {
  token: string
  sessionId: string | null
  onSessionChange: (id: string | null) => void
  role?: string
  onNavigate?: (page: string) => void
}

export default function ChatPage({ token, sessionId, onSessionChange, role, onNavigate }: Props) {
  const chat = useChat(token)
  const [feedbackGiven, setFeedbackGiven] = useState<Record<string, string>>({})

  // Sync external session selection — including New Chat (null)
  useEffect(() => {
    if (sessionId === null && chat.sessionId !== null) {
      // New Chat clicked — clear everything
      chat.clearChat()
    } else if (sessionId && sessionId !== chat.sessionId) {
      // Load an existing session
      getSessionHistory(token, sessionId).then(data => {
        const msgs: ChatMessage[] = data.turns.map((t: any) => ({
          id: crypto.randomUUID(),
          role: t.role,
          content: t.content,
          timestamp: t.timestamp * 1000,
        }))
        chat.setMessages(msgs)
        chat.setSessionId(sessionId)
      }).catch(() => {})
    }
  }, [sessionId])

  // Propagate session changes upward
  useEffect(() => {
    if (chat.sessionId) onSessionChange(chat.sessionId)
  }, [chat.sessionId])

  const handleFeedback = (query: string, answer: string, rating: string) => {
    if (chat.sessionId) {
      sendFeedback(token, chat.sessionId, query, answer, rating)
      // Track which messages got feedback
      setFeedbackGiven(prev => ({ ...prev, [query.slice(0, 50)]: rating }))
    }
  }

  const handleEscalate = async (query: string, answer: string) => {
    try {
      // Create a ticket directly with the chat context
      await createTicket(token, {
        title: `Escalation: ${query.slice(0, 150)}`,
        description: `Employee escalated from chat.\n\nQuestion: ${query}\n\nAI Response: ${answer.slice(0, 500)}`,
        category: 'general',
        priority: 'high',
      })
      // Navigate to tickets page so employee can see and track it
      if (onNavigate) {
        onNavigate('tickets')
      }
    } catch {
      alert('Failed to create ticket. Please try again or go to Tickets page directly.')
    }
  }

  return (
    <ChatWindow
      messages={chat.messages}
      loading={chat.loading}
      streamingText={chat.streamingText}
      onSend={chat.send}
      onFeedback={handleFeedback}
      onEscalate={handleEscalate}
      token={token}
      role={role}
      feedbackGiven={feedbackGiven}
    />
  )
}
