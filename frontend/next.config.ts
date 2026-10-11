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
  // В production `/api` и `/media` проксирует nginx; в разработке — Next
  // (API_PROXY_URL и MEDIA_PROXY_URL из .env.development).
  async rewrites() {
    const apiProxyUrl = process.env.API_PROXY_URL;
    const mediaProxyUrl = process.env.MEDIA_PROXY_URL;
    return [
      ...(apiProxyUrl ? [{ source: "/api/:path*", destination: `${apiProxyUrl}/api/:path*` }] : []),
      ...(mediaProxyUrl ? [{ source: "/media/:path*", destination: `${mediaProxyUrl}/:path*` }] : []),
    ];
  },
};

export default nextConfig;
