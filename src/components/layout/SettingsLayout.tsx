'use client'

import { ReactNode } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { User, Lock, Bell, Eye } from 'lucide-react'

const settingsNavigation = [
  { name: '个人信息', href: '/settings/profile', icon: User },
  { name: '安全设置', href: '/settings/security', icon: Lock },
  { name: '通知设置', href: '/settings/notifications', icon: Bell },
  { name: '显示设置', href: '/settings/display', icon: Eye },
]

interface SettingsLayoutProps {
  children: ReactNode
}

export default function SettingsLayout({ children }: SettingsLayoutProps) {
  const pathname = usePathname()

  return (
    <div className="h-full flex flex-col lg:flex-row">
      {/* 设置导航 */}
      <div className="w-full lg:w-64 bg-white border-b lg:border-r border-gray-200">
        <nav className="px-4 py-6">
          <h2 className="text-lg font-medium text-gray-900 px-2 mb-4">系统设置</h2>
          <ul className="space-y-1">
            {settingsNavigation.map((item) => {
              const isActive = pathname === item.href
              return (
                <li key={item.name}>
                  <Link
                    href={item.href}
                    className={`
                      flex items-center px-2 py-2 text-sm rounded-lg
                      ${
                        isActive
                          ? 'bg-blue-50 text-blue-600'
                          : 'text-gray-700 hover:bg-gray-50'
                      }
                    `}
                  >
                    <item.icon
                      className={`mr-3 h-5 w-5 ${
                        isActive ? 'text-blue-600' : 'text-gray-400'
                      }`}
                    />
                    {item.name}
                  </Link>
                </li>
              )
            })}
          </ul>
        </nav>
      </div>

      {/* 设置内容 */}
      <div className="flex-1 overflow-auto bg-gray-50">
        <div className="max-w-4xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          {children}
        </div>
      </div>
    </div>
  )
}
