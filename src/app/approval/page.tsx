// 文件路径：src/app/approval/page.tsx

'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'  // ← 新增 Link
import { Search, Filter, Clock, CheckCircle, XCircle, AlertCircle, Plus } from 'lucide-react'
import MainLayout from '@/components/layout/MainLayout'
import ContentLayout from '@/components/layout/ContentLayout'
import ApprovalModal from '@/components/approval/ApprovalModal'
import { motion } from 'framer-motion'

// 模拟审批数据（保留作为默认数据）
const mockApprovals = [
  {
    id: 1,
    title: '关于举办2025年政务创新大会的申请',
    type: '会议申请',
    applicant: '张三',
    department: '创新发展部',
    submitTime: '2024-12-20 14:30',
    status: 'pending',
    currentStep: '部门经理审批',
    urgency: 'normal',
  },
  {
    id: 2,
    title: '2025年度预算报告审批',
    type: '预算审批',
    applicant: '李四',
    department: '财务部',
    submitTime: '2024-12-19 09:15',
    status: 'approved',
    currentStep: '已完成',
    urgency: 'high',
  },
  {
    id: 3,
    title: '办公设备采购申请',
    type: '采购申请',
    applicant: '王五',
    department: '行政部',
    submitTime: '2025-5-18 16:45',
    status: 'rejected',
    currentStep: '已拒绝',
    urgency: 'low',
  },
]

