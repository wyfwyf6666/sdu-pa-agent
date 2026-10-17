'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function DocumentsRedirect() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/documents/public')
  }, [router])

  return (
    <div className="flex h-screen items-center justify-center">
      <div className="text-gray-600">跳转中...</div>
    </div>
  )
}
