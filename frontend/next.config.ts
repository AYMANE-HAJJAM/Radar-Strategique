import type { NextConfig } from "next";

function proxyTarget() {
  const configured = process.env.API_PROXY_TARGET?.replace(/\/$/, "");
  if (configured) return configured;
  // Vercel sets VERCEL=1. The browser calls this app's /api, and Next forwards it.
  if (process.env.VERCEL) return "https://radar-strategique.onrender.com";
  return "http://127.0.0.1:5000";
}

const nextConfig: NextConfig = {
  async rewrites() {
    const target = proxyTarget();
    return [{source: "/api/:path*", destination: `${target}/api/:path*`}];
  },
};

export default nextConfig;
