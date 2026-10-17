'use client'

import { useState } from 'react'
import { Menu, X } from 'lucide-react'
import Sidebar from './Sidebar'
import Header from './Header'

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(true)

  return (
    <div className="min-h-screen flex">
      {/* Mobile toggle */}
      <button
        className="lg:hidden fixed left-4 top-4 z-50 p-2 rounded-md bg-white shadow-sm border border-[#E0E4E8]"
        onClick={() => setSidebarOpen(!sidebarOpen)}
      >
        {sidebarOpen ? <X className="h-5 w-5 text-[#2C3E50]" /> : <Menu className="h-5 w-5 text-[#2C3E50]" />}
      </button>

      {/* Sidebar */}
      <div className={`
        fixed lg:static inset-y-0 left-0 z-40
        transform transition-transform duration-300 ease-in-out
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        lg:translate-x-0 lg:w-60
      `}>
        <Sidebar />
      </div>

      {/* Main area */}
      <div className="flex-1 flex flex-col min-h-screen">
        <Header />
        <main className="flex-1 p-5 lg:p-8">
          {children}
        </main>
      </div>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}
    </div>
  )
}
