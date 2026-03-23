import { useState } from 'react'
import {
  MessageSquare, Plus, Settings, LogOut, BarChart3, Upload,
  ChevronLeft, ChevronRight, Search, X, Trash2, Ticket, Shield, Home,
  Phone, Building2,
} from 'lucide-react'
import type { SessionSummary, UserInfo } from '../types/chat'

interface Props {
  user: UserInfo
  sessions: SessionSummary[]
  activeSession: string | null
  onNewChat: () => void
  onSelectSession: (id: string) => void
  onDeleteSession: (id: string) => void
  onNavigate: (page: string) => void
  onLogout: () => void
  currentPage: string
  companyName?: string
  mobileOpen?: boolean
  onMobileClose?: () => void
}

// Group sessions into time buckets for the sidebar
function groupSessions(sessions: SessionSummary[]) {
  const now = Date.now()
  const DAY = 86_400_000

  const groups: { label: string; items: SessionSummary[] }[] = [
    { label: 'Today',     items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'This Week', items: [] },
    { label: 'Older',     items: [] },
  ]

  for (const s of sessions) {
    const age = now - s.last_active * 1000
    if (age < DAY)          groups[0].items.push(s)
    else if (age < 2 * DAY) groups[1].items.push(s)
    else if (age < 7 * DAY) groups[2].items.push(s)
    else                    groups[3].items.push(s)
  }

  return groups.filter(g => g.items.length > 0)
}

