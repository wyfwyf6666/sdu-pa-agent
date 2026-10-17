/**
 * API客户端工具
 * 自动添加Authorization header到所有请求
 */

interface FetchOptions extends RequestInit {
  headers?: Record<string, string>
}

/**
 * 增强的fetch函数，自动添加JWT token
 */
export async function apiFetch(url: string, options: FetchOptions = {}): Promise<Response> {
  // 只在浏览器环境中访问 localStorage
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  // 如果有token，添加Authorization header
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  // 处理401未授权错误（只在浏览器环境）
  if (typeof window !== 'undefined' && response.status === 401) {
    // 清除本地存储
    localStorage.removeItem('token')
    localStorage.removeItem('user')

    // 如果不是登录或注册页面，重定向到登录
    if (!window.location.pathname.includes('/login') &&
        !window.location.pathname.includes('/register')) {
      window.location.href = '/login'
    }
  }

  // 处理403权限不足错误
  if (response.status === 403) {
    console.error('权限不足')
    // 可以在这里显示toast通知，但需要在组件中处理
  }

  return response
}

/**
 * GET请求
 */
export async function apiGet<T = any>(url: string): Promise<T> {
  const response = await apiFetch(url, { method: 'GET' })
  return response.json()
}

/**
 * POST请求
 */
export async function apiPost<T = any>(url: string, data?: any): Promise<T> {
  const response = await apiFetch(url, {
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  })
  return response.json()
}

/**
 * PUT请求
 */
export async function apiPut<T = any>(url: string, data?: any): Promise<T> {
  const response = await apiFetch(url, {
    method: 'PUT',
    body: data ? JSON.stringify(data) : undefined,
  })
  return response.json()
}

/**
 * DELETE请求
 */
export async function apiDelete<T = any>(url: string): Promise<T> {
  const response = await apiFetch(url, { method: 'DELETE' })
  return response.json()
}

/**
 * 上传文件（multipart/form-data）
 */
export async function apiUpload<T = any>(url: string, formData: FormData): Promise<T> {
  // 只在浏览器环境中访问 localStorage
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null

  const headers: Record<string, string> = {}

  // 如果有token，添加Authorization header
  // 注意：不设置Content-Type，让浏览器自动设置multipart boundary
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(url, {
    method: 'POST',
    headers,
    body: formData,
  })

  // 处理401和403（只在浏览器环境）
  if (typeof window !== 'undefined' && response.status === 401) {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    if (!window.location.pathname.includes('/login') &&
        !window.location.pathname.includes('/register')) {
      window.location.href = '/login'
    }
  }

  return response.json()
}

/**
 * 获取当前用户信息
 */
export function getCurrentUser(): any | null {
  // 检查是否在浏览器环境
  if (typeof window === 'undefined') return null

  const userStr = localStorage.getItem('user')
  if (!userStr) return null

  try {
    return JSON.parse(userStr)
  } catch {
    return null
  }
}

/**
 * 检查用户是否已登录
 */
export function isAuthenticated(): boolean {
  // 检查是否在浏览器环境
  if (typeof window === 'undefined') return false

  return !!localStorage.getItem('token')
}

/**
 * 检查用户是否为管理员
 */
export function isAdmin(): boolean {
  const user = getCurrentUser()
  return user?.role === 'admin'
}

/**
 * 登出
 */
export async function logout(): Promise<void> {
  // 只在浏览器环境中执行
  if (typeof window === 'undefined') return

  try {
    // 调用后端登出接口
    await apiFetch('/api/v1/auth/logout', { method: 'POST' })
  } catch (error) {
    console.error('登出错误:', error)
  } finally {
    // 无论是否成功，都清除本地存储
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    window.location.href = '/login'
  }
}
