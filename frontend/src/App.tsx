import { useState, useEffect, useCallback, useRef } from 'react'
import LoginPage from './pages/LoginPage'
import ChatPage from './pages/ChatPage'
import AdminDashboard from './pages/AdminDashboard'
import UploadDocs from './pages/UploadDocs'
import UserSettingsPage from './pages/UserSettingsPage'
import TicketsPage from './pages/TicketsPage'
import ComplaintsPage from './pages/ComplaintsPage'
import EmployeeDashboard from './pages/EmployeeDashboard'
import HRDashboard from './pages/HRDashboard'
import ContactHR from './pages/ContactHR'
import BranchManagement from './pages/BranchManagement'
import Sidebar from './components/Sidebar'
import NotificationBell from './components/NotificationBell'
import { ToastProvider, useToastHelpers } from './components/NotificationToast'
import {
  getSessions, deleteSession, setAuthExpiredHandler, logout as apiLogout,
  refreshAccessToken, getTenantBranding, type TenantBranding,
} from './services/api'
import type { AuthState, SessionSummary, UserInfo } from './types/chat'
import { Menu } from 'lucide-react'

// ── Inner app — wrapped by ToastProvider ─────────────────────────────────────

function AppInner() {
  const toast = useToastHelpers()

  const [auth, setAuth] = useState<AuthState>(() => {
    const saved = localStorage.getItem('hr_auth')
    return saved ? JSON.parse(saved) : { token: null, refreshToken: null, user: null }
  })
  // Phase E: Role-based default home page
  const getHomePage = (role?: string) => {
    if (!role) return 'chat'
    if (['hr_admin', 'super_admin', 'admin'].includes(role)) return 'admin'
    if (['hr_team', 'hr_head'].includes(role)) return 'hr-dashboard'
    return 'home'
  }
  const [page, setPage] = useState(() => {
    const saved = localStorage.getItem('hr_auth')
    if (saved) {
      try { return getHomePage(JSON.parse(saved).user?.role) } catch { /* ignore */ }
    }
    return 'chat'
  })
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [activeSession, setActiveSession] = useState<string | null>(null)
  const [chatKey, setChatKey] = useState(0)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [branding, setBranding] = useState<TenantBranding>({ company_name: 'HR Chatbot' })
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleLogin = useCallback((a: AuthState) => {
    setAuth(a)
    localStorage.setItem('hr_auth', JSON.stringify(a))
    // Phase E: Navigate to role-appropriate home
    setPage(getHomePage(a.user?.role))
  }, [])

  const handleLogout = useCallback(() => {
    if (auth.token) {
      apiLogout(auth.token, auth.refreshToken).catch(() => {})
    }
    setAuth({ token: null, refreshToken: null, user: null })
    localStorage.removeItem('hr_auth')
    setSessions([])
    setActiveSession(null)
    setPage('chat')
    setMobileSidebarOpen(false)
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
  }, [auth.token, auth.refreshToken])

  // Auth expiration handler — try refresh before logout
  useEffect(() => {
    setAuthExpiredHandler(async () => {
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
          return
        } catch {
          // fall through to logout
        }
      }
      toast.warning('Session expired', 'Please sign in again.')
      setAuth({ token: null, refreshToken: null, user: null })
      localStorage.removeItem('hr_auth')
      setSessions([])
      setActiveSession(null)
      setPage('chat')
    })
  }, [auth.refreshToken, auth.user])

  // Proactive token refresh — 5 minutes before expiry
  useEffect(() => {
    if (!auth.token || !auth.refreshToken) return
    try {
      const payload = JSON.parse(atob(auth.token.split('.')[1]))
      const delay = payload.exp * 1000 - Date.now() - 5 * 60 * 1000
      if (delay <= 0) return
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
          // Will get 401 on next request
        }
      }, delay)
    } catch {
      // Invalid JWT — ignore
    }
    return () => { if (refreshTimer.current) clearTimeout(refreshTimer.current) }
  }, [auth.token, auth.refreshToken, auth.user])

  // Inactivity timeout — 30 minutes
  const inactivityTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!auth.token) return
    const resetTimer = () => {
      if (inactivityTimer.current) clearTimeout(inactivityTimer.current)
      inactivityTimer.current = setTimeout(handleLogout, 30 * 60 * 1000)
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
  const refreshSessions = useCallback(() => {
    if (auth.token) {
      getSessions(auth.token).then(d => setSessions(d.sessions || [])).catch(() => {})
    }
  }, [auth.token])

  useEffect(() => { refreshSessions() }, [refreshSessions, activeSession])

  useEffect(() => {
    if (!auth.token) return
    const interval = setInterval(refreshSessions, 10000)
    return () => clearInterval(interval)
  }, [auth.token, refreshSessions])

  // Fetch tenant branding on login
  useEffect(() => {
    if (!auth.token) return
    getTenantBranding(auth.token).then(b => {
      setBranding(b)
      document.title = b.company_name ? `${b.company_name} — HR Chatbot` : 'HR Chatbot'
    })
  }, [auth.token])

  const handleNewChat = () => {
    setActiveSession(null)
    setChatKey(k => k + 1)
    setPage('chat')
    setMobileSidebarOpen(false)
  }

  const handleDeleteSession = useCallback(async (sessionId: string) => {
    if (!auth.token) return
    const session = sessions.find(s => s.session_id === sessionId)
    const label = session?.preview || 'this chat'
    if (!confirm(`Delete "${label}"?`)) return
    try {
      await deleteSession(auth.token, sessionId)
      setSessions(prev => prev.filter(s => s.session_id !== sessionId))
      if (activeSession === sessionId) {
        setActiveSession(null)
        setChatKey(k => k + 1)
      }
    } catch {
      toast.error('Delete failed', 'Could not delete the chat session.')
    }
  }, [auth.token, sessions, activeSession, toast])

  const handleProfileUpdate = useCallback((updated: Partial<UserInfo>) => {
    setAuth(prev => ({
      ...prev,
      user: prev.user ? { ...prev.user, ...updated } : prev.user,
    }))
    const saved = localStorage.getItem('hr_auth')
    if (saved) {
      const parsed = JSON.parse(saved)
      parsed.user = { ...parsed.user, ...updated }
      localStorage.setItem('hr_auth', JSON.stringify(parsed))
    }
  }, [])

  if (!auth.token || !auth.user) {
    return <LoginPage onLogin={handleLogin} />
  }

  return (
    <div className="h-screen flex bg-gray-50 overflow-hidden">
      {/* Mobile sidebar — overlay mode on small screens */}
      <div className="hidden md:flex">
        <Sidebar
          user={auth.user}
          sessions={sessions}
          activeSession={activeSession}
          onNewChat={handleNewChat}
          onSelectSession={(id) => { setActiveSession(id); setPage('chat') }}
          onDeleteSession={handleDeleteSession}
          onNavigate={setPage}
          onLogout={handleLogout}
          currentPage={page}
          companyName={branding.company_name}
        />
      </div>

      {/* Mobile sidebar overlay */}
      {mobileSidebarOpen && (
        <div className="md:hidden">
          <Sidebar
            user={auth.user}
            sessions={sessions}
            activeSession={activeSession}
            onNewChat={handleNewChat}
            onSelectSession={(id) => { setActiveSession(id); setPage('chat') }}
            onDeleteSession={handleDeleteSession}
            onNavigate={(p) => { setPage(p); setMobileSidebarOpen(false) }}
            onLogout={handleLogout}
            currentPage={page}
            companyName={branding.company_name}
            mobileOpen={mobileSidebarOpen}
            onMobileClose={() => setMobileSidebarOpen(false)}
          />
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile header */}
        <div className="md:hidden flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-200 flex-shrink-0">
          <button
            onClick={() => setMobileSidebarOpen(true)}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <Menu size={20} className="text-gray-600" />
          </button>
          <h1 className="text-sm font-semibold text-gray-800 truncate flex-1">{branding.company_name}</h1>
          <NotificationBell token={auth.token} onNavigate={setPage} />
        </div>
        {/* Desktop notification bell */}
        <div className="hidden md:flex items-center justify-end px-4 py-2 bg-white border-b border-gray-100 flex-shrink-0">
          <NotificationBell token={auth.token} onNavigate={setPage} />
        </div>

        {/* Phase E: Role-specific home portals */}
        {page === 'home' && (
          <EmployeeDashboard
            token={auth.token}
            userName={auth.user.full_name || auth.user.username || 'User'}
            userBranchId={auth.user.branch_id}
            onNavigate={setPage}
          />
        )}
        {page === 'hr-dashboard' && (
          <HRDashboard
            token={auth.token}
            role={auth.user.role}
            onNavigate={setPage}
          />
        )}
        {page === 'chat' && (
          <ChatPage
            key={chatKey}
            token={auth.token}
            sessionId={activeSession}
            onSessionChange={setActiveSession}
            role={auth.user.role}
            onNavigate={setPage}
          />
        )}
        {page === 'admin' && (
          <AdminDashboard token={auth.token} />
        )}
        {page === 'upload' && (
          <UploadDocs token={auth.token} role={auth.user.role} />
        )}
        {page === 'tickets' && (
          <TicketsPage token={auth.token} role={auth.user.role} />
        )}
        {page === 'complaints' && (
          <ComplaintsPage token={auth.token} role={auth.user.role} />
        )}
        {page === 'contact-hr' && (
          <ContactHR
            token={auth.token}
            userBranchId={auth.user.branch_id}
            onNavigate={setPage}
          />
        )}
        {page === 'branches' && (
          <BranchManagement token={auth.token} />
        )}
        {page === 'settings' && (
          <UserSettingsPage
            token={auth.token}
            user={auth.user}
            onProfileUpdate={handleProfileUpdate}
          />
        )}
      </main>
    </div>
  )
}

// ── Root — wraps with ToastProvider ──────────────────────────────────────────

export default function App() {
  return (
    <ToastProvider>
      <AppInner />
    </ToastProvider>
  )
}
