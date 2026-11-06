import { Monitor, Store } from "lucide-react";

/**
 * Full-screen overlay shown on viewports narrower than 1024px.
 *
 * Usage:
 *   <DesktopOnlyNotice />
 *   <main className="hidden lg:flex lg:flex-col"> ... landing content ... </main>
 */
export default function DesktopOnlyNotice() {
  return (
    <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-bg px-8 text-center lg:hidden">
      {/* Logo */}
      <div className="mb-10 flex items-center gap-2">
        <Store className="h-7 w-7 text-primary-700" />
        <span className="text-2xl font-bold tracking-tight text-primary-900">
          Dukaan<span className="text-primary-700">ly</span>
        </span>
      </div>

      {/* Icon */}
      <div className="mb-8 flex h-20 w-20 items-center justify-center rounded-2xl bg-primary-50">
        <Monitor className="h-10 w-10 text-primary-700" />
      </div>

      {/* Copy */}
      <h1 className="mb-3 text-2xl font-bold text-primary-900">
        Dukaanly Desktop Experience
      </h1>
      <p className="max-w-md text-base leading-relaxed text-text-secondary">
        This premium experience is optimized for desktop screens. Please visit
        on a device with a viewport of 1024px or wider.
      </p>
    </div>
  );
}
