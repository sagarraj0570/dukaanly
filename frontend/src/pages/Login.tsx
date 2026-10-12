import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/useAuthStore'
import { api } from '@/api/axios'
import { Button } from '@/components/ui/button'

export const Login = () => {
  const [isRegister, setIsRegister] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [password, setPassword] = useState('')
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

  const handleDemoFill = async (demoEmail: string) => {
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

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-md p-8 bg-white rounded-lg shadow-sm border space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-center text-gray-900">
            {isRegister ? 'Create an Account' : 'Login to Dukaanly'}
          </h1>
          <p className="mt-1 text-sm text-center text-gray-500">
            Hyperlocal marketplace connecting Customers, Shops & Riders
          </p>
        </div>

        {/* Mode Toggle */}
        <div className="flex border-b text-sm font-medium">
          <button
            type="button"
            className={`flex-1 pb-3 text-center border-b-2 transition-colors ${
              !isRegister
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => {
              setIsRegister(false)
              setError('')
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`flex-1 pb-3 text-center border-b-2 transition-colors ${
              isRegister
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
            onClick={() => {
              setIsRegister(true)
              setError('')
            }}
          >
            Create Account
          </button>
        </div>

        {error && (
          <div className="p-3 text-sm text-red-600 bg-red-50 rounded-md border border-red-200 text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {isRegister && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
              <input
                type="text"
                className="w-full border rounded-md p-2 text-sm focus:ring-1 focus:ring-primary outline-none"
                placeholder="Rahul Sharma"
                value={name}
                onChange={e => setName(e.target.value)}
                required
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email Address</label>
            <input
              type="email"
              className="w-full border rounded-md p-2 text-sm focus:ring-1 focus:ring-primary outline-none"
              placeholder="user@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
          </div>

          {isRegister && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Phone Number <span className="text-gray-400 font-normal">(Optional)</span>
              </label>
              <input
                type="tel"
                className="w-full border rounded-md p-2 text-sm focus:ring-1 focus:ring-primary outline-none"
                placeholder="9876543210"
                value={phoneNumber}
                onChange={e => setPhoneNumber(e.target.value)}
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
            <input
              type="password"
              className="w-full border rounded-md p-2 text-sm focus:ring-1 focus:ring-primary outline-none"
              placeholder={isRegister ? 'At least 8 characters' : 'Enter password'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              minLength={isRegister ? 8 : undefined}
            />
          </div>

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? 'Please wait...' : isRegister ? 'Register & Continue' : 'Sign In'}
          </Button>
        </form>

        {/* Demo Accounts Quick-Login */}
        <div className="pt-4 border-t">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider text-center mb-3">
            Quick 1-Click Demo Login
          </p>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              disabled={loading}
              onClick={() => handleDemoFill('customer@dukaanly.com')}
              className="px-2 py-2 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded border text-center transition-colors"
            >
              🛒 Customer
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => handleDemoFill('shop@dukaanly.com')}
              className="px-2 py-2 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded border text-center transition-colors"
            >
              🏪 Shop Owner
            </button>
            <button
              type="button"
              disabled={loading}
              onClick={() => handleDemoFill('rider@dukaanly.com')}
              className="px-2 py-2 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded border text-center transition-colors"
            >
              🛵 Rider
            </button>
          </div>
          <p className="text-[11px] text-gray-400 text-center mt-2">
            Default demo password: <code className="bg-gray-100 px-1 rounded">Password123!</code>
          </p>
        </div>
      </div>
    </div>
  )
}
