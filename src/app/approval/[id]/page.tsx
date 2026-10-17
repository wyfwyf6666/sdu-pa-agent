// 文件路径：src/app/approval/[id]/page.tsx

'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import MainLayout from '@/components/layout/MainLayout'
import ContentLayout from '@/components/layout/ContentLayout'

interface ApprovalDetail {
  id: number
  title: string
  type: string
  content: string
  applicant: string
  department: string
  urgency: string
  status: string
  current_step: number
  steps: {
    step_id: number
    name: string
    approver: string
    status: string
    comment?: string
    approve_time?: string
  }[]
  comments: {
    comment_id: number
    user: string
    content: string
    create_time: string
  }[]
  files: {
    file_id: number
    filename: string
    file_type: string
    upload_time: string
  }[]
}

export default function ApprovalDetailPage() {
  // 1. 从 URL 中拿到 params；可能是 Record<string, string | string[]>，也可能是 null
  const params = useParams() // 类型： Record<string, string | string[]> | null

  // 2. 如果 params 目前还是 null，说明路由参数还没准备好，直接显示“加载中”或返回 null 
  if (!params) {
    return (
      <MainLayout>
        <ContentLayout>
          <div className="p-4 text-gray-500">正在获取路由参数…</div>
        </ContentLayout>
      </MainLayout>
    )
  }

  // 3. 这时 TypeScript 能够确定 params 不为 null，所以可以安全取 params.id
  //    但 params.id 可能是 string 或 string[]（比如一个数组），所以我们再做一次处理：
  const rawId = params.id
  // 如果是数组，就取第 0 个；如果不是，就直接用它
  const approvalId =
    typeof rawId === 'string' ? rawId : Array.isArray(rawId) ? rawId[0] : ''

  // 4. 如果 approvalId 还是空字符串，说明 URL 参数不合法，我们直接返回一个提示
  if (!approvalId) {
    return (
      <MainLayout>
        <ContentLayout>
          <div className="p-4 text-red-500">未找到有效的审批 ID。</div>
        </ContentLayout>
      </MainLayout>
    )
  }

  // 5. 把 approvalId 转为 number，以便后面拼接到 fetch URL
  const approvalIdNum = Number(approvalId)

  // 6. 下面就是常规的“根据 ID 向后端请求详情”的逻辑
  const [data, setData] = useState<ApprovalDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchDetail() {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(`/api/v1/approvals/${approvalIdNum}`)
        if (!res.ok) {
          throw new Error(`接口返回 ${res.status}`)
        }
        const json = await res.json()
        setData(json)
      } catch (e: any) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    fetchDetail()
  }, [approvalIdNum])

  // 7. 渲染阶段：根据 loading / error / data 三种状态显示不同内容
  return (
    <MainLayout>
      <ContentLayout>
        {loading ? (
          <div className="p-4 text-gray-500">正在加载审批详情…</div>
        ) : error ? (
          <div className="p-4 text-red-500">加载出错：{error}</div>
        ) : !data ? (
          <div className="p-4 text-gray-500">未找到该审批</div>
        ) : (
          <div className="max-w-3xl mx-auto p-4 bg-white rounded-lg shadow">
            {/* 8. 下面开始真正渲染审批详情 */}
            <h1 className="text-2xl font-bold mb-4">{data.title}</h1>
            <div className="space-y-2 mb-6">
              <p>
                <span className="font-medium">ID：</span>
                {data.id}
              </p>
              <p>
                <span className="font-medium">申请人：</span>
                {data.applicant}
              </p>
              <p>
                <span className="font-medium">所属部门：</span>
                {data.department}
              </p>
              <p>
                <span className="font-medium">审批类型：</span>
                {data.type}
              </p>
              <p>
                <span className="font-medium">紧急程度：</span>
                {data.urgency}
              </p>
              <p>
                <span className="font-medium">当前状态：</span>
                {data.status}
              </p>
            </div>

            <div className="mb-6">
              <h2 className="text-xl font-semibold mb-2">详细内容</h2>
              <p className="whitespace-pre-wrap bg-gray-50 p-4 rounded">
                {data.content}
              </p>
            </div>

            <div className="mb-6">
              <h2 className="text-xl font-semibold mb-2">审批步骤</h2>
              <ul className="space-y-2">
                {data.steps.map((step) => (
                  <li key={step.step_id} className="p-4 border rounded">
                    <p>
                      <span className="font-medium">
                        步骤 {step.step_id}：{step.name}
                      </span>
                    </p>
                    <p>
                      <span className="font-medium">审批人：</span>
                      {step.approver}
                    </p>
                    <p>
                      <span className="font-medium">状态：</span>
                      {step.status}
                    </p>
                    {step.comment && (
                      <p>
                        <span className="font-medium">意见：</span>
                        {step.comment}
                      </p>
                    )}
                    {step.approve_time && (
                      <p>
                        <span className="font-medium">审批时间：</span>
                        {new Date(step.approve_time).toLocaleString()}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>

            <div className="mb-6">
              <h2 className="text-xl font-semibold mb-2">审批评论</h2>
              {data.comments.length > 0 ? (
                <ul className="space-y-2">
                  {data.comments.map((c) => (
                    <li key={c.comment_id} className="p-3 bg-gray-50 rounded">
                      <p>
                        <span className="font-medium">{c.user}</span> 于{' '}
                        {new Date(c.create_time).toLocaleString()} 说：
                      </p>
                      <p className="whitespace-pre-wrap">{c.content}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>暂无评论。</p>
              )}
            </div>

            <div className="mb-6">
              <h2 className="text-xl font-semibold mb-2">附件列表</h2>
              {data.files.length > 0 ? (
                <ul className="space-y-2">
                  {data.files.map((f) => (
                    <li key={f.file_id}>
                      <a
                        href={`/api/v1/approvals/${data.id}/files/${f.file_id}`}
                        className="text-blue-600 hover:underline"
                      >
                        {f.filename}
                      </a>
                      <span className="ml-2 text-gray-500">
                        （{f.file_type}，上传于{' '}
                        {new Date(f.upload_time).toLocaleString()}）
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>暂无附件。</p>
              )}
            </div>
          </div>
        )}
      </ContentLayout>
    </MainLayout>
  )
}
