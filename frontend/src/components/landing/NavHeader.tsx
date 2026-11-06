import { Store } from "lucide-react";
import { Link } from "react-router-dom";

export default function NavHeader() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-border bg-surface/80 backdrop-blur-lg">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-8">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2">
          <Store className="h-6 w-6 text-primary-600" />
          <span className="text-xl font-bold tracking-tight text-primary-900">
            Dukaan<span className="text-primary-700">ly</span>
          </span>
        </Link>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <Link
            to="/login"
            className="rounded-lg px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:bg-primary-50 hover:text-primary-900"
          >
            Sign In
          </Link>
          <Link
            to="/login"
            className="btn-primary rounded-lg px-5 py-2 text-sm font-medium text-white shadow-green-btn transition-all"
          >
            Get Started
          </Link>
        </div>
      </div>
    </header>
  );
}
