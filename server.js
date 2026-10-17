const http = require('http')
const https = require('https')
const { parse } = require('url')
const next = require('next')
const { createProxyMiddleware } = require('http-proxy-middleware')

const TEN_MINUTES_MS = 10 * 60 * 1000

const keepAliveAgentOptions = {
  keepAlive: true,
  keepAliveMsecs: TEN_MINUTES_MS,
}

http.globalAgent = new http.Agent(keepAliveAgentOptions)
https.globalAgent = new https.Agent(keepAliveAgentOptions)

const dev = process.env.NODE_ENV !== 'production'
const hostname = 'localhost'
const port = 3000

const app = next({ dev, hostname, port })
const handle = app.getRequestHandler()

app.prepare().then(() => {
  http.createServer(async (req, res) => {
    try {
      const parsedUrl = parse(req.url, true)
      const { pathname } = parsedUrl

      // 代理所有 /api 请求到后端，并设置长超时
      if (pathname.startsWith('/api/')) {
        const apiProxy = createProxyMiddleware({
          target: 'http://localhost:8890',
          changeOrigin: true,
          timeout: TEN_MINUTES_MS, 
          proxyTimeout: TEN_MINUTES_MS, 
          onProxyReq: (proxyReq, req, res) => {
            if (req.socket) {
              req.socket.setTimeout(TEN_MINUTES_MS) 
            }
          },
          onProxyRes: (proxyRes, req, res) => {
            if (res.socket) {
              res.socket.setTimeout(TEN_MINUTES_MS) 
            }
          },
          onError: (err, req, res) => {
            console.error('代理错误:', err)
            res.writeHead(500, {
              'Content-Type': 'application/json',
            })
            res.end(JSON.stringify({
              error: '后端服务连接失败',
              message: err.message
            }))
          }
        })

        return apiProxy(req, res)
      }

      // 其他请求交给 Next.js 处理
      await handle(req, res, parsedUrl)
    } catch (err) {
      console.error('服务器错误:', err)
      res.statusCode = 500
      res.end('内部服务器错误')
    }
  })
    .once('error', (err) => {
      console.error(err)
      process.exit(1)
    })
    .listen(port, () => {
      console.log(`> Ready on http://${hostname}:${port}`)
    })
})
