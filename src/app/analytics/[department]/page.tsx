'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import MainLayout from '@/components/layout/MainLayout'
import { FileSpreadsheet, BarChart2, PieChart, TrendingUp, Sparkles, RefreshCw } from 'lucide-react'
import ExcelUploadModal from '@/components/analytics/ExcelUploadModal'
import AnalysisReportModal from '@/components/analytics/AnalysisReportModal'
import dynamic from 'next/dynamic'
import { Toaster } from 'react-hot-toast'

// 动态导入图表组件
const LineChart = dynamic(() => import('@/components/charts/LineChart'), { ssr: false })
const PieChartComponent = dynamic(() => import('@/components/charts/PieChart'), { ssr: false })
const BarChartComponent = dynamic(() => import('@/components/charts/BarChart'), { ssr: false })

// 部门数据映射
const departmentMap: Record<string, string> = {
  '1': '市民服务中心',
  '2': '税务管理部门',
  '3': '社会保障部门',
  '4': '公共事业部门',
}

interface DepartmentPageProps {
  params: {
    department: string
  }
}

interface ChartData {
  labels: string[]
  datasets: {
    label: string
    data: number[]
    borderColor: string
    backgroundColor: string
  }[]
}

interface PieChartData {
  labels: string[]
  datasets: {
    data: number[]
    backgroundColor: string[]
  }[]
}

