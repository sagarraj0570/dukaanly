import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { api } from '@/api/axios'
import { Button } from '@/components/ui/button'
import { Store, Eye, EyeOff, Zap, User, ShoppingBag, Bike } from 'lucide-react'

export const Login = () => {
  const [isRegister, setIsRegister] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const performLogin = async (loginEmail: string, loginPass: string) => {
    const res = await api.post('/auth/login', { email: loginEmail, password: loginPass })
    const { access_token } = res.data
    const meRes = await api.get('/auth/me', {
      headers: { Authorization: `Bearer ${access_token}` },
    })
    const user = meRes.data
    setAuth(access_token, user)
    if (user.role === 'customer') navigate('/customer')
    else if (user.role === 'shop_owner') navigate('/shop')
    else if (user.role === 'rider') navigate('/rider')
    else navigate('/')
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (isRegister) {
        await api.post('/auth/register', {
          name,
          email,
          phone_number: phoneNumber || undefined,
          password,
        })
        await performLogin(email, password)
      } else {
        await performLogin(email, password)
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        setError(axiosErr.response?.data?.detail || 'Authentication failed. Please check your credentials.')
      } else {
        setError('An unexpected error occurred. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleDemoLogin = async (demoEmail: string) => {
    setEmail(demoEmail)
    setPassword('Password123!')
    setIsRegister(false)
    setError('')
    setLoading(true)
    try {
      await performLogin(demoEmail, 'Password123!')
    } catch {
      setError('Could not log in with demo account. Ensure backend and database are running.')
    } finally {
      setLoading(false)
    }
  }

  const demoAccounts = [
    { label: 'Customer', email: 'customer@dukaanly.com', icon: ShoppingBag, color: 'bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100' },
    { label: 'Shop Owner', email: 'shop@dukaanly.com', icon: Store, color: 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100' },
    { label: 'Rider', email: 'rider@dukaanly.com', icon: Bike, color: 'bg-orange-50 border-orange-200 text-orange-700 hover:bg-orange-100' },
  ]

  return (
    <div className="min-h-screen bg-[#FAF9F6] flex flex-col items-center justify-center p-4">
      {/* Brand header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="h-12 w-12 rounded-2xl bg-gradient-to-br from-[#176B45] to-[#104B32] shadow-sm flex items-center justify-center">
          <Store className="h-6 w-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-[#202923] tracking-tight">
            Dukaan<span className="text-[#176B45]">ly</span>
          </h1>
          <p className="text-xs text-[#69736C]">Hyperlocal commerce platform</p>
        </div>
      </div>

      {/* Card */}
      <div className="w-full max-w-md bg-white rounded-3xl shadow-soft border border-[#E5E9E4] overflow-hidden">
        {/* Tab switcher */}
        <div role="tablist" aria-label="Authentication mode" className="flex border-b border-[#E5E9E4]">
          {['Sign In', 'Create Account'].map((tab, i) => {
            const active = isRegister ? i === 1 : i === 0
            return (
              <button
                key={tab}
                role="tab"
                id={`auth-tab-${i}`}
                aria-selected={active}
                type="button"
                onClick={() => { setIsRegister(i === 1); setError('') }}
                className={`flex-1 py-3.5 text-sm font-semibold transition-all duration-150 ${
                  active
                    ? 'text-[#176B45] border-b-2 border-[#176B45] bg-[#EDF5EE]/40'
                    : 'text-[#69736C] hover:text-[#202923]'
                }`}
              >
                {tab}
              </button>
            )
          })}
        </div>

        <div className="p-6 space-y-4">
          {/* Error banner */}
          {error && (
            <div
              role="alert"
              aria-live="assertive"
              className="p-3 text-sm text-red-700 bg-red-50 rounded-xl border border-red-200 flex items-start gap-2"
            >
              <span className="mt-0.5 shrink-0" aria-hidden="true">⚠</span>
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {isRegister && (
              <div className="space-y-1.5">
                <label htmlFor="login-name" className="text-sm font-medium text-foreground flex items-center gap-1.5">
                  <User className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                  Full Name
                </label>
                <input
                  id="login-name"
                  type="text"
                  className="w-full h-10 px-3.5 border border-input rounded-lg text-base sm:text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                  placeholder="Rahul Sharma"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  required
                  autoComplete="name"
                />
              </div>
            )}

            <div className="space-y-1.5">
              <label htmlFor="login-email" className="text-sm font-medium text-foreground">Email Address</label>
              <input
                id="login-email"
                type="email"
                className="w-full h-10 px-3.5 border border-input rounded-lg text-base sm:text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                placeholder="user@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>

            {isRegister && (
              <div className="space-y-1.5">
                <label htmlFor="login-phone" className="text-sm font-medium text-foreground">
                  Phone <span className="text-muted-foreground font-normal">(Optional)</span>
                </label>
                <input
                  id="login-phone"
                  type="tel"
                  className="w-full h-10 px-3.5 border border-input rounded-lg text-base sm:text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                  placeholder="9876543210"
                  value={phoneNumber}
                  onChange={e => setPhoneNumber(e.target.value)}
                  autoComplete="tel"
                />
              </div>
            )}

            <div className="space-y-1.5">
              <label htmlFor="login-password" className="text-sm font-medium text-foreground">Password</label>
              <div className="relative">
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  className="w-full h-10 px-3.5 pr-10 border border-input rounded-lg text-base sm:text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                  placeholder={isRegister ? 'At least 8 characters' : 'Enter password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  minLength={isRegister ? 8 : undefined}
                  autoComplete={isRegister ? 'new-password' : 'current-password'}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors p-1"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              className="w-full h-11 font-semibold rounded-xl bg-[#176B45] hover:bg-[#104B32] text-white shadow-sm"
              disabled={loading}
            >
              {loading
                ? 'Please wait…'
                : isRegister
                ? 'Create Account & Continue'
                : 'Sign In'}
            </Button>
          </form>

          {/* Demo Quick Login */}
          <div className="pt-3 border-t border-[#E5E9E4]">
            <div className="flex items-center gap-2 mb-3">
              <div className="flex-1 h-px bg-[#E5E9E4]" />
              <span className="text-xs font-semibold text-[#69736C] flex items-center gap-1">
                <Zap className="h-3.5 w-3.5 text-[#176B45]" aria-hidden="true" /> Quick Demo Access
              </span>
              <div className="flex-1 h-px bg-[#E5E9E4]" />
            </div>

            <div className="grid grid-cols-3 gap-2">
              {demoAccounts.map(({ label, email: demoEmail, icon: Icon, color }) => (
                <button
                  key={label}
                  type="button"
                  disabled={loading}
                  onClick={() => handleDemoLogin(demoEmail)}
                  aria-label={`Log in as demo ${label}`}
                  className={`flex flex-col items-center justify-center min-h-[64px] gap-1 py-2.5 px-1.5 text-[11px] sm:text-xs font-semibold leading-tight border rounded-xl transition-all ${color} disabled:opacity-50 disabled:cursor-not-allowed`}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="text-center">{label}</span>
                </button>
              ))}
            </div>

            <p className="text-[11px] text-[#69736C] text-center mt-2.5">
              Demo password:{' '}
              <code className="bg-[#EDF5EE] text-[#176B45] px-1.5 py-0.5 rounded font-mono font-medium">
                Password123!
              </code>
            </p>
          </div>
        </div>
      </div>

      <p className="mt-6 text-xs text-muted-foreground text-center">
        Connecting customers, local shops & delivery riders
      </p>
    </div>
  )
}
