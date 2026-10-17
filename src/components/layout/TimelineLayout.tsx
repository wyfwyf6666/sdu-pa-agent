'use client'

import { ReactNode } from 'react'
import { Calendar, Filter } from 'lucide-react'

interface TimelineLayoutProps {
  children: ReactNode
  title: string
}

export default function TimelineLayout({
  children,
  title,
}: TimelineLayoutProps) {
  return (
    <div className="h-full flex flex-col">
      {/* 顶部工具栏 */}
      <div className="bg-white border-b border-gray-200 px-4 py-3 sm:px-6 flex items-center justify-between">
        <h1 className="text-lg font-medium text-gray-900">{title}</h1>
        
        <div className="flex items-center space-x-4">
          <button className="inline-flex items-center px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-700 bg-white hover:bg-gray-50">
            <Calendar className="h-4 w-4 mr-2" />
            选择时间范围
          </button>
          
          <button className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-600">
            <Filter className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* 时间线内容区 */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
          {children}
        </div>
      </div>
    </div>
  )
}
