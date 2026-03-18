import ChatWindow from '../components/ChatWindow'
import { useChat } from '../hooks/useChat'
import { sendFeedback, getSessionHistory, escalateToHR } from '../services/api'
import { useEffect } from 'react'
import type { ChatMessage } from '../types/chat'

interface Props {
  token: string
  sessionId: string | null
  onSessionChange: (id: string | null) => void
}

export default function ChatPage({ token, sessionId, onSessionChange }: Props) {
  const chat = useChat(token)

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
    }
  }

  const handleEscalate = async (query: string, answer: string) => {
    try {
      await escalateToHR(token, query, answer, chat.sessionId)
      alert('Your question has been escalated to an HR representative. You will receive a response shortly.')
    } catch {
      alert('Failed to escalate. Please try again.')
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
    />
  )
}
