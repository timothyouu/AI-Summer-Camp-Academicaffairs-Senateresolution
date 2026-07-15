/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          DEFAULT: "#16305e",
          deep: "#122a54",
          text: "#1b2a4a",
        },
        brand: {
          blue: "#1d4ed8",
          bright: "#2563eb",
        },
        gold: "#f5b301",
        cream: "#f7f5f1",
        amberbg: "#fef7e6",
        inkmuted: "#5b6b82",
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
