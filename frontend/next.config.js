/** @type {import('next').NextConfig} */
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";

module.exports = {
  reactStrictMode: true,
  poweredByHeader: false,
  // O navegador fala só com o Next; o Next repassa /api/* para o backend (sem CORS, áudio na mesma origem).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
  async redirects() {
    return [{ source: "/calls", destination: "/ligacoes", permanent: true }];
  },
};
