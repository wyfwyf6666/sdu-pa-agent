import { useState } from 'react'
import { X, CheckCircle, XCircle, Sparkles } from 'lucide-react'
import { Toaster, toast } from 'react-hot-toast'
import AIAnalysisModal from './AIAnalysisModal'

interface ApprovalModalProps {
  isOpen: boolean
  onClose: () => void
  approvalId: number
  currentStep: string
  approvalData: any
  onSuccess: () => void
}

export default function ApprovalModal({
  isOpen,
  onClose,
  approvalId,
  currentStep,
  approvalData,
  onSuccess
}: ApprovalModalProps) {
  const [loading, setLoading] = useState(false)
  const [comment, setComment] = useState('')
  const [showAIAnalysis, setShowAIAnalysis] = useState(false)
  
  if (!isOpen) return null

  const handleAction = async (action: 'approve' | 'reject') => {
    if (!comment.trim()) {
      toast.error('请输入审批意见', {
        duration: 3000,
        position: 'top-center',
      })
      return
    }

    setLoading(true)
    try {
      const response = await fetch(`/api/v1/approvals/${approvalId}/process`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          action,
          comment: comment.trim()
        }),
      })

      const data = await response.json()
      
      if (!response.ok) {
        throw new Error(data.detail || '审批处理失败')
      }

      toast.success(action === 'approve' ? '审批已通过' : '审批已拒绝', {
        duration: 2000,
        position: 'top-center',
      })
      onSuccess()
      onClose()
    } catch (error) {
      console.error('审批处理错误:', error)
      toast.error(error instanceof Error ? error.message : '审批处理失败', {
        duration: 3000,
        position: 'top-center',
        style: {
          background: '#fee2e2',
          color: '#dc2626',
          border: '1px solid #fecaca',
          padding: '16px',
          borderRadius: '8px',
          maxWidth: '400px',
          textAlign: 'center',
        },
      })
    } finally {
      setLoading(false)
    }
  }

  const handleApplyAIComment = (aiComment: string) => {
    setComment(aiComment)
  }

  return (
    <>
      <Toaster />
      
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
                审批处理 - {currentStep}
              </h3>
            </div>

            {/* AI分析按钮 */}
            <div className="mb-4">
              <button
                onClick={() => setShowAIAnalysis(true)}
                className="w-full px-4 py-2 bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-md hover:from-purple-700 hover:to-blue-700 disabled:opacity-50 flex items-center justify-center"
              >
                <Sparkles className="h-5 w-5 mr-2" />
                AI智能分析
              </button>
            </div>

            {/* 审批意见 */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                审批意见
              </label>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="请输入您的审批意见..."
                disabled={loading}
              />
            </div>

            {/* 操作按钮 */}
            <div className="flex justify-end space-x-4">
              <button
                onClick={() => handleAction('reject')}
                disabled={loading}
                className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 flex items-center"
              >
                <XCircle className="h-5 w-5 mr-1" />
                拒绝
              </button>
              <button
                onClick={() => handleAction('approve')}
                disabled={loading}
                className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 flex items-center"
              >
                <CheckCircle className="h-5 w-5 mr-1" />
                通过
              </button>
            </div>

            {/* 加载状态 */}
            {loading && (
              <div className="absolute inset-0 bg-white bg-opacity-50 flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* AI分析模态框 */}
      <AIAnalysisModal
        isOpen={showAIAnalysis}
        onClose={() => setShowAIAnalysis(false)}
        approvalData={approvalData}
        onApply={handleApplyAIComment}
      />
    </>
  )
} 