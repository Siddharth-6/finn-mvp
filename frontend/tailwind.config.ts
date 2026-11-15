import type { Config } from 'tailwindcss';
const config: Config = { content: ['./app/**/*.{js,ts,jsx,tsx}'], theme: { extend: { colors: { ink: '#0B1729', lime: '#A4D65E' } } }, plugins: [] };
export default config;