// 根据不同状态返回对应的背景色与文字色
const getStatusColor = (status: string) => {
  switch (status) {
    case 'pending':
      return 'bg-yellow-100 text-yellow-800'
    case 'approved':
      return 'bg-green-100 text-green-800'
    case 'rejected':
      return 'bg-red-100 text-red-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

// 根据不同状态返回对应的图标组件
const getStatusIcon = (status: string) => {
  switch (status) {
    case 'pending':
      return Clock
    case 'approved':
      return CheckCircle
    case 'rejected':
      return XCircle
    default:
      return AlertCircle
  }
}

// 根据紧急程度返回对应的徽章颜色
const getUrgencyBadge = (urgency: string) => {
  switch (urgency) {
    case 'high':
      return 'bg-red-100 text-red-800'
    case 'normal':
      return 'bg-blue-100 text-blue-800'
    case 'low':
      return 'bg-gray-100 text-gray-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

export default function ApprovalPage() {
  const router = useRouter()
  const [searchQuery, setSearchQuery] = useState('')
  const [filter, setFilter] = useState('all')
  // 初始使用 mock 数据；后续 fetch 后会叠加真实数据
  const [approvals, setApprovals] = useState(mockApprovals)
  const [loading, setLoading] = useState(true)

  // 审批模态框状态
  const [selectedApproval, setSelectedApproval] = useState<{
    id: number
    currentStep: string
    data: any
  } | null>(null)

  // 从后端拉审批列表
  const fetchApprovals = async () => {
    try {
      const response = await fetch('/api/v1/approvals')
      if (response.ok) {
        const data = await response.json()
        // 把从后端拿到的 data（数组）和 mock 放一起，mock在后面
        setApprovals([...data, ...mockApprovals])
      }
    } catch (error) {
      console.error('获取审批列表失败:', error)
    } finally {
      setLoading(false)
    }
  }

  // 组件挂载时马上拉数据
  useEffect(() => {
    fetchApprovals()
  }, [])

  // 筛选 + 搜索逻辑
  const filteredApprovals = approvals.filter((approval) => {
    const matchesSearch =
      approval.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      approval.applicant.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesFilter = filter === 'all' || approval.status === filter
    return matchesSearch && matchesFilter
  })

  // 点击“审批”按钮时，打开模态框；注意要 preventDefault 阻止 Link 跳转
  const handleApproveClick = (approval: any, e: React.MouseEvent) => {
    e.preventDefault() // 阻止 <Link> 默认跳转
    setSelectedApproval({
      id: approval.id,
      currentStep: approval.currentStep,
      data: approval,
    })
  }

  // 模态框审批成功后，刷新列表
  const handleApprovalSuccess = () => {
    fetchApprovals()
  }

  return (
    <MainLayout>
      <ContentLayout>
        {/* 顶部标题 */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 border border-gray-100 mb-6"
        >
          <h1 className="text-2xl font-semibold text-gray-900 bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-blue-800">
            审批流程
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            高效管理各类审批事项，实时跟踪审批进度
          </p>
        </motion.div>

        {/* 搜索 和 筛选 */}
        <div className="mb-6 flex flex-col sm:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder="搜索审批事项..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div className="flex items-center space-x-4">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="all">全部状态</option>
              <option value="pending">待审批</option>
              <option value="approved">已通过</option>
              <option value="rejected">已拒绝</option>
            </select>
            <button
              onClick={() => router.push('/approval/create')}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center"
            >
              <Plus className="h-5 w-5 mr-1" />
              新建审批
            </button>
          </div>
        </div>

        {/* 审批统计卡片 */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">待审批</p>
                <p className="text-2xl font-semibold text-yellow-600">
                  {approvals.filter((a) => a.status === 'pending').length}
                </p>
              </div>
              <Clock className="h-8 w-8 text-yellow-500" />
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">已通过</p>
                <p className="text-2xl font-semibold text-green-600">
                  {approvals.filter((a) => a.status === 'approved').length}
                </p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">已拒绝</p>
                <p className="text-2xl font-semibold text-red-600">
                  {approvals.filter((a) => a.status === 'rejected').length}
                </p>
              </div>
              <XCircle className="h-8 w-8 text-red-500" />
            </div>
          </div>
        </div>

        {/* 审批列表 */}
        <div className="space-y-4">
          {loading ? (
            <div className="text-center py-4 text-gray-500">加载中...</div>
          ) : filteredApprovals.length === 0 ? (
            <div className="text-center py-4 text-gray-500">
              暂无审批数据
            </div>
          ) : (
            filteredApprovals.map((approval) => {
              const StatusIcon = getStatusIcon(approval.status)
              return (
                // 整个卡片包裹在 <Link> 中，点击任意空白区域都跳转到 /approval/[id]
                <Link
                  href={`/approval/${approval.id}`}
                  key={approval.id}
                  className="block bg-white p-4 rounded-lg border border-gray-200 hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <h3 className="text-lg font-medium text-gray-900">
                          {approval.title}
                        </h3>
                        <span
                          className={`px-2 py-1 rounded-full text-xs ${getStatusColor(
                            approval.status
                          )}`}
                        >
                          {approval.status === 'pending'
                            ? '待审批'
                            : approval.status === 'approved'
                            ? '已通过'
                            : '已拒绝'}
                        </span>
                        <span
                          className={`px-2 py-1 rounded-full text-xs ${getUrgencyBadge(
                            approval.urgency
                          )}`}
                        >
                          {approval.urgency === 'high'
                            ? '紧急'
                            : approval.urgency === 'normal'
                            ? '普通'
                            : '低优先级'}
                        </span>
                      </div>
                      <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm text-gray-500">
                        <div>
                          <span className="font-medium">申请人：</span>
                          {approval.applicant}
                        </div>
                        <div>
                          <span className="font-medium">所属部门：</span>
                          {approval.department}
                        </div>
                        <div>
                          <span className="font-medium">申请类型：</span>
                          {approval.type}
                        </div>
                        <div>
                          <span className="font-medium">提交时间：</span>
                          {approval.submitTime}
                        </div>
                      </div>
                    </div>
                    <StatusIcon
                      className={`h-6 w-6 ${
                        approval.status === 'pending'
                          ? 'text-yellow-500'
                          : approval.status === 'approved'
                          ? 'text-green-500'
                          : 'text-red-500'
                      }`}
                    />
                  </div>

                  {/* 如果状态是 pending，就显示“审批”按钮 */}
                  {approval.status === 'pending' && (
                    <div className="mt-4 pt-4 border-t border-gray-100 flex justify-end">
                      <button
                        onClick={(e) => handleApproveClick(approval, e)}
                        className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                      >
                        审批
                      </button>
                    </div>
                  )}
                </Link>
              )
            })
          )}
        </div>

        {/* 审批处理模态框 */}
        {selectedApproval && (
          <ApprovalModal
            isOpen={true}
            onClose={() => setSelectedApproval(null)}
            approvalId={selectedApproval.id}
            currentStep={selectedApproval.currentStep}
            approvalData={selectedApproval.data}
            onSuccess={handleApprovalSuccess}
          />
        )}
      </ContentLayout>
    </MainLayout>
  )
}
