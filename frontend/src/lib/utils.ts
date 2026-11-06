export { cn } from "cn"

export const formatCurrency = (amount: number | string): string => {
  const numericAmount = typeof amount === 'string' ? parseFloat(amount) : amount;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numericAmount || 0);
};

export const getDeliveryWsUrl = (deliveryId: string, token: string | null): string => {
  let wsBase: string

  if (import.meta.env.VITE_WS_URL) {
    wsBase = import.meta.env.VITE_WS_URL
  } else if (import.meta.env.VITE_API_URL) {
    let apiUrl = import.meta.env.VITE_API_URL.replace(/\/+$/, '')
    if (!apiUrl.endsWith('/api/v1')) {
      apiUrl = `${apiUrl}/api/v1`
    }
    if (apiUrl.startsWith('https://')) {
      wsBase = apiUrl.replace(/^https:\/\//, 'wss://')
    } else if (apiUrl.startsWith('http://')) {
      wsBase = apiUrl.replace(/^http:\/\//, 'ws://')
    } else {
      const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:'
      const proto = isHttps ? 'wss:' : 'ws:'
      const host = typeof window !== 'undefined' ? window.location.host : 'localhost:8000'
      wsBase = `${proto}//${host}${apiUrl}`
    }
  } else if (typeof window !== 'undefined' && window.location.host && !window.location.host.includes('localhost:5173')) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    wsBase = `${proto}//${window.location.host}/api/v1`
  } else {
    wsBase = 'ws://localhost:8000/api/v1'
  }

  // Remove trailing slashes and append ws path
  wsBase = wsBase.replace(/\/+$/, '')

  // Prevent mixed-content blocking on HTTPS deployments:
  // Browsers strictly block unencrypted ws:// connections when the page is loaded over https://.
  if (typeof window !== 'undefined' && window.location.protocol === 'https:' && wsBase.startsWith('ws://')) {
    wsBase = wsBase.replace(/^ws:\/\//, 'wss://')
  }

  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${wsBase}/ws/deliveries/${deliveryId}${tokenParam}`
}

export const isTestEntity = (name?: string | null, description?: string | null): boolean => {
  if (!name && !description) return false
  const combined = `${name || ''} ${description || ''}`.toLowerCase()
  return (
    combined.includes('systest') ||
    combined.includes('(test)') ||
    combined.includes('[test]') ||
    combined.includes('system test') ||
    combined.includes('for run st_') ||
    (name ? name.toLowerCase().startsWith('st_') : false)
  )
};
