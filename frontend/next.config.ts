import type { NextConfig } from "next";

// The browser only ever talks to this app; /api/* is forwarded to the ERP API (FastAPI). Same origin
// means the login session can live in an httpOnly cookie, out of reach of page scripts.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
