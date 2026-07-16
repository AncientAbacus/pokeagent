/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'poke-red':       '#CC0000',
        'poke-red-dark':  '#8B0000',
        'poke-red-light': '#FF4444',
        'poke-cream':     '#F5F0E8',
        'poke-cream-dark':'#E8E0D0',
        'poke-screen':    '#98CB98',
      },
      fontFamily: {
        pixel: ['"Press Start 2P"', 'monospace'],
      },
    },
  },
  plugins: [],
};
