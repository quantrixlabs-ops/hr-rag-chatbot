import { useState, useEffect, useCallback } from 'react'
import {
  getMetrics, getFailedQueries, getSecurityEvents,
  getUsers, getPendingUsers, approveUser, suspendUser,
  getAiProviders, getSupportedProviders, createAiProvider, updateAiProvider,
  deleteAiProvider, testAiProvider, getAiUsage, getAiMode, setAiMode,
  getModelRouting, setModelRouting,
} from '../services/api'
import type { AdminMetrics } from '../types/chat'
import { BarChart3, FileText, AlertTriangle, Clock, Shield, ShieldAlert, XCircle, TrendingUp, Users, CheckCircle, ThumbsDown, RefreshCw, UserCheck, Ban, Cpu, Plus, Trash2, Zap, Eye, EyeOff, Activity } from 'lucide-react'

interface Props {
  token: string
}

function StatCard({ icon, label, value, color, subtext }: { icon: React.ReactNode; label: string; value: string | number; color: string; subtext?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow">
      <div className="flex items-center gap-3">
        <div className={`p-2.5 rounded-lg ${color}`}>{icon}</div>
        <div>
          <p className="text-2xl font-bold text-gray-900">{value}</p>
          <p className="text-xs text-gray-500">{label}</p>
          {subtext && <p className="text-[10px] text-gray-400 mt-0.5">{subtext}</p>}
        </div>
      </div>
    </div>
  )
}

