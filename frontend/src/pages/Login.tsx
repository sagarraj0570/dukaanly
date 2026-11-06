import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import axios from 'axios'
import { useAuthStore } from '@/store/useAuthStore'
import { api } from '@/api/axios'
import { Button } from '@/components/ui/button'
import { BazaarPattern } from '@/components/ui/BazaarPattern'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import {
  Store,
  Eye,
  EyeOff,
  Zap,
  User,
  ShoppingBag,
  Bike,
  Lock,
  Mail,
  Phone,
  ArrowLeft,
  Copy,
  Check,
  ShieldCheck,
  AlertCircle,
} from 'lucide-react'

export const Login = () => {
  const [isRegister, setIsRegister] = useState(false)
  useDocumentTitle(isRegister ? 'Create Account' : 'Sign In')

  // Form Fields
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [capsLockActive, setCapsLockActive] = useState(false)
  const [selectedRole, setSelectedRole] = useState<'customer' | 'shop_owner' | 'rider'>('customer')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [copiedPassword, setCopiedPassword] = useState(false)

  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const parseAuthError = (err: unknown, defaultMsg: string): string => {
    if (axios.isAxiosError(err)) {
      if (err.response?.status === 429) {
        const detail = err.response.data?.detail
        return typeof detail === 'string'
          ? detail
          : 'Too many attempts. Please wait a moment before trying again.'
      }
      if (err.response?.data?.detail) {
        const detail = err.response.data.detail
        return typeof detail === 'string' ? detail : JSON.stringify(detail)
      }
      if (!err.response) {
        return 'Cannot connect to backend server. Please verify the API is running at http://localhost:8000 and refresh the page.'
      }
      return 'Authentication failed. Please check your credentials.'
    }
    if (err instanceof Error) {
      return err.message
    }
    return defaultMsg
  }

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
          role: selectedRole,
        })
        await performLogin(email, password)
      } else {
        await performLogin(email, password)
      }
    } catch (err: unknown) {
      setError(parseAuthError(err, 'An unexpected error occurred. Please try again.'))
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
    } catch (err: unknown) {
      setError(parseAuthError(err, 'Could not log in with demo account. Ensure backend and database are running.'))
    } finally {
      setLoading(false)
    }
  }

  const copyDemoPassword = () => {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      navigator.clipboard.writeText('Password123!')
      setCopiedPassword(true)
      setTimeout(() => setCopiedPassword(false), 2000)
    }
  }

  const handlePasswordKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (typeof e.getModifierState === 'function') {
      setCapsLockActive(e.getModifierState('CapsLock'))
    }
  }

  // Client-side password strength calculator
  const getPasswordStrength = (pass: string) => {
    if (!pass) return { score: 0, label: '', color: 'bg-border' }
    let score = 0
    if (pass.length >= 8) score++
    if (/[A-Z]/.test(pass) && /[a-z]/.test(pass)) score++
    if (/\d/.test(pass)) score++
    if (/[^A-Za-z0-9]/.test(pass)) score++

    if (score <= 1) return { score: 1, label: 'Weak', color: 'bg-brick' }
    if (score === 2) return { score: 2, label: 'Fair', color: 'bg-turmeric' }
    if (score === 3) return { score: 3, label: 'Good', color: 'bg-leaf/80' }
    return { score: 4, label: 'Strong', color: 'bg-leaf' }
  }

  const strength = getPasswordStrength(password)

  const demoAccounts = [
    {
      label: 'Customer',
      caption: 'Shop & order',
      email: 'customer@dukaanly.com',
      icon: ShoppingBag,
    },
    {
      label: 'Shop Owner',
      caption: 'Manage inventory',
      email: 'shop@dukaanly.com',
      icon: Store,
    },
    {
      label: 'Rider',
      caption: 'Deliver orders',
      email: 'rider@dukaanly.com',
      icon: Bike,
    },
  ]

  const registrationRoles = [
    { id: 'customer', title: 'Customer', desc: 'Order groceries', icon: ShoppingBag },
    { id: 'shop_owner', title: 'Shop Owner', desc: 'List your store', icon: Store },
    { id: 'rider', title: 'Delivery Partner', desc: 'Deliver & earn', icon: Bike },
  ] as const

  return (
    <div className="min-h-screen bg-paper text-ink flex flex-col justify-center">
      <div className="w-full max-w-6xl mx-auto min-h-screen flex flex-col lg:grid lg:grid-cols-12 lg:items-stretch">
        
        {/* ─── Left Column: Sand Panel (Desktop >= 1024px & Mobile Header) ─── */}
        <aside className="relative bg-sand border-b lg:border-b-0 lg:border-r border-border p-6 sm:p-10 lg:p-12 lg:col-span-5 flex flex-col justify-between overflow-hidden">
          {/* Subtle Mithila-inspired repeating pattern fill */}
          <BazaarPattern variant="fill" className="opacity-40" />

          {/* Top navigation / Logo */}
          <div className="relative z-10 space-y-6">
            <div className="flex items-center justify-between">
              <Link to="/" className="inline-flex items-center gap-2 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf rounded-[8px]">
                <div className="h-9 w-9 rounded-[10px] bg-surface border border-border text-leaf flex items-center justify-center">
                  <Store className="h-5 w-5" />
                </div>
                <span className="font-display text-2xl font-bold tracking-tight text-ink">
                  Dukaanly
                </span>
              </Link>

              <Link
                to="/"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink-soft hover:text-ink px-3 py-1.5 rounded-[8px] bg-surface/80 border border-border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Home
              </Link>
            </div>

            {/* Headline and Narrative */}
            <div className="pt-4 lg:pt-16 space-y-3">
              <h1 className="font-display text-2xl sm:text-[34px] sm:leading-[42px] font-semibold text-ink tracking-[-0.01em]">
                Aapki apni dukaan, ab ghar tak
              </h1>
              <p className="text-sm text-ink-soft leading-relaxed max-w-md">
                Patna ke vishwasniya mohalla kirana aur dukaano se taaza samaan mangwayein, instant 30-minute doorstep delivery ke saath.
              </p>
            </div>

            {/* Customer Value Chips */}
            <div className="flex flex-wrap gap-2 pt-2">
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-[8px] bg-surface border border-border text-xs font-medium text-ink">
                Real shops, real prices
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-[8px] bg-surface border border-border text-xs font-medium text-ink">
                Live order tracking
              </span>
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-[8px] bg-surface border border-border text-xs font-medium text-ink">
                Fast local delivery
              </span>
            </div>
          </div>

          {/* Footer stamp of trust */}
          <div className="relative z-10 pt-8 lg:pt-0 text-xs text-ink-soft hidden lg:block">
            <p className="font-medium">Patna Hyperlocal Commerce • Built for neighbourhoods</p>
          </div>
        </aside>

        {/* ─── Right Column: Form on Surface (All Screens) ─── */}
        <main className="flex-1 lg:col-span-7 p-4 sm:p-8 lg:p-12 xl:p-16 flex flex-col justify-center items-center bg-paper">
          <div className="w-full max-w-[460px] animate-in fade-in-50 duration-200">
            
            {/* Form Card */}
            <div className="bg-surface rounded-[14px] border border-border p-6 sm:p-8 shadow-none">
              
              {/* Header */}
              <div className="mb-6">
                <h2 className="font-display text-2xl sm:text-3xl font-semibold text-ink tracking-tight">
                  {isRegister ? 'Join Dukaanly' : 'Welcome back'}
                </h2>
                <p className="text-xs sm:text-sm text-ink-soft mt-1 leading-relaxed">
                  {isRegister
                    ? 'Create an account to start shopping or partner with neighbourhood stores'
                    : 'Sign in to access your orders, store inventory, or rider routes'}
                </p>
              </div>

              {/* Tabs in underline style (2px leaf underline on active tab) */}
              <div
                role="tablist"
                aria-label="Authentication mode"
                className="flex border-b border-border bg-transparent gap-6 mb-6"
              >
                {['Sign In', 'Create Account'].map((tab, i) => {
                  const active = isRegister ? i === 1 : i === 0
                  return (
                    <button
                      key={tab}
                      role="tab"
                      id={`auth-tab-${i}`}
                      aria-selected={active}
                      type="button"
                      onClick={() => {
                        setIsRegister(i === 1)
                        setError('')
                      }}
                      className={`pb-2.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf cursor-pointer ${
                        active
                          ? 'text-ink border-b-2 border-leaf -mb-[1px]'
                          : 'text-ink-soft hover:text-ink border-b-2 border-transparent'
                      }`}
                    >
                      {tab}
                    </button>
                  )
                })}
              </div>

              {/* Error Alert Banner */}
              {error && (
                <div
                  role="alert"
                  aria-live="assertive"
                  className="mb-5 p-3.5 text-xs sm:text-sm text-brick-ink bg-brick-tint rounded-[12px] border border-brick/30 flex items-start gap-2.5"
                >
                  <AlertCircle className="h-4 w-4 text-brick mt-0.5 shrink-0" aria-hidden="true" />
                  <span className="leading-snug">{error}</span>
                </div>
              )}

              {/* Form */}
              <form onSubmit={handleSubmit} className="space-y-4">
                {/* Registration: Selectable Role Radio Cards */}
                {isRegister && (
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-ink tracking-wide block">
                      I want to join as:
                    </label>
                    <div
                      role="radiogroup"
                      aria-label="Select your role"
                      className="grid grid-cols-3 gap-2"
                    >
                      {registrationRoles.map(role => {
                        const Icon = role.icon
                        const isSelected = selectedRole === role.id
                        return (
                          <button
                            key={role.id}
                            type="button"
                            role="radio"
                            aria-checked={isSelected}
                            onClick={() => setSelectedRole(role.id)}
                            className={`flex flex-col items-center justify-center p-3 rounded-[12px] border text-center transition-colors cursor-pointer min-h-[44px] ${
                              isSelected
                                ? 'bg-sage-tint border-leaf text-leaf ring-1 ring-leaf'
                                : 'bg-surface hover:bg-sand border-border text-ink-soft'
                            }`}
                          >
                            <Icon
                              className={`h-4 w-4 mb-1 ${
                                isSelected ? 'text-leaf' : 'text-ink-soft'
                              }`}
                            />
                            <span className="text-xs font-bold leading-tight text-ink">{role.title}</span>
                            <span className="text-[10px] text-ink-soft mt-0.5">{role.desc}</span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}

                {/* Full Name (Create Account only) */}
                {isRegister && (
                  <div className="space-y-1.5">
                    <label
                      htmlFor="login-name"
                      className="text-xs font-semibold text-ink block"
                    >
                      Full Name
                    </label>
                    <div className="relative">
                      <div className="pointer-events-none absolute inset-y-0 left-0 pl-3.5 flex items-center text-ink-soft">
                        <User className="h-4 w-4" aria-hidden="true" />
                      </div>
                      <input
                        id="login-name"
                        type="text"
                        className="w-full h-12 pl-10 pr-3.5 border border-border-strong rounded-[12px] text-sm bg-surface text-ink placeholder:text-ink-soft transition-colors focus:outline-none focus:border-leaf focus:ring-2 focus:ring-leaf/30"
                        placeholder="Rahul Sharma"
                        value={name}
                        onChange={e => setName(e.target.value)}
                        required
                        autoComplete="name"
                      />
                    </div>
                  </div>
                )}

                {/* Email Address */}
                <div className="space-y-1.5">
                  <label
                    htmlFor="login-email"
                    className="text-xs font-semibold text-ink block"
                  >
                    Email Address
                  </label>
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 pl-3.5 flex items-center text-ink-soft">
                      <Mail className="h-4 w-4" aria-hidden="true" />
                    </div>
                    <input
                      id="login-email"
                      type="email"
                      className="w-full h-12 pl-10 pr-3.5 border border-border-strong rounded-[12px] text-sm bg-surface text-ink placeholder:text-ink-soft transition-colors focus:outline-none focus:border-leaf focus:ring-2 focus:ring-leaf/30"
                      placeholder="user@example.com"
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      required
                      autoComplete="email"
                    />
                  </div>
                </div>

                {/* Phone Number (Create Account only) */}
                {isRegister && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label
                        htmlFor="login-phone"
                        className="text-xs font-semibold text-ink"
                      >
                        Phone Number
                      </label>
                      <span className="text-[11px] text-ink-soft">Optional</span>
                    </div>
                    <div className="relative">
                      <div className="pointer-events-none absolute inset-y-0 left-0 pl-3.5 flex items-center text-ink-soft">
                        <Phone className="h-4 w-4" aria-hidden="true" />
                      </div>
                      <input
                        id="login-phone"
                        type="tel"
                        className="w-full h-12 pl-10 pr-3.5 border border-border-strong rounded-[12px] text-sm bg-surface text-ink placeholder:text-ink-soft transition-colors focus:outline-none focus:border-leaf focus:ring-2 focus:ring-leaf/30"
                        placeholder="9876543210"
                        value={phoneNumber}
                        onChange={e => setPhoneNumber(e.target.value)}
                        autoComplete="tel"
                      />
                    </div>
                  </div>
                )}

                {/* Password Field with Show/Hide & Caps Lock indicator */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label
                      htmlFor="login-password"
                      className="text-xs font-semibold text-ink"
                    >
                      Password
                    </label>
                    {capsLockActive && (
                      <span className="text-[11px] font-semibold text-turmeric-ink bg-turmeric-tint border border-turmeric/30 px-2 py-0.5 rounded-[6px] inline-flex items-center gap-1">
                        ⇪ Caps Lock is ON
                      </span>
                    )}
                  </div>
                  <div className="relative">
                    <div className="pointer-events-none absolute inset-y-0 left-0 pl-3.5 flex items-center text-ink-soft">
                      <Lock className="h-4 w-4" aria-hidden="true" />
                    </div>
                    <input
                      id="login-password"
                      type={showPassword ? 'text' : 'password'}
                      className="w-full h-12 pl-10 pr-11 border border-border-strong rounded-[12px] text-sm bg-surface text-ink placeholder:text-ink-soft transition-colors focus:outline-none focus:border-leaf focus:ring-2 focus:ring-leaf/30"
                      placeholder={isRegister ? 'At least 8 characters' : 'Enter password'}
                      value={password}
                      onChange={e => setPassword(e.target.value)}
                      onKeyDown={handlePasswordKey}
                      onKeyUp={handlePasswordKey}
                      required
                      minLength={isRegister ? 8 : undefined}
                      autoComplete={isRegister ? 'new-password' : 'current-password'}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                      aria-pressed={showPassword}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-soft hover:text-ink transition-colors p-2 rounded-[8px] cursor-pointer"
                    >
                      {showPassword ? (
                        <EyeOff className="h-4 w-4" aria-hidden="true" />
                      ) : (
                        <Eye className="h-4 w-4" aria-hidden="true" />
                      )}
                    </button>
                  </div>

                  {/* Password Strength Meter (Registration only) */}
                  {isRegister && password.length > 0 && (
                    <div className="mt-2 space-y-1">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-ink-soft">Password strength:</span>
                        <span className="font-semibold text-ink">{strength.label}</span>
                      </div>
                      <div className="grid grid-cols-4 gap-1.5 h-1.5">
                        {[1, 2, 3, 4].map(idx => (
                          <div
                            key={idx}
                            className={`rounded-full transition-colors ${
                              idx <= strength.score ? strength.color : 'bg-sand'
                            }`}
                          />
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Primary CTA Submit Button */}
                <Button
                  type="submit"
                  disabled={loading}
                  variant="default"
                  className="w-full min-h-[48px] h-12 font-semibold text-sm rounded-[12px] mt-2"
                >
                  {loading ? (
                    <span className="inline-flex items-center gap-2">
                      <span className="h-4 w-4 border-2 border-leaf-ink/30 border-t-leaf-ink rounded-full animate-spin" />
                      Please wait…
                    </span>
                  ) : isRegister ? (
                    'Create Account & Continue'
                  ) : (
                    'Sign In to Dukaanly'
                  )}
                </Button>
              </form>

              {/* ─── Try a demo account Row ─────────────────────── */}
              <div className="pt-6 mt-6 border-t border-border">
                <div className="flex items-center justify-between gap-2 mb-3">
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-xs font-bold text-ink-soft flex items-center gap-1.5 uppercase tracking-wider">
                    <Zap className="h-3.5 w-3.5 text-turmeric-ink" aria-hidden="true" />
                    Try a demo account
                  </span>
                  <div className="flex-1 h-px bg-border" />
                </div>

                <div className="grid grid-cols-3 gap-2">
                  {demoAccounts.map(({ label, caption, email: demoEmail, icon: Icon }) => (
                    <button
                      key={label}
                      type="button"
                      disabled={loading}
                      onClick={() => handleDemoLogin(demoEmail)}
                      aria-label={`Log in as demo ${label.toLowerCase()}`}
                      className="group flex flex-col items-center justify-center min-h-[64px] p-2.5 text-center rounded-[12px] border border-border bg-surface hover:bg-sand transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf"
                    >
                      <Icon className="h-4 w-4 shrink-0 mb-1 text-leaf" aria-hidden="true" />
                      <span className="text-xs font-bold leading-tight text-ink">{label}</span>
                      <span className="text-[10px] text-ink-soft mt-0.5 font-normal truncate max-w-full">
                        {caption}
                      </span>
                    </button>
                  ))}
                </div>

                {/* Demo Password Copy Chip */}
                <div className="mt-3.5 flex items-center justify-center">
                  <button
                    type="button"
                    onClick={copyDemoPassword}
                    className="inline-flex items-center gap-1.5 text-xs text-ink-soft hover:text-ink bg-sand hover:bg-surface border border-border rounded-full px-3 py-1 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-leaf"
                  >
                    <span className="text-ink-soft">Demo password:</span>
                    <code className="font-mono font-bold text-leaf bg-surface px-1.5 py-0.5 rounded-[4px] border border-border text-[11px]">
                      Password123!
                    </code>
                    {copiedPassword ? (
                      <span className="inline-flex items-center gap-0.5 text-leaf font-semibold text-[11px]">
                        <Check className="h-3.5 w-3.5 text-leaf" /> Copied
                      </span>
                    ) : (
                      <Copy className="h-3 w-3 text-ink-soft" aria-hidden="true" />
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* Footer Trust & Security Note */}
            <div className="mt-6 flex items-center justify-center gap-1.5 text-xs text-ink-soft text-center">
              <ShieldCheck className="h-4 w-4 text-leaf shrink-0" aria-hidden="true" />
              <span>256-bit encrypted session • Secure neighbourhood authentication</span>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

export default Login
