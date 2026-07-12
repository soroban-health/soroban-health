/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0B0F0E",
        surface: "#141918",
        line: "#1E2622",
        ink: "#E2F5EC",
        muted: "#7A9188",
        signal: "#3DDC97", // healthy / pass, primary interactive color
        warn: "#E8A33D", // medium severity
        critical: "#E2574C", // high severity
        "accent-text": "#A8F0CB", // light mint, small accent labels only
      },
      fontFamily: {
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
      },
    },
  },
  plugins: [],
};
