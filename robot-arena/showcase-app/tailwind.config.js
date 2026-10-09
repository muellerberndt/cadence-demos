/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#e8ebf2",
        muted: "#8f98a9",
        panel: "#141924",
        panel2: "#1b2130",
        line: "#273040",
        calm: "#4fa3ff",
        aroused: "#ffb347",
        ring: "#ff7a45",
        hp: "#5ad37a",
        hplow: "#ff5d5d",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: { glow: "0 0 40px rgba(255, 179, 71, 0.25)" },
    },
  },
  plugins: [],
};
