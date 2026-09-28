/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // --- Footy-NAC identity system (Part 2B) ---
        paper: '#F6F1E7',
        ink: '#16130F',
        sherrin: {
          DEFAULT: '#C8102E',
          50: '#FBE7EA',
          100: '#F6C7CE',
          200: '#EB98A5',
          300: '#DF6579',
          400: '#D63B54',
          500: '#C8102E',
          600: '#A50D26',
          700: '#800A1E',
          800: '#5B0715',
        },
        nightgame: {
          DEFAULT: '#F2B705',
          100: '#FBEAB0',
          300: '#F6D24E',
          500: '#F2B705',
          600: '#C79600',
        },
        oval: '#2F6B3A', // ground illustrations only, never UI chrome
        // Warm neutral scale on paper. warm-600 is the AA floor for secondary
        // text on paper (as dark as afl-warm's old #706354, never lighter).
        warm: {
          50: '#F6F1E7',
          100: '#ECE2D0',
          200: '#DCCBAE',
          300: '#C3AC87',
          400: '#A38A67',
          500: '#83694E',
          600: '#6B5A47',
          700: '#544539',
          800: '#3A2F27',
          900: '#16130F',
        },
        // Club palette, driven by CSS variables set by ClubContext.
        // Defaults to Sherrin red / ink until a club is chosen.
        club: {
          primary: 'var(--club-primary, #C8102E)',
          secondary: 'var(--club-secondary, #16130F)',
        },
      },

      fontFamily: {
        // Body copy
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'system-ui', 'sans-serif'],
        // Headlines, scoreboard numerals, pipeline labels
        display: ['Anton', 'Impact', 'sans-serif'],
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
        '8xl': ['6rem', { lineHeight: '1', letterSpacing: '-0.02em' }],
      },

      boxShadow: {
        // New card/button shadow system
        'card-sm': '0 1px 3px rgba(22, 19, 15, 0.06), 0 1px 2px rgba(22, 19, 15, 0.08)',
        'card': '0 4px 10px rgba(22, 19, 15, 0.08), 0 2px 4px rgba(22, 19, 15, 0.06)',
        'card-md': '0 10px 20px rgba(22, 19, 15, 0.10), 0 4px 6px rgba(22, 19, 15, 0.06)',
        'card-lg': '0 20px 30px rgba(22, 19, 15, 0.12), 0 10px 10px rgba(22, 19, 15, 0.05)',
        'card-xl': '0 25px 50px rgba(22, 19, 15, 0.16), 0 12px 18px rgba(22, 19, 15, 0.07)',
      },

      backdropBlur: {
        brand: '20px',
      },

      transitionTimingFunction: {
        brand: 'cubic-bezier(0.25, 0.1, 0.25, 1)',
      },

      transitionDuration: {
        '400': '400ms',
      },

      borderRadius: {
        // One radius system: sm/md/lg/xl, used by .btn-*, .card, .input-field
        'sm': '8px',
        'md': '12px',
        'lg': '16px',
        'xl': '20px',
      },

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

      gridTemplateColumns: {
        '18': 'repeat(18, minmax(0, 1fr))',
      },

      keyframes: {
        sherrinSpin: {
          '0%': { transform: 'translateX(-40px) rotate(-90deg)', opacity: '0' },
          '100%': { transform: 'translateX(0) rotate(0deg)', opacity: '1' },
        },
        flipDown: {
          '0%': { transform: 'rotateX(0deg)' },
          '50%': { transform: 'rotateX(-90deg)' },
          '100%': { transform: 'rotateX(0deg)' },
        },
      },
      animation: {
        'sherrin-spin-in': 'sherrinSpin 0.7s cubic-bezier(0.25, 0.1, 0.25, 1)',
        'flip-down': 'flipDown 0.5s ease-in-out',
      },
    },
  },
  plugins: [],
}
