import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'
import { CheckCircle, XCircle, AlertCircle, Info, X } from 'lucide-react'

// ── Types ────────────────────────────────────────────────────────────────────

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: string
  type: ToastType
  title: string
  message?: string
  duration?: number  // ms, 0 = persistent
}

interface ToastContextValue {
  addToast: (toast: Omit<Toast, 'id'>) => void
  removeToast: (id: string) => void
}

// ── Context ──────────────────────────────────────────────────────────────────

const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

// Convenience helpers
export function useToastHelpers() {
  const { addToast } = useToast()
  return {
    success: (title: string, message?: string) => addToast({ type: 'success', title, message, duration: 4000 }),
    error:   (title: string, message?: string) => addToast({ type: 'error',   title, message, duration: 6000 }),
    warning: (title: string, message?: string) => addToast({ type: 'warning', title, message, duration: 5000 }),
    info:    (title: string, message?: string) => addToast({ type: 'info',    title, message, duration: 4000 }),
  }
}

// ── Toast Item ───────────────────────────────────────────────────────────────

const ICONS = {
  success: <CheckCircle size={18} className="text-emerald-500 flex-shrink-0 mt-0.5" />,
  error:   <XCircle     size={18} className="text-red-500    flex-shrink-0 mt-0.5" />,
  warning: <AlertCircle size={18} className="text-amber-500  flex-shrink-0 mt-0.5" />,
  info:    <Info        size={18} className="text-blue-500   flex-shrink-0 mt-0.5" />,
}

const BORDERS = {
  success: 'border-l-emerald-500',
  error:   'border-l-red-500',
  warning: 'border-l-amber-500',
  info:    'border-l-blue-500',
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: () => void }) {
  const [visible, setVisible] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    // Slide in
    const frame = requestAnimationFrame(() => setVisible(true))

    // Auto-dismiss
    if (toast.duration && toast.duration > 0) {
      timerRef.current = setTimeout(() => {
        setVisible(false)
        setTimeout(onRemove, 300) // wait for slide-out
      }, toast.duration)
    }

    return () => {
      cancelAnimationFrame(frame)
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [toast.duration, onRemove])

  const handleDismiss = () => {
    setVisible(false)
    setTimeout(onRemove, 300)
  }

  return (
    <div
      className={`
        flex items-start gap-3 bg-white border border-gray-200 border-l-4
        ${BORDERS[toast.type]} rounded-lg shadow-lg px-4 py-3 w-80
        transform transition-all duration-300 ease-out
        ${visible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'}
      `}
    >
      {ICONS[toast.type]}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 leading-snug">{toast.title}</p>
        {toast.message && <p className="text-xs text-gray-500 mt-0.5 leading-snug">{toast.message}</p>}
      </div>
      <button onClick={handleDismiss} className="text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0">
        <X size={14} />
      </button>
    </div>
  )
}

// ── Provider + Container ─────────────────────────────────────────────────────

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((t: Omit<Toast, 'id'>) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    setToasts(prev => [...prev, { ...t, id }])
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ addToast, removeToast }}>
      {children}
      {/* Toast container — fixed bottom-right */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map(t => (
          <div key={t.id} className="pointer-events-auto">
            <ToastItem toast={t} onRemove={() => removeToast(t.id)} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
