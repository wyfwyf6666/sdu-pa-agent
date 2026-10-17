import { API_BASE_URL } from '@/config'
import { apiFetch } from '@/lib/api'
import type { ModuleKey, PreReviewResponse, ReviewHistoryItem, TranslateResult } from '@/types/pre-review'

export async function submitFullReview(
  title: string,
  manuscript: string,
  modules?: ModuleKey[]
): Promise<PreReviewResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/pre-review/review`, {
    method: 'POST',
    body: JSON.stringify({ title, manuscript, modules }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '请求失败' }))
    throw new Error(err.detail || '预审请求失败')
  }
  return res.json()
}

export async function uploadFileForReview(file: File): Promise<PreReviewResponse> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null
  const formData = new FormData()
  formData.append('file', file)

  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE_URL}/api/v1/pre-review/upload`, {
    method: 'POST',
    headers,
    body: formData,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(err.detail || '文件上传失败')
  }
  return res.json()
}

export async function getReviewHistory(): Promise<ReviewHistoryItem[]> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/pre-review/history`)
  if (!res.ok) return []
  const data = await res.json()
  return data.history || []
}

export async function getReviewResult(requestId: string): Promise<PreReviewResponse> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/pre-review/history/${requestId}`)
  if (!res.ok) throw new Error('未找到该预审记录')
  return res.json()
}

export async function translateText(text: string, direction: string = 'cn2en'): Promise<TranslateResult> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/pre-review/translate`, {
    method: 'POST',
    body: JSON.stringify({ text, direction }),
  })
  if (!res.ok) throw new Error('翻译失败')
  return res.json()
}

export async function exportReport(requestId: string, format: 'html' | 'txt' = 'html'): Promise<string> {
  const res = await apiFetch(`${API_BASE_URL}/api/v1/pre-review/export`, {
    method: 'POST',
    body: JSON.stringify({ request_id: requestId, format }),
  })
  if (!res.ok) throw new Error('导出失败')
  return res.text()
}

export async function exportReportHtml(requestId: string): Promise<string> {
  return exportReport(requestId, 'html')
}
