/** @type {import('tailwindcss').Config} */  
export default {  
  content: [  
    "./index.html",  
    "./src/**/*.{js,ts,jsx,tsx}",  
  ],  
  theme: {  
    extend: {  
      colors: {  
        bg: {  
          primary: '#0a0a0a',  
          secondary: '#1a1a1a',  
          tertiary: '#2a2a2a',  
        },  
        text: {  
          primary: '#ffffff',  
          secondary: '#cccccc',  
        },  
        accent: {  
          green: '#00d4aa',  
          red: '#ff6b6b',  
          yellow: '#ffd93d',  
        },  
        border: '#333333',  
      },  
    },  
  },  
  plugins: [],  
} 
