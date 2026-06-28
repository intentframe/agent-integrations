/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#22d3ee",
          muted: "#0891b2",
        },
      },
    },
  },
  plugins: [],
};
