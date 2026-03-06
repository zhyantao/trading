/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  basePath: '/trading-bot',
  assetPrefix: '/trading-bot',
};

export default nextConfig;
