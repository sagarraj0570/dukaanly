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
  })
]

export const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
