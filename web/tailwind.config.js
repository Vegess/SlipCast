/** @type {import('tailwindcss').Config} */
const plugin = require("tailwindcss/plugin");

/**
 * Two themes. "dusk" (default) is a soft, colourful dark theme; "light" is its daytime
 * counterpart. Every colour pair used for text meets WCAG AA (4.5:1) on canvas, panel and
 * raised. The *-strong tones are for text on tinted chips (e.g. bg-bad/15), where the base
 * colour alone would fall below 4.5:1.
 */
const palettes = {
  dusk: {
    canvas: "#172033",
    panel: "#1F2A40",
    "panel-tint": "#1C2C4B", // sidebar gradient end: panel with a bluer tint
    raised: "#28354F",
    line: "#34425E",
    grid: "#2A3650", // chart grid lines
    fg: "#EEF2F8",
    muted: "#A3AEC4",
    accent: "#F5B83D",
    "accent-ink": "#231A00",
    info: "#6EA8FE",
    ok: "#4FD1A5",
    bad: "#FF7A7A",
    violet: "#A78BFA",
    "accent-strong": "#FFD587",
    "info-strong": "#B3D0FF",
    "ok-strong": "#93E8CB",
    "bad-strong": "#FFB8B8",
    "violet-strong": "#CFC2FF",
  },
  light: {
    canvas: "#F3F5FA",
    panel: "#FFFFFF",
    "panel-tint": "#EDF2FC",
    raised: "#EAEEF5",
    line: "#D3DAE6",
    grid: "#E4E9F1",
    fg: "#18202F",
    muted: "#566279",
    accent: "#9A5B00",
    "accent-ink": "#FFFFFF",
    info: "#2459D6",
    ok: "#0B7A5C",
    bad: "#C2302F",
    violet: "#6D3FD9",
    "accent-strong": "#7A4700",
    "info-strong": "#1C45A8",
    "ok-strong": "#075C45",
    "bad-strong": "#9E2020",
    "violet-strong": "#5530B0",
  },
};

const channels = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(" ");
const vars = (p) => Object.fromEntries(Object.entries(p).map(([k, v]) => [`--c-${k}`, channels(v)]));

module.exports = {
  content: ["./src/**/*.{html,ts}"],
  theme: {
    extend: {
      colors: Object.fromEntries(
        Object.keys(palettes.dusk).map((k) => [k, `rgb(var(--c-${k}) / <alpha-value>)`]),
      ),
      fontFamily: {
        display: ['"Bricolage Grotesque"', '"Instrument Sans"', "system-ui", "sans-serif"],
        sans: ['"Instrument Sans"', "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
      },
    },
  },
  plugins: [
    plugin(({ addBase }) => {
      addBase({
        ":root": { ...vars(palettes.dusk), colorScheme: "dark" },
        ':root[data-theme="light"]': { ...vars(palettes.light), colorScheme: "light" },
      });
    }),
  ],
  palettes,
};
