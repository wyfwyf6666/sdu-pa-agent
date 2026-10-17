import { useState, useEffect, useCallback } from 'react'
import { X, Download, Copy, BarChart2, Clock, AlertTriangle, Lightbulb, TrendingUp, Shield, Settings, Activity } from 'lucide-react'
import toast from 'react-hot-toast'
import ReactMarkdown from 'react-markdown'
import { fetchWithTimeout, TIMEOUT } from '@/lib/fetchWithTimeout'

interface AnalysisReportModalProps {
  isOpen: boolean
  onClose: () => void
  department: string
}

export default function AnalysisReportModal({
  isOpen,
  onClose,
  department
}: AnalysisReportModalProps) {
  const [loading, setLoading] = useState(true)
  const [report, setReport] = useState('')

  // 获取分析报告
  const fetchReport = useCallback(async () => {
    setLoading(true)
    try {
      // 使用超长超时（5分钟）用于AI生成分析报告
      const response = await fetchWithTimeout(
        `/api/v1/analytics/department/${department}/report`,
        {},
        TIMEOUT.VERY_LONG
      )
      if (!response.ok) {
        throw new Error('获取分析报告失败')
      }
      const data = await response.json()
      setReport(data.report)
    } catch (error) {
      toast.error('获取分析报告失败: ' + (error as Error).message)
    } finally {
      setLoading(false)
    }
  }, [department])

  // 复制报告内容
  const handleCopy = () => {
    navigator.clipboard.writeText(report)
    toast.success('已复制到剪贴板')
  }

  // 下载报告
  const handleDownload = () => {
    const blob = new Blob([report], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${department}分析报告.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success('报告已下载')
  }

  // 当模态框打开时获取报告
  useEffect(() => {
    if (isOpen) {
      fetchReport()
    }
  }, [isOpen, department, fetchReport])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black bg-opacity-50">
      <div className="flex items-center justify-center min-h-screen px-4 py-8">
        {/* 模态框 */}
        <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-5xl">
          {/* 头部 */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div className="flex items-center space-x-3">
              <BarChart2 className="h-6 w-6 text-blue-600" />
              <h3 className="text-xl font-semibold text-gray-900">
                {department} - AI分析报告
              </h3>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-500 transition-colors"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          {/* 报告内容 */}
          {loading ? (
            <div className="flex items-center justify-center p-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
            </div>
          ) : (
            <div className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                {/* 总体评估卡片 */}
                <div className="bg-gradient-to-br from-blue-50 to-white p-6 rounded-xl shadow-sm border border-blue-100">
                  <div className="flex items-center space-x-2 mb-4">
                    <BarChart2 className="h-5 w-5 text-blue-600" />
                    <h4 className="text-lg font-medium text-blue-900">总体评估</h4>
                  </div>
                  <div className="text-gray-700">
                    {report.split('## 总体评估')[1]?.split('##')[0]?.trim()}
                  </div>
                </div>

                {/* 效率分析卡片 */}
                <div className="bg-gradient-to-br from-green-50 to-white p-6 rounded-xl shadow-sm border border-green-100">
                  <div className="flex items-center space-x-2 mb-4">
                    <Clock className="h-5 w-5 text-green-600" />
                    <h4 className="text-lg font-medium text-green-900">效率分析</h4>
                  </div>
                  <div className="text-gray-700">
                    {report.split('## 效率分析')[1]?.split('##')[0]?.trim()}
                  </div>
                </div>

                {/* 问题发现卡片 */}
                <div className="bg-gradient-to-br from-yellow-50 to-white p-6 rounded-xl shadow-sm border border-yellow-100">
                  <div className="flex items-center space-x-2 mb-4">
                    <AlertTriangle className="h-5 w-5 text-yellow-600" />
                    <h4 className="text-lg font-medium text-yellow-900">问题发现</h4>
                  </div>
                  <div className="text-gray-700">
                    {report.split('## 问题发现')[1]?.split('##')[0]?.trim()}
                  </div>
                </div>

                {/* 改进建议卡片 */}
                <div className="bg-gradient-to-br from-purple-50 to-white p-6 rounded-xl shadow-sm border border-purple-100">
                  <div className="flex items-center space-x-2 mb-4">
                    <Lightbulb className="h-5 w-5 text-purple-600" />
                    <h4 className="text-lg font-medium text-purple-900">改进建议</h4>
                  </div>
                  <div className="text-gray-700">
                    {report.split('## 改进建议')[1]?.split('##')[0]?.trim()}
                  </div>
                </div>
              </div>

              {/* 详细分析部分 */}
              <div className="space-y-6">
                {/* 未来预测 */}
                <div className="bg-gradient-to-r from-indigo-50 to-white p-6 rounded-xl shadow-sm border border-indigo-100">
                  <div className="flex items-center space-x-2 mb-4">
                    <TrendingUp className="h-5 w-5 text-indigo-600" />
                    <h4 className="text-lg font-medium text-indigo-900">未来预测</h4>
                  </div>
                  <div className="text-gray-700">
                    {report.split('## 未来预测')[1]?.split('##')[0]?.trim()}
                  </div>
                </div>

                {/* 风险预警 */}
                <div className="bg-gradient-to-r from-red-50 to-white p-6 rounded-xl shadow-sm border border-red-100">
                  <div className="flex items-center space-x-2 mb-4">
                    <Shield className="h-5 w-5 text-red-600" />
                    <h4 className="text-lg font-medium text-red-900">风险预警</h4>
                  </div>
                  <div className="text-gray-700 space-y-4">
                    {report.split('## 风险预警')[1]?.split('##')[0]?.trim().split('\n').map((line, index) => (
                      <div key={index} className="pl-4">{line}</div>
                    ))}
                  </div>
                </div>

                {/* 效率优化建议 */}
                <div className="bg-gradient-to-r from-cyan-50 to-white p-6 rounded-xl shadow-sm border border-cyan-100">
                  <div className="flex items-center space-x-2 mb-4">
                    <Settings className="h-5 w-5 text-cyan-600" />
                    <h4 className="text-lg font-medium text-cyan-900">效率优化建议</h4>
                  </div>
                  <div className="text-gray-700 space-y-4">
                    {report.split('## 效率优化建议')[1]?.split('##')[0]?.trim().split('\n').map((line, index) => (
                      <div key={index} className="pl-4">{line}</div>
                    ))}
                  </div>
                </div>

                {/* 关键指标异常分析 */}
                <div className="bg-gradient-to-r from-orange-50 to-white p-6 rounded-xl shadow-sm border border-orange-100">
                  <div className="flex items-center space-x-2 mb-4">
                    <Activity className="h-5 w-5 text-orange-600" />
                    <h4 className="text-lg font-medium text-orange-900">关键指标异常分析</h4>
                  </div>
                  <div className="text-gray-700 space-y-4">
                    {report.split('## 关键指标异常分析')[1]?.split('---')[0]?.trim().split('\n').map((line, index) => (
                      <div key={index} className="pl-4">{line}</div>
                    ))}
                  </div>
                </div>
              </div>

              {/* 底部信息 */}
              <div className="mt-6 pt-6 border-t border-gray-200">
                <div className="flex justify-between items-center text-sm text-gray-500">
                  <div>
                    {report.split('报告生成时间：')[1]?.split('\n')[0]}
                  </div>
                  <div className="flex space-x-4">
                    <button
                      onClick={handleCopy}
                      className="flex items-center space-x-1 px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
                    >
                      <Copy className="h-4 w-4" />
                      <span>复制</span>
                    </button>
                    <button
                      onClick={handleDownload}
                      className="flex items-center space-x-1 px-4 py-2 bg-blue-600 text-white hover:bg-blue-700 rounded-lg transition-colors"
                    >
                      <Download className="h-4 w-4" />
                      <span>下载</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
} 