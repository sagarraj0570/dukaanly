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
  const httpUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
  const wsBase = httpUrl.replace(/^http/, 'ws')
  const tokenParam = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${wsBase}/ws/deliveries/${deliveryId}${tokenParam}`
};
