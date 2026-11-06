import { MapPin, ShoppingBag, Bike } from "lucide-react";

const steps = [
  {
    number: "01",
    title: "Browse Local Shops",
    description:
      "Discover verified neighbourhood stores and their full product catalogs, right from your desktop.",
    icon: MapPin,
  },
  {
    number: "02",
    title: "Place Your Order",
    description:
      "Add items to cart with real-time stock checks, secure checkout with UPI or Cash on Delivery.",
    icon: ShoppingBag,
  },
  {
    number: "03",
    title: "Rider Delivery",
    description:
      "Track your rider in real-time as your order makes its way from the shop to your doorstep.",
    icon: Bike,
  },
] as const;

export default function HowItWorks() {
  return (
    <section className="bg-white py-24">
      <div className="mx-auto max-w-7xl px-8">
        {/* Header */}
        <div className="mb-16 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-primary-900">
            How It Works
          </h2>
          <p className="mt-3 text-lg text-text-secondary">
            From browsing to doorstep — in three simple steps
          </p>
        </div>

        {/* Steps */}
        <div className="relative grid grid-cols-3 gap-12">
          {/* Connecting line */}
          <div className="pointer-events-none absolute left-[16.67%] right-[16.67%] top-12 hidden h-px bg-gradient-to-r from-border via-primary-200 to-border lg:block" />

          {steps.map(({ number, title, description, icon: Icon }) => (
            <div key={number} className="relative flex flex-col items-center text-center">
              {/* Number badge */}
              <div className="relative z-10 mb-6 flex h-24 w-24 items-center justify-center rounded-full border-2 border-border bg-white">
                <span className="text-3xl font-bold text-primary-700/20">
                  {number}
                </span>
                <div className="absolute inset-0 flex items-center justify-center">
                  <Icon className="h-8 w-8 text-primary-700" />
                </div>
              </div>

              {/* Content */}
              <h3 className="mb-3 text-xl font-semibold text-primary-900">
                {title}
              </h3>
              <p className="max-w-xs text-[15px] leading-relaxed text-text-secondary">
                {description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
