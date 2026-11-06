import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Sparkles,
  Send,
  Loader2,
  AlertCircle,
  Check,
  ShoppingCart,
  Store,
  MapPin,
  RotateCcw,
  Plus,
  Minus,
  X,
  ArrowRight,
  ShieldCheck,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCart, useAddToCart, useClearCart } from '@/hooks/useCart'
import { useLocationStore } from '@/store/useLocationStore'
import {
  sendShoppingAssistantChat,
  type ShoppingAssistantResponse,
  type ShoppingChatMessage,
  type ProposedCart,
  type ProposedCartItem,
} from '@/api/ai'

interface ShoppingAssistantModalProps {
  isOpen: boolean
  onClose: () => void
  initialShopId?: string | null
}

interface ChatTurn {
  id: string
  role: 'user' | 'assistant'
  content: string
  data?: ShoppingAssistantResponse | null
  error?: string | null
  isFallback?: boolean
}

const QUICK_SUGGESTIONS = [
  'Need 1L milk and bread for breakfast',
  'Atta and cooking oil under ₹500',
  'Snacks and biscuits from nearby shop',
  'Fresh dairy items',
]

export const ShoppingAssistantModal: React.FC<ShoppingAssistantModalProps> = ({
  isOpen,
  onClose,
  initialShopId,
}) => {
  const navigate = useNavigate()
  const { coords, addressLabel } = useLocationStore()
  const { data: currentCart } = useCart()
  const addToCartMutation = useAddToCart()
  const clearCartMutation = useClearCart()

  const [inputMessage, setInputMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [messages, setMessages] = useState<ChatTurn[]>([])
  const [activeProposedCart, setActiveProposedCart] = useState<ProposedCart | null>(null)
  const [cartQuantities, setCartQuantities] = useState<Record<string, number>>({})
  const [isApplyingCart, setIsApplyingCart] = useState(false)
  const [cartApplySuccess, setCartApplySuccess] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus input and reset states on open
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [isOpen])

  // Scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [messages, isLoading])

  if (!isOpen) return null

  // Ensure default fallback coordinates (Central Patna / Boring Road) if not set
  const userLat = coords?.latitude ?? 25.6144
  const userLon = coords?.longitude ?? 85.1158

  const handleSendMessage = async (textToSend?: string) => {
    const query = (textToSend || inputMessage).trim()
    if (!query || isLoading) return

    setInputMessage('')
    setCartApplySuccess(false)

    const userTurn: ChatTurn = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
    }

    setMessages((prev) => [...prev, userTurn])
    setIsLoading(true)

    try {
      // Build conversation history (last 4 turns)
      const history: ShoppingChatMessage[] = messages.slice(-4).map((m) => ({
        role: m.role,
        content: m.content,
      }))

      const response = await sendShoppingAssistantChat({
        message: query,
        latitude: userLat,
        longitude: userLon,
        shop_id: initialShopId || null,
        history,
      })

      const assistantTurn: ChatTurn = {
        id: `asst-${Date.now()}`,
        role: 'assistant',
        content: response.assistant_message,
        data: response,
      }

      setMessages((prev) => [...prev, assistantTurn])

      // If proposed cart returned, initialize state for review and quantity editing
      if (response.proposed_cart && response.proposed_cart.items.length > 0) {
        setActiveProposedCart(response.proposed_cart)
        const initialQtys: Record<string, number> = {}
        response.proposed_cart.items.forEach((item) => {
          initialQtys[item.product_id] = item.quantity
        })
        setCartQuantities(initialQtys)
      }
    } catch (err: any) {
      const errorMsg =
        err?.response?.data?.detail ||
        err?.message ||
        'Unable to connect to AI assistant. Please try again.'

      const isServiceDisabled = err?.response?.status === 503

      const assistantTurn: ChatTurn = {
        id: `asst-${Date.now()}`,
        role: 'assistant',
        content: isServiceDisabled
          ? 'The AI Shopping Assistant is currently offline on this deployment. You can browse nearby shops directly using standard catalog search.'
          : 'I encountered an error retrieving live recommendations. Please verify your connection or try again.',
        error: errorMsg,
        isFallback: isServiceDisabled,
      }
      setMessages((prev) => [...prev, assistantTurn])
    } finally {
      setIsLoading(false)
    }
  }

  // Adjust item quantity in proposed cart
  const updateProposedQuantity = (productId: string, delta: number, maxStock: number) => {
    setCartQuantities((prev) => {
      const current = prev[productId] || 1
      const updated = Math.max(1, Math.min(current + delta, maxStock))
      return { ...prev, [productId]: updated }
    })
  }

  // Authoritatively calculate total from current quantities and unit prices
  const calculateRecalculatedTotal = (items: ProposedCartItem[]) => {
    return items.reduce((total, item) => {
      const qty = cartQuantities[item.product_id] || item.quantity
      return total + Number(item.unit_price) * qty
    }, 0)
  }

  // Explicit approval handler: applies proposed items to cart via standard API
  const handleApplyProposedCart = async () => {
    if (!activeProposedCart || isApplyingCart) return

    setIsApplyingCart(true)
    try {
      // If customer already has items from another shop, clear cart first
      if (
        currentCart?.shop_id &&
        currentCart.shop_id !== activeProposedCart.shop_id &&
        currentCart.items.length > 0
      ) {
        await clearCartMutation.mutateAsync()
      }

      // Add each approved item sequentially via standard authoritative cart API
      for (const item of activeProposedCart.items) {
        const qty = cartQuantities[item.product_id] || item.quantity
        await addToCartMutation.mutateAsync({
          product_id: item.product_id,
          quantity: qty,
        })
      }

      setCartApplySuccess(true)
    } catch (err: any) {
      console.error('Failed to apply proposed cart:', err)
    } finally {
      setIsApplyingCart(false)
    }
  }

  const handleResetChat = () => {
    setMessages([])
    setActiveProposedCart(null)
    setCartQuantities({})
    setCartApplySuccess(false)
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="ai-assistant-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-200"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="relative w-full max-w-2xl bg-surface rounded-2xl shadow-2xl flex flex-col max-h-[92vh] sm:max-h-[85vh] border border-border overflow-hidden">
        {/* Header */}
        <header className="flex items-center justify-between px-4 sm:px-6 py-3.5 border-b border-border bg-surface-alt">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-700 text-white shadow-xs">
              <Sparkles className="h-4.5 w-4.5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 id="ai-assistant-title" className="text-base font-bold text-text-primary">
                  Dukaanly AI Assistant
                </h2>
                <span className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-primary-50 text-primary-700 border border-primary-200">
                  <ShieldCheck className="h-3 w-3" />
                  Verified Partner Inventory
                </span>
              </div>
              <p className="text-xs text-text-secondary flex items-center gap-1">
                <MapPin className="h-3 w-3 text-primary-600" />
                {addressLabel || 'Central Patna'} • 5 km serviceability radius
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            {messages.length > 0 && (
              <button
                type="button"
                onClick={handleResetChat}
                className="h-8 w-8 inline-flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-primary-50 transition-colors"
                title="Clear conversation"
                aria-label="Clear conversation"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="h-8 w-8 inline-flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-primary-50 transition-colors"
              aria-label="Close assistant"
            >
              <X className="h-4.5 w-4.5" />
            </button>
          </div>
        </header>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 bg-surface">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-6 sm:py-10 text-center">
              <div className="h-12 w-12 rounded-2xl bg-primary-50 text-primary-700 flex items-center justify-center mb-3">
                <Sparkles className="h-6 w-6" />
              </div>
              <h3 className="text-base font-bold text-text-primary mb-1">
                What can I help you find today?
              </h3>
              <p className="text-xs text-text-secondary max-w-sm mb-6">
                Tell me what groceries or items you need. I will search active verified partner shops within 5 km and build an authoritative single-shop cart proposal.
              </p>

              <div className="w-full max-w-md space-y-2">
                <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider text-left">
                  Suggested requests:
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {QUICK_SUGGESTIONS.map((suggestion, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSendMessage(suggestion)}
                      className="text-left text-xs p-2.5 rounded-xl border border-border bg-surface-alt text-text-primary hover:border-primary-500 hover:bg-primary-50 transition-colors"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${
                  msg.role === 'user' ? 'items-end' : 'items-start'
                }`}
              >
                <div
                  className={`max-w-[85%] sm:max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-primary-700 text-white rounded-tr-xs'
                      : 'bg-surface-alt text-text-primary border border-border rounded-tl-xs'
                  }`}
                >
                  <p>{msg.content}</p>

                  {/* Fallback button if AI is disabled */}
                  {msg.isFallback && (
                    <div className="mt-3 pt-2.5 border-t border-border flex justify-end">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          onClose()
                          navigate('/customer')
                        }}
                        className="text-xs h-8 border-primary-500 text-primary-700 hover:bg-primary-50"
                      >
                        Browse Partner Shops
                        <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
                      </Button>
                    </div>
                  )}
                </div>

                {/* Matched Products Carousel/Cards */}
                {msg.data?.matched_products && msg.data.matched_products.length > 0 && (
                  <div className="w-full mt-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-text-secondary uppercase tracking-wider">
                        Matched in-stock products ({msg.data.matched_products.length})
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {msg.data.matched_products.slice(0, 4).map((product) => (
                        <div
                          key={product.product_id}
                          className="flex flex-col justify-between p-3 rounded-xl border border-border bg-surface hover:border-primary-200 transition-colors"
                        >
                          <div>
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <span className="text-xs font-bold text-text-primary line-clamp-1">
                                {product.product_name}
                              </span>
                              <span className="text-xs font-extrabold text-primary-700 shrink-0">
                                ₹{Number(product.price).toFixed(2)}
                              </span>
                            </div>

                            <p className="text-[11px] text-text-secondary flex items-center gap-1 mb-1.5">
                              <Store className="h-3 w-3 text-primary-600" />
                              <span className="truncate">{product.shop_name}</span>
                              <span>•</span>
                              <span>{(product.distance_meters / 1000).toFixed(1)} km</span>
                            </p>
                          </div>

                          <div className="flex items-center justify-between text-[11px] pt-1.5 border-t border-border/40">
                            <span className="text-primary-700 font-medium">
                              {product.stock} in stock
                            </span>
                            <span className="text-gray-500 bg-gray-50 px-1.5 py-0.5 rounded text-[10px]">
                              5 km eligible
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}

          {/* Loading Indicator */}
          {isLoading && (
            <div className="flex items-center gap-2 text-xs text-text-secondary bg-surface-alt border border-border rounded-2xl px-4 py-3 max-w-[75%] animate-pulse">
              <Loader2 className="h-4 w-4 animate-spin text-primary-600" />
              <span>Searching verified partner inventory in Patna...</span>
            </div>
          )}

          {/* Proposed Cart Card (Authoritative Review & Approval) */}
          {activeProposedCart && activeProposedCart.items.length > 0 && (
            <div className="mt-4 p-4 rounded-2xl border-2 border-primary-200 bg-primary-50/50 shadow-warm-xs space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-1.5 text-xs font-bold text-primary-700">
                    <ShoppingCart className="h-4 w-4" />
                    <span>Proposed Cart Review</span>
                  </div>
                  <h4 className="text-sm font-bold text-text-primary mt-0.5">
                    {activeProposedCart.shop_name}
                  </h4>
                  <p className="text-[11px] text-text-secondary flex items-center gap-1">
                    <MapPin className="h-3 w-3 text-primary-600" />
                    {activeProposedCart.shop_address} • {(activeProposedCart.distance_meters / 1000).toFixed(1)} km away
                  </p>
                </div>

                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-primary-700 text-white">
                  Single Shop
                </span>
              </div>

              {/* Warning if customer has another shop in existing cart */}
              {activeProposedCart.has_different_shop_in_current_cart && (
                <div className="flex items-start gap-2 p-2.5 rounded-xl bg-accent-100/70 border border-accent-200 text-text-primary text-xs">
                  <AlertCircle className="h-4 w-4 text-accent-600 shrink-0 mt-0.5" />
                  <p className="leading-tight">
                    Your cart contains items from another shop. Approving this proposed cart will replace those items to maintain Dukaanly's single-shop rule.
                  </p>
                </div>
              )}

              {/* Items List with Quantity Controls */}
              <div className="space-y-2 bg-surface rounded-xl p-2.5 border border-border">
                {activeProposedCart.items.map((item) => {
                  const qty = cartQuantities[item.product_id] || item.quantity
                  const itemTotal = Number(item.unit_price) * qty

                  return (
                    <div
                      key={item.product_id}
                      className="flex items-center justify-between py-1.5 border-b border-border/40 last:border-b-0 text-xs"
                    >
                      <div className="flex-1 pr-2">
                        <p className="font-semibold text-text-primary truncate">{item.product_name}</p>
                        <p className="text-[11px] text-text-secondary">
                          ₹{Number(item.unit_price).toFixed(2)} each • {item.available_stock} available
                        </p>
                      </div>

                      {/* Quantity Controls */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          type="button"
                          onClick={() => updateProposedQuantity(item.product_id, -1, item.available_stock)}
                          disabled={qty <= 1}
                          className="h-6 w-6 rounded-md bg-surface-alt border border-border flex items-center justify-center text-text-primary hover:bg-primary-50 disabled:opacity-40"
                          aria-label={`Decrease quantity for ${item.product_name}`}
                        >
                          <Minus className="h-3 w-3" />
                        </button>

                        <span className="w-5 text-center font-bold text-xs">{qty}</span>

                        <button
                          type="button"
                          onClick={() => updateProposedQuantity(item.product_id, 1, item.available_stock)}
                          disabled={qty >= item.available_stock}
                          className="h-6 w-6 rounded-md bg-surface-alt border border-border flex items-center justify-center text-text-primary hover:bg-primary-50 disabled:opacity-40"
                          aria-label={`Increase quantity for ${item.product_name}`}
                        >
                          <Plus className="h-3 w-3" />
                        </button>

                        <span className="w-14 text-right font-bold text-text-primary">
                          ₹{itemTotal.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Total & Action */}
              <div className="flex items-center justify-between pt-1">
                <div>
                  <span className="text-[11px] text-text-secondary">Authoritative Total:</span>
                  <p className="text-base font-extrabold text-primary-700">
                    ₹{calculateRecalculatedTotal(activeProposedCart.items).toFixed(2)}
                  </p>
                </div>

                {cartApplySuccess ? (
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-primary-700 flex items-center gap-1">
                      <Check className="h-4 w-4" /> Added to cart
                    </span>
                    <Button
                      size="sm"
                      onClick={() => {
                        onClose()
                        navigate('/customer/cart')
                      }}
                      className="btn-primary text-xs h-9 px-3 rounded-xl"
                    >
                      Go to Cart
                      <ArrowRight className="h-3.5 w-3.5 ml-1" />
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    onClick={handleApplyProposedCart}
                    disabled={isApplyingCart}
                    className="btn-primary text-xs h-9 px-4 rounded-xl font-semibold shadow-green-btn"
                  >
                    {isApplyingCart ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                        Adding to Cart...
                      </>
                    ) : (
                      <>
                        <ShoppingCart className="h-3.5 w-3.5 mr-1.5" />
                        Add Items to Cart
                      </>
                    )}
                  </Button>
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <footer className="p-3 sm:p-4 border-t border-border bg-surface-alt">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleSendMessage()
            }}
            className="flex items-center gap-2"
          >
            <input
              ref={inputRef}
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder="Ask for groceries (e.g. 1L milk and bread)..."
              disabled={isLoading}
              maxLength={500}
              aria-label="Ask AI shopping assistant"
              className="flex-1 h-11 px-4 rounded-xl bg-surface border border-border text-sm text-text-primary placeholder:text-text-muted focus:border-primary-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors disabled:opacity-60"
            />
            <Button
              type="submit"
              disabled={!inputMessage.trim() || isLoading}
              className="btn-primary h-11 px-4 rounded-xl text-white font-semibold transition-colors disabled:opacity-50 shrink-0"
              aria-label="Send message to shopping assistant"
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>
        </footer>
      </div>
    </div>
  )
}
