import { useState, useEffect, useCallback } from 'react'
import {
  Building2, Plus, Edit2, Trash2, Users, MapPin, CheckCircle,
  XCircle, RefreshCw, Phone, Mail, UserPlus, X,
} from 'lucide-react'
import {
  getBranches, createBranch, updateBranch, deleteBranch, getBranchStats,
  getHRContacts, createHRContact, updateHRContact, deleteHRContact,
} from '../services/api'
import type { Branch, BranchStats, HRContact } from '../types/chat'

interface Props {
  token: string
}

export default function BranchManagement({ token }: Props) {
  const [branches, setBranches] = useState<Branch[]>([])
  const [contacts, setContacts] = useState<HRContact[]>([])
  const [tab, setTab] = useState<'branches' | 'contacts'>('branches')
  const [loading, setLoading] = useState(false)
  const [showAll, setShowAll] = useState(false)

  // Branch form
  const [showBranchForm, setShowBranchForm] = useState(false)
  const [editBranch, setEditBranch] = useState<Branch | null>(null)
  const [branchName, setBranchName] = useState('')
  const [branchLocation, setBranchLocation] = useState('')
  const [branchAddress, setBranchAddress] = useState('')

  // Contact form
  const [showContactForm, setShowContactForm] = useState(false)
  const [editContact, setEditContact] = useState<HRContact | null>(null)
  const [contactName, setContactName] = useState('')
  const [contactRole, setContactRole] = useState('hr_team')
  const [contactEmail, setContactEmail] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [contactBranch, setContactBranch] = useState('')

  // Stats
  const [selectedStats, setSelectedStats] = useState<BranchStats | null>(null)

  const loadBranches = useCallback(() => {
    setLoading(true)
    getBranches(token, !showAll)
      .then(d => setBranches(d.branches || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [token, showAll])

  const loadContacts = useCallback(() => {
    getHRContacts(token)
      .then(d => setContacts(d.contacts || []))
      .catch(() => {})
  }, [token])

  useEffect(() => { loadBranches() }, [loadBranches])
  useEffect(() => { loadContacts() }, [loadContacts])

  const openBranchForm = (branch?: Branch) => {
    if (branch) {
      setEditBranch(branch)
      setBranchName(branch.name)
      setBranchLocation(branch.location)
      setBranchAddress(branch.address)
    } else {
      setEditBranch(null)
      setBranchName('')
      setBranchLocation('')
      setBranchAddress('')
    }
    setShowBranchForm(true)
  }

  const saveBranch = async () => {
    if (!branchName.trim()) return
    try {
      if (editBranch) {
        await updateBranch(token, editBranch.branch_id, {
          name: branchName, location: branchLocation, address: branchAddress,
        })
      } else {
        await createBranch(token, {
          name: branchName, location: branchLocation, address: branchAddress,
        })
      }
      setShowBranchForm(false)
      loadBranches()
    } catch { /* ignore */ }
  }

  const handleDeleteBranch = async (b: Branch) => {
    if (!confirm(`Deactivate branch "${b.name}"?`)) return
    await deleteBranch(token, b.branch_id).catch(() => {})
    loadBranches()
  }

  const openContactForm = (contact?: HRContact) => {
    if (contact) {
      setEditContact(contact)
      setContactName(contact.name)
      setContactRole(contact.role)
      setContactEmail(contact.email)
      setContactPhone(contact.phone)
      setContactBranch(contact.branch_id)
    } else {
      setEditContact(null)
      setContactName('')
      setContactRole('hr_team')
      setContactEmail('')
      setContactPhone('')
      setContactBranch('')
    }
    setShowContactForm(true)
  }

  const saveContact = async () => {
    if (!contactName.trim()) return
    try {
      if (editContact) {
        await updateHRContact(token, editContact.contact_id, {
          name: contactName, role: contactRole, email: contactEmail,
          phone: contactPhone, branch_id: contactBranch,
        })
      } else {
        await createHRContact(token, {
          name: contactName, role: contactRole, email: contactEmail,
          phone: contactPhone, branch_id: contactBranch,
        })
      }
      setShowContactForm(false)
      loadContacts()
    } catch { /* ignore */ }
  }

  const handleDeleteContact = async (c: HRContact) => {
    if (!confirm(`Delete contact "${c.name}"?`)) return
    await deleteHRContact(token, c.contact_id).catch(() => {})
    loadContacts()
  }

  const viewBranchStats = async (branchId: string) => {
    try {
      const stats = await getBranchStats(token, branchId)
      setSelectedStats(stats)
    } catch { /* ignore */ }
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Branch & Contact Management</h1>
            <p className="text-sm text-gray-500 mt-1">Manage organizational branches and HR contacts</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-gray-200">
          <button onClick={() => setTab('branches')}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === 'branches' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}>
            <Building2 size={15} /> Branches ({branches.length})
          </button>
          <button onClick={() => setTab('contacts')}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === 'contacts' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}>
            <Phone size={15} /> HR Contacts ({contacts.length})
          </button>
        </div>

        {/* Branches Tab */}
        {tab === 'branches' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)}
                  className="rounded border-gray-300" />
                Show inactive branches
              </label>
              <button onClick={() => openBranchForm()}
                className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800">
                <Plus size={14} /> Add Branch
              </button>
            </div>

            {loading ? (
              <p className="text-sm text-gray-400 text-center py-8">Loading...</p>
            ) : branches.length === 0 ? (
              <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
                <Building2 size={32} className="mx-auto text-gray-300 mb-2" />
                <p className="text-sm text-gray-500">No branches yet. Create your first branch.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {branches.map(b => (
                  <div key={b.branch_id} className={`bg-white rounded-xl border border-gray-200 p-5 ${!b.is_active ? 'opacity-60' : ''}`}>
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <h3 className="text-sm font-semibold text-gray-800">{b.name}</h3>
                        {b.location && (
                          <p className="text-xs text-gray-500 flex items-center gap-1 mt-0.5">
                            <MapPin size={10} /> {b.location}
                          </p>
                        )}
                      </div>
                      {b.is_active ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-green-100 text-green-700">Active</span>
                      ) : (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-500">Inactive</span>
                      )}
                    </div>
                    {b.address && <p className="text-xs text-gray-400 mb-3">{b.address}</p>}
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-500 flex items-center gap-1">
                        <Users size={12} /> {b.user_count} users
                      </span>
                      <div className="flex items-center gap-1">
                        <button onClick={() => viewBranchStats(b.branch_id)}
                          className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600" title="View stats">
                          <RefreshCw size={13} />
                        </button>
                        <button onClick={() => openBranchForm(b)}
                          className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600" title="Edit">
                          <Edit2 size={13} />
                        </button>
                        <button onClick={() => handleDeleteBranch(b)}
                          className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-red-600" title="Deactivate">
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Branch stats popup */}
            {selectedStats && (
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-blue-800">Branch Statistics</h3>
                  <button onClick={() => setSelectedStats(null)} className="text-blue-400 hover:text-blue-600">
                    <X size={14} />
                  </button>
                </div>
                <div className="grid grid-cols-4 gap-4 text-center">
                  <div><p className="text-xl font-bold text-blue-800">{selectedStats.user_count}</p><p className="text-[10px] text-blue-600">Users</p></div>
                  <div><p className="text-xl font-bold text-blue-800">{selectedStats.ticket_count}</p><p className="text-[10px] text-blue-600">Total Tickets</p></div>
                  <div><p className="text-xl font-bold text-yellow-700">{selectedStats.open_tickets}</p><p className="text-[10px] text-blue-600">Open Tickets</p></div>
                  <div><p className="text-xl font-bold text-green-700">{selectedStats.hr_contact_count}</p><p className="text-[10px] text-blue-600">HR Contacts</p></div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Contacts Tab */}
        {tab === 'contacts' && (
          <div className="space-y-4">
            <div className="flex items-center justify-end">
              <button onClick={() => openContactForm()}
                className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800">
                <UserPlus size={14} /> Add Contact
              </button>
            </div>

            {contacts.length === 0 ? (
              <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
                <Phone size={32} className="mx-auto text-gray-300 mb-2" />
                <p className="text-sm text-gray-500">No HR contacts yet.</p>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                    <tr>
                      <th className="px-4 py-3 text-left">Name</th>
                      <th className="px-4 py-3 text-left">Role</th>
                      <th className="px-4 py-3 text-left">Email</th>
                      <th className="px-4 py-3 text-left">Phone</th>
                      <th className="px-4 py-3 text-left">Branch</th>
                      <th className="px-4 py-3 text-left">Status</th>
                      <th className="px-4 py-3 text-left">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {contacts.map(c => (
                      <tr key={c.contact_id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-800">{c.name}</td>
                        <td className="px-4 py-3">
                          <span className="px-2 py-0.5 rounded-full text-xs bg-blue-50 text-blue-700">{c.role}</span>
                        </td>
                        <td className="px-4 py-3 text-gray-600">
                          {c.email ? <a href={`mailto:${c.email}`} className="text-blue-600 hover:underline">{c.email}</a> : '—'}
                        </td>
                        <td className="px-4 py-3 text-gray-600">{c.phone || '—'}</td>
                        <td className="px-4 py-3 text-gray-500">{c.branch_name || 'All'}</td>
                        <td className="px-4 py-3">
                          {c.is_available ? (
                            <span className="flex items-center gap-1 text-xs text-green-600"><CheckCircle size={12} /> Available</span>
                          ) : (
                            <span className="flex items-center gap-1 text-xs text-gray-400"><XCircle size={12} /> Away</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            <button onClick={() => openContactForm(c)} className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-blue-600">
                              <Edit2 size={13} />
                            </button>
                            <button onClick={() => handleDeleteContact(c)} className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-red-600">
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Branch Form Modal */}
        {showBranchForm && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">
                {editBranch ? 'Edit Branch' : 'New Branch'}
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Branch Name *</label>
                  <input value={branchName} onChange={e => setBranchName(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Location</label>
                  <input value={branchLocation} onChange={e => setBranchLocation(e.target.value)}
                    placeholder="e.g., New York, NY"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Address</label>
                  <input value={branchAddress} onChange={e => setBranchAddress(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-5">
                <button onClick={() => setShowBranchForm(false)}
                  className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">Cancel</button>
                <button onClick={saveBranch} disabled={!branchName.trim()}
                  className="px-4 py-2 text-sm bg-gray-900 text-white rounded-lg hover:bg-gray-800 disabled:opacity-50">
                  {editBranch ? 'Save' : 'Create'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Contact Form Modal */}
        {showContactForm && (
          <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">
                {editContact ? 'Edit Contact' : 'New HR Contact'}
              </h3>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Name *</label>
                  <input value={contactName} onChange={e => setContactName(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Role</label>
                  <select value={contactRole} onChange={e => setContactRole(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <option value="hr_team">HR Team</option>
                    <option value="hr_head">HR Head</option>
                    <option value="hr_admin">HR Admin</option>
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Email</label>
                    <input value={contactEmail} onChange={e => setContactEmail(e.target.value)} type="email"
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Phone</label>
                    <input value={contactPhone} onChange={e => setContactPhone(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500" />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Branch</label>
                  <select value={contactBranch} onChange={e => setContactBranch(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm">
                    <option value="">All Branches</option>
                    {branches.map(b => (
                      <option key={b.branch_id} value={b.branch_id}>{b.name}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-5">
                <button onClick={() => setShowContactForm(false)}
                  className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">Cancel</button>
                <button onClick={saveContact} disabled={!contactName.trim()}
                  className="px-4 py-2 text-sm bg-gray-900 text-white rounded-lg hover:bg-gray-800 disabled:opacity-50">
                  {editContact ? 'Save' : 'Create'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
