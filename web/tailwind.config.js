/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{html,ts}"],
  theme: {
    extend: {
      colors: {
        canvas: "#0D1220",
        panel: "#141A29",
        raised: "#1B2235",
        line: "#262E42",
        fg: "#E5E9F2",
        muted: "#8E98AE",
        accent: "#F2B632",
        "accent-ink": "#231A00",
        info: "#7D96F2",
        ok: "#52B5AA",
        bad: "#E66C63",
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', '"Instrument Sans"', "system-ui", "sans-serif"],
        sans: ['"Instrument Sans"', "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
      },
    },
  },
  plugins: [],
};
