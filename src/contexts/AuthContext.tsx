'use client'

import React, { createContext, useContext, useState, useEffect } from 'react'
import { getCurrentUser, isAuthenticated, isAdmin } from '@/lib/api'

interface User {
  user_id: string
  username: string
  role: 'admin' | 'user'
  created_time: string
  last_login: string | null
  is_active: boolean
}

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isAdmin: boolean
  loading: boolean
  setUser: (user: User | null) => void
  refreshAuth: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [authenticated, setAuthenticated] = useState(false)
  const [adminStatus, setAdminStatus] = useState(false)

  const refreshAuth = () => {
    const currentUser = getCurrentUser()
    const authenticated = isAuthenticated()
    const adminStatus = isAdmin()

    setUser(currentUser)
    setAuthenticated(authenticated)
    setAdminStatus(adminStatus)
    setLoading(false)
  }

  useEffect(() => {
    // 初始化时加载用户信息
    refreshAuth()

    // 监听storage事件（跨标签页同步）
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'user' || e.key === 'token') {
        refreshAuth()
      }
    }

    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  const value: AuthContextType = {
    user,
    isAuthenticated: authenticated,
    isAdmin: adminStatus,
    loading,
    setUser,
    refreshAuth,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
