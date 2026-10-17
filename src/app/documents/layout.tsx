'use client'

import { usePathname, useRouter } from 'next/navigation'
import MainLayout from '@/components/layout/MainLayout'
import { FileText, Share2, Users } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'

export default function DocumentsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { isAdmin: userIsAdmin, user } = useAuth()

  const isPublic = pathname?.includes('/documents/public')
  const isPrivate = pathname?.includes('/documents/private')
  const isGraph = pathname?.includes('/documents/graph')

  const tabs = [
    {
      label: '公共文档库',
      icon: FileText,
      path: '/documents/public',
      active: isPublic,
    },
    ...(user
      ? [
          {
            label: '私人文档库',
            icon: Users,
            path: '/documents/private',
            active: isPrivate,
          },
        ]
      : []),
    {
      label: '知识图谱',
      icon: Share2,
      path: '/documents/graph',
      active: isGraph,
    },
  ]

  return (
    <MainLayout>
      <div className="min-h-screen bg-slate-50">
        <div className="mx-auto max-w-7xl px-4 py-8">
          {/* Tab Navigation */}
          <div className="mb-6 flex items-center gap-4 rounded-2xl border border-gray-100 bg-white p-2 shadow-sm">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.path}
                  onClick={() => router.push(tab.path)}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-6 py-3 text-sm font-medium transition-all ${
                    tab.active
                      ? 'bg-blue-500 text-white shadow-sm'
                      : 'text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  {tab.label}
                </button>
              )
            })}
          </div>

          {/* Page Content */}
          {children}
        </div>
      </div>
    </MainLayout>
  )
}
