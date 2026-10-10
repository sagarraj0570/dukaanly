import '@testing-library/jest-dom'
import { beforeAll, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { HttpResponse, http } from 'msw'

export const handlers = [
  http.get('http://localhost:8000/api/v1/shops', () => {
    return HttpResponse.json({
      items: [
        {
          id: 'shop-1',
          owner_id: 'owner-1',
          name: 'Test Shop',
          description: 'A test shop',
          address: '123 Test St',
          is_active: true,
          location: { latitude: 0, longitude: 0 },
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }
      ],
      total: 1,
      page: 1,
      size: 20
    })
  }),
  http.get('http://localhost:8000/api/v1/shops/:id', ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      owner_id: 'owner-1',
      name: 'Test Shop Details',
      description: 'A test shop',
      address: '123 Test St',
      is_active: true,
      location: { latitude: 0, longitude: 0 },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  }),
  http.get('http://localhost:8000/api/v1/shops/:id/products', () => {
    return HttpResponse.json({
      items: [
        {
          id: 'prod-1',
          shop_id: 'shop-1',
          name: 'Test Product',
          description: 'A test product',
          category: 'Grocery',
          price: 150.00,
          image_url: 'https://example.com/img.png',
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        }
      ],
      total: 1,
      page: 1,
      size: 20
    })
  }),
  http.get('http://localhost:8000/api/v1/products/:id', ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      shop_id: 'shop-1',
      name: 'Test Product Details',
      description: 'A test product',
      category: 'Grocery',
      price: 150.00,
      image_url: 'https://example.com/img.png',
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  }),
  http.get('http://localhost:8000/api/v1/cart', () => {
    return HttpResponse.json({
      id: 'cart-1',
      customer_id: 'cust-1',
      shop_id: 'shop-1',
      items: [
        {
          id: 'item-1',
          product_id: 'prod-1',
          quantity: 2,
          product_name: 'Test Product Details',
          product_price: 150.00,
          item_total: 300.00
        }
      ],
      total_amount: 300.00
    })
  }),
  http.post('http://localhost:8000/api/v1/cart/items', () => {
    return HttpResponse.json({
      id: 'cart-1',
      customer_id: 'cust-1',
      shop_id: 'shop-1',
      items: [
        {
          id: 'item-1',
          product_id: 'prod-1',
          quantity: 3, // quantity updated after add
          product_name: 'Test Product Details',
          product_price: 150.00,
          item_total: 450.00
        }
      ],
      total_amount: 450.00
    })
  }),
  http.patch('http://localhost:8000/api/v1/cart/items/:id', () => {
    return HttpResponse.json({
      id: 'cart-1',
      customer_id: 'cust-1',
      shop_id: 'shop-1',
      items: [
        {
          id: 'item-1',
          product_id: 'prod-1',
          quantity: 1, // simulated quantity update
          product_name: 'Test Product Details',
          product_price: 150.00,
          item_total: 150.00
        }
      ],
      total_amount: 150.00
    })
  }),
  http.delete('http://localhost:8000/api/v1/cart/items/:id', () => {
    return HttpResponse.json({
      id: 'cart-1',
      customer_id: 'cust-1',
      shop_id: 'shop-1',
      items: [],
      total_amount: 0.00
    })
  }),
  http.delete('http://localhost:8000/api/v1/cart', () => {
    return HttpResponse.json({
      id: 'cart-1',
      customer_id: 'cust-1',
      shop_id: 'shop-1',
      items: [],
      total_amount: 0.00
    })
  }),
  http.post('http://localhost:8000/api/v1/orders/checkout', () => {
    return HttpResponse.json({
      id: 'order-1',
      customer_id: 'cust-1',
      shop_id: 'shop-1',
      status: 'pending',
      total_amount: 300.00,
      items: [
        {
          id: 'orderitem-1',
          product_id: 'prod-1',
          product_name: 'Test Product Details',
          unit_price: 150.00,
          quantity: 2,
          line_total: 300.00
        }
      ],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }, { status: 201 })
  }),
  http.get('http://localhost:8000/api/v1/orders/:id', ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      customer_id: 'cust-1',
      shop_id: 'shop-1',
      status: 'pending',
      total_amount: 300.00,
      items: [
        {
          id: 'orderitem-1',
          product_id: 'prod-1',
          product_name: 'Test Product Details',
          unit_price: 150.00,
          quantity: 2,
          line_total: 300.00
        }
      ],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  }),
  http.post('http://localhost:8000/api/v1/orders/:id/payment', ({ params }) => {
    return HttpResponse.json({
      payment_id: 'pay_init-1',
      order_id: params.id,
      provider: 'razorpay',
      provider_order_id: 'order_mock_123',
      amount: 300.00,
      currency: 'INR',
      key_id: 'mock_key_id'
    })
  }),
  http.post('http://localhost:8000/api/v1/payments/verify', () => {
    return HttpResponse.json({
      id: 'pay-1',
      order_id: 'order-1',
      provider: 'razorpay',
      provider_payment_id: 'pay_mock_123',
      amount: 300.00,
      currency: 'INR',
      status: 'captured',
      created_at: new Date().toISOString(),
      paid_at: new Date().toISOString()
    })
  }),
  // Rider API Mocks
  http.get('http://localhost:8000/api/v1/riders/me', () => {
    return HttpResponse.json({
      id: 'rider-1',
      user_id: 'user-rider-1',
      is_available: true,
      latitude: 12.971598,
      longitude: 77.594562,
      location_updated_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  }),
  http.post('http://localhost:8000/api/v1/riders/profile', () => {
    return HttpResponse.json({
      id: 'rider-1',
      user_id: 'user-rider-1',
      is_available: false,
      latitude: null,
      longitude: null,
      location_updated_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    }, { status: 201 })
  }),
  http.patch('http://localhost:8000/api/v1/riders/me/availability', async ({ request }) => {
    const data = await request.json() as { is_available: boolean }
    return HttpResponse.json({
      id: 'rider-1',
      user_id: 'user-rider-1',
      is_available: data.is_available,
      latitude: null,
      longitude: null,
      location_updated_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  }),
  http.patch('http://localhost:8000/api/v1/riders/me/location', async ({ request }) => {
    const data = await request.json() as { latitude: number, longitude: number }
    return HttpResponse.json({
      id: 'rider-1',
      user_id: 'user-rider-1',
      is_available: true,
      latitude: data.latitude,
      longitude: data.longitude,
      location_updated_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  }),
  http.get('http://localhost:8000/api/v1/riders/me/deliveries', () => {
    return HttpResponse.json([
      {
        id: 'delivery-1',
        order_id: 'order-1',
        rider_id: 'rider-1',
        status: 'assigned',
        destination_latitude: 12.972,
        destination_longitude: 77.595,
        assigned_at: new Date().toISOString(),
        picked_up_at: null,
        delivered_at: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      },
      {
        id: 'delivery-2',
        order_id: 'order-2',
        rider_id: 'rider-1',
        status: 'delivered',
        destination_latitude: 12.972,
        destination_longitude: 77.595,
        assigned_at: new Date().toISOString(),
        picked_up_at: new Date().toISOString(),
        delivered_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ])
  }),
  http.get('http://localhost:8000/api/v1/deliveries/:id', ({ params }) => {
    return HttpResponse.json({
      id: params.id,
      order_id: 'order-1',
      rider_id: 'rider-1',
      status: 'out_for_delivery',
      destination_latitude: 12.972,
      destination_longitude: 77.595,
      assigned_at: new Date().toISOString(),
      picked_up_at: new Date().toISOString(),
      delivered_at: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  }),
  http.patch('http://localhost:8000/api/v1/deliveries/:id/status', async ({ params, request }) => {
    const data = await request.json() as { status: string }
    return HttpResponse.json({
      id: params.id,
      order_id: 'order-1',
      rider_id: 'rider-1',
      status: data.status,
      destination_latitude: 12.972,
      destination_longitude: 77.595,
      assigned_at: new Date().toISOString(),
      picked_up_at: new Date().toISOString(),
      delivered_at: data.status === 'delivered' ? new Date().toISOString() : null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  })
]

export const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
