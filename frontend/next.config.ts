import type { NextConfig } from "next";

// Where the FastAPI backend lives, from the Next server's point of view.
// Default is foghorn's backend port on loopback (127.0.0.1:8100); the fleet
// deployment and the e2e suite override it via env. Note: 8000 is ficycle's
// port on this machine, so the default must never be 8000.
const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8100";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image (deploy/); local
  // `npm run dev` / `npm run start` behavior is unchanged.
  output: "standalone",
  // Browser-side API calls use relative /api/* URLs so they reach whatever
  // host served the page (the laptop directly, or the laptop over Tailscale
  // from a phone). This rewrite proxies those to the backend server-side, so
  // the backend can keep binding 127.0.0.1 only and remote devices still work.
  // The frontend has no route handlers under /api, so there's no collision.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
