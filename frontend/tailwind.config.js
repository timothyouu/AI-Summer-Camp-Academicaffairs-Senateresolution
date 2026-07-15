/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: "rgb(var(--c-navy) / <alpha-value>)",
          deep: "rgb(var(--c-navy-deep) / <alpha-value>)",
          text: "rgb(var(--c-navy-text) / <alpha-value>)",
        },
        brand: {
          blue: "rgb(var(--c-brand-blue) / <alpha-value>)",
          bright: "#2563eb",
        },
        gold: "#f5b301",
        cream: "rgb(var(--c-cream) / <alpha-value>)",
        amberbg: "rgb(var(--c-amberbg) / <alpha-value>)",
        inkmuted: "rgb(var(--c-inkmuted) / <alpha-value>)",
        white: "rgb(var(--c-white) / <alpha-value>)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 3px rgba(22, 48, 94, 0.08), 0 1px 2px rgba(22, 48, 94, 0.04)",
      },
    },
  },
  plugins: [],
};
