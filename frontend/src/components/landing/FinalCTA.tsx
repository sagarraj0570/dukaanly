import { Link } from "react-router-dom";

export default function FinalCTA() {
  return (
    <section className="bg-gradient-to-br from-primary-700 via-primary-800 to-primary-900 py-24">
      <div className="mx-auto max-w-3xl px-8 text-center">
        <h2 className="text-4xl font-bold leading-tight tracking-tight text-white">
          Ready to explore your neighbourhood?
        </h2>
        <p className="mx-auto mt-5 max-w-xl text-lg leading-relaxed text-white/80">
          Join Dukaanly and discover what's available right around the corner.
        </p>
        <Link
          to="/login"
          className="mt-10 inline-block rounded-lg bg-white px-8 py-3.5 text-sm font-semibold text-primary-700 shadow-lg transition-all hover:bg-bg hover:shadow-xl"
        >
          Get Started
        </Link>
      </div>
    </section>
  );
}
