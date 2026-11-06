import type { Config } from "tailwindcss";

const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        plane: v("plane"),
        surface: v("surface"),
        raised: v("raised"),
        ink: { DEFAULT: v("ink"), 2: v("ink-2"), muted: v("ink-muted") },
        line: v("line"),
        brand: { DEFAULT: v("brand"), soft: v("brand-soft"), ink: v("brand-ink") },
        good: v("good"),
        warn: v("warn"),
        serious: v("serious"),
        critical: v("critical"),
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: { xl: "14px", "2xl": "18px" },
      boxShadow: {
        card: "0 1px 0 rgb(var(--ink) / 0.03), 0 1px 3px rgb(var(--ink) / 0.06)",
        pop: "0 12px 40px -8px rgb(0 0 0 / 0.35)",
      },
      keyframes: {
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "pulse-ring": { "0%": { transform: "scale(.8)", opacity: ".7" }, "100%": { transform: "scale(2.2)", opacity: "0" } },
      },
      animation: {
        shimmer: "shimmer 1.4s infinite",
        "pulse-ring": "pulse-ring 1.8s cubic-bezier(.2,.6,.4,1) infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
