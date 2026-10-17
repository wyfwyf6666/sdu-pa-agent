'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { motion } from 'framer-motion'
import {
  MessageSquare,
  FileText,
  BookOpen,
  ScrollText,
  Lightbulb,
  Zap,
  GraduationCap,
  FileSearch,
  Shield,
  Database,
} from 'lucide-react'

const menuItems = [
  { name: '智能AI助手', icon: MessageSquare, href: '/chat' },
  { name: '千章预审稿', icon: FileSearch, href: '/pre-review' },
  { name: '学术诚信检测', icon: Shield, href: '/pre-review/academic-integrity' },
  { name: '本地题录库', icon: Database, href: '/bibliography' },
  { name: '知识库管理', icon: FileText, href: '/documents' },
  { name: '概念解析', icon: Lightbulb, href: '/concepts' },
  { name: '论文阅读', icon: ScrollText, href: '/papers' },
  { name: '案例分析', icon: BookOpen, href: '/cases' },
  { name: '教学工具', icon: Zap, href: '/teaching' },
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <div className="w-60 bg-[#1E1E20] text-white flex flex-col h-full">
      {/* Logo area */}
      <div className="px-5 py-5 border-b border-white/10">
        <div className="flex items-center gap-3 mb-2">
          <GraduationCap className="w-6 h-6 text-white/80" />
          <h2 className="text-sm font-semibold tracking-wide font-['Noto_Serif_SC']">山大公管智能体</h2>
        </div>
        <p className="text-[11px] text-white/40">SDU SPA Agent</p>
      </div>

      {/* Menu */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {menuItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
          const Icon = item.icon

          return (
            <Link key={item.href} href={item.href}>
              <motion.div
                whileHover={{ x: 3 }}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors ${
                  isActive
                    ? 'bg-[#7A1014] text-white font-medium'
                    : 'text-white/60 hover:text-white hover:bg-white/5'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-white/40'}`} />
                <span>{item.name}</span>
              </motion.div>
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-white/10">
        <p className="text-[10px] text-white/25">
          山东大学政治学与公共管理学院<br />
          公共管理+信息双学位实训
        </p>
      </div>
    </div>
  )
}
