import { useState, useEffect, useCallback } from 'react'
import {
  Phone, Mail, MapPin, Building2, Users, CheckCircle,
  XCircle, MessageSquare, ChevronDown,
} from 'lucide-react'
import { getHRContacts, getBranches } from '../services/api'
import type { HRContact, Branch } from '../types/chat'

interface Props {
  token: string
  userBranchId?: string
  onNavigate: (page: string) => void
}

export default function ContactHR({ token, userBranchId, onNavigate }: Props) {
  const [contacts, setContacts] = useState<HRContact[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [filterBranch, setFilterBranch] = useState(userBranchId || '')
  const [loading, setLoading] = useState(false)

  const loadData = useCallback(() => {
    setLoading(true)
    Promise.all([
      getHRContacts(token, filterBranch || undefined).then(d => setContacts(d.contacts || [])),
      getBranches(token).then(d => setBranches(d.branches || [])),
    ])
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [token, filterBranch])

  useEffect(() => { loadData() }, [loadData])

  const myBranch = branches.find(b => b.branch_id === userBranchId)

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Contact HR</h1>
          <p className="text-sm text-gray-500 mt-1">
            Reach out to your HR team for assistance
            {myBranch && <span> &middot; Your branch: <strong>{myBranch.name}</strong></span>}
          </p>
        </div>

        {/* Quick actions */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <button onClick={() => onNavigate('chat')}
            className="bg-gradient-to-r from-blue-500 to-blue-600 rounded-xl p-5 text-white text-left hover:from-blue-600 hover:to-blue-700 transition-all">
            <MessageSquare size={24} className="mb-2" />
            <h3 className="text-sm font-semibold">Ask AI Assistant</h3>
            <p className="text-xs text-blue-100 mt-1">Get instant answers to HR questions</p>
          </button>
          <button onClick={() => onNavigate('tickets')}
            className="bg-gradient-to-r from-green-500 to-green-600 rounded-xl p-5 text-white text-left hover:from-green-600 hover:to-green-700 transition-all">
            <Phone size={24} className="mb-2" />
            <h3 className="text-sm font-semibold">Raise a Ticket</h3>
            <p className="text-xs text-green-100 mt-1">Submit a formal HR request</p>
          </button>
        </div>

        {/* Branch filter */}
        <div className="flex items-center gap-3">
          <Building2 size={16} className="text-gray-400" />
          <select value={filterBranch} onChange={e => setFilterBranch(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
            <option value="">All Branches</option>
            {branches.map(b => (
              <option key={b.branch_id} value={b.branch_id}>{b.name}</option>
            ))}
          </select>
          {filterBranch && (
            <button onClick={() => setFilterBranch('')} className="text-xs text-gray-500 hover:text-gray-700">
              Clear filter
            </button>
          )}
        </div>

        {/* Contact cards */}
        {loading ? (
          <p className="text-sm text-gray-400 text-center py-8">Loading contacts...</p>
        ) : contacts.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
            <Users size={32} className="mx-auto text-gray-300 mb-2" />
            <p className="text-sm text-gray-500">
              {filterBranch ? 'No HR contacts found for this branch.' : 'No HR contacts available.'}
            </p>
            <p className="text-xs text-gray-400 mt-1">You can still use the AI assistant or raise a ticket.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {contacts.map(c => (
              <div key={c.contact_id}
                className={`bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow ${!c.is_available ? 'opacity-60' : ''}`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-sm">
                      {c.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-gray-800">{c.name}</h3>
                      <p className="text-xs text-gray-500 capitalize">{c.role.replace('_', ' ')}</p>
                    </div>
                  </div>
                  {c.is_available ? (
                    <span className="flex items-center gap-1 text-[10px] text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
                      <CheckCircle size={10} /> Available
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-[10px] text-gray-400 bg-gray-50 px-2 py-0.5 rounded-full">
                      <XCircle size={10} /> Away
                    </span>
                  )}
                </div>

                <div className="space-y-2">
                  {c.email && (
                    <a href={`mailto:${c.email}`}
                      className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
                      <Mail size={14} className="text-gray-400" />
                      {c.email}
                    </a>
                  )}
                  {c.phone && (
                    <a href={`tel:${c.phone}`}
                      className="flex items-center gap-2 text-sm text-blue-600 hover:text-blue-800">
                      <Phone size={14} className="text-gray-400" />
                      {c.phone}
                    </a>
                  )}
                  {c.branch_name && (
                    <p className="flex items-center gap-2 text-xs text-gray-500">
                      <MapPin size={14} className="text-gray-400" />
                      {c.branch_name}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
