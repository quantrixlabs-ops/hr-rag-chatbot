import { MessageSquare, Plus, Settings, LogOut, BarChart3, Upload } from 'lucide-react'
import type { SessionSummary, UserInfo } from '../types/chat'

interface Props {
  user: UserInfo
  sessions: SessionSummary[]
  activeSession: string | null
  onNewChat: () => void
  onSelectSession: (id: string) => void
  onNavigate: (page: string) => void
  onLogout: () => void
  currentPage: string
}

export default function Sidebar({ user, sessions, activeSession, onNewChat, onSelectSession, onNavigate, onLogout, currentPage }: Props) {
  return (
    <div className="w-72 bg-gray-900 text-gray-300 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <h1 className="text-lg font-bold text-white">HR Chatbot</h1>
        <p className="text-xs text-gray-400 mt-0.5">{user.role} &middot; {user.department || 'General'}</p>
      </div>

      {/* New Chat */}
      <div className="p-3">
        <button onClick={onNewChat} className="w-full flex items-center gap-2 px-3 py-2.5 border border-gray-600 rounded-lg hover:bg-gray-800 transition-colors text-sm">
          <Plus size={16} /> New Chat
        </button>
      </div>

      {/* Sessions */}
      <div className="flex-1 overflow-y-auto px-3 space-y-1">
        {sessions.map(s => (
          <button
            key={s.session_id}
            onClick={() => onSelectSession(s.session_id)}
            className={`w-full text-left flex items-center gap-2 px-3 py-2 rounded-lg text-sm truncate transition-colors ${activeSession === s.session_id ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}
          >
            <MessageSquare size={14} className="flex-shrink-0" />
            <span className="truncate">{s.preview || 'Chat session'}</span>
          </button>
        ))}
      </div>

      {/* Navigation */}
      <div className="border-t border-gray-700 p-3 space-y-1">
        <button onClick={() => onNavigate('chat')} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'chat' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
          <MessageSquare size={14} /> Chat
        </button>
        {user.role === 'hr_admin' && (
          <>
            <button onClick={() => onNavigate('admin')} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'admin' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
              <BarChart3 size={14} /> Dashboard
            </button>
            <button onClick={() => onNavigate('upload')} className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${currentPage === 'upload' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}`}>
              <Upload size={14} /> Upload Docs
            </button>
          </>
        )}
        <button onClick={onLogout} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-gray-800 text-red-400 transition-colors">
          <LogOut size={14} /> Logout
        </button>
      </div>
    </div>
  )
}
