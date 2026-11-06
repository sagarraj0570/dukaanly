import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ProductImage } from './ProductImage'

describe('ProductImage component', () => {
  it('renders image with proper alt text, lazy loading, and async decoding', () => {
    render(
      <ProductImage
        src="/static/media/products/sample.webp"
        alt="Aashirvaad Whole Wheat Atta 5kg"
        category="Groceries"
      />
    )

    const img = screen.getByAltText('Aashirvaad Whole Wheat Atta 5kg') as HTMLImageElement
    expect(img).toBeTruthy()
    expect(img.getAttribute('src')).toBe('/static/media/products/sample.webp')
    expect(img.getAttribute('loading')).toBe('lazy')
    expect(img.getAttribute('decoding')).toBe('async')
  })

  it('renders loading shimmer initially when valid src is provided', () => {
    render(
      <ProductImage
        src="/static/media/products/sample.webp"
        alt="Amul Butter"
        category="Dairy"
      />
    )

    const skeleton = screen.getByTestId('product-image-skeleton')
    expect(skeleton).toBeTruthy()
  })

  it('hides loading shimmer when image onLoad triggers', () => {
    render(
      <ProductImage
        src="/static/media/products/sample.webp"
        alt="Amul Butter"
        category="Dairy"
      />
    )

    const img = screen.getByAltText('Amul Butter')
    fireEvent.load(img)

    expect(screen.queryByTestId('product-image-skeleton')).toBeNull()
  })

  it('renders category fallback icon and label when image triggers onError', () => {
    render(
      <ProductImage
        src="/static/media/products/broken.webp"
        alt="Dolo 650 Tablets"
        category="Medicines"
      />
    )

    const img = screen.getByAltText('Dolo 650 Tablets')
    fireEvent.error(img)

    const fallback = screen.getByTestId('product-image-fallback')
    expect(fallback).toBeTruthy()
    expect(fallback.textContent).toContain('Medicines')
    expect(screen.getByTestId('category-fallback-icon')).toBeTruthy()
  })

  it('renders fallback directly when src is null or empty', () => {
    render(
      <ProductImage
        src={null}
        alt="Artisan Garlic Bread"
        category="Bakery"
      />
    )

    expect(screen.queryByRole('img')).toBeNull()
    const fallback = screen.getByTestId('product-image-fallback')
    expect(fallback).toBeTruthy()
    expect(fallback.textContent).toContain('Bakery')
  })

  it('adapts fallback icon per category (Groceries vs Dairy vs Bakery)', () => {
    const { unmount } = render(
      <ProductImage src={null} alt="Milk" category="Dairy" />
    )
    expect(screen.getByTestId('product-image-fallback').textContent).toContain('Dairy')
    unmount()

    render(<ProductImage src={null} alt="Croissant" category="Bakery" />)
    expect(screen.getByTestId('product-image-fallback').textContent).toContain('Bakery')
  })
})
