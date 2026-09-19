/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        ink: {
          900: "#0b0d10",
          800: "#111418",
          700: "#181c22",
          600: "#232830",
          500: "#3a4049",
          400: "#6b7280",
          300: "#9ca3af",
          200: "#d1d5db",
        },
        accent: {
          DEFAULT: "#3b82f6",
          up: "#10b981",
          down: "#ef4444",
        },
      },
    },
  },
  plugins: [],
};
