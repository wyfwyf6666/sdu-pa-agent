'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import MainLayout from '@/components/layout/MainLayout'
import ContentLayout from '@/components/layout/ContentLayout'
import { Upload, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'

// 审批类型选项
const approvalTypes = [
  { value: 'meeting', label: '会议申请' },
  { value: 'budget', label: '预算申请' },
  { value: 'purchase', label: '采购申请' },
  { value: 'leave', label: '请假申请' },
  { value: 'other', label: '其他' },
]

// 紧急程度选项
const urgencyLevels = [
  { value: 'high', label: '紧急', class: 'bg-red-100 text-red-800' },
  { value: 'normal', label: '普通', class: 'bg-blue-100 text-blue-800' },
  { value: 'low', label: '低优先级', class: 'bg-gray-100 text-gray-800' },
]

export default function CreateApprovalPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  
  // 表单数据
  const [formData, setFormData] = useState({
    title: '',
    type: 'meeting',
    content: '',
    urgency: 'normal',
    approvers: [''],  // 审批人列表
    files: [] as File[],
  })

  // 处理表单字段变化
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  // 处理审批人变化
  const handleApproverChange = (index: number, value: string) => {
    const newApprovers = [...formData.approvers]
    newApprovers[index] = value
    setFormData(prev => ({ ...prev, approvers: newApprovers }))
  }

  // 添加审批人
  const addApprover = () => {
    setFormData(prev => ({
      ...prev,
      approvers: [...prev.approvers, ''],
    }))
  }

  // 移除审批人
  const removeApprover = (index: number) => {
    if (formData.approvers.length > 1) {
      const newApprovers = formData.approvers.filter((_, i) => i !== index)
      setFormData(prev => ({ ...prev, approvers: newApprovers }))
    }
  }

  // 处理文件选择
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files)
      setFormData(prev => ({
        ...prev,
        files: [...prev.files, ...newFiles],
      }))
    }
  }

  // 移除文件
  const removeFile = (index: number) => {
    const newFiles = formData.files.filter((_, i) => i !== index)
    setFormData(prev => ({ ...prev, files: newFiles }))
  }

  // 提交表单
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      // 创建审批
      const response = await fetch('/api/v1/approvals', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: formData.title,
          type: formData.type,
          content: formData.content,
          urgency: formData.urgency,
          steps: formData.approvers.filter(a => a.trim()),  // 过滤空的审批人
        }),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || '创建审批失败')
      }

      const approval = await response.json()

      // 如果有文件，上传文件
      if (formData.files.length > 0) {
        for (const file of formData.files) {
          const formData = new FormData()
          formData.append('file', file)

          const fileResponse = await fetch(`/api/v1/approvals/${approval.id}/files`, {
            method: 'POST',
            body: formData,
          })

          if (!fileResponse.ok) {
            throw new Error('文件上传失败')
          }
        }
      }

      // 显示成功提示
      toast.success('审批创建成功！')

      // 跳转到审批列表页
      router.push('/approval')
      router.refresh() // 刷新页面数据
      
    } catch (err) {
      toast.error(err instanceof Error ? err.message : '创建审批失败')
      setError(err instanceof Error ? err.message : '创建审批失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <MainLayout>
      <ContentLayout title="新建审批">
        <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
          {/* 错误提示 */}
          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center text-red-700">
              <AlertCircle className="h-5 w-5 mr-2" />
              {error}
            </div>
          )}

          {/* 基本信息 */}
          <div className="bg-white p-6 rounded-lg shadow mb-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">基本信息</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  审批标题
                </label>
                <input
                  type="text"
                  name="title"
                  value={formData.title}
                  onChange={handleChange}
                  required
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="请输入审批标题"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    审批类型
                  </label>
                  <select
                    name="type"
                    value={formData.type}
                    onChange={handleChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  >
                    {approvalTypes.map(type => (
                      <option key={type.value} value={type.value}>
                        {type.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    紧急程度
                  </label>
                  <select
                    name="urgency"
                    value={formData.urgency}
                    onChange={handleChange}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  >
                    {urgencyLevels.map(level => (
                      <option key={level.value} value={level.value}>
                        {level.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  审批内容
                </label>
                <textarea
                  name="content"
                  value={formData.content}
                  onChange={handleChange}
                  required
                  rows={4}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="请输入审批内容"
                />
              </div>
            </div>
          </div>

          {/* 审批流程 */}
          <div className="bg-white p-6 rounded-lg shadow mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-medium text-gray-900">审批流程</h3>
              <button
                type="button"
                onClick={addApprover}
                className="px-4 py-2 text-sm text-blue-600 hover:text-blue-700"
              >
                添加审批人
              </button>
            </div>

            <div className="space-y-4">
              {formData.approvers.map((approver, index) => (
                <div key={index} className="flex items-center gap-4">
                  <div className="flex-1">
                    <input
                      type="text"
                      value={approver}
                      onChange={(e) => handleApproverChange(index, e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      placeholder={`第 ${index + 1} 步审批人`}
                      required
                    />
                  </div>
                  {formData.approvers.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeApprover(index)}
                      className="px-3 py-2 text-sm text-red-600 hover:text-red-700"
                    >
                      删除
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* 附件上传 */}
          <div className="bg-white p-6 rounded-lg shadow mb-6">
            <h3 className="text-lg font-medium text-gray-900 mb-4">附件</h3>
            
            <div className="space-y-4">
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-6">
                <div className="flex flex-col items-center">
                  <Upload className="h-8 w-8 text-gray-400 mb-2" />
                  <label className="cursor-pointer">
                    <span className="text-blue-600 hover:text-blue-700">点击上传</span>
                    <span className="text-gray-500"> 或拖拽文件到这里</span>
                    <input
                      type="file"
                      multiple
                      onChange={handleFileChange}
                      className="hidden"
                    />
                  </label>
                </div>
              </div>

              {/* 文件列表 */}
              {formData.files.length > 0 && (
                <div className="space-y-2">
                  {formData.files.map((file, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between p-2 bg-gray-50 rounded"
                    >
                      <span className="text-sm text-gray-600">{file.name}</span>
                      <button
                        type="button"
                        onClick={() => removeFile(index)}
                        className="text-red-600 hover:text-red-700 text-sm"
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 提交按钮 */}
          <div className="flex justify-end space-x-4">
            <button
              type="button"
              onClick={() => router.back()}
              className="px-6 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? '提交中...' : '提交审批'}
            </button>
          </div>
        </form>
      </ContentLayout>
    </MainLayout>
  )
} 