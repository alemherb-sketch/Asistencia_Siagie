import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ['sqlite3', 'pg', 'bcryptjs'],
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
