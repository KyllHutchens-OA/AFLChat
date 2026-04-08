/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Legacy brand colors (keep for compatibility)
        'brand-blue': '#3b82f6',
        'brand-red': '#ef4444',
        'brand-green': '#10b981',

        // Apple-inspired color palette
        'apple-blue': {
          50: '#E5F1FF',
          100: '#CCE4FF',
          500: '#007AFF',  // Apple's primary blue
          600: '#0051D5',
          700: '#0040A8',
        },
        'apple-gray': {
          50: '#F5F5F7',   // Apple's lightest gray
          100: '#E8E8ED',  // Secondary background
          200: '#D1D1D6',  // Tertiary
          300: '#C7C7CC',  // Separator
          500: '#8E8E93',  // Label secondary
          700: '#636366',  // Label tertiary
          900: '#1C1C1E',  // Label primary
        },
        'apple-green': '#34C759',
        'apple-red': '#FF3B30',
        'apple-orange': '#FF9500',

        // AFL warm accent palette (red-based primary)
        'afl-accent': {
          DEFAULT: '#CC2936',
          50: '#FEF2F2',
          100: '#FDE6E7',
          200: '#FACDD0',
          300: '#F5A3A9',
          400: '#E8636C',
          500: '#CC2936',
          600: '#B8232F',
          700: '#9A1D28',
          800: '#7D1821',
          900: '#60121A',
        },
        // AFL warm neutral palette (cream/tan)
        'afl-warm': {
          50: '#FAF7F2',
          100: '#F0EBE3',
          200: '#E0D5C8',
          300: '#C8B9A8',
          400: '#A89888',
          500: '#8A7B6B',
          600: '#706354',
          700: '#574D42',
          800: '#3E3732',
          900: '#2A2522',
        },
      },

      // SF Pro-like typography
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'SF Pro Display', 'SF Pro Text', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['SF Mono', 'Monaco', 'Menlo', 'Consolas', 'monospace'],
      },

      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem', letterSpacing: '-0.01em' }],
        sm: ['0.875rem', { lineHeight: '1.25rem', letterSpacing: '-0.01em' }],
        base: ['1rem', { lineHeight: '1.5rem', letterSpacing: '-0.011em' }],
        lg: ['1.125rem', { lineHeight: '1.75rem', letterSpacing: '-0.014em' }],
        xl: ['1.25rem', { lineHeight: '1.875rem', letterSpacing: '-0.017em' }],
        '2xl': ['1.5rem', { lineHeight: '2rem', letterSpacing: '-0.019em' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem', letterSpacing: '-0.021em' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem', letterSpacing: '-0.022em' }],
        '5xl': ['3rem', { lineHeight: '1', letterSpacing: '-0.025em' }],
        '6xl': ['3.75rem', { lineHeight: '1', letterSpacing: '-0.025em' }],
        '7xl': ['4.5rem', { lineHeight: '1', letterSpacing: '-0.025em' }],
      },

      // Apple-style shadows (subtle depth)
      boxShadow: {
        'apple-sm': '0 1px 3px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06)',
        'apple': '0 4px 6px rgba(0, 0, 0, 0.07), 0 2px 4px rgba(0, 0, 0, 0.05)',
        'apple-md': '0 10px 15px rgba(0, 0, 0, 0.08), 0 4px 6px rgba(0, 0, 0, 0.05)',
        'apple-lg': '0 20px 25px rgba(0, 0, 0, 0.10), 0 10px 10px rgba(0, 0, 0, 0.04)',
        'apple-xl': '0 25px 50px rgba(0, 0, 0, 0.12), 0 12px 18px rgba(0, 0, 0, 0.06)',
      },

      // Frosted glass blur utilities
      backdropBlur: {
        'apple': '20px',
        'apple-sm': '10px',
        'apple-lg': '40px',
      },

      // Smooth animations
      transitionTimingFunction: {
        'apple': 'cubic-bezier(0.25, 0.1, 0.25, 1)',  // Apple's smooth easing
        'apple-spring': 'cubic-bezier(0.5, 1.5, 0.5, 1)',
      },

      transitionDuration: {
        '400': '400ms',
      },

      // Border radius (Apple uses generous rounding)
      borderRadius: {
        'apple': '12px',
        'apple-sm': '8px',
        'apple-lg': '16px',
        'apple-xl': '20px',
        // Clean 3-tier hierarchy aliases
        'sm': '8px',
        'md': '12px',
        'lg': '16px',
      },

      // Spacing scale (8pt grid + Apple generous whitespace)
      spacing: {
        '1': '0.25rem',
        '2': '0.5rem',
        '3': '0.75rem',
        '4': '1rem',
        '5': '1.25rem',
        '6': '1.5rem',
        '8': '2rem',
        '10': '2.5rem',
        '12': '3rem',
        '16': '4rem',
        '18': '4.5rem',
        '22': '5.5rem',
      },
    },
  },
  plugins: [],
}
