"use client"

import React, { useState, useCallback, useRef, useEffect } from "react"
import {
  Card,
  Button,
  Checkbox,
  Progress,
  Tag,
  Upload,
  Input,
  Space,
  Typography,
  Alert,
  message,
  Empty,
} from "antd"
import {
  UploadOutlined,
  SafetyOutlined,
  ExportOutlined,
  FilePdfOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  SearchOutlined,
  LoadingOutlined,
  CopyOutlined,
} from "@ant-design/icons"
import { useRouter } from "next/navigation"
import MainLayout from "@/components/layout/MainLayout"
import ContentLayout from "@/components/layout/ContentLayout"
import { isAuthenticated } from "@/lib/api"
import PdfManuscript from "@/components/pre-review/PdfManuscript"

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input
const API_BASE = "/api/v1"

interface MatchedSource {
  title?: string; url?: string; source_type?: string; similarity?: number
  snippet?: string; provider?: string; matched_title?: string; matched_doi?: string; score?: number
}
interface PlagSegment {
  index: number; text: string; similarity_score: number; risk_level: string
  matched_sources: MatchedSource[]; reason: string; suggestion: string; check_type?: string
}
interface PlagiarismResult {
  total_similarity: number; local_similarity: number; web_similarity: number; self_similarity: number
  corpus_size?: number; risk_level: string; summary: string; segments: PlagSegment[]
  check_method?: string; disclaimer?: string
}
interface RefItem {
  index: number; raw_reference: string
  parsed: { title: string; authors: string[]; year: number | null; journal: string; doi: string; volume: string; issue: string; pages: string; url: string }
  status: string; status_label?: string; format_score: number; match_confidence: number; final_confidence: number
  confidence_explanation?: string; matched_sources: MatchedSource[]; mismatch_fields: string[]
  risk_reason: string; suggestion: string; provider_trace?: { provider: string; called?: boolean }[]
  language?: string; local_match_status?: string
  manual_check_links?: { name: string; url: string }[]
}
interface ReferenceResult {
  total_references: number; verified_count: number; suspicious_count: number; not_found_count: number
  risk_level: string; summary: string; items: RefItem[]; disclaimer?: string
  chinese_web_configured?: boolean
}
interface TaskResult {
  overall_score: number; overall_risk_level: string; summary: string; key_findings: string[]
  plagiarism: PlagiarismResult | null; references: ReferenceResult | null; disclaimer: string
  pdf_extract?: { method?: string; pages?: number; ocr_pages?: number }
}

const RISK_LABEL: Record<string, string> = { low: "低风险", medium: "中风险", high: "高风险", critical: "严重风险" }
const REF_STATUS_META: Record<string, { color: string; icon: React.ReactNode }> = {
  verified: { color: "success", icon: <CheckCircleOutlined /> },
  likely_real: { color: "cyan", icon: <CheckCircleOutlined /> },
  likely_real_with_mismatch: { color: "warning", icon: <ExclamationCircleOutlined /> },
  insufficient_open_metadata: { color: "processing", icon: <ExclamationCircleOutlined /> },
  not_found: { color: "gold", icon: <ExclamationCircleOutlined /> },
  suspicious: { color: "error", icon: <CloseCircleOutlined /> },
  parse_failed: { color: "default", icon: <CloseCircleOutlined /> },
  check_failed: { color: "default", icon: <CloseCircleOutlined /> },
}
const riskLabel = (k?: string) => RISK_LABEL[k || "low"] || "低风险"
function scoreColor(s: number) { if (s >= 80) return "#15803d"; if (s >= 60) return "#b45309"; if (s >= 40) return "#ea580c"; return "#b91c1c" }
function simColor(v: number) { if (v <= 0.15) return "#15803d"; if (v <= 0.3) return "#b45309"; if (v <= 0.5) return "#b91c1c"; return "#7f1d1d" }

// 结果区左右两栏等高：左栏 PDF 以“完整一页”的实际渲染高度自然撑开（fitToPage），
// 一整页论文完整露出、不在 PDF 框内裁切；右栏意见拉伸到与 PDF 等高，内容在其框内滚动。
const DETAIL_GRID_MIN_H = "calc(100vh - 260px)"
const DETAIL_SOLO_H = "calc(100vh - 260px)"

