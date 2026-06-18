import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ['sqlite3', 'pg', 'bcryptjs'],
  experimental: {
    proxyTimeout: 1500000, // 25 minutos: la mayor parte es la SUBIDA de los archivos, no el procesamiento
  },
  async rewrites() {
    return [
      {
        source: '/asistencia/:path*',
        destination: 'http://127.0.0.1:8000/:path*',
      },
      {
        source: '/asistencia',
        destination: 'http://127.0.0.1:8000/',
      }
    ]
  }
};

export default nextConfig;

