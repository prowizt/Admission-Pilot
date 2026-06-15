/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'daedong-navy': '#1a214e',
        'daedong-cyan': '#30bfd0',
        'daedong-green': '#00ab74',
        'daedong-red': '#ef4a47',
      },
      fontFamily: {
        sans: ['"Inter"', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
