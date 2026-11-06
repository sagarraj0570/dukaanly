import React from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck, ExternalLink, Image, ArrowLeft, Heart, Sparkles } from 'lucide-react'

export const CreditsPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-surface-alt/40 py-10 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Navigation & Header */}
        <div className="space-y-4">
          <Link
            to="/customer"
            className="inline-flex items-center text-sm font-medium text-primary-700 hover:text-primary-800 transition-colors gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded-md"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Marketplace
          </Link>
          <div className="border-b border-border pb-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-100 text-primary-800 text-xs font-semibold mb-3">
              <ShieldCheck className="h-3.5 w-3.5" />
              Verified License-Safe Media
            </div>
            <h1 className="text-3xl sm:text-4xl font-extrabold text-primary-950 tracking-tight">
              Product Media & Attributions
            </h1>
            <p className="mt-2 text-base text-text-muted max-w-2xl">
              Dukaanly strictly respects copyright and open-source licensing. Every product image in our catalog is normalized into high-efficiency WebP studio assets and sourced exclusively from permissible, license-safe repositories.
            </p>
          </div>
        </div>

        {/* Data Sources Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Open Food Facts */}
          <div className="bg-surface border border-border rounded-2xl p-6 shadow-warm-xs flex flex-col justify-between">
            <div className="space-y-3">
              <div className="h-10 w-10 rounded-xl bg-primary-50 border border-primary-200/50 flex items-center justify-center text-primary-700">
                <Image className="h-5 w-5" />
              </div>
              <h2 className="text-xl font-bold text-primary-950">Open Food Facts</h2>
              <p className="text-sm text-text-muted leading-relaxed">
                Packaged groceries and branded consumer goods are enriched via the non-profit Open Food Facts database using canonical EAN-13 barcodes.
              </p>
              <div className="text-xs space-y-1 text-text-muted">
                <p>
                  <strong className="text-text">Database License:</strong> Open Database License (ODbL)
                </p>
                <p>
                  <strong className="text-text">Image License:</strong> Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)
                </p>
                <p>
                  <strong className="text-text">Attribution:</strong> Open Food Facts contributors
                </p>
              </div>
            </div>
            <div className="mt-6 pt-4 border-t border-border">
              <a
                href="https://world.openfoodfacts.org"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary-700 hover:text-primary-800 transition-colors"
              >
                Visit Open Food Facts
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          </div>

          {/* Wikimedia Commons */}
          <div className="bg-surface border border-border rounded-2xl p-6 shadow-warm-xs flex flex-col justify-between">
            <div className="space-y-3">
              <div className="h-10 w-10 rounded-xl bg-accent-50 border border-accent-200/50 flex items-center justify-center text-accent-700">
                <Sparkles className="h-5 w-5" />
              </div>
              <h2 className="text-xl font-bold text-primary-950">Wikimedia Commons</h2>
              <p className="text-sm text-text-muted leading-relaxed">
                Fresh artisan bakery items, local staple grains, and commodity goods feature public educational photography contributed to Wikimedia Commons.
              </p>
              <div className="text-xs space-y-1 text-text-muted">
                <p>
                  <strong className="text-text">Licenses:</strong> CC BY-SA 4.0, CC BY 3.0, and Public Domain (CC0)
                </p>
                <p>
                  <strong className="text-text">Attribution:</strong> Respective Wikimedia Commons authors & photographers
                </p>
              </div>
            </div>
            <div className="mt-6 pt-4 border-t border-border">
              <a
                href="https://commons.wikimedia.org"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary-700 hover:text-primary-800 transition-colors"
              >
                Explore Wikimedia Commons
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          </div>

          {/* Pexels */}
          <div className="bg-surface border border-border rounded-2xl p-6 shadow-warm-xs flex flex-col justify-between">
            <div className="space-y-3">
              <div className="h-10 w-10 rounded-xl bg-terracotta-50 border border-terracotta-200/50 flex items-center justify-center text-terracotta-700">
                <Heart className="h-5 w-5" />
              </div>
              <h2 className="text-xl font-bold text-primary-950">Pexels</h2>
              <p className="text-sm text-text-muted leading-relaxed">
                Select high-resolution produce and beverage imagery is sourced under the free-to-use Pexels License.
              </p>
              <div className="text-xs space-y-1 text-text-muted">
                <p>
                  <strong className="text-text">License:</strong> Pexels License (Commercial & Non-commercial free use)
                </p>
                <p>
                  <strong className="text-text">Attribution:</strong> Pexels Creators & Community
                </p>
              </div>
            </div>
            <div className="mt-6 pt-4 border-t border-border">
              <a
                href="https://www.pexels.com"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary-700 hover:text-primary-800 transition-colors"
              >
                Visit Pexels
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          </div>

          {/* Shop Owner Uploads */}
          <div className="bg-surface border border-border rounded-2xl p-6 shadow-warm-xs flex flex-col justify-between">
            <div className="space-y-3">
              <div className="h-10 w-10 rounded-xl bg-primary-100 border border-primary-300/50 flex items-center justify-center text-primary-800">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <h2 className="text-xl font-bold text-primary-950">Shop Owner Custom Media</h2>
              <p className="text-sm text-text-muted leading-relaxed">
                Registered shop owners can upload proprietary storefront or studio product photos. Custom uploads override master catalog imagery only for that merchant&apos;s listing.
              </p>
              <div className="text-xs space-y-1 text-text-muted">
                <p>
                  <strong className="text-text">Policy:</strong> Verified merchant uploads with 5MB validation, automatic EXIF stripping, and WebP studio normalization.
                </p>
              </div>
            </div>
            <div className="mt-6 pt-4 border-t border-border text-xs text-text-muted">
              Managed securely through the Dukaanly Merchant Dashboard.
            </div>
          </div>
        </div>

        {/* Footer Note */}
        <div className="bg-primary-50/60 border border-primary-200/60 rounded-2xl p-5 text-sm text-primary-900 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs leading-relaxed text-text-muted">
            If you are a copyright holder and believe any asset requires attribution adjustment or removal, please contact the Dukaanly compliance team at{' '}
            <a href="mailto:compliance@dukaanly.com" className="font-semibold text-primary-700 underline">
              compliance@dukaanly.com
            </a>
            .
          </p>
          <Link
            to="/customer"
            className="whitespace-nowrap px-4 py-2 rounded-xl bg-primary-700 text-white text-xs font-semibold hover:bg-primary-800 transition-colors"
          >
            Return to Shopping
          </Link>
        </div>
      </div>
    </div>
  )
}

export default CreditsPage
