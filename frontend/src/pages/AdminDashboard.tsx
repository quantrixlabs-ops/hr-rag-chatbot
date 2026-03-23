import { useState, useEffect, useCallback } from 'react'
import {
  getMetrics, getFailedQueries, getSecurityEvents,
  getUsers, getPendingUsers, approveUser, suspendUser,
} from '../services/api'
import type { AdminMetrics } from '../types/chat'
import { BarChart3, FileText, AlertTriangle, Clock, Shield, ShieldAlert, XCircle, TrendingUp, Users, CheckCircle, ThumbsDown, RefreshCw, UserCheck, Ban } from 'lucide-react'

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
  const [tab, setTab] = useState<'overview' | 'failed' | 'security' | 'users'>('overview')
  const [refreshing, setRefreshing] = useState(false)
  const [userFilter, setUserFilter] = useState('')

  const refreshData = useCallback(() => {
    setRefreshing(true)
    Promise.all([
      getMetrics(token).then(setMetrics).catch(() => {}),
      getFailedQueries(token).then(d => setFailedQueries(d.failed_queries || [])).catch(() => {}),
      getSecurityEvents(token).then(d => setSecurityEvents(d.events || [])).catch(() => {}),
      getUsers(token).then(d => setUsers(d.users || [])).catch(() => {}),
      getPendingUsers(token).then(d => setPendingUsers(d.pending_users || d.users || [])).catch(() => {}),
    ]).finally(() => setRefreshing(false))
  }, [token])

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
          {([['overview', 'Overview', BarChart3], ['users', 'User Management', Users], ['failed', 'Failed Queries', XCircle], ['security', 'Security Events', ShieldAlert]] as const).map(([key, label, Icon]) => (
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
      </div>
    </div>
  )
}
