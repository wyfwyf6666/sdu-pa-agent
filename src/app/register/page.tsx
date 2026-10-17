'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { toast, Toaster } from 'react-hot-toast'
import { useAuth } from '@/contexts/AuthContext'

export default function RegisterPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const router = useRouter()
  const { refreshAuth } = useAuth()

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()

    // 验证
    if (!username.trim()) {
      toast.error('请输入用户名')
      return
    }
    if (username.length < 3) {
      toast.error('用户名至少3个字符')
      return
    }
    if (!password) {
      toast.error('请输入密码')
      return
    }
    if (password.length < 6) {
      toast.error('密码至少6个字符')
      return
    }
    if (password !== confirmPassword) {
      toast.error('两次输入的密码不一致')
      return
    }

    setLoading(true)
    try {
      const res = await fetch('/api/v1/auth/register', {
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
        data = { detail: text || '注册失败' }
      }

      if (!res.ok) {
        throw new Error(data.detail || data.message || '注册失败')
      }

      // 保存token和用户信息
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('user', JSON.stringify(data.user))

      // 立即更新AuthContext
      refreshAuth()

      toast.success('注册成功！')
      setTimeout(() => {
        router.push('/')
      }, 1000)
    } catch (err: any) {
      console.error('注册错误:', err)
      toast.error(err.message || '注册失败')
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
            <h1 className="text-3xl font-bold text-gray-900 mb-2">注册账号</h1>
            <p className="text-gray-600">创建新账号以使用系统功能</p>
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
                placeholder="请输入用户名（至少3个字符）"
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
                placeholder="请输入密码（至少6个字符）"
                disabled={loading}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                确认密码
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="请再次输入密码"
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-gradient-to-r from-blue-500 to-blue-600 text-white py-3 rounded-lg font-medium hover:from-blue-600 hover:to-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {loading ? '注册中...' : '注册'}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-gray-600">
            已有账号？
            <Link
              href="/login"
              className="ml-2 text-blue-600 hover:text-blue-700 font-medium"
            >
              立即登录
            </Link>
          </div>
        </div>

        <div className="mt-4 text-center text-xs text-gray-500">
          <p>注册后您将成为普通用户</p>
          <p>如需管理员权限，请联系系统管理员</p>
        </div>
      </div>
    </div>
  )
}
