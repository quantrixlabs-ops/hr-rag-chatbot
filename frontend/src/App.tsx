import { useState, useEffect, useCallback, useRef } from 'react'
import LoginPage from './pages/LoginPage'
import ChatPage from './pages/ChatPage'
import AdminDashboard from './pages/AdminDashboard'
import Sidebar from './components/Sidebar'
import { getSessions, setAuthExpiredHandler, logout as apiLogout, refreshAccessToken } from './services/api'
import type { AuthState, SessionSummary } from './types/chat'

export default function App() {
  const [auth, setAuth] = useState<AuthState>(() => {
    const saved = localStorage.getItem('hr_auth')
    return saved ? JSON.parse(saved) : { token: null, refreshToken: null, user: null }
  })
  const [page, setPage] = useState('chat')
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleLogin = useCallback((a: AuthState) => {
    setAuth(a)
    localStorage.setItem('hr_auth', JSON.stringify(a))
  }, [])

  const handleLogout = useCallback(() => {
    // Best-effort server-side logout
    if (auth.token) {
      apiLogout(auth.token, auth.refreshToken).catch(() => {})
    }
    setAuth({ token: null, refreshToken: null, user: null })
    localStorage.removeItem('hr_auth')
    setSessions([])
    setActiveSession(null)
    setPage('chat')
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
  }, [auth.token, auth.refreshToken])

  // Wire auth expiration handler so 401s attempt refresh before logout
  useEffect(() => {
    setAuthExpiredHandler(async () => {
      // Try refresh before logging out
      if (auth.refreshToken) {
        try {
          const data = await refreshAccessToken(auth.refreshToken)
          const newAuth: AuthState = {
            token: data.access_token,
            refreshToken: data.refresh_token,
            user: auth.user,
          }
          setAuth(newAuth)
          localStorage.setItem('hr_auth', JSON.stringify(newAuth))
          return // Refresh succeeded — caller should retry
        } catch {
          // Refresh failed — fall through to logout
        }
      }
      setAuth({ token: null, refreshToken: null, user: null })
      localStorage.removeItem('hr_auth')
      setSessions([])
      setActiveSession(null)
      setPage('chat')
    })
  }, [auth.refreshToken, auth.user])

  // Proactive token refresh — refresh 5 minutes before expiry
  useEffect(() => {
    if (!auth.token || !auth.refreshToken) return
    // Parse JWT to get exp claim
    try {
      const payload = JSON.parse(atob(auth.token.split('.')[1]))
      const expiresAt = payload.exp * 1000 // ms
      const refreshAt = expiresAt - 5 * 60 * 1000 // 5 min before expiry
      const delay = refreshAt - Date.now()
      if (delay <= 0) return // Already past refresh window
      refreshTimer.current = setTimeout(async () => {
        try {
          const data = await refreshAccessToken(auth.refreshToken!)
          const newAuth: AuthState = {
            token: data.access_token,
            refreshToken: data.refresh_token,
            user: auth.user,
          }
          setAuth(newAuth)
          localStorage.setItem('hr_auth', JSON.stringify(newAuth))
        } catch {
          // Refresh failed — user will get 401 on next request
        }
      }, delay)
    } catch {
      // Invalid JWT — ignore
    }
    return () => {
      if (refreshTimer.current) clearTimeout(refreshTimer.current)
    }
  }, [auth.token, auth.refreshToken, auth.user])

  // Inactivity timeout — logout after 30 minutes of no interaction
  const inactivityTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const INACTIVITY_TIMEOUT = 30 * 60 * 1000 // 30 minutes

  useEffect(() => {
    if (!auth.token) return

    const resetTimer = () => {
      if (inactivityTimer.current) clearTimeout(inactivityTimer.current)
      inactivityTimer.current = setTimeout(() => {
        handleLogout()
      }, INACTIVITY_TIMEOUT)
    }

    const events = ['mousedown', 'keydown', 'scroll', 'touchstart']
    events.forEach(e => window.addEventListener(e, resetTimer, { passive: true }))
    resetTimer()

    return () => {
      events.forEach(e => window.removeEventListener(e, resetTimer))
      if (inactivityTimer.current) clearTimeout(inactivityTimer.current)
    }
  }, [auth.token, handleLogout])

  // Load sessions
  useEffect(() => {
    if (auth.token) {
      getSessions(auth.token).then(d => setSessions(d.sessions || [])).catch(() => {})
    }
  }, [auth.token, activeSession])

  const handleNewChat = () => {
    setActiveSession(null)
    setPage('chat')
  }

  if (!auth.token || !auth.user) {
    return <LoginPage onLogin={handleLogin} />
  }

  return (
    <div className="h-screen flex bg-gray-50">
      <Sidebar
        user={auth.user}
        sessions={sessions}
        activeSession={activeSession}
        onNewChat={handleNewChat}
        onSelectSession={(id) => { setActiveSession(id); setPage('chat') }}
        onNavigate={setPage}
        onLogout={handleLogout}
        currentPage={page}
      />
      <main className="flex-1 flex flex-col min-w-0">
        {page === 'chat' && (
          <ChatPage token={auth.token} sessionId={activeSession} onSessionChange={setActiveSession} />
        )}
        {(page === 'admin' || page === 'upload') && (
          <AdminDashboard token={auth.token} />
        )}
      </main>
    </div>
  )
}
