import { useState, useEffect } from 'react'
import { login, register, verifyMfaLogin, getSetupStatus, forgotPassword, verifySecretAnswer, resetPassword, checkEmailResetAvailable, requestOtp, verifyOtp, resetWithOtp } from '../services/api'
import type { AuthState } from '../types/chat'
import { Eye, EyeOff, ShieldCheck, KeyRound, Mail } from 'lucide-react'

interface Props {
  onLogin: (auth: AuthState) => void
}

type LoginStep = 'credentials' | 'mfa' | 'forgot' | 'forgot-answer' | 'forgot-reset' | 'otp-sent' | 'otp-verify' | 'otp-reset'

const SECRET_QUESTIONS = [
  "What is your mother's maiden name?",
  "What was the name of your first pet?",
  "What city were you born in?",
  "What was your childhood nickname?",
  "What is the name of your first school?",
  "What is your favorite book?",
]

export default function LoginPage({ onLogin }: Props) {
  const [isRegister, setIsRegister] = useState(false)
  const [loginStep, setLoginStep] = useState<LoginStep>('credentials')
  const [mfaToken, setMfaToken] = useState('')   // server-issued short-lived token
  const [mfaCode, setMfaCode] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  // Login fields
  const [loginUser, setLoginUser] = useState('')
  const [loginPass, setLoginPass] = useState('')
  const [showLoginPass, setShowLoginPass] = useState(false)

  // Register fields
  const [regName, setRegName] = useState('')
  const [regEmail, setRegEmail] = useState('')
  const [regPhone, setRegPhone] = useState('')
  const [regUser, setRegUser] = useState('')
  const [regPass, setRegPass] = useState('')
  const [regConfirm, setRegConfirm] = useState('')
  const [regRole, setRegRole] = useState('employee')
  const [showRegPass, setShowRegPass] = useState(false)
  const [regSecretQ, setRegSecretQ] = useState('')
  const [regSecretA, setRegSecretA] = useState('')

  // Forgot password fields
  const [forgotUser, setForgotUser] = useState('')
  const [forgotQuestion, setForgotQuestion] = useState('')
  const [forgotAnswer, setForgotAnswer] = useState('')
  const [forgotNewPass, setForgotNewPass] = useState('')
  const [forgotConfirm, setForgotConfirm] = useState('')

  // OTP fields
  const [emailResetAvailable, setEmailResetAvailable] = useState(false)
  const [otpCode, setOtpCode] = useState('')
  const [otpEmailMasked, setOtpEmailMasked] = useState('')
  const [otpNewPass, setOtpNewPass] = useState('')
  const [otpConfirm, setOtpConfirm] = useState('')

  // Check if email OTP reset is available on this server
  useEffect(() => {
    checkEmailResetAvailable().then(d => setEmailResetAvailable(d.available)).catch(() => {})
  }, [])

  // Bootstrap: check if admin/hr_head roles need to be created
  const [setupStatus, setSetupStatus] = useState<{ has_users: boolean; has_admin: boolean; has_hr_head: boolean }>({ has_users: true, has_admin: true, has_hr_head: true })
  useEffect(() => {
    getSetupStatus().then(setSetupStatus).catch(() => {})
  }, [])
  // Re-fetch after successful registration (hides bootstrap options once roles are filled)
  const refreshSetupStatus = () => getSetupStatus().then(setSetupStatus).catch(() => {})

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      const data = await login(loginUser, loginPass)
      if (data.mfa_required && data.mfa_token) {
        // Server requires TOTP step-up
        setMfaToken(data.mfa_token)
        setLoginStep('mfa')
      } else {
        onLogin({ token: data.access_token, refreshToken: data.refresh_token || null, user: data.user })
      }
    } catch (err: any) {
      setError(err.message || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  const handleMfaVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    if (mfaCode.replace(/\s/g, '').length < 6) {
      setError('Enter the 6-digit code from your authenticator app.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const data = await verifyMfaLogin(mfaToken, mfaCode.replace(/\s/g, ''))
      onLogin({ token: data.access_token, refreshToken: data.refresh_token || null, user: data.user })
    } catch (err: any) {
      setError(err.message || 'Invalid MFA code. Try again.')
      setMfaCode('')
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
      const result = await register({
        username: regUser,
        password: regPass,
        full_name: regName,
        email: regEmail,
        phone: regPhone,
        role: regRole,
        secret_question: regSecretQ,
        secret_answer: regSecretA,
      })
      setSuccess(result.message || 'Account created! Your registration is pending admin approval.')
      refreshSetupStatus()
      setIsRegister(false)
      setLoginUser(regUser)
      setLoginPass('')
      setRegName(''); setRegEmail(''); setRegPhone('')
      setRegUser(''); setRegPass(''); setRegConfirm(''); setRegRole('employee')
      setRegSecretQ(''); setRegSecretA('')
    } catch (err: any) {
      setError(err.message || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  const switchMode = () => {
    setIsRegister(!isRegister)
    setError('')
    setSuccess('')
  }

  const backToCredentials = () => {
    setLoginStep('credentials')
    setMfaToken('')
    setMfaCode('')
    setForgotUser('')
    setForgotQuestion('')
    setForgotAnswer('')
    setForgotNewPass('')
    setForgotConfirm('')
    setOtpCode('')
    setOtpEmailMasked('')
    setOtpNewPass('')
    setOtpConfirm('')
    setError('')
  }

  const handleForgotStep1 = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await forgotPassword(forgotUser)
      if (data.has_question) {
        setForgotQuestion(data.secret_question)
        setLoginStep('forgot-answer')
      } else {
        setError(data.message || 'No security question set. Contact HR.')
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleForgotStep2 = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await verifySecretAnswer(forgotUser, forgotAnswer)
      setLoginStep('forgot-reset')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleForgotStep3 = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (forgotNewPass !== forgotConfirm) { setError('Passwords do not match'); return }
    setLoading(true)
    try {
      const data = await resetPassword(forgotUser, forgotAnswer, forgotNewPass)
      setSuccess(data.message || 'Password reset successfully!')
      setLoginUser(forgotUser)
      backToCredentials()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // ── OTP handlers ──────────────────────────────────────────────────────────
  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await requestOtp(forgotUser)
      if (data.sent) {
        setOtpEmailMasked(data.email_masked || '')
        setLoginStep('otp-verify')
      } else {
        setError(data.message || 'No email on file. Use security question instead.')
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await verifyOtp(forgotUser, otpCode)
      setLoginStep('otp-reset')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleResetWithOtp = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (otpNewPass !== otpConfirm) { setError('Passwords do not match'); return }
    setLoading(true)
    try {
      const data = await resetWithOtp(forgotUser, otpCode, otpNewPass)
      setSuccess(data.message || 'Password reset successfully!')
      setLoginUser(forgotUser)
      backToCredentials()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // ── OTP Email Reset steps ──────────────────────────────────────────────────
  if (loginStep === 'otp-sent' || loginStep === 'otp-verify' || loginStep === 'otp-reset') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-emerald-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-8">
          <div className="text-center mb-6">
            <div className="w-14 h-14 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-3">
              <Mail size={28} className="text-blue-600" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Email Reset</h1>
            <p className="text-gray-500 text-sm mt-1">
              {loginStep === 'otp-verify' && `Enter the 6-digit code sent to ${otpEmailMasked}`}
              {loginStep === 'otp-reset' && 'Set your new password'}
            </p>
          </div>

          {/* OTP Step 1: Enter 6-digit code */}
          {loginStep === 'otp-verify' && (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">6-Digit Code</label>
                <input type="text" value={otpCode} onChange={e => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  required autoFocus maxLength={6} placeholder="000000"
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-center text-2xl font-mono tracking-[0.5em]" />
                <p className="text-xs text-gray-400 mt-1 text-center">Code expires in 10 minutes</p>
              </div>
              {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}
              <button type="submit" disabled={loading || otpCode.length !== 6}
                className="w-full py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 font-medium text-sm transition-colors">
                {loading ? 'Verifying...' : 'Verify Code'}
              </button>
            </form>
          )}

          {/* OTP Step 2: New password */}
          {loginStep === 'otp-reset' && (
            <form onSubmit={handleResetWithOtp} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">New Password</label>
                <input type="password" value={otpNewPass} onChange={e => setOtpNewPass(e.target.value)} required autoFocus
                  placeholder="Min 12 chars, letter + number + symbol"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Confirm New Password</label>
                <input type="password" value={otpConfirm} onChange={e => setOtpConfirm(e.target.value)} required
                  placeholder="Re-enter new password"
                  className={`w-full px-4 py-2.5 border rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm ${
                    otpConfirm && otpConfirm !== otpNewPass ? 'border-red-300 bg-red-50' : 'border-gray-300'
                  }`} />
              </div>
              {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}
              <button type="submit" disabled={loading || !otpNewPass || otpNewPass !== otpConfirm}
                className="w-full py-2.5 bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 disabled:opacity-50 font-medium text-sm transition-colors">
                {loading ? 'Resetting...' : 'Reset Password'}
              </button>
            </form>
          )}

          <button onClick={backToCredentials} className="w-full text-center text-sm text-gray-500 mt-4 hover:text-gray-700">
            Back to Sign In
          </button>
        </div>
      </div>
    )
  }

  // ── Forgot Password steps ──────────────────────────────────────────────────
  if (loginStep === 'forgot' || loginStep === 'forgot-answer' || loginStep === 'forgot-reset') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-emerald-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-8">
          <div className="text-center mb-6">
            <div className="w-14 h-14 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-3">
              <KeyRound size={28} className="text-amber-600" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Reset Password</h1>
            <p className="text-gray-500 text-sm mt-1">
              {loginStep === 'forgot' && 'Enter your username to get started'}
              {loginStep === 'forgot-answer' && 'Answer your security question'}
              {loginStep === 'forgot-reset' && 'Set your new password'}
            </p>
          </div>

          {/* Step 1: Enter username + choose method */}
          {loginStep === 'forgot' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                <input type="text" value={forgotUser} onChange={e => setForgotUser(e.target.value)}
                  autoFocus placeholder="Enter your username"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-amber-500 focus:border-transparent text-sm" />
              </div>
              {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}

              {/* Method 1: Security Question */}
              <button onClick={handleForgotStep1} disabled={loading || !forgotUser.trim()}
                className="w-full py-2.5 bg-amber-600 text-white rounded-xl hover:bg-amber-700 disabled:opacity-50 font-medium text-sm transition-colors flex items-center justify-center gap-2">
                <KeyRound size={16} /> {loading ? 'Checking...' : 'Use Security Question'}
              </button>

              {/* Method 2: Email OTP (only shown if SMTP configured) */}
              {emailResetAvailable && (
                <>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 h-px bg-gray-200" />
                    <span className="text-xs text-gray-400">or</span>
                    <div className="flex-1 h-px bg-gray-200" />
                  </div>
                  <button onClick={handleRequestOtp} disabled={loading || !forgotUser.trim()}
                    className="w-full py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 font-medium text-sm transition-colors flex items-center justify-center gap-2">
                    <Mail size={16} /> {loading ? 'Sending...' : 'Send Code to Email'}
                  </button>
                </>
              )}
            </div>
          )}

          {/* Step 2: Answer secret question */}
          {loginStep === 'forgot-answer' && (
            <form onSubmit={handleForgotStep2} className="space-y-4">
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <p className="text-xs font-medium text-amber-700 mb-1">Security Question</p>
                <p className="text-sm text-amber-900 font-medium">{forgotQuestion}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Your Answer</label>
                <input type="text" value={forgotAnswer} onChange={e => setForgotAnswer(e.target.value)} required autoFocus
                  placeholder="Enter your answer"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-amber-500 focus:border-transparent text-sm" />
              </div>
              {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}
              <button type="submit" disabled={loading || !forgotAnswer.trim()}
                className="w-full py-2.5 bg-amber-600 text-white rounded-xl hover:bg-amber-700 disabled:opacity-50 font-medium text-sm transition-colors">
                {loading ? 'Verifying...' : 'Verify Answer'}
              </button>
            </form>
          )}

          {/* Step 3: Set new password */}
          {loginStep === 'forgot-reset' && (
            <form onSubmit={handleForgotStep3} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">New Password</label>
                <input type="password" value={forgotNewPass} onChange={e => setForgotNewPass(e.target.value)} required autoFocus
                  placeholder="Min 12 chars, letter + number + symbol"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-amber-500 focus:border-transparent text-sm" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Confirm New Password</label>
                <input type="password" value={forgotConfirm} onChange={e => setForgotConfirm(e.target.value)} required
                  placeholder="Re-enter new password"
                  className={`w-full px-4 py-2.5 border rounded-xl focus:ring-2 focus:ring-amber-500 focus:border-transparent text-sm ${
                    forgotConfirm && forgotConfirm !== forgotNewPass ? 'border-red-300 bg-red-50' : 'border-gray-300'
                  }`} />
              </div>
              {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}
              {success && <p className="text-emerald-700 text-sm bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">{success}</p>}
              <button type="submit" disabled={loading || !forgotNewPass || forgotNewPass !== forgotConfirm}
                className="w-full py-2.5 bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 disabled:opacity-50 font-medium text-sm transition-colors">
                {loading ? 'Resetting...' : 'Reset Password'}
              </button>
            </form>
          )}

          <button onClick={backToCredentials} className="w-full text-center text-sm text-gray-500 mt-4 hover:text-gray-700">
            Back to Sign In
          </button>
        </div>
      </div>
    )
  }

  // ── MFA step ───────────────────────────────────────────────────────────────
  if (loginStep === 'mfa') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-emerald-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-8">
          <div className="text-center mb-6">
            <div className="w-14 h-14 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-3">
              <ShieldCheck size={28} className="text-blue-600" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Two-Factor Auth</h1>
            <p className="text-gray-500 text-sm mt-1">
              Open your authenticator app and enter the 6-digit code.
            </p>
          </div>

          <form onSubmit={handleMfaVerify} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Authenticator Code</label>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9 ]*"
                maxLength={7}
                value={mfaCode}
                onChange={e => setMfaCode(e.target.value)}
                autoFocus
                placeholder="000 000"
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-center text-2xl font-mono tracking-[0.4em] letter-spacing-wide"
              />
            </div>

            {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}

            <button type="submit" disabled={loading || mfaCode.replace(/\s/g, '').length < 6}
              className="w-full py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 font-medium text-sm transition-colors">
              {loading ? 'Verifying...' : 'Verify Code'}
            </button>

            <button type="button" onClick={backToCredentials}
              className="w-full py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors">
              ← Back to login
            </button>
          </form>

          <p className="text-center text-xs text-gray-400 mt-4">
            Lost access to your authenticator?{' '}
            <span className="text-blue-500">Contact your IT administrator</span>
          </p>
        </div>
      </div>
    )
  }

  // ── Credentials step ───────────────────────────────────────────────────────
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

            {success && <p className="text-emerald-700 text-sm bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">{success}</p>}
            {error && <p className="text-red-500 text-sm bg-red-50 rounded-lg px-3 py-2">{error}</p>}

            <button type="submit" disabled={loading}
              className="w-full py-2.5 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 font-medium text-sm transition-colors">
              {loading ? 'Signing in...' : 'Sign In'}
            </button>
            <button type="button" onClick={() => { setError(''); setLoginStep('forgot') }}
              className="w-full text-center text-sm text-blue-600 hover:text-blue-800 hover:underline mt-1">
              Forgot Password?
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
                {!setupStatus.has_admin && <option value="admin">Admin</option>}
                {!setupStatus.has_hr_head && <option value="hr_head">HR Head</option>}
                <option value="employee">Employee</option>
                <option value="hr_team">HR Team</option>
              </select>
              <p className="text-xs text-gray-400 mt-0.5">
                {regRole === 'admin' ? 'First admin — auto-approved, can log in immediately'
                  : regRole === 'hr_head' ? 'First HR Head — auto-approved, can log in immediately'
                  : regRole === 'hr_team' ? 'HR Team requests require HR Head approval'
                  : 'Requires HR approval'}
              </p>
            </div>

            {/* Security Question — for password recovery */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Security Question</label>
              <select value={regSecretQ} onChange={e => setRegSecretQ(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm bg-white">
                <option value="">Select a security question...</option>
                {SECRET_QUESTIONS.map(q => <option key={q} value={q}>{q}</option>)}
              </select>
            </div>
            {regSecretQ && (
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Security Answer</label>
                <input type="text" value={regSecretA} onChange={e => setRegSecretA(e.target.value)}
                  placeholder="Your answer (used for password recovery)"
                  className="w-full px-3 py-2 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm" />
                <p className="text-xs text-gray-400 mt-0.5">This will be used if you forget your password</p>
              </div>
            )}

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
