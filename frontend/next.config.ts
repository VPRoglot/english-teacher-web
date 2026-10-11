import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // В production `/api` проксирует nginx; в разработке — Next (API_PROXY_URL из .env.development).
  async rewrites() {
    const apiProxyUrl = process.env.API_PROXY_URL;
    return apiProxyUrl ? [{ source: "/api/:path*", destination: `${apiProxyUrl}/api/:path*` }] : [];
  },
};

export default nextConfig;
