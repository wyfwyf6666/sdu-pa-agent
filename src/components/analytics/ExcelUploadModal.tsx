import { useState, useRef } from 'react'
import { X, Upload, FileSpreadsheet } from 'lucide-react'
import toast from 'react-hot-toast'
import { fetchWithTimeout, TIMEOUT } from '@/lib/fetchWithTimeout'

interface ExcelUploadModalProps {
  isOpen: boolean
  onClose: () => void
  onUploadSuccess: (data: any) => void
}

export default function ExcelUploadModal({
  isOpen,
  onClose,
  onUploadSuccess
}: ExcelUploadModalProps) {
  const [loading, setLoading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true)
    } else if (e.type === "dragleave") {
      setDragActive(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    const files = e.dataTransfer.files
    if (files?.[0]) {
      handleFileUpload(files[0])
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files?.[0]) {
      handleFileUpload(files[0])
    }
  }

  const handleFileUpload = async (file: File) => {
    // 检查文件类型
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
      toast.error('请上传Excel文件(.xlsx, .xls)')
      return
    }

    // 检查文件大小（10MB限制）
    if (file.size > 10 * 1024 * 1024) {
      toast.error('文件大小不能超过10MB')
      return
    }

    setLoading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)

      console.log('开始上传文件:', file.name, '大小:', file.size, '类型:', file.type)

      // 使用长超时（3分钟）用于Excel上传和处理
      const response = await fetchWithTimeout(
        '/api/v1/analytics/upload-excel',
        {
          method: 'POST',
          body: formData,
        },
        TIMEOUT.LONG
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: '上传失败' }))
        throw new Error(errorData.detail || '上传失败')
      }

      const data = await response.json()
      console.log('上传成功:', data)

      if (data.status === 'error') {
        throw new Error(data.message || '处理文件失败')
      }

      toast.success('文件上传成功')
      onUploadSuccess(data)
      onClose()
    } catch (error) {
      console.error('上传错误:', error)
      toast.error(error instanceof Error ? error.message : '文件上传失败')
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4">
        {/* 背景遮罩 */}
        <div
          className="fixed inset-0 bg-black bg-opacity-30 transition-opacity"
          onClick={onClose}
        />

        {/* 模态框 */}
        <div className="relative bg-white rounded-lg max-w-lg w-full p-6">
          {/* 关闭按钮 */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 text-gray-400 hover:text-gray-500"
          >
            <X className="h-5 w-5" />
          </button>

          {/* 标题 */}
          <div className="mb-6">
            <h3 className="text-lg font-medium text-gray-900">
              上传Excel文件
            </h3>
          </div>

          {/* 上传区域 */}
          <div
            className={`relative border-2 border-dashed rounded-lg p-8 text-center ${
              dragActive
                ? 'border-blue-500 bg-blue-50'
                : 'border-gray-300 hover:border-gray-400'
            }`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".xlsx,.xls"
              onChange={handleFileSelect}
              disabled={loading}
            />

            <FileSpreadsheet className="mx-auto h-12 w-12 text-gray-400" />
            
            <div className="mt-4">
              <button
                type="button"
                className="text-sm font-semibold text-blue-600 hover:text-blue-500"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading}
              >
                选择文件
              </button>
              <p className="mt-1 text-sm text-gray-500">
                或将文件拖放到这里
              </p>
            </div>
            
            <p className="mt-2 text-xs text-gray-500">
              支持 .xlsx, .xls 格式
            </p>

            {/* 加载状态 */}
            {loading && (
              <div className="absolute inset-0 bg-white bg-opacity-50 flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
} 