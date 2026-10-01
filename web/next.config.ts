import type { NextConfig } from "next";

// The browser only ever talks to this app; /api/* is forwarded to the POS API. Same origin
// means the login session can live in an httpOnly cookie, out of reach of page scripts.
const POS_API_URL = process.env.POS_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${POS_API_URL}/api/:path*` }];
  },
};

export default nextConfig;
