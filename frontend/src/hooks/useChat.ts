import { useState, useCallback, useRef } from 'react'
import type { ChatMessage } from '../types/chat'
import { sendMessage, sendMessageStream } from '../services/api'
import type { StreamDoneData } from '../services/api'

export function useChat(token: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const streamIdRef = useRef<string | null>(null)

  const send = useCallback(async (query: string) => {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: query,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    setStreamingText('')

    const botId = crypto.randomUUID()
    streamIdRef.current = botId

    try {
      let streamWorked = false

      await sendMessageStream(
        token, query, sessionId,
        (token_chunk) => {
          streamWorked = true
          setStreamingText(prev => prev + token_chunk)
        },
        (doneData: StreamDoneData) => {
          setStreamingText('')
          // Capture session_id from streaming response
          if (doneData.session_id) setSessionId(doneData.session_id)
          if (doneData.full_text) {
            setMessages(prev => [...prev, {
              id: botId, role: 'assistant', content: doneData.full_text,
              citations: doneData.citations,
              confidence: doneData.confidence,
              faithfulness_score: doneData.faithfulness_score,
              suggested_questions: doneData.suggested_questions,
              timestamp: Date.now(),
            }])
          }
        },
        (_err) => { /* will fallback below */ },
      )

      if (!streamWorked) {
        // Fallback to non-streaming — this returns the session_id
        const data = await sendMessage(token, query, sessionId)
        if (data.session_id) setSessionId(data.session_id)
        setMessages(prev => [...prev, {
          id: botId, role: 'assistant', content: data.answer,
          citations: data.citations, confidence: data.confidence,
          faithfulness_score: data.faithfulness_score,
          query_type: data.query_type, latency_ms: data.latency_ms,
          suggested_questions: data.suggested_questions,
          timestamp: Date.now(),
        }])
      }

    } catch {
      setStreamingText('')
      setMessages(prev => [
        ...prev,
        { id: botId, role: 'assistant', content: 'Sorry, something went wrong. Please try again.', timestamp: Date.now() },
      ])
    } finally {
      setLoading(false)
      setStreamingText('')
      streamIdRef.current = null
    }
  }, [token, sessionId])

  const clearChat = useCallback(() => {
    setMessages([])
    setSessionId(null)
    setStreamingText('')
  }, [])

  return { messages, loading, sessionId, streamingText, send, clearChat, setMessages, setSessionId }
}
