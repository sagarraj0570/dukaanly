import { Radio, MapPinned, Store } from "lucide-react";

const values = [
  {
    title: "Real-Time Inventory",
    description:
      "Every price and stock count comes directly from the shop. No hidden markups, no phantom availability.",
    icon: Radio,
  },
  {
    title: "Live Order Tracking",
    description:
      "Follow your delivery in real-time on a map, from shop pickup to your doorstep.",
    icon: MapPinned,
  },
  {
    title: "Local First",
    description:
      "Supporting neighbourhood businesses with technology that puts them in control.",
    icon: Store,
  },
] as const;

export default function BrandSection() {
  return (
    <section className="bg-bg py-24">
      <div className="mx-auto max-w-7xl px-8">
        {/* Header */}
        <div className="mx-auto mb-16 max-w-3xl text-center">
          <h2 className="text-3xl font-bold tracking-tight text-primary-900">
            Built for Your Neighbourhood
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-text-secondary">
            Dukaanly connects you directly with local shop owners and delivery
            riders — powering hyperlocal commerce with real-time inventory, live
            tracking, and honest pricing.
          </p>
        </div>

        {/* Value cards */}
        <div className="grid grid-cols-3 gap-6">
          {values.map(({ title, description, icon: Icon }) => (
            <div
              key={title}
              className="rounded-2xl border border-border bg-white p-8 transition-shadow hover:shadow-lg hover:shadow-warm-md"
            >
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-primary-50">
                <Icon className="h-5 w-5 text-primary-700" />
              </div>
              <h3 className="mb-2 text-lg font-semibold text-primary-900">
                {title}
              </h3>
              <p className="text-[15px] leading-relaxed text-text-secondary">
                {description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
