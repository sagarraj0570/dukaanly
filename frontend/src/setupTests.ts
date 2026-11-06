import '@testing-library/jest-dom'
import { beforeAll, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { HttpResponse, http, delay } from 'msw'

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
          is_orderable: true,
          verification_status: 'verified',
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
      is_orderable: true,
      verification_status: 'verified',
      location: { latitude: 0, longitude: 0 },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString()
    })
  }),
  http.get('http://localhost:8000/api/v1/shops/:id/delivery-eligibility', ({ params }) => {
    return HttpResponse.json({
      shop_id: params.id,
      shop_name: 'Test Shop Details',
      customer_location: { latitude: 12.9716, longitude: 77.5946 },
      distance_meters: 1200.0,
      is_delivery_eligible: true,
      delivery_radius_meters: 5000,
      message: 'Shop is 1.2 km away. Delivery is available to your location.'
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
  http.post('http://localhost:8000/api/v1/orders/checkout', async () => {
    await delay(200)
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
  http.get('http://localhost:8000/api/v1/orders', () => {
    return HttpResponse.json({
      items: [
        {
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
        }
      ],
      total: 1,
      page: 1,
      size: 20
    })
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
      updated_at: new Date().toISOString(),
      delivery: {
        id: 'delivery-1',
        status: 'assigned',
        rider_id: 'rider-1',
        assigned_at: new Date().toISOString(),
        picked_up_at: null,
        delivered_at: null
      }
    })
  }),
  http.get('http://localhost:8000/api/v1/orders/:id/reservation', ({ params }) => {
    return HttpResponse.json({
      order_id: params.id,
      status: 'active',
      expires_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
      seconds_remaining: 900,
      server_time: new Date().toISOString(),
      is_expired: false,
      items: [
        {
          product_id: 'prod-1',
          quantity: 2,
          status: 'active',
          reservation_reference: 'res_mock_1',
        }
      ],
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
  }),
  http.get('http://localhost:8000/api/v1/deliveries/:id/route', ({ params }) => {
    return HttpResponse.json({
      delivery_id: params.id,
      status: 'assigned',
      rider_location: { latitude: 12.971, longitude: 77.594, name: 'Delivery Partner' },
      shop_location: { latitude: 12.9716, longitude: 77.5946, name: 'Test Shop' },
      customer_location: { latitude: 12.972, longitude: 77.595, name: 'Customer Destination' },
      legs: [
        {
          from_name: 'Rider',
          to_name: 'Shop',
          from_latitude: 12.971,
          from_longitude: 77.594,
          to_latitude: 12.9716,
          to_longitude: 77.5946,
          distance_meters: 650.0,
          duration_seconds: 120.0,
          duration_minutes: 2.0,
          geometry: [[12.971, 77.594], [12.9716, 77.5946]],
          is_fallback: false,
          cached: true
        },
        {
          from_name: 'Shop',
          to_name: 'Customer',
          from_latitude: 12.9716,
          from_longitude: 77.5946,
          to_latitude: 12.972,
          to_longitude: 77.595,
          distance_meters: 1100.0,
          duration_seconds: 240.0,
          duration_minutes: 4.0,
          geometry: [[12.9716, 77.5946], [12.972, 77.595]],
          is_fallback: false,
          cached: true
        }
      ],
      total_distance_meters: 1750.0,
      total_duration_seconds: 360.0,
      total_duration_minutes: 6.0,
      combined_geometry: [[12.971, 77.594], [12.9716, 77.5946], [12.972, 77.595]],
      active_leg_index: 0,
      is_fallback: false,
      cached: true,
      attribution: 'Route data © OpenStreetMap contributors, powered by OSRM'
    })
  }),
  http.get('http://localhost:8000/api/v1/deliveries/:id/eta', ({ params }) => {
    return HttpResponse.json({
      delivery_id: params.id,
      order_id: 'order-1',
      status: 'out_for_delivery',
      eta: {
        earliest_at: new Date(Date.now() + 15 * 60 * 1000).toISOString(),
        latest_at: new Date(Date.now() + 25 * 60 * 1000).toISOString(),
        calculated_at: new Date().toISOString(),
        remaining_seconds: 1200,
        remaining_minutes: 20,
        arrival_window_text: '15–25 min',
        source: 'osrm',
        delay_reason: null,
        update_reason: 'Rider en route'
      },
      breakdown: {
        preparation_remaining_seconds: 0,
        assignment_wait_seconds: 0,
        pickup_travel_remaining_seconds: 0,
        dropoff_travel_seconds: 720,
        handoff_buffer_seconds: 180,
        confidence_buffer_seconds: 300,
        total_remaining_seconds: 1200
      },
      delay_explanation: null
    })
  }),
  http.patch('http://localhost:8000/api/v1/deliveries/:id/preparation', async ({ params, request }) => {
    const data = (await request.json()) as { estimated_prep_minutes: number; delay_reason?: string }
    return HttpResponse.json({
      delivery_id: params.id,
      order_id: 'order-1',
      status: 'preparing',
      eta: {
        earliest_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
        latest_at: new Date(Date.now() + 20 * 60 * 1000).toISOString(),
        calculated_at: new Date().toISOString(),
        remaining_seconds: 900,
        remaining_minutes: 15,
        arrival_window_text: '10–20 min',
        source: 'osrm',
        delay_reason: data.delay_reason || null,
        update_reason: 'Preparation time adjusted by merchant'
      },
      breakdown: {
        preparation_remaining_seconds: (data.estimated_prep_minutes || 10) * 60,
        assignment_wait_seconds: 180,
        pickup_travel_remaining_seconds: 240,
        dropoff_travel_seconds: 360,
        handoff_buffer_seconds: 180,
        confidence_buffer_seconds: 300,
        total_remaining_seconds: 900
      },
      delay_explanation: data.delay_reason ? `Merchant delay: ${data.delay_reason}` : null
    })
  }),
  http.get('http://localhost:8000/api/v1/discovery/nearby', ({ request }) => {
    const url = new URL(request.url)
    const category = url.searchParams.get('category')
    return HttpResponse.json({
      items: [
        {
          source: 'geoapify',
          source_id: 'geo-101',
          name: 'City Supermarket',
          category: category || 'supermarket',
          address: 'Main Road, Sector 4',
          latitude: 12.9716,
          longitude: 77.5946,
          distance_meters: 450.0,
          phone: '+91 98765 43210',
          website: 'https://example.com/city-supermarket',
          opening_hours: '08:00 - 22:00',
          is_directory_listing: true,
          is_dukaanly_merchant: false,
          is_orderable: false,
          is_delivery_eligible: false,
          attribution: 'Powered by Geoapify | © OpenStreetMap contributors',
        },
        {
          source: 'geoapify',
          source_id: 'geo-102',
          name: 'Apollo Pharmacy',
          category: 'chemist',
          address: 'Boring Road Cross, Patna',
          latitude: 12.9720,
          longitude: 77.5950,
          distance_meters: 750.0,
          phone: null,
          website: null,
          opening_hours: '24 Hours',
          is_directory_listing: true,
          is_dukaanly_merchant: false,
          is_orderable: false,
          is_delivery_eligible: false,
          attribution: 'Powered by Geoapify | © OpenStreetMap contributors',
        },
      ],
      total: 2,
      latitude: 12.9716,
      longitude: 77.5946,
      radius_meters: 3000,
      category: category || null,
      cached: false,
      attribution: 'Powered by Geoapify | © OpenStreetMap contributors',
    })
  }),
  http.get('http://localhost:8000/api/v1/ai/status', () => {
    return HttpResponse.json({
      enabled: true,
      provider: 'mock',
      model: 'gpt-4o-mini',
      features: {
        shopping_assistant: true,
        catalog_search: true,
        order_support: false,
      },
      circuit_breaker_open: false,
      details: 'Operational (Mock provider active)',
    })
  }),
  http.post('http://localhost:8000/api/v1/ai/assistant/chat', () => {
    return HttpResponse.json({
      assistant_message: 'I found fresh items for your breakfast from Boring Road Mart.',
      clarifying_question: null,
      matched_products: [
        {
          product_id: 'prod-milk-1',
          product_name: 'Amul Fresh Milk 1L',
          product_description: 'Pasteurized toned milk',
          category: 'Dairy',
          price: 66.0,
          stock: 10,
          shop_id: 'shop-1',
          shop_name: 'Boring Road Mart',
          shop_address: 'Boring Road, Patna',
          distance_meters: 1200.0,
          is_delivery_eligible: true,
        },
      ],
      proposed_cart: {
        shop_id: 'shop-1',
        shop_name: 'Boring Road Mart',
        shop_address: 'Boring Road, Patna',
        distance_meters: 1200.0,
        items: [
          {
            product_id: 'prod-milk-1',
            product_name: 'Amul Fresh Milk 1L',
            quantity: 1,
            unit_price: 66.0,
            item_total: 66.0,
            available_stock: 10,
          },
        ],
        total_amount: 66.0,
        is_delivery_eligible: true,
        has_different_shop_in_current_cart: false,
        warning_message: null,
      },
      search_query_used: 'Need milk',
      provider: 'mock',
      model: 'gpt-4o-mini',
      latency_ms: 120.0,
    })
  })
]

export const server = setupServer(...handlers)

beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' })
  if (typeof window !== 'undefined' && !window.ResizeObserver) {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  }
})
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
