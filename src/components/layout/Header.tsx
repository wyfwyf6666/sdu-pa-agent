'use client'

import { useState } from 'react'
import Link from 'next/link'
import Image from 'next/image'
import { Bell, User, ChevronDown, LogOut } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '@/contexts/AuthContext'
import { logout } from '@/lib/api'

export default function Header() {
  const { user, isAuthenticated, isAdmin: userIsAdmin } = useAuth()
  const [showUserMenu, setShowUserMenu] = useState(false)

  const handleLogout = async () => {
    await logout()
  }

  return (
    <motion.div
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="bg-white border-b border-[#E0E4E8] px-5 py-2.5 flex items-center justify-between"
    >
      <div className="flex items-center gap-3">
        {/* 院徽 */}
        <Image
          src="/logo.jpg"
          alt="山大公管院徽"
          width={32}
          height={32}
          className="rounded object-contain"
        />
        <div className="flex flex-col">
          <h1 className="text-[15px] font-medium text-[#7A1014] tracking-wide font-['Noto_Serif_SC']">
            山大公管智能体
          </h1>
          <span className="text-[11px] text-[#5A6B7A] -mt-0.5">
            SDU SPA Agent · 公共管理教学助手
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {isAuthenticated && (
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="p-2 rounded-md hover:bg-[#F9ECEC] relative"
          >
            <Bell className="w-4 h-4 text-[#5A6B7A]" />
          </motion.button>
        )}

        {isAuthenticated && user ? (
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="flex items-center gap-2 hover:bg-[#F8F9FA] px-2 py-1.5 rounded-md transition-colors"
            >
              <div className="w-7 h-7 rounded-full bg-[#7A1014] flex items-center justify-center">
                <span className="text-white text-xs font-medium">
                  {user.username.charAt(0)}
                </span>
              </div>
              <span className="text-sm text-[#2C3E50]">{user.username}</span>
              <ChevronDown className={`w-3.5 h-3.5 text-[#5A6B7A] transition-transform ${showUserMenu ? 'rotate-180' : ''}`} />
            </button>

            <AnimatePresence>
              {showUserMenu && (
                <motion.div
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 mt-1 w-44 bg-white rounded-md shadow-[0_4px_16px_rgba(0,0,0,0.06)] border border-[#E0E4E8] py-1.5 z-50"
                  onMouseLeave={() => setShowUserMenu(false)}
                >
                  <div className="px-3 py-1.5 border-b border-[#E0E4E8] mb-1">
                    <p className="text-sm font-medium text-[#2C3E50]">{user.username}</p>
                    <p className="text-[11px] text-[#5A6B7A]">{userIsAdmin ? '管理员' : '用户'}</p>
                  </div>
                  <button onClick={handleLogout}
                    className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-[#7A1014] hover:bg-[#F9ECEC] transition-colors">
                    <LogOut className="w-3.5 h-3.5" />退出登录
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ) : (
          <Link href="/login"
            className="flex items-center gap-1.5 px-4 py-1.5 bg-[#7A1014] text-white rounded-md hover:bg-[#5C0C0F] transition-colors text-sm">
            <User className="w-3.5 h-3.5" />登录
          </Link>
        )}
      </div>
    </motion.div>
  )
}
