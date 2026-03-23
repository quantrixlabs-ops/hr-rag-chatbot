import { useState, useEffect, useCallback } from 'react'
import {
  MessageSquare, Ticket, Shield, Clock, CheckCircle,
  AlertTriangle, ArrowRight, Plus, Phone,
} from 'lucide-react'
import { getTickets, getNotifications, getHRContacts } from '../services/api'
import type { Ticket as TicketType, Notification, HRContact } from '../types/chat'

interface Props {
  token: string
  userName: string
  userBranchId?: string
  onNavigate: (page: string) => void
}

function timeAgo(ts: number): string {
  const diff = Date.now() / 1000 - ts
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const STATUS_COLORS: Record<string, string> = {
  raised: 'bg-yellow-100 text-yellow-800',
  assigned: 'bg-blue-100 text-blue-800',
  in_progress: 'bg-purple-100 text-purple-800',
  resolved: 'bg-green-100 text-green-800',
  closed: 'bg-gray-100 text-gray-700',
  rejected: 'bg-red-100 text-red-800',
}

export default function EmployeeDashboard({ token, userName, userBranchId, onNavigate }: Props) {
  const [tickets, setTickets] = useState<TicketType[]>([])
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [ticketCounts, setTicketCounts] = useState({ open: 0, resolved: 0, total: 0 })
  const [hrContacts, setHrContacts] = useState<HRContact[]>([])

  const loadData = useCallback(() => {
    getTickets(token, { limit: 5 })
      .then(d => {
        const list = d.tickets || []
        setTickets(list)
        const open = list.filter((t: TicketType) => !['resolved', 'closed', 'rejected'].includes(t.status)).length
        const resolved = list.filter((t: TicketType) => t.status === 'resolved').length
        setTicketCounts({ open, resolved, total: d.total || 0 })
      })
      .catch(() => {})

    getNotifications(token)
      .then(d => {
        setNotifications((d.notifications || []).slice(0, 5))
        setUnreadCount(d.unread_count || 0)
      })
      .catch(() => {})

    getHRContacts(token, userBranchId || undefined)
      .then(d => setHrContacts((d.contacts || []).slice(0, 3)))
      .catch(() => {})
  }, [token, userBranchId])

  useEffect(() => { loadData() }, [loadData])

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Welcome header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{greeting}, {userName}!</h1>
          <p className="text-sm text-gray-500 mt-1">Here's your HR portal overview</p>
        </div>

        {/* Quick actions */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <button onClick={() => onNavigate('chat')}
            className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md hover:border-blue-300 transition-all text-left group">
            <MessageSquare size={20} className="text-blue-500 mb-2 group-hover:scale-110 transition-transform" />
            <p className="text-sm font-semibold text-gray-800">Ask HR</p>
            <p className="text-xs text-gray-500 mt-0.5">Chat with AI assistant</p>
          </button>
          <button onClick={() => onNavigate('tickets')}
            className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md hover:border-green-300 transition-all text-left group">
            <Plus size={20} className="text-green-500 mb-2 group-hover:scale-110 transition-transform" />
            <p className="text-sm font-semibold text-gray-800">New Ticket</p>
            <p className="text-xs text-gray-500 mt-0.5">Raise an HR request</p>
          </button>
          <button onClick={() => onNavigate('complaints')}
            className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md hover:border-red-300 transition-all text-left group">
            <Shield size={20} className="text-red-500 mb-2 group-hover:scale-110 transition-transform" />
            <p className="text-sm font-semibold text-gray-800">Report Issue</p>
            <p className="text-xs text-gray-500 mt-0.5">Anonymous complaint</p>
          </button>
          <button onClick={() => onNavigate('contact-hr')}
            className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md hover:border-purple-300 transition-all text-left group">
            <Phone size={20} className="text-purple-500 mb-2 group-hover:scale-110 transition-transform" />
            <p className="text-sm font-semibold text-gray-800">Contact HR</p>
            <p className="text-xs text-gray-500 mt-0.5">Find your HR team</p>
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Ticket summary cards */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-3">
              <Ticket size={16} className="text-blue-500" />
              <h3 className="text-sm font-semibold text-gray-800">My Tickets</h3>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div>
                <p className="text-xl font-bold text-yellow-600">{ticketCounts.open}</p>
                <p className="text-[10px] text-gray-500">Open</p>
              </div>
              <div>
                <p className="text-xl font-bold text-green-600">{ticketCounts.resolved}</p>
                <p className="text-[10px] text-gray-500">Resolved</p>
              </div>
              <div>
                <p className="text-xl font-bold text-gray-600">{ticketCounts.total}</p>
                <p className="text-[10px] text-gray-500">Total</p>
              </div>
            </div>
          </div>

          {/* Unread notifications */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle size={16} className="text-amber-500" />
              <h3 className="text-sm font-semibold text-gray-800">Notifications</h3>
            </div>
            <p className="text-xl font-bold text-amber-600">{unreadCount}</p>
            <p className="text-[10px] text-gray-500">Unread notifications</p>
          </div>

          {/* Quick help */}
          <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-5 text-white">
            <h3 className="text-sm font-semibold mb-1">Need Help?</h3>
            <p className="text-xs text-blue-100 mb-3">Ask our AI assistant any HR-related question.</p>
            <button onClick={() => onNavigate('chat')}
              className="flex items-center gap-1 text-xs bg-white/20 hover:bg-white/30 px-3 py-1.5 rounded-lg transition-colors">
              Start Chat <ArrowRight size={12} />
            </button>
          </div>
        </div>

        {/* Recent tickets */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-800">Recent Tickets</h3>
            <button onClick={() => onNavigate('tickets')}
              className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
              View all <ArrowRight size={11} />
            </button>
          </div>
          {tickets.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-6">No tickets yet</p>
          ) : (
            <div className="divide-y divide-gray-50">
              {tickets.map(t => (
                <div key={t.ticket_id} className="flex items-center justify-between px-5 py-3 hover:bg-gray-50">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-800 truncate">{t.title}</p>
                    <p className="text-[10px] text-gray-400">{timeAgo(t.created_at)}</p>
                  </div>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${STATUS_COLORS[t.status] || 'bg-gray-100 text-gray-600'}`}>
                    {t.status.replace('_', ' ')}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* HR Contacts */}
        {hrContacts.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
              <h3 className="text-sm font-semibold text-gray-800">Your HR Contacts</h3>
              <button onClick={() => onNavigate('contact-hr')}
                className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
                View all <ArrowRight size={11} />
              </button>
            </div>
            <div className="divide-y divide-gray-50">
              {hrContacts.map(c => (
                <div key={c.contact_id} className="flex items-center gap-3 px-5 py-3">
                  <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-xs flex-shrink-0">
                    {c.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-800">{c.name}</p>
                    <p className="text-[10px] text-gray-500 capitalize">{c.role.replace('_', ' ')}{c.branch_name ? ` · ${c.branch_name}` : ''}</p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {c.email && (
                      <a href={`mailto:${c.email}`} className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600">
                        <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
                      </a>
                    )}
                    {c.phone && (
                      <a href={`tel:${c.phone}`} className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-green-600">
                        <Phone size={14} />
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent notifications */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-800">Recent Notifications</h3>
          </div>
          {notifications.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-6">No notifications</p>
          ) : (
            <div className="divide-y divide-gray-50">
              {notifications.map(n => (
                <div key={n.notification_id} className={`flex items-center gap-3 px-5 py-3 ${!n.is_read ? 'bg-blue-50/30' : ''}`}>
                  <Clock size={14} className="text-gray-400 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className={`text-sm truncate ${!n.is_read ? 'font-medium text-gray-900' : 'text-gray-600'}`}>{n.title}</p>
                    {n.message && <p className="text-[10px] text-gray-400 truncate">{n.message}</p>}
                  </div>
                  <span className="text-[10px] text-gray-400 flex-shrink-0">{timeAgo(n.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
