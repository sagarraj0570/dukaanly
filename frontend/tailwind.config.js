/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: [
    './index.html',
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: '1.5rem',
      screens: {
        '2xl': '1400px',
      },
    },
    extend: {
      fontFamily: {
        display: ['var(--font-display)'],
        sans: ['var(--font-sans)'],
      },
      colors: {
        paper: 'var(--paper)',
        surface: {
          DEFAULT: 'var(--surface)',
          alt: 'var(--sand)',
        },
        sand: 'var(--sand)',
        border: 'var(--border)',
        'border-strong': 'var(--border-strong)',
        input: 'var(--border-strong)',
        ring: 'var(--leaf)',
        background: 'var(--paper)',
        foreground: 'var(--ink)',
        bg: 'var(--paper)',
        ink: {
          DEFAULT: 'var(--ink)',
          soft: 'var(--ink-soft)',
        },
        leaf: {
          DEFAULT: 'var(--leaf)',
          hover: 'var(--leaf-hover)',
          ink: 'var(--leaf-ink)',
        },
        'sage-tint': 'var(--sage-tint)',
        turmeric: {
          DEFAULT: 'var(--turmeric)',
          tint: 'var(--turmeric-tint)',
          ink: 'var(--turmeric-ink)',
        },
        brick: {
          DEFAULT: 'var(--brick)',
          tint: 'var(--brick-tint)',
          ink: 'var(--brick-ink)',
        },
        text: {
          primary: 'var(--ink)',
          secondary: 'var(--ink-soft)',
          muted: 'var(--ink-soft)',
        },
        primary: {
          DEFAULT: 'var(--leaf)',
          foreground: 'var(--leaf-ink)',
          50: 'var(--primary-50)',
          100: 'var(--primary-100)',
          200: 'var(--sage-tint)',
          500: 'var(--leaf)',
          600: 'var(--leaf-hover)',
          700: 'var(--leaf)',
          900: 'var(--primary-900)',
        },
        secondary: {
          DEFAULT: 'var(--sand)',
          foreground: 'var(--ink)',
        },
        destructive: {
          DEFAULT: 'var(--brick)',
          foreground: 'var(--leaf-ink)',
        },
        muted: {
          DEFAULT: 'var(--sand)',
          foreground: 'var(--ink-soft)',
        },
        accent: {
          DEFAULT: 'var(--sage-tint)',
          foreground: 'var(--ink)',
          100: 'var(--accent-100)',
          200: 'var(--turmeric-tint)',
          500: 'var(--turmeric)',
          600: 'var(--turmeric-ink)',
          700: 'var(--turmeric-ink)',
        },
        terracotta: {
          DEFAULT: 'var(--brick)',
          100: 'var(--brick-tint)',
          600: 'var(--brick)',
        },
        popover: {
          DEFAULT: 'var(--surface)',
          foreground: 'var(--ink)',
        },
        card: {
          DEFAULT: 'var(--surface)',
          foreground: 'var(--ink)',
        },
        brand: {
          primary: 'var(--leaf)',
          deep: 'var(--leaf-hover)',
          accent: 'var(--turmeric)',
          marigold: 'var(--turmeric)',
          terracotta: 'var(--brick)',
          warmBg: 'var(--paper)',
          text: 'var(--ink)',
          textSecondary: 'var(--ink-soft)',
          border: 'var(--border)',
          soft: 'var(--sage-tint)',
        },
        role: {
          customer: 'var(--role-customer)',
          customerBg: 'var(--role-customer-bg)',
          shop: 'var(--leaf)',
          shopBg: 'var(--sage-tint)',
          rider: 'var(--turmeric-ink)',
          riderBg: 'var(--turmeric-tint)',
        },
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        DEFAULT: 'var(--radius)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-lg)',
        '2xl': 'var(--radius-lg)',
      },
      boxShadow: {
        overlay: '0 8px 24px rgba(30, 42, 36, 0.12)',
        xs: 'none',
        soft: 'none',
        card: 'none',
        elevated: '0 8px 24px rgba(30, 42, 36, 0.12)',
        primary: 'none',
        accent: 'none',
      },
      transitionDuration: {
        fast: 'var(--dur-fast)',
        DEFAULT: 'var(--dur)',
      },
      transitionTimingFunction: {
        DEFAULT: 'var(--ease)',
      },
      animation: {
        'fade-in': 'fadeIn var(--dur) var(--ease) forwards',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
