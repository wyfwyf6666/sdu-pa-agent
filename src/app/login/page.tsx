'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { toast, Toaster } from 'react-hot-toast'
import { useAuth } from '@/contexts/AuthContext'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const router = useRouter()
  const { refreshAuth, isAuthenticated, user } = useAuth()

  // 如果已登录，重定向到首页
  useEffect(() => {
    if (isAuthenticated && user) {
      router.push('/')
    }
  }, [isAuthenticated, user, router])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()

    // 验证
    if (!username.trim()) {
      toast.error('请输入用户名')
      return
    }
    if (!password) {
      toast.error('请输入密码')
      return
    }

    setLoading(true)
    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      })

      // 先检查响应类型
      const contentType = res.headers.get('content-type')
      let data: any

      if (contentType && contentType.includes('application/json')) {
        data = await res.json()
      } else {
        // 如果不是 JSON，读取为文本
        const text = await res.text()
        data = { detail: text || '登录失败' }
      }

      if (!res.ok) {
        throw new Error(data.detail || data.message || '登录失败')
      }

      // 保存token和用户信息
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('user', JSON.stringify(data.user))

      // 立即更新AuthContext
      refreshAuth()

      toast.success('登录成功！')
      setTimeout(() => {
        router.push('/')
      }, 1000)
    } catch (err: any) {
      console.error('登录错误:', err)
      toast.error(err.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
      <Toaster position="top-center" />

      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">用户登录</h1>
            <p className="text-gray-600">登录以使用系统功能</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                用户名
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="请输入用户名"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                密码
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="请输入密码"
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-blue-500 to-blue-600 text-white py-3 rounded-lg font-medium hover:from-blue-600 hover:to-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {loading ? '登录中...' : '登录'}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-gray-600">
            还没有账号？
            <Link
              href="/register"
              className="ml-2 text-blue-600 hover:text-blue-700 font-medium"
            >
              立即注册
            </Link>
          </div>
        </div>

        <div className="mt-4 text-center text-xs text-gray-500">
          <p>默认管理员账号：admin / admin123</p>
          <p>默认用户账号：kevin / 123456</p>
        </div>
      </div>
    </div>
  )
}
