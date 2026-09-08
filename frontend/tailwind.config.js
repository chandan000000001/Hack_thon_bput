/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      colors: {
        // Strict black / white / red palette — neutral scale pinned to exact
        // surfaces: page #050505, panels #0a0a0a, cards #101010, borders #262626.
        zinc: {
          50: '#fafafa',
          100: '#f4f4f5',
          200: '#e4e4e7',
          300: '#d4d4d8',
          400: '#a3a3a3',
          500: '#71717a',
          600: '#52525b',
          700: '#3f3f46',
          800: '#262626',
          900: '#0a0a0a',
          950: '#050505',
        },
        severity: {
          safe: '#e4e4e7',
          low: '#71717a',
          medium: '#f87171',
          high: '#dc2626',
          critical: '#ef4444',
        },
      },
      animation: {
        'pulse-dot': 'pulseDot 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'pulse-ring': 'pulseRing 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        pulseDot: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.4', transform: 'scale(0.85)' },
        },
        pulseRing: {
          '0%': { 'box-shadow': '0 0 0 0 rgba(239, 68, 68, 0.55)' },
          '70%': { 'box-shadow': '0 0 0 7px rgba(239, 68, 68, 0)' },
          '100%': { 'box-shadow': '0 0 0 0 rgba(239, 68, 68, 0)' },
        },
      },
    },
  },
  plugins: [],
};
