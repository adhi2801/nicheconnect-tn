import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The browser tests build into their own folder, so they never clash with a running dev server.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // The stylesheet goes into the HTML itself: on a slow phone link that saves a round trip before the first paint
  // (measured on the landing page, frontend.md section 4). Every page's CSS is small (about 11 KB compressed).
  experimental: { inlineCss: true },
};

export default nextConfig;