const apiFetch = async (url: string, options?: RequestInit): Promise<any> => {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
  const res = await fetch(url, { ...options, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options?.headers } })
  if (res.status === 401) { localStorage.removeItem("token"); localStorage.removeItem("user"); window.location.href = "/login"; throw new Error("未登录") }
  return res.json()
}

export default function AcademicIntegrityPage() {
  const router = useRouter()
  const [text, setText] = useState("")
  const [title, setTitle] = useState("")
  const [doPlagiarism, setDoPlagiarism] = useState(true)
  const [doReferences, setDoReferences] = useState(true)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [taskStatus, setTaskStatus] = useState("")
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState("")
  const [result, setResult] = useState<TaskResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [pdfUrl, setPdfUrl] = useState("")
  const [showPdf, setShowPdf] = useState(true)
  const [fileLoading, setFileLoading] = useState(false)
  const [uploadingFile, setUploadingFile] = useState("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => { if (typeof window !== "undefined" && !isAuthenticated()) router.push("/login") }, [router])
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current) }, [])

  const startPolling = useCallback((id: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const data = await apiFetch(`${API_BASE}/pre-review/academic-integrity/${id}`)
        setTaskStatus(data.status); setProgress(data.progress || 0); setCurrentStep(data.current_step || "")
        if (data.status === "completed") {
          setResult(data.result); setPdfUrl(data.pdf_url || ""); setLoading(false)
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
          message.success("检测完成！")
        } else if (data.status === "failed") {
          setError(data.error_message || "检测失败"); setLoading(false)
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
        }
      } catch (e) { console.error(e) }
    }, 1500)
  }, [])

  // 支持通过 ?task=<id> 直接恢复一次进行中/已完成的任务（刷新或分享链接不丢结果）
  useEffect(() => {
    if (typeof window === "undefined") return
    const id = new URLSearchParams(window.location.search).get("task")
    if (id) {
      setTaskId(id); setTaskStatus("running"); setProgress(0)
      setResult(null); setPdfUrl(""); setLoading(true); setError("")
      startPolling(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const kickoff = (id: string) => {
    setTaskId(id); setTaskStatus("running"); setProgress(0); setResult(null); setPdfUrl(""); setLoading(true); setError("")
    startPolling(id)
  }

  const handleSubmit = async () => {
    if (!text || text.trim().length < 100) { message.warning("请至少输入 100 字以上的论文文本，或上传文件"); return }
    try {
      const data = await apiFetch(`${API_BASE}/pre-review/academic-integrity/analyze`, {
        method: "POST",
        body: JSON.stringify({
          text: text.trim(), title: title || "未命名文稿",
          options: { check_plagiarism: doPlagiarism, check_references: doReferences, check_data_sources: false, use_web_search: true, use_local_knowledge_base: true, use_external_academic_apis: true, language: "zh-CN" },
        }),
      })
      kickoff(data.task_id)
    } catch (e: any) { setError(e.message || "请求失败"); setLoading(false) }
  }

  const handleFileUpload = (opts: any) => {
    const { file, onSuccess, onError } = opts
    const rawFile = file instanceof File ? file : file?.originFileObj || file
    if (!rawFile) return
    const ext = (rawFile.name || "").split(".").pop()?.toLowerCase()
    if (!["txt", "pdf", "docx"].includes(ext || "")) { message.error("仅支持 TXT / PDF / DOCX"); onError?.(new Error("格式不支持")); return }
    setUploadingFile(rawFile.name); setFileLoading(true); setError("")
    const token = localStorage.getItem("token")
    const fd = new FormData(); fd.append("file", rawFile); if (title) fd.append("title", title)
    fd.append("options", JSON.stringify({
      check_plagiarism: doPlagiarism,
      check_references: doReferences,
      check_data_sources: false,
      use_web_search: true,
      use_local_knowledge_base: true,
      use_external_academic_apis: true,
      language: "zh-CN",
    }))
    const xhr = new XMLHttpRequest()
    xhr.open("POST", `${API_BASE}/pre-review/academic-integrity/upload`)
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`)
    xhr.onload = () => {
      try {
        if (xhr.status === 401) { localStorage.removeItem("token"); localStorage.removeItem("user"); message.error("登录已过期，请重新登录"); window.location.href = "/login"; return }
        const data = JSON.parse(xhr.responseText)
        if (xhr.status >= 200 && xhr.status < 300) { kickoff(data.task_id); onSuccess?.(data); message.success(`已上传《${rawFile.name}》，开始检测…`) }
        else { setError(data.detail || "上传失败"); message.error(data.detail || "上传失败"); onError?.(new Error(data.detail)) }
      } catch { setError("服务器响应异常") }
      setFileLoading(false); setUploadingFile("")
    }
    xhr.onerror = () => { setError("网络请求失败，请确认后端已启动"); setFileLoading(false); setUploadingFile(""); onError?.(new Error("网络错误")) }
    xhr.send(fd)
  }

  const handleExport = async (fmt: "html" | "txt") => {
    if (!taskId) return
    const token = localStorage.getItem("token")
    const res = await fetch(`${API_BASE}/pre-review/academic-integrity/${taskId}/export?format=${fmt}`, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) { message.error("导出失败"); return }
    const blob = await res.blob(); const url = URL.createObjectURL(blob)
    const a = document.createElement("a"); a.href = url; a.download = `学术诚信检测报告.${fmt}`; a.click(); URL.revokeObjectURL(url)
  }

  const plag = result?.plagiarism || null
  const refs = result?.references || null

  return (
    <MainLayout>
      <ContentLayout>
        <div style={{ maxWidth: 1400, margin: "0 auto", padding: "20px 16px 16px" }}>
          <div style={{ marginBottom: 18 }}>
            <Title level={3} style={{ marginBottom: 4, color: "#7A1014" }}>
              <SafetyOutlined style={{ marginRight: 8, color: "#ef7d00" }} />学术诚信检测
            </Title>
            <Text type="secondary">本地指纹查重 · 参考文献真实性逐条核验 · 左原文右意见对照</Text>
          </div>

          {!result && (
            <Card style={{ marginBottom: 20, borderRadius: 12 }}>
              <Space direction="vertical" style={{ width: "100%" }} size="middle">
                <Input placeholder="论文标题（可选）" value={title} onChange={(e) => setTitle(e.target.value)} allowClear />
                <TextArea placeholder="粘贴论文全文（至少 100 字），或直接上传 PDF / DOCX / TXT…" value={text} onChange={(e) => setText(e.target.value)} rows={9} />
                <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
                  <Space wrap>
                    <Checkbox checked={doPlagiarism} onChange={(e) => setDoPlagiarism(e.target.checked)}>本地指纹查重</Checkbox>
                    <Checkbox checked={doReferences} onChange={(e) => setDoReferences(e.target.checked)}>参考文献真实性核验</Checkbox>
                  </Space>
                  <Space>
                    <Upload accept=".txt,.pdf,.docx" showUploadList={false} customRequest={handleFileUpload} disabled={fileLoading}>
                      <Button icon={<UploadOutlined />} loading={fileLoading}>{fileLoading ? `正在上传 ${uploadingFile}…` : "上传 PDF / DOCX / TXT"}</Button>
                    </Upload>
                    <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={handleSubmit} disabled={!text || text.trim().length < 100} style={{ background: "#7A1014", borderColor: "#7A1014" }}>开始检测</Button>
                  </Space>
                </div>
              </Space>
            </Card>
          )}

          {(loading || (taskStatus && taskStatus !== "completed")) && (
            <Card style={{ marginBottom: 20, borderRadius: 12 }}>
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space><LoadingOutlined spin style={{ color: "#ef7d00", fontSize: 18 }} /><Text strong>{currentStep || "正在初始化…"}</Text></Space>
                <Progress percent={Math.round(progress * 100)} strokeColor="#7A1014" status="active" />
                <Text type="secondary" style={{ fontSize: 12 }}>文献在线核验可能需要数十秒，请稍候，勿关闭页面。</Text>
              </Space>
            </Card>
          )}

          {error && <Alert type="error" message="检测出错" description={error} showIcon closable style={{ marginBottom: 20 }} onClose={() => setError("")} />}

          {result && (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 8 }}>
                <Space wrap>
                  <Button onClick={() => { setResult(null); setTaskStatus(""); setPdfUrl("") }}>检测新文稿</Button>
                  {pdfUrl && (
                    <Button type={showPdf ? "primary" : "default"} icon={<FilePdfOutlined />} onClick={() => setShowPdf(v => !v)} style={showPdf ? { background: "#7A1014", borderColor: "#7A1014" } : {}}>
                      {showPdf ? "收起原文对照" : "打开 PDF 原文对照"}
                    </Button>
                  )}
                </Space>
                <Space>
                  <Button icon={<ExportOutlined />} onClick={() => handleExport("html")}>导出 HTML</Button>
                  <Button icon={<ExportOutlined />} onClick={() => handleExport("txt")}>导出 TXT</Button>
                </Space>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginBottom: 18 }}>
                <SummaryCard label="诚信综合评分" value={`${result.overall_score?.toFixed(0)}`} suffix="/100" color={scoreColor(result.overall_score)} />
                <SummaryCard label="综合风险" value={riskLabel(result.overall_risk_level)} color={scoreColor(result.overall_score)} />
                <SummaryCard label="本地查重重复率" value={plag ? `${(plag.total_similarity * 100).toFixed(1)}%` : "—"} color={plag ? simColor(plag.total_similarity) : "#6b7280"} />
                <SummaryCard label="参考文献核验" value={refs ? `${refs.verified_count}/${refs.total_references}` : "—"} suffix="已核验" color="#7A1014" />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: showPdf && pdfUrl ? "minmax(380px,1fr) minmax(420px,1.15fr)" : "1fr", gap: 18, alignItems: "stretch", minHeight: DETAIL_GRID_MIN_H }}>
                {showPdf && pdfUrl && (
                  <PdfManuscript pdfPath={pdfUrl} title={title || "论文原文"} annotations={[] as any} activeAnn={null} jump={null} onMarkClick={() => {}} fitToPage />
                )}

                <div style={{ position: "relative", minWidth: 0, minHeight: 420, ...(showPdf && pdfUrl ? {} : { height: DETAIL_SOLO_H }) }}>
                <section style={{ position: "absolute", inset: 0, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden", borderRadius: 12, border: "1px solid #eadbbf", background: "#f7f5f0", boxShadow: "0 1px 2px rgba(0,0,0,0.04)" }}>
                  <div style={{ flex: "1 1 auto", minHeight: 0, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 18 }}>
                  {(result.pdf_extract?.method === "ocr" || result.pdf_extract?.method === "hybrid") && (result.pdf_extract?.ocr_pages || 0) > 0 && (
                    <Alert
                      type="warning" showIcon style={{ borderRadius: 10 }}
                      message={`该 PDF 文字层损坏，已通过 OCR 光学识别提取文本（${result.pdf_extract?.ocr_pages}/${result.pdf_extract?.pages} 页）`}
                      description="左侧仍为论文原始 PDF 页面；右侧查重与文献核验基于 OCR 识别文本，个别字符或标点可能存在识别误差，关键结论请对照原文。"
                    />
                  )}
                  <Card style={{ borderRadius: 12, borderLeft: "4px solid #7A1014" }}>
                    <Paragraph style={{ marginBottom: 8, fontSize: 14 }}>{result.summary}</Paragraph>
                    {result.key_findings?.length > 0 && (
                      <ul style={{ margin: 0, paddingLeft: 20 }}>{result.key_findings.map((f, i) => <li key={i} style={{ marginBottom: 4, color: "#374151", fontSize: 13 }}>{f}</li>)}</ul>
                    )}
                  </Card>
                  {plag && <PlagiarismPanel plag={plag} />}
                  {refs && <ReferencesPanel refs={refs} />}
                  <Alert type="info" showIcon message="结果说明" description={result.disclaimer} style={{ borderRadius: 10 }} />
                  </div>
                </section>
                </div>
              </div>
            </>
          )}

          {!result && !loading && (
            <Card style={{ borderRadius: 12 }}>
              <Text strong>关于本模块</Text>
              <ul style={{ color: "#6b7280", fontSize: 13, lineHeight: 1.9, marginBottom: 0 }}>
                <li><b>本地指纹查重</b>：复刻 paper_checking 连续 13 字指纹算法，做「与本地文献库纵向比对 + 论文内部横向自查重」，离线即可运行，给出具体雷同片段；不等同知网等正式查重。</li>
                <li><b>参考文献真实性核验</b>：逐条解析参考文献，英文文献经 DOI / Crossref / OpenAlex 交叉验证，中文文献结合本地题录与格式规范核验，给出真实性状态、匹配来源与修改建议；开放库未收录不等于文献不存在，中文文献请以 CNKI/万方/维普人工复核为准。</li>
              </ul>
            </Card>
          )}
        </div>
      </ContentLayout>
    </MainLayout>
  )
}

function SummaryCard({ label, value, suffix, color }: { label: string; value: string; suffix?: string; color: string }) {
  return (
    <Card styles={{ body: { padding: "16px 18px" } }} style={{ borderRadius: 12 }}>
      <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
      <div style={{ fontSize: 30, fontWeight: 700, color, lineHeight: 1.2, marginTop: 4 }}>{value}{suffix && <span style={{ fontSize: 14, color: "#9ca3af", fontWeight: 400 }}> {suffix}</span>}</div>
    </Card>
  )
}

function SectionTitle({ icon, title, extra }: { icon: React.ReactNode; title: string; extra?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
      <Title level={4} style={{ margin: 0, color: "#7A1014" }}><span style={{ color: "#ef7d00", marginRight: 8 }}>{icon}</span>{title}</Title>
      {extra}
    </div>
  )
}

function MiniStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: "#f9fafb", borderRadius: 8, padding: "8px 12px", textAlign: "center" }}>
      <div style={{ fontSize: 11, color: "#9ca3af" }}>{label}</div>
      <div style={{ fontSize: 19, fontWeight: 700, color }}>{value}</div>
    </div>
  )
}

function ConfBar({ label, value }: { label: string; value?: number }) {
  const v = value ?? 0
  const color = v >= 0.7 ? "#15803d" : v >= 0.4 ? "#b45309" : "#9ca3af"
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#6b7280", marginBottom: 2 }}><span>{label}</span><span>{(v * 100).toFixed(0)}%</span></div>
      <Progress percent={v * 100} size="small" strokeColor={color} showInfo={false} />
    </div>
  )
}

function PlagiarismPanel({ plag }: { plag: PlagiarismResult }) {
  const segs = [...(plag.segments || [])].sort((a, b) => b.similarity_score - a.similarity_score)
  return (
    <Card style={{ borderRadius: 12 }}>
      <SectionTitle icon={<CopyOutlined />} title="一、本地指纹查重"
        extra={<Tag color={plag.risk_level === "low" ? "success" : plag.risk_level === "medium" ? "warning" : "error"}>{riskLabel(plag.risk_level)}</Tag>} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 10, marginBottom: 14 }}>
        <MiniStat label="总重复率" value={`${(plag.total_similarity * 100).toFixed(1)}%`} color={simColor(plag.total_similarity)} />
        <MiniStat label="内部重复" value={`${((plag.self_similarity || 0) * 100).toFixed(1)}%`} color="#b45309" />
        <MiniStat label="本地库重合" value={`${((plag.local_similarity || 0) * 100).toFixed(1)}%`} color="#1d4ed8" />
        <MiniStat label="比对库规模" value={`${plag.corpus_size ?? 0} 篇`} color="#6b7280" />
      </div>
      <Paragraph type="secondary" style={{ fontSize: 12.5, marginBottom: 6 }}>{plag.summary}</Paragraph>
      <Paragraph type="secondary" style={{ fontSize: 11.5, marginBottom: 14 }}>查重方法：{plag.check_method}。{plag.disclaimer}</Paragraph>
      {segs.length === 0 ? (
        <Alert type="success" showIcon message="未发现连续 13 字以上的雷同片段，原创性良好。" style={{ borderRadius: 10 }} />
      ) : (
        <Space direction="vertical" style={{ width: "100%" }} size={10}>
          {segs.map((s) => {
            const src = s.matched_sources?.[0] || {}
            const c = simColor(s.similarity_score)
            const isSelf = s.check_type === "self" || src.source_type === "self_duplicate"
            return (
              <div key={s.index} style={{ border: "1px solid #e5e7eb", borderLeft: `4px solid ${c}`, borderRadius: 10, padding: "12px 14px", background: isSelf ? "#fffbeb" : "#fef2f2" }}>
                <Space wrap size={6} style={{ marginBottom: 6 }}>
                  <Tag color={isSelf ? "warning" : "error"} style={{ margin: 0 }}>{isSelf ? "内部重复" : "本地库雷同"}</Tag>
                  <Tag style={{ margin: 0, color: c, borderColor: c, background: "#fff" }}>相似度 {(s.similarity_score * 100).toFixed(0)}%</Tag>
                  {src.title && <Text type="secondary" style={{ fontSize: 12 }}>来源：{src.title}</Text>}
                </Space>
                <div style={{ background: "#fff", borderLeft: "3px solid #d1d5db", padding: "7px 11px", borderRadius: 4, fontSize: 13, color: "#374151", marginBottom: 8, whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{s.text}</div>
                {src.snippet && src.snippet !== s.text && <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 6 }}><b>比对到的连续文字：</b>{src.snippet?.slice(0, 120)}</Paragraph>}
                <div style={{ fontSize: 12.5, marginBottom: 4 }}><b style={{ color: "#b91c1c" }}>判定：</b>{s.reason}</div>
                <div style={{ fontSize: 12.5 }}><b style={{ color: "#065f46" }}>建议：</b>{s.suggestion}</div>
              </div>
            )
          })}
        </Space>
      )}
    </Card>
  )
}

function ReferencesPanel({ refs }: { refs: ReferenceResult }) {
  const items = refs.items || []
  const countBy = (st: string[]) => items.filter((it) => st.includes(it.status)).length
  const stats = [
    { label: "已核验", n: countBy(["verified", "likely_real"]), color: "#15803d" },
    { label: "字段不一致", n: countBy(["likely_real_with_mismatch"]), color: "#b45309" },
    { label: "需人工核验", n: countBy(["insufficient_open_metadata"]), color: "#1d4ed8" },
    { label: "未检索到", n: countBy(["not_found"]), color: "#a16207" },
    { label: "疑似异常", n: countBy(["suspicious", "parse_failed", "check_failed"]), color: "#b91c1c" },
  ]
  return (
    <Card style={{ borderRadius: 12 }}>
      <SectionTitle icon={<SafetyOutlined />} title="二、参考文献真实性逐条核验"
        extra={<Tag color={refs.risk_level === "low" ? "success" : refs.risk_level === "medium" ? "warning" : "error"}>{refs.total_references} 条</Tag>} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
        {stats.map((s) => (
          <Tag key={s.label} style={{ fontSize: 13, padding: "3px 12px", borderRadius: 14, color: s.color, borderColor: s.color, background: "#fff" }}>{s.label} <b>{s.n}</b></Tag>
        ))}
      </div>
      {refs.chinese_web_configured === false && items.some((it) => it.language === "zh" && it.status === "insufficient_open_metadata") && (
        <Alert
          type="warning" showIcon style={{ borderRadius: 10, marginBottom: 12 }}
          message="中文参考文献尚未联网核查"
          description={
            <span style={{ lineHeight: 1.8 }}>
              当前英文 / 带 DOI 的文献已通过 Crossref、OpenAlex、Semantic Scholar 在线核验；中文文献仅做了本地题录库比对与格式核验，因此多数显示「需人工核验」。
              如需对<b>全部中文文献</b>在知网、万方、维普、国家哲学社会科学文献中心逐条联网核验，请在后端项目根目录的 <Text code>.env</Text> 中配置免费搜索密钥
              <Text code>SERPER_API_KEY</Text>（前往 serper.dev 注册即送免费额度），保存后重启后端即可，无需改动其他设置。
            </span>
          }
        />
      )}
      <Paragraph type="secondary" style={{ fontSize: 12.5, marginBottom: 14 }}>{refs.summary}</Paragraph>
      {items.length === 0 ? (
        <Empty description="未从文稿中解析出参考文献（请确认文稿含「参考文献」列表）" />
      ) : (
        <Space direction="vertical" style={{ width: "100%" }} size={10}>
          {items.map((it) => {
            const meta = REF_STATUS_META[it.status] || REF_STATUS_META.parse_failed
            const p = it.parsed || {} as any
            const matched = it.matched_sources?.[0]
            const providers = (it.provider_trace || []).filter((t) => t.called).map((t) => t.provider)
            return (
              <div key={it.index} style={{ border: "1px solid #e5e7eb", borderRadius: 10, overflow: "hidden" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "12px 14px", background: "#fafafa" }}>
                  <div style={{ flex: "0 0 26px", height: 26, borderRadius: "50%", background: "#7A1014", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700 }}>{it.index}</div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: "#1f2937", lineHeight: 1.7, wordBreak: "break-word" }}>{it.raw_reference}</div>
                    <div style={{ marginTop: 6 }}>
                      <Tag color={meta.color} icon={meta.icon} style={{ marginRight: 6 }}>{it.status_label || it.status}</Tag>
                      {it.language === "zh" ? <Tag>中文文献</Tag> : <Tag>英文文献</Tag>}
                      {it.local_match_status?.includes("verified") && <Tag color="success">本地题录命中</Tag>}
                    </div>
                  </div>
                </div>
                <div style={{ padding: "10px 14px", fontSize: 12.5 }}>
                  {(p.title || p.authors?.length || p.year || p.journal || p.doi) && (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 4, marginBottom: 8, color: "#4b5563" }}>
                      {p.title && <div><b>题名：</b>{p.title}</div>}
                      {p.authors?.length > 0 && <div><b>作者：</b>{p.authors.join("; ")}</div>}
                      {p.year && <div><b>年份：</b>{p.year}</div>}
                      {p.journal && <div><b>期刊/来源：</b>{p.journal}</div>}
                      {p.doi && <div style={{ wordBreak: "break-all" }}><b>DOI：</b>{p.doi}</div>}
                    </div>
                  )}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 8, marginBottom: 8 }}>
                    <ConfBar label="格式完整度" value={it.format_score} />
                    <ConfBar label="开放源匹配度" value={it.match_confidence} />
                    <ConfBar label="综合置信度" value={it.final_confidence} />
                  </div>
                  {matched && (
                    <div style={{ fontSize: 12, color: "#065f46", marginBottom: 6 }}>
                      <b>匹配来源：</b>{matched.provider || matched.source_type || "开放数据库"}{matched.matched_title || matched.title ? ` — ${matched.matched_title || matched.title}` : ""}
                      {providers.length > 0 && <Text type="secondary">（已检索：{providers.join("、")}）</Text>}
                    </div>
                  )}
                  {it.mismatch_fields?.length > 0 && <div style={{ fontSize: 12, color: "#b45309", marginBottom: 6 }}><b>字段不一致：</b>{it.mismatch_fields.join("、")}</div>}
                  {it.risk_reason && <div style={{ fontSize: 12.5, marginBottom: 4 }}><b style={{ color: "#b91c1c" }}>核验说明：</b>{it.risk_reason}</div>}
                  {it.suggestion && <div style={{ fontSize: 12.5, marginBottom: 6 }}><b style={{ color: "#065f46" }}>处理建议：</b>{it.suggestion}</div>}
                  {!["verified", "likely_real"].includes(it.status) && (it.manual_check_links?.length ?? 0) > 0 && (
                    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 6, marginTop: 2 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>一键人工核验：</Text>
                      {it.manual_check_links?.map((lk) => (
                        <a key={lk.name} href={lk.url} target="_blank" rel="noreferrer"
                          style={{ fontSize: 12, padding: "2px 10px", borderRadius: 12, border: "1px solid #7A1014", color: "#7A1014", background: "#fff", whiteSpace: "nowrap" }}>
                          {lk.name}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </Space>
      )}
      <Paragraph type="secondary" style={{ fontSize: 11.5, marginTop: 12, marginBottom: 0 }}>{refs.disclaimer || "开放数据库未收录不等于文献不存在，中文文献请结合 CNKI、万方、维普人工复核。"}</Paragraph>
    </Card>
  )
}
