"use client"

import React, { useState, useEffect, useCallback, use } from "react"
import { Spin, Alert, Button, Space, Typography } from "antd"
import { ArrowLeftOutlined, ExportOutlined } from "@ant-design/icons"
import { useRouter } from "next/navigation"
import MainLayout from "@/components/layout/MainLayout"
import ContentLayout from "@/components/layout/ContentLayout"
import DocumentPreview from "@/components/academic-integrity/DocumentPreview"
import IssuePanel from "@/components/academic-integrity/IssuePanel"
import { isAuthenticated } from "@/lib/api"

const { Title } = Typography
const API_BASE = "/api/v1"

interface HighlightData { issueId: string; category: string; startChar: number; endChar: number; severity: string }
interface IssueData {
  id: string; category: string; severity: string; title: string; message: string
  suggestion: string; evidence_quote: string; page: number; section: string
  start_offset: number; end_offset: number; dedupe_key: string; score_delta: number
  provider_trace?: any[]; manual_review_required: boolean; folded?: boolean; affected_count?: number
}

export default function ReviewPreviewPage({ params }: { params: Promise<{ taskId: string }> }) {
  const { taskId } = use(params)
  const router = useRouter()
  const [text, setText] = useState("")
  const [title, setTitle] = useState("")
  const [highlights, setHighlights] = useState<HighlightData[]>([])
  const [issues, setIssues] = useState<IssueData[]>([])
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null)
  const [filterCategory, setFilterCategory] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const apiFetch = useCallback(async (url: string, opts?: RequestInit) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
    const res = await fetch(url, { ...opts, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...opts?.headers } })
    if (res.status === 401) { localStorage.removeItem("token"); router.push("/login"); throw new Error("未登录") }
    return res.json()
  }, [router])

  useEffect(() => {
    if (typeof window !== "undefined" && !isAuthenticated()) { router.push("/login"); return }
    loadData()
  }, [taskId])

  const loadData = async () => {
    setLoading(true)
    try {
      const result = await apiFetch(`${API_BASE}/pre-review/academic-integrity/${taskId}`)
      const r = result.result

      // Load full text
      let fullText = ""
      try {
        const tr = await apiFetch(`${API_BASE}/pre-review/academic-integrity/${taskId}/full-text`)
        fullText = tr.text || ""
        if (tr.title) setTitle(tr.title)
      } catch {}

      setText(fullText)
      const hls: HighlightData[] = []
      const is: IssueData[] = []

      // Plagiarism
      if (r?.plagiarism?.segments) {
        for (const seg of r.plagiarism.segments) {
          const id = `plag-${seg.index}`
          hls.push({ issueId: id, category: seg.risk_level === "high" || seg.risk_level === "critical" ? "plagiarism_high" : "plagiarism_medium", startChar: seg.start_char || 0, endChar: seg.end_char || 0, severity: seg.risk_level || "low" })
          is.push({ id, category: "plagiarism", severity: seg.risk_level || "low", title: `段落#${seg.index} 相似度${(seg.similarity_score * 100).toFixed(0)}%`, message: seg.reason || "", suggestion: seg.suggestion || "", evidence_quote: (seg.text || "").slice(0, 200), page: 0, section: "", start_offset: seg.start_char || 0, end_offset: seg.end_char || 0, dedupe_key: `plag-${seg.index}`, score_delta: -Math.round(seg.similarity_score * 20), manual_review_required: seg.risk_level === "high" || seg.risk_level === "critical" })
        }
      }
      if (r?.plagiarism?.similarity_status === "insufficient_coverage") {
        is.unshift({ id: "coverage-warn", category: "plagiarism", severity: "medium", title: "开放来源覆盖不足", message: r.plagiarism.coverage_note || "", suggestion: "配置SERPER_API_KEY或上传参考文档到本地知识库", evidence_quote: "", page: 0, section: "", start_offset: 0, end_offset: 0, dedupe_key: "coverage", score_delta: 0, manual_review_required: false })
      }

      // Data sources
      if (r?.data_sources?.items) {
        for (const item of r.data_sources.items) {
          const id = `ds-${item.index}`
          const idx = fullText.indexOf(item.source_text || "")
          const start = idx >= 0 ? idx : 0
          hls.push({ issueId: id, category: "data_source", startChar: start, endChar: start + (item.source_text?.length || 0), severity: item.risk_level || "medium" })
          if (item.missing_fields?.length > 0 || item.risk_level !== "low") {
            is.push({ id, category: "data_sources", severity: item.risk_level || "medium", title: `${item.source_type_name || item.source_name}`, message: item.risk_reason || "", suggestion: item.suggestion || "", evidence_quote: item.evidence_quote || (item.source_text || "").slice(0, 200), page: 0, section: "", start_offset: start, end_offset: start + (item.source_text?.length || 0), dedupe_key: item.dedupe_key || `ds-${item.index}`, score_delta: item.risk_level === "high" ? -8 : item.risk_level === "medium" ? -3 : 0, manual_review_required: item.risk_level === "high" || item.risk_level === "critical", folded: item.folded || false })
          }
        }
      }

      // Deduped DS groups
      if (r?.deduped_ds_issues) {
        for (const grp of r.deduped_ds_issues) {
          is.push({ id: grp.id || `dsg-${grp.source_type}`, category: "data_sources", severity: grp.severity || "medium", title: `${grp.title}`, message: grp.reason || "", suggestion: grp.suggestion || "", evidence_quote: grp.evidence || "", page: 0, section: "", start_offset: 0, end_offset: 0, dedupe_key: grp.dedupe_key || "", score_delta: -3, manual_review_required: grp.severity === "high", folded: true, affected_count: grp.affected_count || 1 })
        }
      }

      // References
      if (r?.references?.items) {
        for (const item of r.references.items) {
          const id = `ref-${item.index}`
          const status = item.status || ""
          const rawRef = item.raw_reference || ""
          const idx = fullText.indexOf(rawRef)
          const cat = status === "verified" || status === "likely_real" || item.local_match_status === "verified_by_local_library" ? "verified_ref" : status === "suspicious" ? "suspicious_ref" : "not_found_ref"
          const sev = status === "suspicious" ? "high" : status === "verified" || status === "likely_real" || item.local_match_status === "verified_by_local_library" ? "low" : "medium"
          hls.push({ issueId: id, category: cat, startChar: idx >= 0 ? idx : 0, endChar: idx >= 0 ? idx + rawRef.length : 0, severity: sev })
          if (status !== "verified" && status !== "likely_real" && item.local_match_status !== "verified_by_local_library") {
            is.push({ id, category: "references", severity: sev, title: `[${item.index}] ${rawRef.slice(0, 80)}`, message: item.risk_reason || "", suggestion: item.suggestion || "", evidence_quote: rawRef.slice(0, 200), page: 0, section: "", start_offset: idx >= 0 ? idx : 0, end_offset: idx >= 0 ? idx + rawRef.length : 0, dedupe_key: `ref-${status}`, score_delta: status === "suspicious" ? -5 : -2, manual_review_required: status === "needs_manual_check" || status === "suspicious", provider_trace: item.provider_trace || [] })
          }
        }
      }

      // Priority fixes
      if (r?.priority_fixes) {
        for (let i = 0; i < r.priority_fixes.length; i++) {
          const fix = r.priority_fixes[i]
          is.push({ id: `fix-${i}`, category: fix.category || fix.module || "other", severity: fix.priority === "P0" ? "high" : fix.priority === "P1" ? "medium" : "low", title: fix.title || fix.issue || "", message: fix.reason || "", suggestion: fix.action || "", evidence_quote: fix.evidence || "", page: 0, section: fix.affected_sections?.[0] || "", start_offset: 0, end_offset: 0, dedupe_key: fix.fix_id || `fix-${i}`, score_delta: fix.priority === "P0" ? -10 : fix.priority === "P1" ? -5 : -2, manual_review_required: fix.manual_review_required || false, folded: (fix.affected_count || 0) > 1, affected_count: fix.affected_count || 1 })
        }
      }

      setHighlights(hls)
      setIssues(is)
    } catch (e: any) { setError(e.message || "加载失败") }
    finally { setLoading(false) }
  }

  const handleIssueClick = (id: string) => setActiveIssueId(id)

  if (loading) {
    return <MainLayout><ContentLayout><div className="flex items-center justify-center h-96"><Spin size="large" tip="加载中..." /></div></ContentLayout></MainLayout>
  }

  return (
    <MainLayout>
      <ContentLayout>
        <div className="flex flex-col h-[calc(100vh-80px)]">
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-200 bg-white">
            <Space>
              <Button icon={<ArrowLeftOutlined />} onClick={() => router.push("/pre-review/academic-integrity")}>返回</Button>
              <Title level={5} style={{ margin: 0 }}>审阅预览 - {title || taskId}</Title>
            </Space>
            <Button icon={<ExportOutlined />} onClick={() => window.open(`${API_BASE}/pre-review/academic-integrity/${taskId}/export?format=html`, "_blank")}>导出报告</Button>
          </div>
          {error && <Alert type="error" message={error} closable className="mx-2 mt-2" onClose={() => setError("")} />}
          <div className="flex-1 flex overflow-hidden">
            <div className="w-[65%] border-r border-gray-200 overflow-hidden">
              <DocumentPreview text={text} highlights={highlights} activeIssueId={activeIssueId} onHighlightClick={handleIssueClick} />
            </div>
            <div className="w-[35%] overflow-hidden">
              <IssuePanel issues={issues} activeIssueId={activeIssueId} onIssueClick={(id) => handleIssueClick(id)} filterCategory={filterCategory} onFilterChange={setFilterCategory} />
            </div>
          </div>
        </div>
      </ContentLayout>
    </MainLayout>
  )
}
