import {
  ShoppingCart,
  Droplets,
  Cookie,
  Coffee,
  Heart,
  Home,
  Croissant,
  Pill,
} from "lucide-react";

const categories = [
  { name: "Groceries", icon: ShoppingCart },
  { name: "Dairy", icon: Droplets },
  { name: "Snacks", icon: Cookie },
  { name: "Beverages", icon: Coffee },
  { name: "Personal Care", icon: Heart },
  { name: "Household Essentials", icon: Home },
  { name: "Bakery", icon: Croissant },
  { name: "Medicines", icon: Pill },
] as const;

export default function CategorySection() {
  return (
    <section className="bg-bg py-24">
      <div className="mx-auto max-w-7xl px-8">
        {/* Header */}
        <div className="mb-14 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-primary-900">
            Shop by Category
          </h2>
          <p className="mt-3 text-lg text-text-secondary">
            Everything your neighbourhood has to offer
          </p>
        </div>

        {/* Grid */}
        <div className="grid grid-cols-4 gap-5">
          {categories.map(({ name, icon: Icon }) => (
            <div
              key={name}
              className="group flex flex-col items-center gap-4 rounded-2xl border border-border bg-white px-6 py-8 transition-all duration-200 hover:scale-[1.03] hover:shadow-lg hover:shadow-warm-md"
            >
              <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-50 transition-colors group-hover:bg-primary-100">
                <Icon className="h-6 w-6 text-primary-700" />
              </div>
              <span className="text-sm font-semibold text-primary-900">
                {name}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
