import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * Tailwind is scoped to the new shadcn/ui surfaces (the waiting-bubble mask,
 * skeleton primitives, future shadcn components). Preflight is disabled so
 * the existing CSS Modules + globals.css reset continues to own the
 * page-wide baseline.
 */
const config: Config = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        bg: {
          base: "var(--bg-base)",
          surface: "var(--bg-surface)",
          elevated: "var(--bg-elevated)",
          overlay: "var(--bg-overlay)",
        },
        border: {
          subtle: "var(--border-subtle)",
          DEFAULT: "var(--border-default)",
          strong: "var(--border-strong)",
        },
        text: {
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          tertiary: "var(--text-tertiary)",
        },
        gold: {
          DEFAULT: "var(--accent-gold)",
          dim: "var(--accent-gold-dim)",
        },
        blue: {
          DEFAULT: "var(--accent-blue)",
          dim: "var(--accent-blue-dim)",
        },
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
      },
      fontFamily: {
        sans: "var(--font-sans)",
        display: "var(--font-display)",
      },
      keyframes: {
        "dot-pulse": {
          "0%, 80%, 100%": { opacity: "0.25", transform: "translateY(0)" },
          "40%": { opacity: "1", transform: "translateY(-2px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "dot-pulse": "dot-pulse 1.2s ease-in-out infinite",
        shimmer: "shimmer 2.4s linear infinite",
      },
    },
  },
  plugins: [animate],
};

export default config;