export default function DepartmentPage({ params: { department } }: DepartmentPageProps) {
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<any>(null)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [showReportModal, setShowReportModal] = useState(false)

  // 获取部门名称
  const departmentName = departmentMap[department] || '未知部门'

  // 获取部门统计数据
  const fetchStats = async () => {
    setLoading(true)
    try {
      const response = await fetch(`/api/v1/analytics/department/${department}`)
      if (!response.ok) {
        throw new Error('获取数据失败')
      }
      const data = await response.json()
      setStats(data)
    } catch (error) {
      console.error('获取数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
  }, [department])

  // 处理Excel上传成功
  const handleUploadSuccess = (data: any) => {
    fetchStats()  // 刷新数据
  }

  // 准备图表数据
  const getChartData = (): ChartData => {
    if (!stats?.monthly_trends) {
      return {
        labels: [],
        datasets: [
          {
            label: '已通过',
            data: [],
            borderColor: 'rgb(34, 197, 94)',
            backgroundColor: 'rgba(34, 197, 94, 0.5)',
          },
          {
            label: '已拒绝',
            data: [],
            borderColor: 'rgb(239, 68, 68)',
            backgroundColor: 'rgba(239, 68, 68, 0.5)',
          },
          {
            label: '总数',
            data: [],
            borderColor: 'rgb(59, 130, 246)',
            backgroundColor: 'rgba(59, 130, 246, 0.5)',
          },
        ],
      }
    }

    const months = Object.keys(stats.monthly_trends)
    const approvedData = months.map(m => stats.monthly_trends[m].approved || 0)
    const rejectedData = months.map(m => stats.monthly_trends[m].rejected || 0)
    const totalData = months.map(m => stats.monthly_trends[m].total || 0)

    return {
      labels: months,
      datasets: [
        {
          label: '已通过',
          data: approvedData,
          borderColor: 'rgb(34, 197, 94)',
          backgroundColor: 'rgba(34, 197, 94, 0.5)',
        },
        {
          label: '已拒绝',
          data: rejectedData,
          borderColor: 'rgb(239, 68, 68)',
          backgroundColor: 'rgba(239, 68, 68, 0.5)',
        },
        {
          label: '总数',
          data: totalData,
          borderColor: 'rgb(59, 130, 246)',
          backgroundColor: 'rgba(59, 130, 246, 0.5)',
        },
      ],
    }
  }

  const getPieChartData = (): PieChartData => {
    if (!stats?.status_distribution) {
      return {
        labels: ['待审批', '已通过', '已拒绝'],
        datasets: [
          {
            data: [0, 0, 0],
            backgroundColor: [
              'rgba(59, 130, 246, 0.5)',
              'rgba(34, 197, 94, 0.5)',
              'rgba(239, 68, 68, 0.5)',
            ],
          },
        ],
      }
    }

    return {
      labels: ['待审批', '已通过', '已拒绝'],
      datasets: [
        {
          data: [
            stats.status_distribution.pending || 0,
            stats.status_distribution.approved || 0,
            stats.status_distribution.rejected || 0,
          ],
          backgroundColor: [
            'rgba(59, 130, 246, 0.5)',
            'rgba(34, 197, 94, 0.5)',
            'rgba(239, 68, 68, 0.5)',
          ],
        },
      ],
    }
  }

  return (
    <MainLayout>
      <Toaster position="top-right" />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* 部门标题 */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">{departmentName} - 业务数据</h1>
          <p className="mt-2 text-sm text-gray-500">
            查看部门审批数据统计和分析报告
          </p>
        </div>

        {loading ? (
          <div className="flex justify-center items-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          </div>
        ) : (
          <>
            {/* 数据卡片 */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
              <div className="bg-white p-6 rounded-lg shadow">
                <div className="flex items-center">
                  <BarChart2 className="h-10 w-10 text-blue-500" />
                  <div className="ml-4">
                    <p className="text-sm font-medium text-gray-500">总审批数</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {stats?.total_approvals || 0}
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-white p-6 rounded-lg shadow">
                <div className="flex items-center">
                  <PieChart className="h-10 w-10 text-green-500" />
                  <div className="ml-4">
                    <p className="text-sm font-medium text-gray-500">通过率</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {stats?.status_distribution?.approved
                        ? ((stats.status_distribution.approved / stats.total_approvals) * 100).toFixed(1)
                        : 0}%
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-white p-6 rounded-lg shadow">
                <div className="flex items-center">
                  <TrendingUp className="h-10 w-10 text-yellow-500" />
                  <div className="ml-4">
                    <p className="text-sm font-medium text-gray-500">平均处理时间</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {stats?.avg_processing_time
                        ? `${stats.avg_processing_time.toFixed(1)}h`
                        : 'N/A'}
                    </p>
                  </div>
                </div>
              </div>

              <div className="bg-white p-6 rounded-lg shadow">
                <div className="flex items-center">
                  <FileSpreadsheet className="h-10 w-10 text-purple-500" />
                  <div className="ml-4">
                    <p className="text-sm font-medium text-gray-500">待处理</p>
                    <p className="text-2xl font-semibold text-gray-900">
                      {stats?.status_distribution?.pending || 0}
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="flex space-x-4 mb-8">
              <button
                onClick={() => setShowUploadModal(true)}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center"
              >
                <FileSpreadsheet className="h-5 w-5 mr-2" />
                导入Excel数据
              </button>
              <button
                onClick={() => setShowReportModal(true)}
                className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 flex items-center"
              >
                <Sparkles className="h-5 w-5 mr-2" />
                查看AI分析报告
              </button>
            </div>

            {/* 图表区域 */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
              {/* 趋势图 */}
              <div className="bg-white p-6 rounded-lg shadow">
                <h3 className="text-lg font-medium text-gray-900 mb-4">审批趋势</h3>
                <div className="h-80">
                  <LineChart data={getChartData()} />
                </div>
              </div>

              {/* 状态分布图 */}
              <div className="bg-white p-6 rounded-lg shadow">
                <h3 className="text-lg font-medium text-gray-900 mb-4">状态分布</h3>
                <div className="h-80">
                  <PieChartComponent data={getPieChartData()} />
                </div>
              </div>
            </div>

            {/* 月度统计表格 */}
            <div className="bg-white p-6 rounded-lg shadow">
              <h3 className="text-lg font-medium text-gray-900 mb-4">月度统计</h3>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead>
                    <tr>
                      <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        月份
                      </th>
                      <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        总数
                      </th>
                      <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        已通过
                      </th>
                      <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        已拒绝
                      </th>
                      <th className="px-6 py-3 bg-gray-50 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        通过率
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {stats?.monthly_trends &&
                      Object.entries(stats.monthly_trends).map(([month, data]: [string, any]) => (
                        <tr key={month}>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {month}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {data.total}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {data.approved}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {data.rejected}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {data.total > 0
                              ? ((data.approved / data.total) * 100).toFixed(1)
                              : 0}%
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>

      {/* 模态框 */}
      <ExcelUploadModal
        isOpen={showUploadModal}
        onClose={() => setShowUploadModal(false)}
        onUploadSuccess={handleUploadSuccess}
      />
      <AnalysisReportModal
        isOpen={showReportModal}
        onClose={() => setShowReportModal(false)}
        department={department}
      />

      {/* 添加悬浮提示按钮 */}
      <div className="fixed bottom-8 right-8 space-y-4">
        <button
          onClick={() => setShowUploadModal(true)}
          className="flex items-center justify-center w-12 h-12 bg-blue-600 text-white rounded-full hover:bg-blue-700 shadow-lg group relative"
        >
          <FileSpreadsheet className="h-6 w-6" />
          <span className="absolute right-full mr-2 bg-gray-900 text-white text-sm py-1 px-2 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
            导入Excel数据
          </span>
        </button>
        <button
          onClick={() => setShowReportModal(true)}
          className="flex items-center justify-center w-12 h-12 bg-purple-600 text-white rounded-full hover:bg-purple-700 shadow-lg group relative"
        >
          <Sparkles className="h-6 w-6" />
          <span className="absolute right-full mr-2 bg-gray-900 text-white text-sm py-1 px-2 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
            查看AI分析报告
          </span>
        </button>
      </div>

      {/* 添加数据更新提示 */}
      {loading && (
        <div className="fixed top-4 right-4 bg-blue-100 text-blue-800 px-4 py-2 rounded-md shadow-md">
          正在更新数据...
        </div>
      )}

      {/* 添加数据刷新按钮 */}
      <button
        onClick={fetchStats}
        className="fixed bottom-8 left-8 flex items-center justify-center w-12 h-12 bg-gray-600 text-white rounded-full hover:bg-gray-700 shadow-lg group relative"
      >
        <RefreshCw className="h-6 w-6" />
        <span className="absolute left-full ml-2 bg-gray-900 text-white text-sm py-1 px-2 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
          刷新数据
        </span>
      </button>
    </MainLayout>
  )
}