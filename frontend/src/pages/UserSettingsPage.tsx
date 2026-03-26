import { useState, useEffect } from 'react'
import {
  User, ShieldCheck, Download, Trash2, QrCode, CheckCircle,
  Eye, EyeOff, AlertTriangle, Copy, Check, Shield, Lock, Send
} from 'lucide-react'
import {
  getMyProfile, updateMyProfile,
  enrollMfa, confirmMfaEnrollment, disableMfa,
  exportGdprData, requestGdprErasure, changePassword,
} from '../services/api'
import type { UserInfo } from '../types/chat'
import { useToastHelpers } from '../components/NotificationToast'

interface Props {
  token: string
  user: UserInfo
  onProfileUpdate: (updated: Partial<UserInfo>) => void
}

type SettingsTab = 'profile' | 'security' | 'privacy' | 'complaints'

type MfaState = 'idle' | 'enrolling' | 'confirming' | 'done'

export default function UserSettingsPage({ token, user, onProfileUpdate }: Props) {
  const toast = useToastHelpers()
  const [tab, setTab] = useState<SettingsTab>('profile')

  // ── Profile ────────────────────────────────────────────────────────────────
  const [profile, setProfile] = useState({
    full_name: '', email: '', phone: '', department: '', team: '',
    username: '', role: '', employee_id: '', branch_name: '', created_at: 0,
  })
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileSaving, setProfileSaving] = useState(false)
  const [isEditing, setIsEditing] = useState(false)

  useEffect(() => {
    setProfileLoading(true)
    getMyProfile(token)
      .then(d => setProfile({
        full_name: d.full_name || '',
        email: d.email || '',
        phone: d.phone || '',
        department: d.department || '',
        team: d.team || '',
        username: d.username || '',
        role: d.role || '',
        employee_id: d.employee_id || '',
        branch_name: d.branch_name || '',
        created_at: d.created_at || 0,
      }))
      .catch(() => {})
      .finally(() => setProfileLoading(false))
  }, [token])

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setProfileSaving(true)
    try {
      await updateMyProfile(token, profile)
      onProfileUpdate({ department: profile.department || null })
      toast.success('Profile updated', 'Your changes have been saved.')
    } catch (err: any) {
      toast.error('Update failed', err.message)
    } finally {
      setProfileSaving(false)
    }
  }

  // ── Change Password ───────────────────────────────────────────────────────
  const [currentPass, setCurrentPass] = useState('')
  const [newPass, setNewPass] = useState('')
  const [confirmNewPass, setConfirmNewPass] = useState('')
  const [passChanging, setPassChanging] = useState(false)

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (newPass !== confirmNewPass) { toast.error('Mismatch', 'Passwords do not match'); return }
    setPassChanging(true)
    try {
      await changePassword(token, currentPass, newPass)
      toast.success('Password changed', 'Your password has been updated.')
      setCurrentPass(''); setNewPass(''); setConfirmNewPass('')
    } catch (err: any) {
      toast.error('Failed', err.message)
    } finally {
      setPassChanging(false)
    }
  }

  // ── Complaints ───────────────────────────────────────────────────────────
  const [complaintCategory, setComplaintCategory] = useState('other')
  const [complaintDescription, setComplaintDescription] = useState('')
  const [complaintSubmitting, setComplaintSubmitting] = useState(false)
  const [complaintSubmitted, setComplaintSubmitted] = useState(false)

  const COMPLAINT_CATEGORIES = [
    'harassment', 'discrimination', 'fraud', 'safety', 'ethics',
    'retaliation', 'misconduct', 'policy_violation', 'other',
  ]

  const handleSubmitComplaint = async (e: React.FormEvent) => {
    e.preventDefault()
    if (complaintDescription.trim().length < 10) { toast.error('Too short', 'Please provide more detail (min 10 characters).'); return }
    setComplaintSubmitting(true)
    try {
      const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const res = await fetch(`${BASE}/complaints`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ category: complaintCategory, description: complaintDescription }),
      })
      if (!res.ok) throw new Error('Submission failed')
      setComplaintSubmitted(true)
      setComplaintDescription('')
      setComplaintCategory('other')
    } catch (err: any) {
      toast.error('Failed', err.message)
    } finally {
      setComplaintSubmitting(false)
    }
  }

  // ── MFA ────────────────────────────────────────────────────────────────────
  const [mfaEnabled, setMfaEnabled] = useState(false)
  const [mfaState, setMfaState] = useState<MfaState>('idle')
  const [qrDataUrl, setQrDataUrl] = useState('')
  const [otpauthUrl, setOtpauthUrl] = useState('')
  const [mfaSecret, setMfaSecret] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [disableCode, setDisableCode] = useState('')
  const [showDisableForm, setShowDisableForm] = useState(false)
  const [copiedSecret, setCopiedSecret] = useState(false)
  const [copiedCodes, setCopiedCodes] = useState(false)
  const [mfaLoading, setMfaLoading] = useState(false)

  useEffect(() => {
    getMyProfile(token)
      .then(d => setMfaEnabled(!!d.totp_enabled))
      .catch(() => {})
  }, [token])

  const startEnrollment = async () => {
    setMfaLoading(true)
    try {
      const data = await enrollMfa(token)
      setQrDataUrl(data.qr_data_url || '')
      setOtpauthUrl(data.otpauth_url || '')
      setMfaSecret(data.secret || '')
      setMfaState('enrolling')
    } catch (err: any) {
      toast.error('Enrollment failed', err.message)
    } finally {
      setMfaLoading(false)
    }
  }

  const confirmEnrollment = async (e: React.FormEvent) => {
    e.preventDefault()
    setMfaLoading(true)
    try {
      const data = await confirmMfaEnrollment(token, totpCode.replace(/\s/g, ''))
      setRecoveryCodes(data.recovery_codes || [])
      setMfaEnabled(true)
      setMfaState('done')
      setTotpCode('')
      toast.success('MFA enabled', 'Two-factor authentication is now active.')
    } catch (err: any) {
      toast.error('Verification failed', err.message)
      setTotpCode('')
    } finally {
      setMfaLoading(false)
    }
  }

  const handleDisableMfa = async (e: React.FormEvent) => {
    e.preventDefault()
    setMfaLoading(true)
    try {
      await disableMfa(token, disableCode.replace(/\s/g, ''))
      setMfaEnabled(false)
      setShowDisableForm(false)
      setDisableCode('')
      toast.success('MFA disabled', 'Two-factor authentication has been removed.')
    } catch (err: any) {
      toast.error('Disable failed', err.message)
      setDisableCode('')
    } finally {
      setMfaLoading(false)
    }
  }

  const copyToClipboard = (text: string, onDone: () => void) => {
    navigator.clipboard.writeText(text).then(onDone)
  }

  // ── GDPR ───────────────────────────────────────────────────────────────────
  const [gdprExporting, setGdprExporting] = useState(false)
  const [eraseConfirm, setEraseConfirm] = useState('')
  const [eraseLoading, setEraseLoading] = useState(false)
  const [showEraseConfirm, setShowEraseConfirm] = useState(false)

  const downloadDataExport = async () => {
    setGdprExporting(true)
    try {
      const data = await exportGdprData(token, user.user_id)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `hr-chatbot-data-export-${new Date().toISOString().slice(0,10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Export downloaded', 'Your data has been saved to a JSON file.')
    } catch (err: any) {
      toast.error('Export failed', err.message)
    } finally {
      setGdprExporting(false)
    }
  }

  const handleErasure = async (e: React.FormEvent) => {
    e.preventDefault()
    if (eraseConfirm !== 'DELETE MY ACCOUNT') return
    setEraseLoading(true)
    try {
      await requestGdprErasure(token, user.user_id)
      toast.success('Erasure requested', 'Your account will be removed. You will be logged out.')
      setTimeout(() => window.location.reload(), 3000)
    } catch (err: any) {
      toast.error('Erasure failed', err.message)
    } finally {
      setEraseLoading(false)
    }
  }

  // ── Tabs ───────────────────────────────────────────────────────────────────
  const TABS: { id: SettingsTab; label: string; icon: React.ReactNode }[] = [
    { id: 'profile',    label: 'Profile',    icon: <User size={16} /> },
    { id: 'security',   label: 'Security',   icon: <ShieldCheck size={16} /> },
    { id: 'complaints', label: 'Complaints', icon: <Shield size={16} /> },
    { id: 'privacy',    label: 'Privacy',    icon: <Download size={16} /> },
  ]

  return (
    <div className="h-full overflow-y-auto bg-gray-50">
      <div className="max-w-2xl mx-auto p-6 space-y-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Settings</h1>
          <p className="text-sm text-gray-500 mt-1">Manage your account, security, and privacy.</p>
        </div>

        {/* Tab Bar */}
        <div className="flex gap-1 bg-white border border-gray-200 rounded-xl p-1">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === t.id
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* ── Profile Tab ─────────────────────────────────────────────────── */}
        {tab === 'profile' && (
          <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">Personal Information</h2>
              {!isEditing ? (
                <button onClick={() => setIsEditing(true)}
                  className="px-4 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors">
                  Edit Profile
                </button>
              ) : (
                <button onClick={() => setIsEditing(false)}
                  className="px-4 py-1.5 text-sm font-medium text-gray-500 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors">
                  Cancel
                </button>
              )}
            </div>

            {profileLoading ? (
              <div className="space-y-3 animate-pulse">
                {[1,2,3,4,5,6].map(i => <div key={i} className="h-10 bg-gray-100 rounded-lg" />)}
              </div>
            ) : !isEditing ? (
              /* ── Read-Only View ── */
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Full Name</p>
                    <p className="text-sm font-medium text-gray-900">{profile.full_name || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Username</p>
                    <p className="text-sm font-medium text-gray-900">{profile.username || '—'}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Employee ID</p>
                    <p className="text-sm text-gray-900">{profile.employee_id || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Role</p>
                    <p className="text-sm"><span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-xs font-medium">{profile.role}</span></p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Email Address</p>
                    <p className="text-sm text-gray-900">{profile.email || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Phone Number</p>
                    <p className="text-sm text-gray-900">{profile.phone || '—'}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Department</p>
                    <p className="text-sm text-gray-900">{profile.department || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Team</p>
                    <p className="text-sm text-gray-900">{profile.team || '—'}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Branch / Location</p>
                    <p className="text-sm text-gray-900">{profile.branch_name || '—'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-400 mb-1">Member Since</p>
                    <p className="text-sm text-gray-900">{profile.created_at ? new Date(profile.created_at * 1000).toLocaleDateString() : '—'}</p>
                  </div>
                </div>
              </div>
            ) : (
              /* ── Edit View ── */
              <form onSubmit={async (e) => { e.preventDefault(); await saveProfile(e); setIsEditing(false); }} className="space-y-4">
                {/* Read-only fields shown as info */}
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 grid grid-cols-3 gap-3">
                  <div>
                    <p className="text-[10px] font-medium text-gray-400">Username</p>
                    <p className="text-xs font-medium text-gray-700">{profile.username}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-medium text-gray-400">Role</p>
                    <p className="text-xs font-medium text-gray-700">{profile.role}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-medium text-gray-400">Employee ID</p>
                    <p className="text-xs font-medium text-gray-700">{profile.employee_id || '—'}</p>
                  </div>
                </div>

                {/* Editable fields */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Full Name</label>
                    <input type="text" value={profile.full_name}
                      onChange={e => setProfile(p => ({ ...p, full_name: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Department</label>
                    <input type="text" value={profile.department}
                      onChange={e => setProfile(p => ({ ...p, department: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Email Address</label>
                  <input type="email" value={profile.email}
                    onChange={e => setProfile(p => ({ ...p, email: e.target.value }))}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Phone Number</label>
                    <input type="tel" value={profile.phone}
                      onChange={e => setProfile(p => ({ ...p, phone: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Team</label>
                    <input type="text" value={profile.team}
                      onChange={e => setProfile(p => ({ ...p, team: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
                  </div>
                </div>
                <div className="flex justify-end pt-2">
                  <button type="submit" disabled={profileSaving}
                    className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors">
                    {profileSaving ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            )}
          </div>
        )}

        {/* ── Security Tab ────────────────────────────────────────────────── */}
        {tab === 'security' && (
          <div className="space-y-4">
            <div className="bg-white border border-gray-200 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center ${mfaEnabled ? 'bg-emerald-100' : 'bg-gray-100'}`}>
                    <ShieldCheck size={20} className={mfaEnabled ? 'text-emerald-600' : 'text-gray-400'} />
                  </div>
                  <div>
                    <h2 className="font-semibold text-gray-900">Two-Factor Authentication</h2>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {mfaEnabled ? 'Active — your account has extra protection.' : 'Not enabled — add extra security to your account.'}
                    </p>
                  </div>
                </div>
                <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${mfaEnabled ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
                  {mfaEnabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>

              {/* Not enrolled */}
              {!mfaEnabled && mfaState === 'idle' && (
                <button onClick={startEnrollment} disabled={mfaLoading}
                  className="w-full py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors flex items-center justify-center gap-2">
                  <QrCode size={16} /> {mfaLoading ? 'Loading...' : 'Set Up Authenticator App'}
                </button>
              )}

              {/* Step 1: Show QR code */}
              {mfaState === 'enrolling' && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600">
                    Scan the QR code with your authenticator app (Google Authenticator, Authy, etc.), then enter the 6-digit code below.
                  </p>
                  {qrDataUrl && (
                    <div className="flex justify-center">
                      <img src={qrDataUrl} alt="TOTP QR code" className="w-48 h-48 border border-gray-200 rounded-lg p-2" />
                    </div>
                  )}
                  {/* Manual entry */}
                  <div className="bg-gray-50 rounded-lg p-3">
                    <p className="text-xs text-gray-500 mb-1">Can't scan? Enter this key manually:</p>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 text-xs font-mono text-gray-800 break-all">{mfaSecret}</code>
                      <button
                        onClick={() => copyToClipboard(mfaSecret, () => { setCopiedSecret(true); setTimeout(() => setCopiedSecret(false), 2000) })}
                        className="text-blue-500 hover:text-blue-700 flex-shrink-0"
                      >
                        {copiedSecret ? <Check size={14} /> : <Copy size={14} />}
                      </button>
                    </div>
                  </div>
                  <form onSubmit={confirmEnrollment} className="flex gap-2">
                    <input
                      type="text"
                      inputMode="numeric"
                      maxLength={7}
                      value={totpCode}
                      onChange={e => setTotpCode(e.target.value)}
                      placeholder="000 000"
                      autoFocus
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-center font-mono tracking-[0.3em] text-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                    <button type="submit" disabled={mfaLoading || totpCode.replace(/\s/g, '').length < 6}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors">
                      {mfaLoading ? '...' : 'Verify'}
                    </button>
                  </form>
                </div>
              )}

              {/* Step 2: Recovery codes */}
              {mfaState === 'done' && recoveryCodes.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-start gap-2 text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
                    <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
                    <p className="text-xs">Save these recovery codes somewhere safe. Each code can only be used once and won't be shown again.</p>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {recoveryCodes.map((code, i) => (
                      <code key={i} className="text-xs font-mono bg-gray-50 border border-gray-200 rounded px-2.5 py-1.5 text-center">{code}</code>
                    ))}
                  </div>
                  <button
                    onClick={() => copyToClipboard(recoveryCodes.join('\n'), () => { setCopiedCodes(true); setTimeout(() => setCopiedCodes(false), 2000) })}
                    className="w-full py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors flex items-center justify-center gap-2"
                  >
                    {copiedCodes ? <><Check size={14} className="text-emerald-500" /> Copied!</> : <><Copy size={14} /> Copy all codes</>}
                  </button>
                  <button onClick={() => setMfaState('idle')}
                    className="w-full py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 text-sm font-medium transition-colors flex items-center justify-center gap-2">
                    <CheckCircle size={14} /> Done — I've saved my codes
                  </button>
                </div>
              )}

              {/* Enrolled — disable option */}
              {mfaEnabled && mfaState === 'idle' && !showDisableForm && (
                <button onClick={() => setShowDisableForm(true)}
                  className="w-full py-2 border border-red-200 text-red-600 rounded-lg hover:bg-red-50 text-sm font-medium transition-colors">
                  Disable Two-Factor Authentication
                </button>
              )}

              {mfaEnabled && showDisableForm && (
                <form onSubmit={handleDisableMfa} className="space-y-3">
                  <p className="text-sm text-gray-600">Enter your current authenticator code to confirm:</p>
                  <input
                    type="text" inputMode="numeric" maxLength={7}
                    value={disableCode} onChange={e => setDisableCode(e.target.value)}
                    placeholder="000 000" autoFocus
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-center font-mono tracking-[0.3em] text-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
                  />
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { setShowDisableForm(false); setDisableCode('') }}
                      className="flex-1 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">
                      Cancel
                    </button>
                    <button type="submit" disabled={mfaLoading || disableCode.replace(/\s/g, '').length < 6}
                      className="flex-1 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 text-sm font-medium transition-colors">
                      {mfaLoading ? 'Disabling...' : 'Disable MFA'}
                    </button>
                  </div>
                </form>
              )}
            </div>
          {/* Change Password */}
            <div className="bg-white border border-gray-200 rounded-xl p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center">
                  <Lock size={20} className="text-amber-600" />
                </div>
                <div>
                  <h2 className="font-semibold text-gray-900">Change Password</h2>
                  <p className="text-xs text-gray-500">Update your password</p>
                </div>
              </div>
              <form onSubmit={handleChangePassword} className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Current Password</label>
                  <input type="password" value={currentPass} onChange={e => setCurrentPass(e.target.value)} required
                    placeholder="Enter current password"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-transparent text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">New Password</label>
                  <input type="password" value={newPass} onChange={e => setNewPass(e.target.value)} required
                    placeholder="Min 12 chars, letter + number + symbol"
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-transparent text-sm" />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Confirm New Password</label>
                  <input type="password" value={confirmNewPass} onChange={e => setConfirmNewPass(e.target.value)} required
                    placeholder="Re-enter new password"
                    className={`w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-amber-500 focus:border-transparent text-sm ${
                      confirmNewPass && confirmNewPass !== newPass ? 'border-red-300 bg-red-50' : 'border-gray-300'
                    }`} />
                </div>
                <button type="submit" disabled={passChanging || !currentPass || !newPass || newPass !== confirmNewPass}
                  className="px-5 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 text-sm font-medium transition-colors">
                  {passChanging ? 'Changing...' : 'Change Password'}
                </button>
              </form>
            </div>
          </div>
        )}

        {/* ── Complaints Tab ─────────────────────────────────────────────── */}
        {tab === 'complaints' && (
          <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-5">
            {complaintSubmitted ? (
              <div className="text-center py-8">
                <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <CheckCircle size={32} className="text-emerald-600" />
                </div>
                <h2 className="text-lg font-bold text-gray-900 mb-2">Complaint Submitted</h2>
                <p className="text-sm text-gray-500 mb-4">Your complaint has been submitted anonymously. Only HR Head can view it.</p>
                <button onClick={() => setComplaintSubmitted(false)}
                  className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                  Submit Another
                </button>
              </div>
            ) : (
              <>
                <div>
                  <h2 className="font-semibold text-gray-900 flex items-center gap-2">
                    <Shield size={18} className="text-violet-600" /> Raise a Complaint
                  </h2>
                  <p className="text-xs text-gray-500 mt-1">Submit a workplace complaint. All submissions are fully anonymous.</p>
                </div>

                <div className="bg-violet-50 border border-violet-200 rounded-lg p-3 flex items-start gap-2">
                  <AlertTriangle size={16} className="text-violet-600 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-violet-700">
                    <strong>Privacy guarantee:</strong> No user identity or IP address is stored with your complaint.
                    Only HR Head can view and investigate complaints.
                  </p>
                </div>

                <form onSubmit={handleSubmitComplaint} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Category</label>
                    <select value={complaintCategory} onChange={e => setComplaintCategory(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent text-sm bg-white">
                      {COMPLAINT_CATEGORIES.map(c => (
                        <option key={c} value={c}>{c.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Description</label>
                    <textarea value={complaintDescription} onChange={e => setComplaintDescription(e.target.value)}
                      rows={5} required minLength={10} maxLength={5000}
                      placeholder="Describe the issue in detail (minimum 10 characters)..."
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent text-sm resize-none" />
                    <p className="text-xs text-gray-400 text-right mt-0.5">{complaintDescription.length}/5000</p>
                  </div>

                  <button type="submit" disabled={complaintSubmitting || complaintDescription.trim().length < 10}
                    className="inline-flex items-center gap-2 px-5 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-50 text-sm font-medium transition-colors">
                    <Send size={14} /> {complaintSubmitting ? 'Submitting...' : 'Submit Complaint'}
                  </button>
                </form>
              </>
            )}
          </div>
        )}

        {/* ── Privacy Tab ─────────────────────────────────────────────────── */}
        {tab === 'privacy' && (
          <div className="space-y-4">
            {/* Data Export */}
            <div className="bg-white border border-gray-200 rounded-xl p-6">
              <div className="flex items-start gap-3 mb-4">
                <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <Download size={18} className="text-blue-600" />
                </div>
                <div>
                  <h2 className="font-semibold text-gray-900">Download Your Data</h2>
                  <p className="text-xs text-gray-500 mt-1">
                    Export all personal data we hold about you — chat history, profile, audit log.
                    This is your right under GDPR Article 15.
                  </p>
                </div>
              </div>
              <button onClick={downloadDataExport} disabled={gdprExporting}
                className="w-full py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors flex items-center justify-center gap-2">
                <Download size={15} /> {gdprExporting ? 'Preparing export...' : 'Download Data Export (JSON)'}
              </button>
            </div>

            {/* Account Erasure */}
            <div className="bg-white border border-red-200 rounded-xl p-6">
              <div className="flex items-start gap-3 mb-4">
                <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <Trash2 size={18} className="text-red-600" />
                </div>
                <div>
                  <h2 className="font-semibold text-red-800">Delete My Account</h2>
                  <p className="text-xs text-gray-500 mt-1">
                    Permanently erase your personal data — messages, profile, sessions.
                    Audit logs are anonymised and retained for compliance (7 years).
                    This action cannot be undone.
                  </p>
                </div>
              </div>

              {!showEraseConfirm ? (
                <button onClick={() => setShowEraseConfirm(true)}
                  className="w-full py-2.5 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 text-sm font-medium transition-colors">
                  Request Account Erasure (GDPR Art. 17)
                </button>
              ) : (
                <form onSubmit={handleErasure} className="space-y-3">
                  <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg p-3">
                    <AlertTriangle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
                    <p className="text-xs text-red-700">
                      Type <strong>DELETE MY ACCOUNT</strong> exactly to confirm permanent erasure.
                    </p>
                  </div>
                  <input
                    type="text"
                    value={eraseConfirm}
                    onChange={e => setEraseConfirm(e.target.value)}
                    placeholder="DELETE MY ACCOUNT"
                    className="w-full px-3 py-2 border border-red-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500 focus:border-transparent font-mono"
                  />
                  <div className="flex gap-2">
                    <button type="button" onClick={() => { setShowEraseConfirm(false); setEraseConfirm('') }}
                      className="flex-1 py-2 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">
                      Cancel
                    </button>
                    <button type="submit"
                      disabled={eraseLoading || eraseConfirm !== 'DELETE MY ACCOUNT'}
                      className="flex-1 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 text-sm font-medium transition-colors">
                      {eraseLoading ? 'Processing...' : 'Erase My Account'}
                    </button>
                  </div>
                </form>
              )}
            </div>

            <p className="text-xs text-gray-400 text-center">
              Questions about your data? Contact{' '}
              <a href="mailto:privacy@company.com" className="text-blue-500 hover:underline">privacy@company.com</a>
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
