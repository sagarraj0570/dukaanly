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
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${wsBase}/ws/deliveries/${deliveryId}${tokenParam}`
};