export default function AdminDashboard({ token }: Props) {
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null)
  const [failedQueries, setFailedQueries] = useState<any[]>([])
  const [securityEvents, setSecurityEvents] = useState<any[]>([])
  const [users, setUsers] = useState<any[]>([])
  const [pendingUsers, setPendingUsers] = useState<any[]>([])
  const [tab, setTab] = useState<'overview' | 'failed' | 'security' | 'users' | 'ai'>('overview')
  const [refreshing, setRefreshing] = useState(false)
  const [userFilter, setUserFilter] = useState('')
  // AI Configuration state
  const [aiProviders, setAiProviders] = useState<any[]>([])
  const [supportedProviders, setSupportedProviders] = useState<any[]>([])
  const [aiUsage, setAiUsage] = useState<any>(null)
  const [showAddProvider, setShowAddProvider] = useState(false)
  const [newProvider, setNewProvider] = useState({ provider_name: '', api_key: '', model_name: '', priority: 10, status: 'active', usage_limit: 0 })
  const [testingProvider, setTestingProvider] = useState('')
  const [testResult, setTestResult] = useState<any>(null)
  // AI Mode state
  const [aiMode, setAiModeState] = useState<any>({ ai_mode: 'internal', active_provider: '', provider_display_name: '', provider_model: '' })
  const [switchingMode, setSwitchingMode] = useState(false)
  // Model routing state
  const [routingConfig, setRoutingConfig] = useState<any[]>([])
  const [editingTier, setEditingTier] = useState<string | null>(null)
  const [editModel, setEditModel] = useState('')

  const loadAiData = useCallback(() => {
    getAiProviders(token).then(d => setAiProviders(d.providers || [])).catch(() => {})
    getSupportedProviders(token).then(d => setSupportedProviders(d.providers || [])).catch(() => {})
    getAiUsage(token, 7).then(setAiUsage).catch(() => {})
    getAiMode(token).then(setAiModeState).catch(() => {})
    getModelRouting(token).then(d => setRoutingConfig(d.routing || [])).catch(() => {})
  }, [token])

  const refreshData = useCallback(() => {
    setRefreshing(true)
    Promise.all([
      getMetrics(token).then(setMetrics).catch(() => {}),
      getFailedQueries(token).then(d => setFailedQueries(d.failed_queries || [])).catch(() => {}),
      getSecurityEvents(token).then(d => setSecurityEvents(d.events || [])).catch(() => {}),
      getUsers(token).then(d => setUsers(d.users || [])).catch(() => {}),
      getPendingUsers(token).then(d => setPendingUsers(d.pending_users || d.users || [])).catch(() => {}),
    ]).finally(() => setRefreshing(false))
    loadAiData()
  }, [token, loadAiData])

  useEffect(() => { refreshData() }, [refreshData])

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(refreshData, 30000)
    return () => clearInterval(interval)
  }, [refreshData])

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Analytics Dashboard</h1>
            <p className="text-sm text-gray-500 mt-1">Real-time metrics and system health</p>
          </div>
          <button onClick={refreshData} disabled={refreshing}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-40 transition-colors">
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>

        {/* Metrics Grid */}
        {metrics && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard icon={<BarChart3 size={18} className="text-blue-600" />} label="Queries Today" value={metrics.queries_today} color="bg-blue-50" subtext={`${metrics.queries_this_week} this week`} />
            <StatCard icon={<Clock size={18} className="text-amber-600" />} label="Avg Latency" value={`${metrics.avg_latency_ms}ms`} color="bg-amber-50" />
            <StatCard icon={<Shield size={18} className="text-emerald-600" />} label="Faithfulness" value={`${Math.round(metrics.avg_faithfulness * 100)}%`} color="bg-emerald-50" subtext={`${Math.round(metrics.query_success_rate * 100)}% success rate`} />
            <StatCard icon={<AlertTriangle size={18} className="text-red-600" />} label="Hallucination Rate" value={`${Math.round(metrics.hallucination_rate * 100)}%`} color="bg-red-50" subtext={`${metrics.failed_queries} failed queries`} />
            <StatCard icon={<FileText size={18} className="text-purple-600" />} label="Documents" value={metrics.total_documents} color="bg-purple-50" subtext={`${metrics.total_chunks} chunks indexed`} />
            <StatCard icon={<Users size={18} className="text-indigo-600" />} label="Active Sessions" value={metrics.active_sessions} color="bg-indigo-50" subtext="Last 24 hours" />
            <StatCard icon={<CheckCircle size={18} className="text-cyan-600" />} label="Success Rate" value={`${Math.round(metrics.query_success_rate * 100)}%`} color="bg-cyan-50" />
            <StatCard icon={<ThumbsDown size={18} className="text-rose-600" />} label="Negative Feedback" value={metrics.negative_feedback_count} color="bg-rose-50" subtext="This week" />
          </div>
        )}

        {/* Top Documents + Query Type Distribution */}
        {metrics && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Top Documents */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                <TrendingUp size={16} className="text-emerald-600" /> Top Documents (7 days)
              </h3>
              {metrics.top_documents && metrics.top_documents.length > 0 ? (
                <div className="space-y-2">
                  {metrics.top_documents.slice(0, 6).map((d, i) => (
                    <div key={i} className="flex items-center justify-between">
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <span className="text-xs text-gray-400 w-4">{i + 1}.</span>
                        <span className="text-sm text-gray-700 truncate">{d.source}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-500 rounded-full"
                            style={{ width: `${Math.min(100, (d.query_count / (metrics.top_documents?.[0]?.query_count || 1)) * 100)}%` }} />
                        </div>
                        <span className="text-xs text-gray-400 w-8 text-right">{d.query_count}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400">No query data yet</p>
              )}
            </div>

            {/* Query Type Distribution */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                <BarChart3 size={16} className="text-blue-600" /> Query Types (7 days)
              </h3>
              {metrics.query_type_distribution && Object.keys(metrics.query_type_distribution).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(metrics.query_type_distribution).sort((a, b) => b[1] - a[1]).map(([type, count]) => {
                    const total = Object.values(metrics.query_type_distribution!).reduce((s, c) => s + c, 0)
                    const pct = Math.round((count / total) * 100)
                    const colors: Record<string, string> = {
                      factual: 'bg-blue-500', procedural: 'bg-emerald-500', comparative: 'bg-amber-500',
                      policy_lookup: 'bg-purple-500', clarification: 'bg-gray-400', redirect: 'bg-rose-400',
                    }
                    return (
                      <div key={type} className="flex items-center justify-between">
                        <span className="text-sm text-gray-700 capitalize w-28">{type.replace('_', ' ')}</span>
                        <div className="flex items-center gap-2 flex-1">
                          <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                            <div className={`h-full rounded-full ${colors[type] || 'bg-gray-400'}`}
                              style={{ width: `${pct}%` }} />
                          </div>
                          <span className="text-xs text-gray-400 w-12 text-right">{pct}% ({count})</span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-400">No query data yet</p>
              )}
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="flex gap-1 border-b border-gray-200">
          {([['overview', 'Overview', BarChart3], ['users', 'User Management', Users], ['failed', 'Failed Queries', XCircle], ['security', 'Security Events', ShieldAlert], ['ai', 'AI Configuration', Cpu]] as const).map(([key, label, Icon]) => (
            <button key={key} onClick={() => setTab(key as any)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${tab === key ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
              <Icon size={15} /> {label}
              {key === 'failed' && failedQueries.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 text-xs bg-red-100 text-red-600 rounded-full">{failedQueries.length}</span>
              )}
              {key === 'users' && pendingUsers.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 text-xs bg-amber-100 text-amber-600 rounded-full">{pendingUsers.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* Users Tab */}
        {tab === 'users' && (
          <div className="space-y-4">
            {/* Pending approvals */}
            {pendingUsers.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-amber-800 mb-3 flex items-center gap-2">
                  <UserCheck size={15} /> Pending Approvals ({pendingUsers.length})
                </h3>
                <div className="space-y-2">
                  {pendingUsers.map((u: any) => (
                    <div key={u.user_id} className="flex items-center justify-between bg-white rounded-lg p-3 border border-amber-100">
                      <div>
                        <p className="text-sm font-medium text-gray-800">{u.full_name || u.username}</p>
                        <p className="text-xs text-gray-500">{u.email || 'No email'} | Requested: {u.requested_role || 'employee'}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={async () => {
                            await approveUser(token, u.user_id, 'approve', u.requested_role || 'employee')
                            refreshData()
                          }}
                          className="px-3 py-1.5 text-xs font-medium bg-green-600 text-white rounded-lg hover:bg-green-700"
                        >
                          Approve
                        </button>
                        <button
                          onClick={async () => {
                            await approveUser(token, u.user_id, 'reject')
                            refreshData()
                          }}
                          className="px-3 py-1.5 text-xs font-medium bg-red-100 text-red-700 rounded-lg hover:bg-red-200"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* User list */}
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100">
                <h3 className="text-sm font-semibold text-gray-800">All Users ({users.length})</h3>
                <input
                  type="text"
                  value={userFilter}
                  onChange={e => setUserFilter(e.target.value)}
                  placeholder="Search users..."
                  className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg w-48 focus:ring-1 focus:ring-blue-500 focus:outline-none"
                />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="text-left px-6 py-3 font-medium">User</th>
                      <th className="text-left px-6 py-3 font-medium">Role</th>
                      <th className="text-left px-6 py-3 font-medium">Department</th>
                      <th className="text-left px-6 py-3 font-medium">Status</th>
                      <th className="text-left px-6 py-3 font-medium">Joined</th>
                      <th className="text-left px-6 py-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {users
                      .filter(u => {
                        if (!userFilter) return true
                        const q = userFilter.toLowerCase()
                        return (u.username || '').toLowerCase().includes(q)
                          || (u.full_name || '').toLowerCase().includes(q)
                          || (u.email || '').toLowerCase().includes(q)
                          || (u.role || '').toLowerCase().includes(q)
                      })
                      .map((u: any) => (
                      <tr key={u.user_id} className="hover:bg-gray-50">
                        <td className="px-6 py-3">
                          <p className="font-medium text-gray-800">{u.full_name || u.username}</p>
                          <p className="text-xs text-gray-400">{u.email || u.username}</p>
                        </td>
                        <td className="px-6 py-3">
                          <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700">
                            {u.role}
                          </span>
                        </td>
                        <td className="px-6 py-3 text-gray-600">{u.department || '—'}</td>
                        <td className="px-6 py-3">
                          {u.suspended ? (
                            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">Suspended</span>
                          ) : u.status === 'pending' ? (
                            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-700">Pending</span>
                          ) : (
                            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700">Active</span>
                          )}
                        </td>
                        <td className="px-6 py-3 text-gray-400 text-xs">
                          {u.created_at ? new Date(u.created_at * 1000).toLocaleDateString() : '—'}
                        </td>
                        <td className="px-6 py-3">
                          {!u.suspended && u.status !== 'pending' && (
                            <button
                              onClick={async () => {
                                if (!confirm(`Suspend user "${u.full_name || u.username}"?`)) return
                                await suspendUser(token, u.user_id).catch(() => {})
                                refreshData()
                              }}
                              className="flex items-center gap-1 text-xs text-red-600 hover:text-red-800"
                              title="Suspend user"
                            >
                              <Ban size={12} /> Suspend
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Failed Queries Tab */}
        {tab === 'failed' && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="text-left px-6 py-3 font-medium">Query Hash</th>
                    <th className="text-left px-6 py-3 font-medium">Type</th>
                    <th className="text-left px-6 py-3 font-medium">Faithfulness</th>
                    <th className="text-left px-6 py-3 font-medium">Hallucination</th>
                    <th className="text-left px-6 py-3 font-medium">Reason</th>
                    <th className="text-left px-6 py-3 font-medium">Latency</th>
                    <th className="text-left px-6 py-3 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {failedQueries.map((q: any, i: number) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-6 py-3 font-mono text-xs text-gray-600">{q.query_hash}</td>
                      <td className="px-6 py-3">{q.query_type || '-'}</td>
                      <td className="px-6 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${(q.faithfulness_score || 0) < 0.4 ? 'bg-red-50 text-red-700' : 'bg-yellow-50 text-yellow-700'}`}>
                          {Math.round((q.faithfulness_score || 0) * 100)}%
                        </span>
                      </td>
                      <td className="px-6 py-3 text-gray-600">{Math.round((q.hallucination_risk || 0) * 100)}%</td>
                      <td className="px-6 py-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs ${q.failure_reason === 'low_faithfulness' ? 'bg-red-50 text-red-600' : 'bg-orange-50 text-orange-600'}`}>
                          {q.failure_reason === 'low_faithfulness' ? 'Low confidence' : 'Negative feedback'}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-gray-500">{Math.round(q.latency_ms || 0)}ms</td>
                      <td className="px-6 py-3 text-gray-400 text-xs">{q.timestamp ? new Date(q.timestamp * 1000).toLocaleString() : '-'}</td>
                    </tr>
                  ))}
                  {failedQueries.length === 0 && (
                    <tr><td colSpan={7} className="px-6 py-8 text-center text-gray-400">No failed queries recorded</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Security Events Tab */}
        {tab === 'security' && (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-600">
                  <tr>
                    <th className="text-left px-6 py-3 font-medium">Event</th>
                    <th className="text-left px-6 py-3 font-medium">User</th>
                    <th className="text-left px-6 py-3 font-medium">IP</th>
                    <th className="text-left px-6 py-3 font-medium">Details</th>
                    <th className="text-left px-6 py-3 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {securityEvents.map((e: any, i: number) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-6 py-3"><span className="px-2 py-0.5 bg-gray-100 text-gray-700 rounded text-xs font-mono">{e.event_type}</span></td>
                      <td className="px-6 py-3 text-gray-600 text-xs font-mono">{e.user_id || '-'}</td>
                      <td className="px-6 py-3 text-gray-500 text-xs">{e.ip_address || '-'}</td>
                      <td className="px-6 py-3 text-gray-500 text-xs max-w-xs truncate">{JSON.stringify(e.details)}</td>
                      <td className="px-6 py-3 text-gray-400 text-xs">{e.timestamp ? new Date(e.timestamp * 1000).toLocaleString() : '-'}</td>
                    </tr>
                  ))}
                  {securityEvents.length === 0 && (
                    <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-400">No security events recorded</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* AI Configuration Tab */}
        {tab === 'ai' && (
          <div className="space-y-6">

            {/* ── AI Mode Selector (Primary Choice) ── */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2 mb-1">
                <Cpu size={20} className="text-violet-600" /> AI Engine Mode
              </h2>
              <p className="text-xs text-gray-500 mb-5">Choose which AI engine powers the chatbot.</p>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Option 1: Internal (Ollama) */}
                <button
                  onClick={async () => {
                    if (aiMode.ai_mode === 'internal') return
                    setSwitchingMode(true)
                    try {
                      await setAiMode(token, 'internal')
                      loadAiData()
                    } catch (e: any) { alert(e.message) }
                    setSwitchingMode(false)
                  }}
                  disabled={switchingMode}
                  className={`relative text-left p-5 rounded-xl border-2 transition-all ${
                    aiMode.ai_mode === 'internal'
                      ? 'border-emerald-500 bg-emerald-50 ring-2 ring-emerald-200'
                      : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  {aiMode.ai_mode === 'internal' && (
                    <span className="absolute top-3 right-3 px-2 py-0.5 text-[10px] font-bold bg-emerald-500 text-white rounded-full">ACTIVE</span>
                  )}
                  <div className="flex items-center gap-3 mb-2">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${aiMode.ai_mode === 'internal' ? 'bg-emerald-500 text-white' : 'bg-gray-100 text-gray-500'}`}>
                      <Cpu size={20} />
                    </div>
                    <div>
                      <p className="font-semibold text-gray-900">Local AI (Ollama)</p>
                      <p className="text-xs text-gray-500">llama3:8b — runs on your server</p>
                    </div>
                  </div>
                  <ul className="text-xs text-gray-500 space-y-1 mt-3 ml-1">
                    <li>No API costs — completely free</li>
                    <li>Data stays on your server (100% private)</li>
                    <li>No internet required</li>
                  </ul>
                </button>

                {/* Option 2: External API */}
                <div className={`relative text-left p-5 rounded-xl border-2 transition-all ${
                  aiMode.ai_mode === 'external'
                    ? 'border-violet-500 bg-violet-50 ring-2 ring-violet-200'
                    : 'border-gray-200 bg-white'
                }`}>
                  {aiMode.ai_mode === 'external' && (
                    <span className="absolute top-3 right-3 px-2 py-0.5 text-[10px] font-bold bg-violet-500 text-white rounded-full">ACTIVE</span>
                  )}
                  <div className="flex items-center gap-3 mb-2">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${aiMode.ai_mode === 'external' ? 'bg-violet-500 text-white' : 'bg-gray-100 text-gray-500'}`}>
                      <Zap size={20} />
                    </div>
                    <div>
                      <p className="font-semibold text-gray-900">External API</p>
                      <p className="text-xs text-gray-500">
                        {aiMode.ai_mode === 'external' && aiMode.provider_display_name
                          ? `${aiMode.provider_display_name} — ${aiMode.provider_model}`
                          : 'OpenAI, Claude, Gemini, Groq, etc.'}
                      </p>
                    </div>
                  </div>
                  <ul className="text-xs text-gray-500 space-y-1 mt-3 ml-1">
                    <li>More powerful models (GPT-4, Claude, Gemini)</li>
                    <li>Faster responses for complex queries</li>
                    <li>Requires API key + internet</li>
                  </ul>

                  {/* Provider selector — only if providers exist */}
                  {aiProviders.filter(p => p.status === 'active').length > 0 ? (
                    <div className="mt-4 pt-3 border-t border-gray-200">
                      <label className="block text-xs font-medium text-gray-600 mb-1.5">Select AI Provider</label>
                      <div className="flex gap-2">
                        <select
                          value={aiMode.ai_mode === 'external' ? aiMode.active_provider : ''}
                          onChange={async (e) => {
                            if (!e.target.value) return
                            setSwitchingMode(true)
                            try {
                              await setAiMode(token, 'external', e.target.value)
                              loadAiData()
                            } catch (err: any) { alert(err.message) }
                            setSwitchingMode(false)
                          }}
                          disabled={switchingMode}
                          className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-300 focus:outline-none bg-white"
                        >
                          <option value="">Select provider...</option>
                          {aiProviders.filter(p => p.status === 'active').map(p => (
                            <option key={p.provider_name} value={p.provider_name}>
                              {p.display_name || p.provider_name} ({p.model_name})
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-4 pt-3 border-t border-gray-200 text-xs text-amber-600">
                      Add an API provider below first, then switch to External mode.
                    </p>
                  )}
                </div>
              </div>

              {switchingMode && (
                <p className="text-xs text-violet-600 text-center mt-3 animate-pulse">Switching AI mode...</p>
              )}
            </div>

            {/* ── Add Provider Section ── */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-900">API Providers</h3>
                <p className="text-xs text-gray-500">Add external AI providers with API keys. Used when External API mode is selected.</p>
              </div>
              <button onClick={() => setShowAddProvider(!showAddProvider)}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-violet-600 text-white rounded-lg hover:bg-violet-700 transition-colors">
                <Plus size={14} /> Add Provider
              </button>
            </div>

            {/* Add Provider Form */}
            {showAddProvider && (
              <div className="bg-violet-50 border border-violet-200 rounded-xl p-5 space-y-4">
                <h3 className="text-sm font-semibold text-violet-800">Add External AI Provider</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Provider</label>
                    <select value={newProvider.provider_name} onChange={e => setNewProvider(p => ({ ...p, provider_name: e.target.value, model_name: '' }))}
                      className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-300 focus:outline-none">
                      <option value="">Select provider...</option>
                      {supportedProviders.map(p => (
                        <option key={p.name} value={p.name}>{p.display_name} ({p.default_model})</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">API Key</label>
                    <input type="password" value={newProvider.api_key} onChange={e => setNewProvider(p => ({ ...p, api_key: e.target.value }))}
                      placeholder="sk-... or key-..."
                      className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-300 focus:outline-none" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Model (optional — uses default)</label>
                    <input type="text" value={newProvider.model_name} onChange={e => setNewProvider(p => ({ ...p, model_name: e.target.value }))}
                      placeholder={supportedProviders.find(s => s.name === newProvider.provider_name)?.default_model || 'default'}
                      className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-300 focus:outline-none" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Priority (1=highest)</label>
                      <input type="number" min={1} max={99} value={newProvider.priority} onChange={e => setNewProvider(p => ({ ...p, priority: parseInt(e.target.value) || 10 }))}
                        className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-300 focus:outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-700 mb-1">Usage Limit (0=unlimited)</label>
                      <input type="number" min={0} value={newProvider.usage_limit} onChange={e => setNewProvider(p => ({ ...p, usage_limit: parseInt(e.target.value) || 0 }))}
                        className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-violet-300 focus:outline-none" />
                    </div>
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <button onClick={() => setShowAddProvider(false)} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">Cancel</button>
                  <button
                    disabled={!newProvider.provider_name || !newProvider.api_key}
                    onClick={async () => {
                      try {
                        await createAiProvider(token, newProvider)
                        setShowAddProvider(false)
                        setNewProvider({ provider_name: '', api_key: '', model_name: '', priority: 10, status: 'active', usage_limit: 0 })
                        loadAiData()
                      } catch (e: any) { alert(e.message || 'Failed to add provider') }
                    }}
                    className="px-4 py-2 text-sm font-medium bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                    Save Provider
                  </button>
                </div>
              </div>
            )}

            {/* Configured Providers List */}
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-6 py-3 border-b border-gray-100">
                <h3 className="text-sm font-semibold text-gray-800">Configured Providers ({aiProviders.length})</h3>
              </div>
              {aiProviders.length === 0 ? (
                <div className="px-6 py-12 text-center">
                  <Cpu size={32} className="mx-auto text-gray-200 mb-3" />
                  <p className="text-sm text-gray-400">No external AI providers configured.</p>
                  <p className="text-xs text-gray-400 mt-1">The system uses internal AI (Ollama) by default. Add an external provider as a fallback.</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-100">
                  {aiProviders.map((p: any) => (
                    <div key={p.id} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50">
                      <div className="flex items-center gap-4">
                        <div className={`w-2.5 h-2.5 rounded-full ${p.status === 'active' ? 'bg-emerald-500' : 'bg-gray-300'}`} />
                        <div>
                          <p className="text-sm font-medium text-gray-900">{p.display_name || p.provider_name}</p>
                          <p className="text-xs text-gray-500">Model: {p.model_name} | Priority: {p.priority} | Usage: {p.usage_count}{p.usage_limit > 0 ? `/${p.usage_limit}` : ''}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {/* Test button */}
                        <button
                          disabled={testingProvider === p.provider_name}
                          onClick={async () => {
                            setTestingProvider(p.provider_name)
                            setTestResult(null)
                            try {
                              const r = await testAiProvider(token, p.provider_name)
                              setTestResult(r)
                            } catch { setTestResult({ status: 'error', error: 'Request failed' }) }
                            setTestingProvider('')
                          }}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-violet-700 bg-violet-50 border border-violet-200 rounded-lg hover:bg-violet-100 disabled:opacity-40 transition-colors">
                          <Zap size={12} /> {testingProvider === p.provider_name ? 'Testing...' : 'Test'}
                        </button>
                        {/* Toggle status */}
                        <button
                          onClick={async () => {
                            await updateAiProvider(token, p.provider_name, { status: p.status === 'active' ? 'inactive' : 'active' })
                            loadAiData()
                          }}
                          className={`inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                            p.status === 'active'
                              ? 'text-amber-700 bg-amber-50 border-amber-200 hover:bg-amber-100'
                              : 'text-emerald-700 bg-emerald-50 border-emerald-200 hover:bg-emerald-100'
                          }`}>
                          {p.status === 'active' ? <><EyeOff size={12} /> Disable</> : <><Eye size={12} /> Enable</>}
                        </button>
                        {/* Delete */}
                        <button
                          onClick={async () => {
                            if (!confirm(`Delete ${p.display_name || p.provider_name}? This cannot be undone.`)) return
                            await deleteAiProvider(token, p.provider_name)
                            loadAiData()
                          }}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors">
                          <Trash2 size={12} /> Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Test Result Banner */}
            {testResult && (
              <div className={`rounded-xl border p-4 ${testResult.status === 'success' ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'}`}>
                <div className="flex items-center gap-2">
                  {testResult.status === 'success'
                    ? <CheckCircle size={16} className="text-emerald-600" />
                    : <XCircle size={16} className="text-red-600" />}
                  <span className={`text-sm font-medium ${testResult.status === 'success' ? 'text-emerald-800' : 'text-red-800'}`}>
                    {testResult.status === 'success'
                      ? `Connected to ${testResult.provider} (${testResult.model}) in ${testResult.latency_ms}ms`
                      : `Connection failed: ${testResult.error}`}
                  </span>
                  <button onClick={() => setTestResult(null)} className="ml-auto text-gray-400 hover:text-gray-600"><XCircle size={14} /></button>
                </div>
                {testResult.response_preview && (
                  <p className="text-xs text-gray-600 mt-2 ml-6">Response: "{testResult.response_preview}"</p>
                )}
              </div>
            )}

            {/* Model Routing — which Ollama model handles which query type */}
            {aiMode.ai_mode === 'internal' && (
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h3 className="text-sm font-semibold text-gray-900 mb-1">Model Routing</h3>
                <p className="text-xs text-gray-500 mb-4">Assign different Ollama models to different query complexity tiers. The system automatically routes each query to the right model.</p>
                <div className="space-y-3">
                  {routingConfig.map((r: any) => {
                    const tierColors: Record<string, string> = {
                      fast: 'bg-emerald-50 border-emerald-200 text-emerald-700',
                      standard: 'bg-blue-50 border-blue-200 text-blue-700',
                      advanced: 'bg-violet-50 border-violet-200 text-violet-700',
                    }
                    const tierLabels: Record<string, string> = { fast: 'Fast', standard: 'Standard', advanced: 'Advanced' }
                    const color = tierColors[r.tier] || 'bg-gray-50 border-gray-200 text-gray-700'
                    return (
                      <div key={r.tier} className={`flex items-center justify-between p-3 rounded-lg border ${color}`}>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold uppercase">{tierLabels[r.tier] || r.tier}</span>
                            {r.is_default && <span className="text-[10px] text-gray-400">(default)</span>}
                          </div>
                          <p className="text-[11px] opacity-70 mt-0.5">{r.description}</p>
                        </div>
                        {editingTier === r.tier ? (
                          <div className="flex items-center gap-2">
                            <input type="text" value={editModel} onChange={e => setEditModel(e.target.value)}
                              placeholder="e.g. gemma3:4b"
                              className="px-2 py-1 text-xs border border-gray-300 rounded-lg w-36 focus:ring-1 focus:ring-blue-500 focus:outline-none" />
                            <button onClick={async () => {
                              if (!editModel.trim()) return
                              try {
                                await setModelRouting(token, r.tier, editModel.trim())
                                setEditingTier(null); setEditModel(''); loadAiData()
                              } catch (e: any) { alert(e.message) }
                            }} className="px-2 py-1 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700">Save</button>
                            <button onClick={() => { setEditingTier(null); setEditModel('') }}
                              className="px-2 py-1 text-xs text-gray-500 hover:text-gray-700">Cancel</button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono font-medium">{r.model_name}</span>
                            <button onClick={() => { setEditingTier(r.tier); setEditModel(r.model_name) }}
                              className="px-2 py-1 text-[11px] text-blue-600 hover:bg-blue-50 rounded-lg transition-colors">
                              Change
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Usage Analytics */}
            {aiUsage && aiUsage.providers && aiUsage.providers.length > 0 && (
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <Activity size={16} className="text-violet-600" /> AI Usage (Last 7 days)
                </h3>
                <div className="space-y-3">
                  {aiUsage.providers.map((p: any, i: number) => (
                    <div key={i} className="flex items-center justify-between text-sm">
                      <span className="text-gray-700 font-medium w-40">{p.provider}</span>
                      <span className="text-gray-500 w-20">{p.total_calls} calls</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${p.success_rate >= 90 ? 'bg-emerald-50 text-emerald-700' : p.success_rate >= 50 ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'}`}>
                        {p.success_rate}% success
                      </span>
                      <span className="text-gray-400 text-xs w-28 text-right">{p.avg_latency_ms}ms avg</span>
                      <span className="text-gray-400 text-xs w-32 text-right">{(p.total_prompt_tokens + p.total_completion_tokens).toLocaleString()} tokens</span>
                    </div>
                  ))}
                </div>
                {aiUsage.recent_errors && aiUsage.recent_errors.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-gray-100">
                    <p className="text-xs font-medium text-red-600 mb-2">Recent Errors</p>
                    {aiUsage.recent_errors.slice(0, 5).map((e: any, i: number) => (
                      <p key={i} className="text-xs text-gray-500 mb-1">
                        <span className="font-mono text-red-500">{e.provider}</span>: {e.error}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
