import type { NextConfig } from 'next';

// The Next.js server talks to FastAPI over the Codespace's loopback network.
// The browser only talks to its own frontend origin.
const backendOrigin = process.env.FINN_BACKEND_ORIGIN || 'http://127.0.0.1:8000';

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: '/health', destination: `${backendOrigin}/health` },
      { source: '/api/:path*', destination: `${backendOrigin}/api/:path*` },
    ];
  },
};

export default nextConfig;
