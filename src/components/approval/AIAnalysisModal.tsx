import { useState, useEffect } from 'react'
import { X, AlertTriangle, CheckCircle, FileText, Copy } from 'lucide-react'
import toast from 'react-hot-toast'
import { fetchWithTimeout, TIMEOUT } from '@/lib/fetchWithTimeout'

interface AIAnalysisModalProps {
  isOpen: boolean
  onClose: () => void
  approvalData: any
  onApply: (comment: string) => void
}

interface AnalysisResult {
  compliance_check: string
  process_check: string
  risk_assessment: string
  suggestion: string
  key_points: string[]
}

export default function AIAnalysisModal({
  isOpen,
  onClose,
  approvalData,
  onApply
}: AIAnalysisModalProps) {
  const [loading, setLoading] = useState(true)
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [similarCases, setSimilarCases] = useState<any[]>([])
  const [suggestedComment, setSuggestedComment] = useState('')

  useEffect(() => {
    if (isOpen && approvalData) {
      fetchAnalysis()
    }
  }, [isOpen, approvalData])

  const fetchAnalysis = async () => {
    setLoading(true)
    try {
      // 获取AI分析结果 - 使用超长超时（5分钟）
      const analysisResponse = await fetchWithTimeout(
        '/api/v1/approvals/ai/analyze',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(approvalData),
        },
        TIMEOUT.VERY_LONG
      )
      const analysisData = await analysisResponse.json()
      setAnalysis(analysisData)

      // 获取相似案例 - 使用长超时（3分钟）
      const similarResponse = await fetchWithTimeout(
        '/api/v1/approvals/ai/similar-cases',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(approvalData),
        },
        TIMEOUT.LONG
      )
      const similarData = await similarResponse.json()
      setSimilarCases(similarData)

      // 获取建议意见 - 使用超长超时（5分钟）
      const commentResponse = await fetchWithTimeout(
        '/api/v1/approvals/ai/suggest-comment',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            approval: approvalData,
            analysis: analysisData,
          }),
        },
        TIMEOUT.VERY_LONG
      )
      const commentData = await commentResponse.json()
      setSuggestedComment(commentData.comment)

    } catch (error) {
      toast.error('获取AI分析结果失败: ' + (error as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const handleApplyComment = () => {
    onApply(suggestedComment)
    onClose()
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
        <div className="relative bg-white rounded-lg max-w-4xl w-full p-6">
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
              AI审批分析报告
            </h3>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
            </div>
          ) : (
            <div className="space-y-6">
              {/* 分析结果 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-blue-50 p-4 rounded-lg">
                  <h4 className="font-medium text-blue-900 mb-2">合规性检查</h4>
                  <p className="text-blue-800">{analysis?.compliance_check}</p>
                </div>
                <div className="bg-green-50 p-4 rounded-lg">
                  <h4 className="font-medium text-green-900 mb-2">流程检查</h4>
                  <p className="text-green-800">{analysis?.process_check}</p>
                </div>
                <div className="bg-yellow-50 p-4 rounded-lg">
                  <h4 className="font-medium text-yellow-900 mb-2">风险评估</h4>
                  <p className="text-yellow-800">{analysis?.risk_assessment}</p>
                </div>
                <div className="bg-purple-50 p-4 rounded-lg">
                  <h4 className="font-medium text-purple-900 mb-2">建议意见</h4>
                  <p className="text-purple-800">{analysis?.suggestion}</p>
                </div>
              </div>

              {/* 关键要点 */}
              <div className="bg-gray-50 p-4 rounded-lg">
                <h4 className="font-medium text-gray-900 mb-2">关键要点</h4>
                <ul className="list-disc list-inside space-y-1">
                  {analysis?.key_points.map((point, index) => (
                    <li key={index} className="text-gray-700">
                      {point}
                    </li>
                  ))}
                </ul>
              </div>

              {/* 相似案例 */}
              {similarCases.length > 0 && (
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h4 className="font-medium text-gray-900 mb-2">相似案例参考</h4>
                  <div className="space-y-2">
                    {similarCases.map((case_, index) => (
                      <div
                        key={index}
                        className="bg-white p-3 rounded border border-gray-200"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{case_.title}</span>
                          <span className="text-sm text-gray-500">
                            相似度: {case_.similarity.toFixed(1)}%
                          </span>
                        </div>
                        <p className="text-sm text-gray-600 mt-1">
                          {case_.content}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI建议的审批意见 */}
              <div className="bg-gray-50 p-4 rounded-lg">
                <h4 className="font-medium text-gray-900 mb-2">
                  AI建议的审批意见
                </h4>
                <div className="bg-white p-3 rounded border border-gray-200">
                  <p className="text-gray-700 whitespace-pre-line">
                    {suggestedComment}
                  </p>
                </div>
                <div className="mt-4 flex justify-end space-x-4">
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(suggestedComment)
                      toast.success('已复制到剪贴板')
                    }}
                    className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700 disabled:opacity-50 flex items-center"
                  >
                    <Copy className="h-4 w-4 mr-1" />
                    复制
                  </button>
                  <button
                    onClick={handleApplyComment}
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 flex items-center"
                  >
                    <CheckCircle className="h-4 w-4 mr-1" />
                    应用
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
} 