import * as React from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { BillCard } from "@/components/ui/BillCard"
import { StatusStamp } from "@/components/ui/StatusStamp"
import { BazaarPattern } from "@/components/ui/BazaarPattern"

export const DevComponentsShowcase: React.FC = () => {
  return (
    <div className="min-h-screen bg-paper text-ink p-6 sm:p-10 space-y-12 max-w-5xl mx-auto">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-[-0.01em] text-ink">
          Bazaar Paper Component Showcase
        </h1>
        <p className="mt-1 text-sm text-ink-soft">
          Handcrafted Indian neighbourhood shop visual tokens & signature primitives.
        </p>
      </div>

      {/* Bazaar Pattern Strip */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold text-ink">1. Bazaar Pattern (Strip)</h2>
        <div className="border border-border rounded-[14px] p-4 bg-surface space-y-3">
          <BazaarPattern variant="strip" />
          <p className="text-xs text-ink-soft">Quiet 12px Mithila-inspired repeating border motif</p>
        </div>
      </section>

      {/* Bazaar Pattern Fill */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold text-ink">2. Bazaar Pattern (Fill)</h2>
        <div className="relative h-32 border border-border rounded-[14px] bg-sand overflow-hidden flex items-center justify-center p-6 text-center">
          <BazaarPattern variant="fill" />
          <div className="relative z-10 bg-surface/90 px-4 py-2 rounded-[8px] border border-border">
            <span className="text-xs font-semibold text-ink">Decorative tile overlay across empty surfaces</span>
          </div>
        </div>
      </section>

      {/* Status Stamps */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold text-ink">3. Status Stamps</h2>
        <div className="flex flex-wrap gap-4 items-center p-5 bg-surface border border-border rounded-[14px]">
          <StatusStamp tone="success">Delivered</StatusStamp>
          <StatusStamp tone="warning">Preparing</StatusStamp>
          <StatusStamp tone="danger">Cancelled</StatusStamp>
          <StatusStamp tone="neutral">Out For Delivery</StatusStamp>
        </div>
      </section>

      {/* Bill Card */}
      <section className="space-y-3 max-w-md">
        <h2 className="font-display text-xl font-semibold text-ink">4. Printed Bill Card</h2>
        <BillCard
          title="Chowdhury Kirana & General Store"
          note="Order #DKN-8421 • Boring Road, Patna"
          rows={[
            { label: "Aashirvaad Shudh Chakki Atta", value: "₹450.00", sub: "10 kg pack" },
            { label: "Amul Taaza Homogenised Milk", value: "₹144.00", sub: "2 x 1L pouch" },
            { label: "Tata Salt Vacuum Evaporated", value: "₹28.00", sub: "1 kg pack" },
            { label: "Doorstep Hyperlocal Delivery", value: "₹25.00", emphasis: true },
          ]}
          footer={{ label: "Grand Total", value: "₹647.00" }}
        />
      </section>

      {/* Button Variants */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold text-ink">5. Buttons</h2>
        <div className="flex flex-wrap gap-3 items-center p-5 bg-surface border border-border rounded-[14px]">
          <Button variant="default">Primary Action</Button>
          <Button variant="secondary">Secondary Action</Button>
          <Button variant="outline">Outline Action</Button>
          <Button variant="ghost">Ghost Action</Button>
          <Button variant="accent">Accent Action</Button>
          <Button variant="destructive">Destructive</Button>
          <Button variant="link">Link Style</Button>
        </div>
      </section>

      {/* Input */}
      <section className="space-y-3 max-w-md">
        <h2 className="font-display text-xl font-semibold text-ink">6. Form Input</h2>
        <div className="space-y-2 p-5 bg-surface border border-border rounded-[14px]">
          <label className="text-xs font-semibold text-ink block">Delivery Address or Landmark</label>
          <Input placeholder="e.g. Near Maurya Lok Complex, Dak Bungalow..." />
        </div>
      </section>

      {/* Badges */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold text-ink">7. Badges & Chips</h2>
        <div className="flex flex-wrap gap-3 items-center p-5 bg-surface border border-border rounded-[14px]">
          <Badge variant="neutral">Neutral Pill</Badge>
          <Badge variant="success">Verified Partner</Badge>
          <Badge variant="warning">Low Stock</Badge>
          <Badge variant="danger">Discontinued</Badge>
          <Badge variant="count" size="count">3</Badge>
        </div>
      </section>

      {/* Tabs */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold text-ink">8. Underline Tabs</h2>
        <div className="p-5 bg-surface border border-border rounded-[14px]">
          <Tabs defaultValue="all">
            <TabsList>
              <TabsTrigger value="all">All Stores</TabsTrigger>
              <TabsTrigger value="online">Order Online</TabsTrigger>
              <TabsTrigger value="directory">Directory Listings</TabsTrigger>
            </TabsList>
            <TabsContent value="all">
              <p className="text-sm text-ink-soft">Showing all verified neighborhood merchants and directory listings.</p>
            </TabsContent>
            <TabsContent value="online">
              <p className="text-sm text-ink-soft">Showing partner merchants with instant 30-minute doorstep delivery.</p>
            </TabsContent>
            <TabsContent value="directory">
              <p className="text-sm text-ink-soft">Showing verified local shops discovered via OpenStreetMap.</p>
            </TabsContent>
          </Tabs>
        </div>
      </section>
    </div>
  )
}
export default DevComponentsShowcase
