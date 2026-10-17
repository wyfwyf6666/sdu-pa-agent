import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full space-y-6 p-6 bg-white rounded-lg shadow-md text-center">
        <h2 className="text-2xl font-bold text-gray-900 mb-2">页面未找到</h2>
        <p className="text-gray-600 mb-4">
          抱歉，您访问的页面不存在。
        </p>
        <Link
          href="/"
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          返回首页
        </Link>
      </div>
    </div>
  )
}
