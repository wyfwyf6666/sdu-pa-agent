'use client'

import { ReactNode } from 'react'
import { Filter, Grid, List } from 'lucide-react'

interface ContentLayoutProps {
  title?: string;
  children: ReactNode
  showViewToggle?: boolean
  showFilter?: boolean
}

export default function ContentLayout({
  children,
  title,
  showViewToggle = false,
  showFilter = false,
}: ContentLayoutProps) {
  return (
    <div className="h-full flex flex-col">
      {/* 主内容区 */}
      <div className="flex-1 overflow-auto p-4 sm:p-6 bg-gray-50">
        {children}
      </div>
    </div>
  )
}