export default function Sidebar({
  user, sessions, activeSession, onNewChat, onSelectSession, onDeleteSession,
  onNavigate, onLogout, currentPage, companyName = 'HR Chatbot',
  mobileOpen = true, onMobileClose,
}: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [search, setSearch] = useState('')

  // Phase E: Role-based portal helpers
  const isAdmin = ['hr_admin', 'super_admin', 'admin'].includes(user.role)
  const isHR = ['hr_team', 'hr_head', ...(['hr_admin', 'super_admin', 'admin'] as const)].includes(user.role as any)
  const isHRHead = ['hr_head', 'hr_admin', 'admin', 'super_admin'].includes(user.role)
  const homePage = isAdmin ? 'admin' : isHR ? 'hr-dashboard' : 'home'

  const filtered = search.trim()
    ? sessions.filter(s => (s.preview || '').toLowerCase().includes(search.toLowerCase()))
    : sessions

  const groups = groupSessions(filtered)

  // ── Collapsed (icon-only) sidebar ─────────────────────────────────────────
  if (collapsed) {
    return (
      <div className="w-16 bg-gray-900 text-gray-300 flex flex-col h-full transition-all duration-200">
        {/* Logo */}
        <div className="p-3 flex justify-center border-b border-gray-700">
          <span className="text-lg">🏢</span>
        </div>

        {/* Icon nav */}
        <div className="flex-1 flex flex-col items-center gap-1 py-3">
          <button onClick={() => onNavigate(homePage)} title="Home"
            className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${['home', 'hr-dashboard', 'admin'].includes(currentPage) ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Home size={16} />
          </button>
          <button onClick={onNewChat}
            title="New Chat"
            className="w-10 h-10 flex items-center justify-center rounded-lg border border-gray-600 hover:bg-gray-800 transition-colors">
            <Plus size={16} />
          </button>
          <div className="w-full h-px bg-gray-700 my-1" />
          <button onClick={() => onNavigate('chat')} title="Chat"
            className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${currentPage === 'chat' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <MessageSquare size={16} />
          </button>
          {isAdmin && (
            <button onClick={() => onNavigate('admin')} title="Analytics"
              className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${currentPage === 'admin' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
              <BarChart3 size={16} />
            </button>
          )}
          {isHR && (
            <button onClick={() => onNavigate('upload')} title="Upload Docs"
              className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${currentPage === 'upload' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
              <Upload size={16} />
            </button>
          )}
          <button onClick={() => onNavigate('tickets')} title="Tickets"
            className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${currentPage === 'tickets' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Ticket size={16} />
          </button>
          <button onClick={() => onNavigate('complaints')} title="Complaints"
            className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${currentPage === 'complaints' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Shield size={16} />
          </button>
          <button onClick={() => onNavigate('contact-hr')} title="Contact HR"
            className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${currentPage === 'contact-hr' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Phone size={16} />
          </button>
          {isAdmin && (
            <button onClick={() => onNavigate('branches')} title="Branches"
              className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${currentPage === 'branches' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
              <Building2 size={16} />
            </button>
          )}
        </div>

        <div className="flex flex-col items-center gap-1 p-3 border-t border-gray-700">
          <button onClick={() => onNavigate('settings')} title="Settings"
            className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${currentPage === 'settings' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Settings size={16} />
          </button>
          <button onClick={onLogout} title="Logout"
            className="w-10 h-10 flex items-center justify-center rounded-lg hover:bg-gray-800 text-red-400 transition-colors">
            <LogOut size={16} />
          </button>
          {/* Expand */}
          <button onClick={() => setCollapsed(false)} title="Expand sidebar"
            className="w-10 h-10 flex items-center justify-center rounded-lg hover:bg-gray-800 transition-colors mt-1">
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
    )
  }

  // ── Expanded sidebar ───────────────────────────────────────────────────────
  return (
    <>
      {/* Mobile overlay */}
      {onMobileClose && (
        <div
          className="fixed inset-0 bg-black/40 z-30 md:hidden"
          onClick={onMobileClose}
        />
      )}

      <div className={`
        w-72 bg-gray-900 text-gray-300 flex flex-col h-full transition-all duration-200
        ${onMobileClose ? 'fixed inset-y-0 left-0 z-40 md:relative' : ''}
        ${onMobileClose && !mobileOpen ? '-translate-x-full md:translate-x-0' : 'translate-x-0'}
      `}>
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <div className="min-w-0">
            <h1 className="text-sm font-bold text-white truncate">{companyName}</h1>
            <p className="text-xs text-gray-400 mt-0.5 truncate">{user.role} &middot; {user.department || 'General'}</p>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0 ml-2">
            {/* Mobile close */}
            {onMobileClose && (
              <button onClick={onMobileClose}
                className="md:hidden w-7 h-7 flex items-center justify-center rounded text-gray-400 hover:text-white hover:bg-gray-800">
                <X size={14} />
              </button>
            )}
            {/* Collapse */}
            <button onClick={() => setCollapsed(true)}
              className="hidden md:flex w-7 h-7 items-center justify-center rounded text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
              title="Collapse sidebar">
              <ChevronLeft size={14} />
            </button>
          </div>
        </div>

        {/* New Chat */}
        <div className="p-3">
          <button onClick={onNewChat}
            className="w-full flex items-center gap-2 px-3 py-2.5 border border-gray-600 rounded-lg hover:bg-gray-800 transition-colors text-sm">
            <Plus size={16} /> New Chat
          </button>
        </div>

        {/* Search */}
        {sessions.length > 4 && (
          <div className="px-3 pb-2">
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
              <input
                type="text"
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search chats..."
                className="w-full pl-8 pr-8 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-xs text-gray-300 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              {search && (
                <button onClick={() => setSearch('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
                  <X size={12} />
                </button>
              )}
            </div>
          </div>
        )}

        {/* Sessions — date grouped */}
        <div className="flex-1 overflow-y-auto px-3 space-y-3 pb-2">
          {groups.length === 0 && (
            <p className="text-xs text-gray-500 text-center py-4">
              {search ? 'No matching chats' : 'No chat history yet'}
            </p>
          )}
          {groups.map(group => (
            <div key={group.label}>
              <p className="text-xs text-gray-500 font-medium px-1 mb-1">{group.label}</p>
              <div className="space-y-0.5">
                {group.items.map(s => (
                  <div
                    key={s.session_id}
                    className={`group flex items-center rounded-lg text-sm transition-colors ${
                      activeSession === s.session_id ? 'bg-gray-700 text-white' : 'hover:bg-gray-800 text-gray-300'
                    }`}
                  >
                    <button
                      onClick={() => { onSelectSession(s.session_id); onMobileClose?.() }}
                      className="flex-1 min-w-0 flex items-center gap-2 px-3 py-2 text-left"
                    >
                      <MessageSquare size={13} className="flex-shrink-0 opacity-60" />
                      <span className="truncate text-xs">{s.preview || 'Chat session'}</span>
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); onDeleteSession(s.session_id) }}
                      className="flex-shrink-0 w-7 h-7 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 hover:bg-red-500/20 hover:text-red-400 text-gray-500 transition-all mr-1"
                      title="Delete chat"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Navigation */}
        <div className="border-t border-gray-700 p-3 space-y-0.5">
          <button onClick={() => onNavigate(homePage)}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${['home', 'hr-dashboard', 'admin'].includes(currentPage) ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Home size={14} /> {isAdmin ? 'Admin Home' : isHR ? 'HR Home' : 'Home'}
          </button>

          <button onClick={() => onNavigate('chat')}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'chat' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <MessageSquare size={14} /> Chat
          </button>

          {isAdmin && (
            <button onClick={() => onNavigate('admin')}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'admin' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
              <BarChart3 size={14} /> Analytics
            </button>
          )}
          {isHR && !isAdmin && (
            <button onClick={() => onNavigate('hr-dashboard')}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'hr-dashboard' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
              <BarChart3 size={14} /> HR Dashboard
            </button>
          )}
          {isHR && (
            <button onClick={() => onNavigate('upload')}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'upload' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
              <Upload size={14} /> Upload Docs
            </button>
          )}

          <button onClick={() => onNavigate('tickets')}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'tickets' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Ticket size={14} /> Tickets
          </button>

          <button onClick={() => onNavigate('complaints')}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'complaints' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Shield size={14} /> Complaints
          </button>

          <button onClick={() => onNavigate('contact-hr')}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'contact-hr' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Phone size={14} /> Contact HR
          </button>

          {isAdmin && (
            <button onClick={() => onNavigate('branches')}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'branches' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
              <Building2 size={14} /> Branches
            </button>
          )}

          <button onClick={() => onNavigate('settings')}
            className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'settings' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
            <Settings size={14} /> Settings
          </button>

          <button onClick={onLogout}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-gray-800 text-red-400 transition-colors">
            <LogOut size={14} /> Logout
          </button>
        </div>
      </div>
    </>
  )
}
