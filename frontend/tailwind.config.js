/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0B0E11",
        surface: "#12161B",
        line: "#22272E",
        ink: "#E6EAEE",
        muted: "#8A93A0",
        signal: "#3DDC97", // healthy / pass
        warn: "#E8A33D", // medium severity
        critical: "#E2574C", // high severity
        accent: "#5B8CFF", // links, interactive
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui"],
      },
    },
  },
  plugins: [],
};
