const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  serverRuntimeConfig: {
    apiTimeout: 600000,
  },

  httpAgentOptions: {
    keepAlive: true,
  },

  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      '@': path.resolve(__dirname, 'src'),
    };
    return config;
  },

  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8890/api/:path*' 
      }
    ]
  },

  experimental: {
    proxyTimeout: 600000, 
  }
};

module.exports = nextConfig; 
