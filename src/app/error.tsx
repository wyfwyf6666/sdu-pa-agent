'use client'

import { useEffect } from 'react'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-6 p-6 bg-white rounded-lg shadow-md">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">出错了</h2>
          <p className="text-gray-600 mb-4">抱歉，加载过程中发生了错误。</p>
          <button
            onClick={reset}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            重试
          </button>
        </div>
      </div>
    </div>
  )
}
