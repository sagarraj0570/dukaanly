import { Store } from "lucide-react";

export default function Footer() {
  return (
    <footer className="border-t border-border bg-bg">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-8 py-8">
        {/* Brand */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <Store className="h-5 w-5 text-primary-700" />
            <span className="text-base font-bold tracking-tight text-primary-900">
              Dukaan<span className="text-primary-700">ly</span>
            </span>
          </div>
          <span className="text-sm text-text-secondary">
            © 2024 Dukaanly. Hyperlocal commerce platform.
          </span>
        </div>

        {/* Links */}
        <div className="flex items-center gap-6">
          <a
            href="#"
            className="text-sm text-text-secondary transition-colors hover:text-primary-900"
          >
            Privacy Policy
          </a>
          <a
            href="#"
            className="text-sm text-text-secondary transition-colors hover:text-primary-900"
          >
            Terms of Service
          </a>
        </div>
      </div>
    </footer>
  );
}
