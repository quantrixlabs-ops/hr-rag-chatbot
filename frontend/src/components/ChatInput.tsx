import { useState, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'

// Quick-start chips — only questions that match uploaded policy documents
const CHIPS_BY_ROLE: Record<string, string[]> = {
  employee: [
    'What is the leave policy?',
    'What is the anti-harassment policy?',
    'What is the code of conduct?',
    'What is the disciplinary policy?',
  ],
  hr_admin: [
    'What is the exit process?',
    'What is the attendance policy?',
    'What is the conflict of interest policy?',
    'What is the payroll policy?',
  ],
  manager: [
    'What is the leave policy?',
    'What is the transfer policy?',
    'What is the disciplinary process?',
    'What is the attendance policy?',
  ],
  super_admin: [
    'What is the code of conduct?',
    'What is the anti-harassment policy?',
    'What is the leave policy?',
    'What is the medical policy?',
  ],
}

const DEFAULT_CHIPS = CHIPS_BY_ROLE.employee

interface Props {
  onSend: (message: string) => void
  disabled?: boolean
  role?: string
  suggestedQuestions?: string[]  // dynamic suggestions from last AI response
}

export default function ChatInput({ onSend, disabled, role, suggestedQuestions }: Props) {
  const [input, setInput] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { ref.current?.focus() }, [])

  const handleSubmit = () => {
    const trimmed = input.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setInput('')
    if (ref.current) ref.current.style.height = 'auto'
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    if (ref.current) {
      ref.current.style.height = 'auto'
      ref.current.style.height = Math.min(ref.current.scrollHeight, 160) + 'px'
    }
  }

  const sendChip = (text: string) => {
    if (disabled) return
    onSend(text)
  }

  // Show AI-suggested questions if available, else show role-aware defaults when input is empty
  const chips = suggestedQuestions && suggestedQuestions.length > 0
    ? suggestedQuestions.slice(0, 3)
    : !input.trim()
      ? (CHIPS_BY_ROLE[role || ''] || DEFAULT_CHIPS).slice(0, 4)
      : []

  return (
    <div className="border-t border-gray-200 bg-white">
      {/* Quick chips */}
      {chips.length > 0 && (
        <div className="px-4 pt-3 flex flex-wrap gap-2">
          {chips.map((chip, i) => (
            <button
              key={i}
              onClick={() => sendChip(chip)}
              disabled={disabled}
              className="text-xs px-3 py-1.5 bg-blue-50 text-blue-700 border border-blue-200 rounded-full hover:bg-blue-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors whitespace-nowrap max-w-[260px] truncate"
              title={chip}
            >
              {chip}
            </button>
          ))}
        </div>
      )}

      {/* Input row */}
      <div className="p-4">
        <div className="max-w-3xl mx-auto flex items-end gap-3">
          <textarea
            ref={ref}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask an HR question..."
            rows={1}
            disabled={disabled}
            className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:bg-gray-50"
          />
          <button
            onClick={handleSubmit}
            disabled={!input.trim() || disabled}
            className="p-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
