import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from '@/components/Providers'
import CampusBackground from '@/components/layout/CampusBackground'

const inter = Inter({ subsets: ['latin'] })

export const metadata = {
  title: '山大公管智能体',
  description: '山东大学公共管理学科 AI 教学助手',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh">
      <body className={`${inter.className} bg-[#F8F9FA]`}>
        <CampusBackground />
        <div className="relative z-10">
          <Providers>{children}</Providers>
        </div>
      </body>
    </html>
  )
}
