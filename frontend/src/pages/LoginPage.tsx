import { useState } from 'react'
import { login, register } from '../services/api'
import type { AuthState } from '../types/chat'
import { Eye, EyeOff } from 'lucide-react'

interface Props {
  onLogin: (auth: AuthState) => void
}

export default function LoginPage({ onLogin }: Props) {
  const [isRegister, setIsRegister] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // Login fields
  const [loginUser, setLoginUser] = useState('')
  const [loginPass, setLoginPass] = useState('')
  const [showLoginPass, setShowLoginPass] = useState(false)

  // Register fields
  const [regName, setRegName] = useState('')
  const [regEmail, setRegEmail] = useState('')
  const [regPhone, setRegPhone] = useState('')
  const [regRole, setRegRole] = useState('employee')
  const [regUser, setRegUser] = useState('')
  const [regPass, setRegPass] = useState('')
  const [regConfirm, setRegConfirm] = useState('')
  const [showRegPass, setShowRegPass] = useState(false)

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await login(loginUser, loginPass)
      onLogin({ token: data.access_token, refreshToken: data.refresh_token || null, user: data.user })
    } catch (err: any) {
      setError(err.message || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (regPass !== regConfirm) {
      setError('Passwords do not match')
      return
    }
    setLoading(true)
    try {
      await register({
        username: regUser,
        password: regPass,
        full_name: regName,
        email: regEmail,
        phone: regPhone,
        role: regRole,
      })
      // Auto-login after registration
      const data = await login(regUser, regPass)
      onLogin({ token: data.access_token, refreshToken: data.refresh_token || null, user: data.user })
    } catch (err: any) {
      setError(err.message || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  const switchMode = () => {
    setIsRegister(!isRegister)
    setError('')
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-emerald-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-8">
        <div className="text-center mb-6">
          <div className="w-14 h-14 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-3">
            <span className="text-2xl">🏢</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">HR Chatbot</h1>
          <p className="text-gray-500 text-sm mt-1">
            {isRegister ? 'Create your account' : 'Sign in to continue'}
          </p>
        </div>

        {!isRegister ? (
          /* ── Login Form ── */
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
              <input type="text" value={loginUser} onChange={e => setLoginUser(e.target.value)} required
                placeholder="Enter your username"
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
              <div className="relative">
                <input type={showLoginPass ? 'text' : 'password'} value={loginPass} onChange={e => setLoginPass(e.target.value)} required
                  placeholder="Enter your password"
                  className="w-full px-4 py-2.5 pr-12 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
                <button type="button" onClick={() => setShowLoginPass(!showLoginPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors">
                  {showLoginPass ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}

            <button type="submit" disabled={loading}
              className="w-full py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 font-medium text-sm transition-colors">
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
          </form>
        ) : (
          /* ── Register Form ── */
          <form onSubmit={handleRegister} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Full Name</label>
                <input type="text" value={regName} onChange={e => setRegName(e.target.value)} required
                  placeholder="John Doe"
                  className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Username</label>
                <input type="text" value={regUser} onChange={e => setRegUser(e.target.value)} required
                  placeholder="johndoe"
                  className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Email</label>
              <input type="email" value={regEmail} onChange={e => setRegEmail(e.target.value)} required
                placeholder="john@company.com"
                className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Phone Number</label>
                <input type="tel" value={regPhone} onChange={e => setRegPhone(e.target.value)}
                  placeholder="+1 555-123-4567"
                  className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Role</label>
                <select value={regRole} onChange={e => setRegRole(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm bg-white">
                  <option value="employee">Employee</option>
                  <option value="hr_admin">Admin</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Password</label>
              <div className="relative">
                <input type={showRegPass ? 'text' : 'password'} value={regPass} onChange={e => setRegPass(e.target.value)} required
                  placeholder="Min 12 chars, letter + number + symbol"
                  className="w-full px-3 py-2 pr-12 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
                <button type="button" onClick={() => setShowRegPass(!showRegPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors">
                  {showRegPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Confirm Password</label>
              <div className="relative">
                <input type={showRegPass ? 'text' : 'password'} value={regConfirm} onChange={e => setRegConfirm(e.target.value)} required
                  placeholder="Re-enter your password"
                  className={`w-full px-3 py-2 border rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm ${
                    regConfirm && regConfirm !== regPass ? 'border-red-300 bg-red-50' : 'border-gray-300'
                  }`} />
                {regConfirm && regConfirm !== regPass && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-red-400 text-xs">Mismatch</span>
                )}
              </div>
            </div>

            {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}

            <button type="submit" disabled={loading || (!!regConfirm && regConfirm !== regPass)}
              className="w-full py-2.5 bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 disabled:opacity-50 font-medium text-sm transition-colors">
              {loading ? 'Creating account...' : 'Create Account'}
            </button>
          </form>
        )}

        <p className="text-center text-sm text-gray-500 mt-5">
          {isRegister ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button onClick={switchMode} className="text-blue-600 hover:underline font-medium">
            {isRegister ? 'Sign in' : 'Register'}
          </button>
        </p>
      </div>
    </div>
  )
}
