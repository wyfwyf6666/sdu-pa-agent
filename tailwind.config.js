/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        sdu: {
          burgundy: '#7A1014',
          'burgundy-dark': '#5C0C0F',
          'burgundy-light': '#F9ECEC',
          text: '#2C3E50',
          'text-light': '#5A6B7A',
          bg: '#F8F9FA',
          border: '#E0E4E8',
        }
      },
      fontFamily: {
        serif: ['Noto Serif SC', 'Songti SC', 'STSong', 'serif'],
        sans: ['PingFang SC', 'Microsoft YaHei', 'Inter', 'sans-serif'],
      },
      borderRadius: {
        'sdu': '6px',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.5s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)' },
          '100%': { transform: 'translateY(0)' },
        },
      },
    },
  },
  plugins: [],
}
