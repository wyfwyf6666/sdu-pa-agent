'use client'

import { useMemo, useState, useCallback, useRef, useEffect } from 'react'
import MainLayout from '@/components/layout/MainLayout'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Download,
  PencilLine,
  RefreshCw,
  Send,
  Sparkles,
  Upload,
  FileText,
  Loader2,
  XCircle,
  Info,
  BookOpen,
  Search,
  Languages,
  Gauge,
  ShieldAlert,
  Lightbulb,
  FileCheck,
  Database,
  Crosshair,
  ListChecks,
  BarChart3,
  Wrench,
  type LucideIcon,
} from 'lucide-react'
import { submitFullReview, uploadFileForReview, exportReport, getReviewResult } from '@/services/pre-review'
import PdfManuscript from '@/components/pre-review/PdfManuscript'
import type {
  PreReviewResponse,
  ModuleKey,
  Annotation,
  OverallAssessment,
  ModuleResult,
  ChecklistItem,
  RiskWarning,
  RewriteExample,
} from '@/types/pre-review'
import { MODULE_NAMES, ALL_MODULES } from '@/types/pre-review'

type PagePhase = 'input' | 'reviewing' | 'results'
type RightTab = 'annotations' | 'overall' | 'checklist' | 'extras'
type SevFilter = 'all' | '严重' | '一般' | '建议'

const moduleIcons: Record<ModuleKey, LucideIcon> = {
  references: BookOpen,
  depth: Search,
  language: PencilLine,
  literature: Lightbulb,
  reviewers: Gauge,
  journals: FileCheck,
  comparison: FileText,
  translation: Languages,
  format: FileCheck,
  data_methods: Database,
}

// 默认只勾选核心审稿模块，避免默认触发整篇翻译等耗时且模板化的任务
const DEFAULT_MODULES: ModuleKey[] = [
  'references', 'depth', 'language', 'format', 'data_methods', 'literature', 'journals',
]

const CORE_MODULE_FILTERS: { key: string; name: string }[] = [
  { key: 'depth', name: '深度论证' },
  { key: 'language', name: '语言表达' },
  { key: 'references', name: '文献引用' },
  { key: 'format', name: '格式规范' },
  { key: 'data_methods', name: '数据方法' },
]

const SEV_STYLE: Record<string, {
  text: string; badge: string; mark: string; bar: string; soft: string; border: string; dot: string
}> = {
  '严重': {
    text: 'text-red-700', badge: 'bg-red-600 text-white', mark: 'bg-red-200 text-red-950 rounded px-0.5',
    bar: 'bg-red-500', soft: 'bg-red-50', border: 'border-red-200', dot: 'bg-red-500',
  },
  '一般': {
    text: 'text-amber-700', badge: 'bg-amber-500 text-white', mark: 'bg-amber-200 text-amber-950 rounded px-0.5',
    bar: 'bg-amber-500', soft: 'bg-amber-50/70', border: 'border-amber-200', dot: 'bg-amber-500',
  },
  '建议': {
    text: 'text-blue-700', badge: 'bg-blue-500 text-white', mark: 'bg-blue-200 text-blue-950 rounded px-0.5',
    bar: 'bg-blue-500', soft: 'bg-blue-50/70', border: 'border-blue-200', dot: 'bg-blue-500',
  },
}

const sevRank = (s: string) => (s === '严重' ? 0 : s === '一般' ? 1 : 2)

// ---------------------------------------------------------------------------
// 原文摘录定位工具：直接匹配 → 压缩空白匹配（带索引映射）
// ---------------------------------------------------------------------------
function findRange(text: string, quote: string): [number, number] | null {
  if (!quote || !text) return null
  const direct = text.indexOf(quote)
  if (direct >= 0) return [direct, direct + quote.length]
  const isWs = (ch: string) => /\s/.test(ch)
  const cq = quote.replace(/\s+/g, '')
  if (cq.length < 4) return null
  const map: number[] = []
  let ct = ''
  for (let i = 0; i < text.length; i++) {
    if (!isWs(text[i])) {
      ct += text[i]
      map.push(i)
    }
  }
  const ci = ct.indexOf(cq)
  if (ci < 0) return null
  const start = map[ci]
  const endIdx = Math.min(ci + cq.length - 1, map.length - 1)
  return [start, map[endIdx] + 1]
}

interface HighlightRange {
  start: number
  end: number
  annIds: number[]
  severity: string
}

function buildHighlights(text: string, anns: Annotation[]): HighlightRange[] {
  const raw: HighlightRange[] = []
  for (const a of anns) {
    if (a.paragraph < 1) continue
    const r = findRange(text, a.quote)
    if (!r) continue
    raw.push({ start: r[0], end: r[1], annIds: [a.id], severity: a.severity })
  }
  if (raw.length === 0) return []
  raw.sort((x, y) => x.start - y.start || y.end - x.end)
  // 合并重叠区间，严重度取最高
  const merged: HighlightRange[] = []
  for (const r of raw) {
    const last = merged[merged.length - 1]
    if (last && r.start <= last.end) {
      last.end = Math.max(last.end, r.end)
      last.annIds = Array.from(new Set([...last.annIds, ...r.annIds]))
      if (sevRank(r.severity) < sevRank(last.severity)) last.severity = r.severity
    } else {
      merged.push({ ...r, annIds: [...r.annIds] })
    }
  }
  return merged
}

const sampleTitle = '基于系统动力学的城市共享电单车动态规模预测与调控策略研究'
const sampleSubtitle = '——以青岛市即墨区为例'
const sampleManuscript = `王怡帆  基于系统动力学的城市共享电单车动态规模预测与调控策略研究
——以青岛市即墨区为例

一、研究背景
共享单车是共享经济和绿色低碳出行模式的典型代表，其健康发展与多项国家战略紧密相连。

1. 国家治理体系与治理能力现代化：共享单车带来的"过度投放""乱停乱放"和报废潮等问题，是城市治理能力现代化的重要检验。

2. 城市精细化治理：共享电单车在社区、商圈、校园和交通枢纽的分布不均，反映出基础设施、需求响应与政策调控之间的张力。

3. 研究意义：通过系统动力学方法预测动态规模，有助于为地方政府、平台企业与执法部门提供协同治理参考。

二、研究思路
本文拟构建需求、投放、损耗、回收和治理干预之间的动态反馈模型，分析不同政策情景下共享电单车规模变化。

三、研究方法
本文采用系统动力学方法，构建城市共享电单车动态规模预测与调控模型。通过Vensim软件进行仿真模拟，设置基准情景、强监管情景和弱监管情景三种政策情景。

四、案例分析
选取青岛市即墨区为案例，基于2020-2023年共享电单车运营数据，分析需求量、投放量、回收量和监管强度之间的动态关系。

五、结论
研究结果表明，适度的政策干预可以有效平衡共享电单车的供需关系，建议采用动态配额管理和分区定价策略。

六、参考文献
[1] 张三. 共享经济与城市治理研究[J]. 公共管理学报, 2020, 17(3): 45-58.
[2] 李四. 系统动力学在公共政策分析中的应用[M]. 北京: 科学出版社, 2019.
[3] Smith J. Urban Mobility and Shared Economy[J]. Journal of Public Policy, 2021, 41(2): 112-130.`

export default function PreReviewPage() {
  const [phase, setPhase] = useState<PagePhase>('input')
  const [title, setTitle] = useState('')
  const [subtitle, setSubtitle] = useState('')
  const [manuscript, setManuscript] = useState('')
  const [selectedModules, setSelectedModules] = useState<ModuleKey[]>([...DEFAULT_MODULES])
  const [result, setResult] = useState<PreReviewResponse | null>(null)
  const [error, setError] = useState('')
  const [progressText, setProgressText] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 两栏联动状态
  const [rightTab, setRightTab] = useState<RightTab>('annotations')
  const [sevFilter, setSevFilter] = useState<SevFilter>('all')
  const [modFilter, setModFilter] = useState<string>('all')
  const [activePara, setActivePara] = useState<number | null>(null)
  const [activeAnn, setActiveAnn] = useState<number | null>(null)
  const [pdfJump, setPdfJump] = useState<{ page: number; annId: number | null } | null>(null)
  const paraRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({})

  const annotations = useMemo(() => result?.annotations ?? [], [result])

  const paragraphs = useMemo(() => {
    if (!result) return []
    if (result.paragraphs && result.paragraphs.length) return result.paragraphs
    return (result.raw_text || '')
      .split(/\n+/)
      .map((p) => p.trim())
      .filter(Boolean)
  }, [result])

  const annsByPara = useMemo(() => {
    const map = new Map<number, Annotation[]>()
    for (const a of annotations) {
      if (a.paragraph > 0) {
        const list = map.get(a.paragraph) || []
        list.push(a)
        map.set(a.paragraph, list)
      }
    }
    map.forEach((list) => {
      list.sort((x, y) => sevRank(x.severity) - sevRank(y.severity))
    })
    return map
  }, [annotations])

  const sevCount = useMemo(() => {
    const c = { '严重': 0, '一般': 0, '建议': 0 }
    for (const a of annotations) if (a.severity in c) c[a.severity as keyof typeof c]++
    return c
  }, [annotations])

  const filteredAnnotations = useMemo(() => {
    return annotations
      .filter((a) => (sevFilter === 'all' ? true : a.severity === sevFilter))
      .filter((a) => (modFilter === 'all' ? true : a.module === modFilter))
      .sort((a, b) => {
        const s = sevRank(a.severity) - sevRank(b.severity)
        return s !== 0 ? s : (a.paragraph || 9999) - (b.paragraph || 9999)
      })
  }, [annotations, sevFilter, modFilter])

  const depthItems = useMemo(() => {
    const m = result?.module_results.find((x) => x.module_key === 'depth')
    if (!m) return []
    return m.items
      .filter((it: Record<string, any>) => typeof it.score === 'number')
      .map((it: Record<string, any>) => ({ label: String(it.label), score: Number(it.score), note: String(it.note || '') }))
  }, [result])

  const averageScore = useMemo(() => {
    if (depthItems.length) return Math.round(depthItems.reduce((a, b) => a + b.score, 0) / depthItems.length)
    return result?.overall_assessment.overall_score ?? 0
  }, [depthItems, result])

  const extraModules = useMemo(() => {
    return (result?.module_results || []).filter(
      (m) => ['literature', 'journals', 'reviewers', 'comparison', 'translation'].includes(m.module_key) && m.items.length > 0
    )
  }, [result])

  const loadExample = useCallback(() => {
    setTitle(sampleTitle)
    setSubtitle(sampleSubtitle)
    setManuscript(sampleManuscript)
    setPhase('input')
    setResult(null)
    setError('')
  }, [])

  const resetReviewState = () => {
    setRightTab('annotations'); setSevFilter('all'); setModFilter('all')
    setActivePara(null); setActiveAnn(null)
  }

  // 支持通过 ?request_id=<id> 直接恢复一次已完成的审阅结果（刷新或分享链接不丢结果）
  useEffect(() => {
    if (typeof window === 'undefined') return
    const rid = new URLSearchParams(window.location.search).get('request_id')
    if (!rid) return
    let cancelled = false
    setPhase('reviewing')
    setProgressText('正在恢复审阅结果...')
    getReviewResult(rid)
      .then((res) => {
        if (cancelled) return
        setTitle(res.title || '')
        setManuscript(res.raw_text || '')
        setResult(res)
        setRightTab('annotations'); setSevFilter('all'); setModFilter('all')
        setActivePara(null); setActiveAnn(null)
        setPhase('results')
      })
      .catch(() => { if (!cancelled) setPhase('input') })
    return () => { cancelled = true }
  }, [])

  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    setPhase('reviewing')
    setProgressText('正在解析文件并逐段通读全文...')
    try {
      const res = await uploadFileForReview(file)
      setTitle(res.title || file.name.replace(/\.[^.]+$/, ''))
      setManuscript(res.raw_text || '')
      setResult(res)
      resetReviewState()
      setPhase('results')
    } catch (err: any) {
      const msg = err.message || '文件上传失败'
      if (msg.includes('无法提取有效文本') || msg.includes('扫描图片')) {
        setError(msg + '\n\n建议：请直接将论文文字内容复制粘贴到下方文本框中提交。')
      } else {
        setError(msg)
      }
      setPhase('input')
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [])

  const handleSubmit = useCallback(async () => {
    if (!manuscript.trim()) {
      setError('请输入或粘贴论文内容')
      return
    }
    if (manuscript.trim().length < 50) {
      setError('文稿内容过短，请至少提供50字以上内容')
      return
    }
    setError('')
    setPhase('reviewing')
    setProgressText('正在逐段通读全文并定位问题，请稍候...')
    try {
      const fullTitle = subtitle ? `${title}${subtitle}` : title || '未命名文稿'
      const res = await submitFullReview(fullTitle, manuscript, selectedModules)
      setResult(res)
      resetReviewState()
      setPhase('results')
    } catch (err: any) {
      setError(err.message || '分析失败，请重试')
      setPhase('input')
    }
  }, [title, subtitle, manuscript, selectedModules])

  const handleExport = useCallback(async (format: 'html' | 'txt' = 'html') => {
    if (!result) return
    // 在点击手势的同步阶段先打开窗口，避免 await 网络请求后 window.open 被浏览器拦截
    let w: Window | null = null
    if (format === 'html') {
      w = window.open('', '_blank', 'width=900,height=700')
    }
    const downloadFile = (content: string, mime: string, ext: string) => {
      const blob = new Blob([content], { type: `${mime};charset=utf-8` })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `审阅报告_${result.title.slice(0, 20)}.${ext}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    }
    try {
      const content = await exportReport(result.request_id, format)
      if (format === 'html') {
        if (w) {
          w.document.write(content)
          w.document.close()
          w.focus()
        } else {
          // 弹窗被拦截时降级为下载 HTML 文件，双击即可打开并打印为 PDF
          downloadFile(content, 'text/html', 'html')
        }
      } else {
        downloadFile(content, 'text/plain', 'txt')
      }
    } catch {
      if (w && !w.closed) w.close()
      setError('导出失败，请稍后重试或重新分析。')
    }
  }, [result])

  const toggleModule = (key: ModuleKey) => {
    setSelectedModules((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    )
  }

  // 右栏意见 → 左栏原文定位
  const focusParagraph = useCallback((para: number, annId?: number) => {
    if (para < 1) return
    setActivePara(para)
    if (annId !== undefined) setActiveAnn(annId)
    requestAnimationFrame(() => {
      paraRefs.current[para]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }, [])

  // 右栏意见 → 左栏原文定位（PDF 模式跳页，文字模式滚动段落）
  const locateAnnotation = useCallback((a: Annotation) => {
    if (result?.pdf_url && a.page && a.page > 0 && Array.isArray(a.bbox) && a.bbox.length === 4) {
      setActiveAnn(a.id)
      setPdfJump({ page: a.page, annId: a.id })
      return
    }
    focusParagraph(a.paragraph, a.id)
  }, [result, focusParagraph])

  // 左栏高亮 → 右栏意见定位
  const focusAnnotation = useCallback((annId: number) => {
    setRightTab('annotations')
    setSevFilter('all')
    setModFilter('all')
    setActiveAnn(annId)
    setTimeout(() => {
      cardRefs.current[annId]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 80)
  }, [])

  const goBackToInput = () => {
    setPhase('input')
    setResult(null)
    setError('')
  }

  return (
    <MainLayout>
      <div className="min-h-screen bg-[#f7f4ec] text-slate-900">
        {/* Top bar */}
        <div className="border-b border-[#eadbbf] bg-[#fbf8f0]">
          <div className="mx-auto flex max-w-[1600px] items-center justify-between px-4 py-3">
            <div className="flex items-center gap-3">
              <img
                src="/sdu-spa-logo.jpg"
                alt="山大政管学院院徽"
                className="h-10 w-10 rounded-full object-cover border-2 border-[#e3c58b]"
              />
              <div>
                <div className="text-lg font-bold text-[#8a4f00]">山大政管·砺文智审系统</div>
                <div className="text-xs text-[#a27739]">论文智能预审与学术写作辅助</div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {phase === 'results' && result && (
                <>
                  <button
                    onClick={() => handleExport('txt')}
                    className="rounded-full border border-[#e6e1d3] bg-white px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                  >
                    <Download className="mr-1.5 inline-block h-4 w-4" />
                    导出 TXT
                  </button>
                  <button
                    onClick={() => handleExport('html')}
                    className="rounded-full bg-[#ef7d00] px-5 py-2 text-sm font-semibold text-white hover:bg-[#d66d00]"
                    title="在新窗口打开格式化报告，可通过浏览器打印为 PDF"
                  >
                    <Download className="mr-1.5 inline-block h-4 w-4" />
                    导出审阅报告
                  </button>
                </>
              )}
              <button
                onClick={() => (phase === 'results' ? goBackToInput() : loadExample())}
                className="rounded-full border border-[#e6e1d3] bg-white px-5 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                <RefreshCw className="mr-2 inline-block h-4 w-4" />
                {phase === 'results' ? '重新分析' : '加载示例'}
              </button>
              {phase === 'input' && (
                <button
                  onClick={handleSubmit}
                  disabled={!manuscript.trim()}
                  className="rounded-full bg-[#ef7d00] px-5 py-2 text-sm font-semibold text-white hover:bg-[#d66d00] disabled:opacity-50"
                >
                  <Send className="mr-2 inline-block h-4 w-4" />
                  全面分析
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="mx-auto max-w-[1600px] px-4 py-4">
          {/* Breadcrumb / status bar */}
          <div className="mb-3 flex items-center gap-3 text-sm text-slate-600">
            <ArrowLeft className="h-4 w-4 cursor-pointer" onClick={goBackToInput} />
            <span className="cursor-pointer hover:text-slate-900" onClick={goBackToInput}>返回</span>
            {result && <span className="font-medium text-slate-900">{result.title}</span>}
            <span className="rounded-full bg-[#f4efe3] px-3 py-1 text-xs text-[#9a6732]">
              AI 生成仅供参考，请注意甄别
            </span>
          </div>

          {/* Error message */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="mb-4 whitespace-pre-line rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
              >
                <XCircle className="mr-2 inline-block h-4 w-4" />
                {error}
                <button onClick={() => setError('')} className="ml-3 underline">关闭</button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Phase: Input */}
          {phase === 'input' && (
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
              <section className="rounded-2xl border border-[#eadbbf] bg-white shadow-sm p-5">
                <h2 className="mb-4 text-lg font-semibold text-slate-900 flex items-center gap-2">
                  <FileText className="h-5 w-5 text-[#d06a00]" />
                  提交文稿进行预审
                </h2>

                <div className="grid gap-4 mb-4 lg:grid-cols-3">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">论文标题</label>
                    <input
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="输入论文标题（可选）"
                      className="w-full rounded-xl border border-[#ece2cf] bg-[#fffdf8] px-4 py-2.5 text-sm text-slate-900 outline-none focus:border-[#ef7d00]"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">副标题（可选）</label>
                    <input
                      type="text"
                      value={subtitle}
                      onChange={(e) => setSubtitle(e.target.value)}
                      placeholder="如：——以XX为例"
                      className="w-full rounded-xl border border-[#ece2cf] bg-[#fffdf8] px-4 py-2.5 text-sm text-slate-900 outline-none focus:border-[#ef7d00]"
                    />
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".txt,.pdf,.docx"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full rounded-xl border border-dashed border-[#e3c58b] bg-[#fdfaf3] px-4 py-2.5 text-sm text-slate-600 hover:bg-[#fbf6ea] transition-colors"
                    >
                      <Upload className="mr-2 inline-block h-4 w-4" />
                      上传文件 (.txt / .pdf / .docx)
                    </button>
                    <p className="text-xs text-amber-600">提示：扫描版或文字层损坏的 PDF 将自动 OCR 识别，页数较多时请耐心等待，期间请勿关闭页面</p>
                  </div>
                </div>

                <label className="block text-sm font-medium text-slate-700 mb-1">论文内容</label>
                <textarea
                  value={manuscript}
                  onChange={(e) => setManuscript(e.target.value)}
                  className="h-[360px] w-full resize-none rounded-xl border border-[#ece2cf] bg-[#fffdf8] p-4 text-[15px] leading-8 text-slate-900 outline-none focus:border-[#ef7d00]"
                  placeholder="在此粘贴论文全文、摘要或部分段落...&#10;&#10;提示：系统将逐段通读全文，内容越完整，定位越准确。至少需要50字。"
                />

                {/* Module selection */}
                <div className="mt-4">
                  <label className="block text-sm font-medium text-slate-700 mb-2">
                    分析模块（可勾选；默认核心审稿项，翻译/过刊比较等建议类任务请按需勾选）
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {ALL_MODULES.map((key) => {
                      const Icon = moduleIcons[key]
                      const sel = selectedModules.includes(key)
                      return (
                        <button
                          key={key}
                          onClick={() => toggleModule(key)}
                          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs transition-colors ${
                            sel
                              ? 'bg-[#ef7d00] text-white'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          }`}
                        >
                          <Icon className="h-3.5 w-3.5" />
                          {MODULE_NAMES[key]}
                        </button>
                      )
                    })}
                  </div>
                </div>

                <div className="mt-4 flex justify-end">
                  <button
                    onClick={handleSubmit}
                    disabled={!manuscript.trim() || manuscript.trim().length < 50}
                    className="rounded-full bg-[#ef7d00] px-6 py-2.5 text-sm font-semibold text-white hover:bg-[#d66d00] disabled:opacity-50 transition-all"
                  >
                    <Sparkles className="mr-2 inline-block h-4 w-4" />
                    开始预审分析
                  </button>
                </div>
              </section>

              {/* System info */}
              <section className="rounded-2xl border border-[#eadbbf] bg-white px-5 py-4 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-950 flex items-center gap-2">
                  <Info className="h-5 w-5 text-[#d06a00]" />
                  系统说明
                </h2>
                <p className="mt-3 text-sm leading-7 text-slate-600">
                  山大政管·砺文智审系统面向政治学与公共管理学院场景下的论文智能预审与学术写作辅助。系统会逐段通读全文，每一条意见都附原文摘录与段落定位，点击即可在原文与意见之间双向对照；不替代导师、审稿人或学校最终审核，只提供提交前的规范化建设性检查。
                </p>
              </section>
            </motion.div>
          )}

          {/* Phase: Reviewing */}
          {phase === 'reviewing' && (
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex flex-col items-center justify-center py-24"
            >
              <div className="flex h-20 w-20 items-center justify-center rounded-full bg-[#fef7eb] border border-[#f0c56a] mb-6">
                <Loader2 className="h-10 w-10 text-[#ef7d00] animate-spin" />
              </div>
              <h2 className="text-xl font-semibold text-slate-900 mb-2">正在逐段智能预审</h2>
              <p className="text-sm text-slate-500 mb-8">{progressText || '正在通读全文并定位问题...'}</p>
              <div className="flex flex-wrap justify-center gap-2 max-w-2xl">
                {selectedModules.map((key, idx) => (
                  <span key={key} className="rounded-full bg-[#f5f1e7] px-3 py-1.5 text-xs text-slate-600 animate-pulse" style={{ animationDelay: `${idx * 100}ms` }}>
                    {MODULE_NAMES[key]}
                  </span>
                ))}
              </div>
              <p className="mt-8 text-xs text-slate-400">系统正在逐段通读全文并核对原文，长文预计需要 30-90 秒</p>
            </motion.div>
          )}

          {/* Phase: Results —— 左右两栏联动 */}
          {phase === 'results' && result && (
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
              <div className="grid gap-4 lg:grid-cols-2">
                {/* 左栏：原文（PDF 上传时渲染原始 PDF 页+荧光笔，否则文字段落视图） */}
                <ManuscriptPane
                  title={result.title}
                  docType={result.overall_assessment.document_type}
                  paragraphs={paragraphs}
                  annsByPara={annsByPara}
                  totalAnns={annotations.length}
                  activePara={activePara}
                  activeAnn={activeAnn}
                  paraRefs={paraRefs}
                  onMarkClick={focusAnnotation}
                  onBadgeClick={(para) => {
                    const first = annsByPara.get(para)?.[0]
                    if (first) focusAnnotation(first.id)
                  }}
                  pdfUrl={result.pdf_url || ''}
                  annotations={annotations}
                  pdfJump={pdfJump}
                />

                {/* 右栏：审阅意见 */}
                <section className="flex min-h-[680px] flex-col overflow-hidden rounded-2xl border border-[#eadbbf] bg-white shadow-sm lg:h-[calc(100vh-150px)]">
                  {/* 统计 + Tabs */}
                  <div className="border-b border-[#f0eadc] px-4 pt-3">
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                      <div className="mr-1 flex items-baseline gap-1">
                        <span className="text-2xl font-bold text-[#d06a00]">{averageScore}</span>
                        <span className="text-xs text-slate-400">/100</span>
                      </div>
                      <button
                        onClick={() => { setRightTab('annotations'); setSevFilter('严重') }}
                        className="rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs text-red-700 hover:bg-red-100"
                      >
                        严重 {sevCount['严重']}
                      </button>
                      <button
                        onClick={() => { setRightTab('annotations'); setSevFilter('一般') }}
                        className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs text-amber-700 hover:bg-amber-100"
                      >
                        一般 {sevCount['一般']}
                      </button>
                      <button
                        onClick={() => { setRightTab('annotations'); setSevFilter('建议') }}
                        className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs text-blue-700 hover:bg-blue-100"
                      >
                        建议 {sevCount['建议']}
                      </button>
                    </div>
                    <div className="flex flex-wrap items-center gap-1 text-sm">
                      <TabButton active={rightTab === 'annotations'} onClick={() => setRightTab('annotations')} icon={ListChecks}>
                        逐条意见{annotations.length ? ` (${annotations.length})` : ''}
                      </TabButton>
                      <TabButton active={rightTab === 'overall'} onClick={() => setRightTab('overall')} icon={BarChart3}>
                        总体与评分
                      </TabButton>
                      <TabButton active={rightTab === 'checklist'} onClick={() => setRightTab('checklist')} icon={Wrench}>
                        修改清单
                      </TabButton>
                      {extraModules.length > 0 && (
                        <TabButton active={rightTab === 'extras'} onClick={() => setRightTab('extras')} icon={Lightbulb}>
                          参考建议
                        </TabButton>
                      )}
                    </div>
                  </div>

                  <div className="min-h-0 flex-1 overflow-y-auto p-4">
                    <AnimatePresence mode="wait">
                      {rightTab === 'annotations' && (
                        <motion.div key="ann" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                          {/* 筛选器 */}
                          <div className="mb-3 flex flex-wrap items-center gap-1.5">
                            <FilterChip active={sevFilter === 'all'} onClick={() => setSevFilter('all')}>全部严重度</FilterChip>
                            <span className="mx-1 h-3 w-px bg-slate-200" />
                            {CORE_MODULE_FILTERS.map((m) => (
                              <FilterChip key={m.key} active={modFilter === m.key} onClick={() => setModFilter(modFilter === m.key ? 'all' : m.key)}>
                                {m.name}
                              </FilterChip>
                            ))}
                          </div>
                          {filteredAnnotations.length === 0 ? (
                            <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
                              {annotations.length === 0
                                ? '本次审查未生成带原文定位的意见，可查看"总体与评分"页签。'
                                : '当前筛选条件下没有意见。'}
                            </div>
                          ) : (
                            <div className="space-y-3">
                              {filteredAnnotations.map((a) => {
                                const st = SEV_STYLE[a.severity] || SEV_STYLE['一般']
                                return (
                                  <div
                                    key={a.id}
                                    ref={(el) => { cardRefs.current[a.id] = el }}
                                    className={`rounded-xl border ${st.border} ${st.soft} p-3 transition-all duration-300 ${
                                      activeAnn === a.id ? 'ring-2 ring-[#ef7d00] ring-offset-1 shadow-md' : ''
                                    }`}
                                  >
                                    <div className="mb-1.5 flex flex-wrap items-center gap-2">
                                      <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${st.badge}`}>{a.severity}</span>
                                      <span className="rounded-md border border-slate-200 bg-white/80 px-2 py-0.5 text-xs text-slate-600">
                                        {a.module_name}
                                      </span>
                                      {(a.paragraph > 0 || (a.page && Array.isArray(a.bbox))) && (
                                        <button
                                          onClick={() => locateAnnotation(a)}
                                          className="ml-auto inline-flex items-center gap-1 rounded-md border border-[#e3c58b] bg-[#fef7eb] px-2 py-0.5 text-xs text-[#9a5c00] hover:bg-[#fdeecd]"
                                          title="在左侧原文中定位"
                                        >
                                          <Crosshair className="h-3 w-3" />
                                          {a.page && Array.isArray(a.bbox) ? `定位到第 ${a.page} 页` : `定位到第 ${a.paragraph} 段`}
                                        </button>
                                      )}
                                    </div>
                                    {a.quote && (
                                      <>
                                        <blockquote className="mt-1 border-l-[3px] border-slate-300 bg-white/80 px-3 py-1.5 text-[13px] leading-6 text-slate-700">
                                          {a.quote}
                                        </blockquote>
                                        {!a.quote_matched && (
                                          <div className="mt-0.5 text-[11px] text-slate-400">摘录与原文未能逐字匹配，已按段落定位</div>
                                        )}
                                      </>
                                    )}
                                    <div className="mt-2 text-[13px] leading-6 text-slate-800">
                                      <span className="font-semibold text-slate-900">问题：</span>{a.issue}
                                    </div>
                                    {a.suggestion && (
                                      <div className="mt-1 text-[13px] leading-6 text-emerald-800">
                                        <span className="font-semibold">修改建议：</span>{a.suggestion}
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </motion.div>
                      )}

                      {rightTab === 'overall' && (
                        <motion.div key="overall" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                          <OverallTab assessment={result.overall_assessment} depthItems={depthItems} averageScore={averageScore} />
                        </motion.div>
                      )}

                      {rightTab === 'checklist' && (
                        <motion.div key="check" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                          <ChecklistTab
                            checklist={result.modification_checklist}
                            risks={result.risk_warnings}
                            rewrites={result.rewrite_examples}
                          />
                        </motion.div>
                      )}

                      {rightTab === 'extras' && (
                        <motion.div key="extras" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-5">
                          {extraModules.map((m) => (
                            <ModulePanel key={m.module_key} module={m} />
                          ))}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </section>
              </div>

              {/* 底部说明 */}
              <section className="mt-4 rounded-2xl border border-[#eadbbf] bg-white px-5 py-3 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="flex items-start gap-2 text-xs leading-6 text-slate-500">
                    <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#d06a00]" />
                    本报告由 AI 逐段通读原文生成，每条意见均附原文摘录与段落定位，供修改参考；AI 可能存在误判，请结合导师意见、课程要求与学院规范综合判断。
                  </p>
                  <button
                    onClick={() => handleExport('html')}
                    className="shrink-0 rounded-full bg-[#ef7d00] px-5 py-2 text-sm font-semibold text-white hover:bg-[#d66d00]"
                  >
                    <Download className="mr-1.5 inline-block h-4 w-4" />
                    导出审阅报告（HTML / 打印 PDF）
                  </button>
                </div>
              </section>
            </motion.div>
          )}
        </div>
      </div>
    </MainLayout>
  )
}

// ---------------------------------------------------------------------------
// 左栏：原文
// ---------------------------------------------------------------------------
function ManuscriptPane({
  title, docType, paragraphs, annsByPara, totalAnns, activePara, activeAnn,
  paraRefs, onMarkClick, onBadgeClick, pdfUrl, annotations, pdfJump,
}: {
  title: string
  docType: string
  paragraphs: string[]
  annsByPara: Map<number, Annotation[]>
  totalAnns: number
  activePara: number | null
  activeAnn: number | null
  paraRefs: React.MutableRefObject<Record<number, HTMLDivElement | null>>
  onMarkClick: (annId: number) => void
  onBadgeClick: (para: number) => void
  pdfUrl?: string
  annotations?: Annotation[]
  pdfJump?: { page: number; annId: number | null } | null
}) {
  if (pdfUrl) {
    return (
      <PdfManuscript
        pdfPath={pdfUrl}
        title={title}
        annotations={annotations || []}
        activeAnn={activeAnn}
        jump={pdfJump || null}
        onMarkClick={onMarkClick}
      />
    )
  }
  return (
    <section className="flex min-h-[680px] flex-col overflow-hidden rounded-2xl border border-[#eadbbf] bg-white shadow-sm lg:h-[calc(100vh-150px)]">
      <div className="border-b border-[#f0eadc] px-5 py-3">
        <div className="truncate text-base font-semibold text-slate-900">{title}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
          <span>文稿类型：{docType}</span>
          <span>共 {paragraphs.length} 段</span>
          <span className="font-medium text-[#d06a00]">{totalAnns} 条意见已在原文标注</span>
        </div>
      </div>
      <div className="flex items-center justify-between border-b border-[#f7f1e4] bg-[#fdfaf3] px-4 py-1.5 font-sans text-[11px] text-slate-500">
        <span>点击文中高亮处可跳转右侧对应意见</span>
        <span className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-red-200" />严重</span>
          <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-200" />一般</span>
          <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-blue-200" />建议</span>
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto bg-[#fffdf8] px-4 py-3">
        {paragraphs.length === 0 ? (
          <p className="p-4 font-sans text-sm text-slate-400">暂无文稿内容 — 如果上传了 PDF 但此处空白，请刷新页面重新上传，或直接粘贴文字。</p>
        ) : (
          <div className="space-y-1.5 font-serif text-[15px] leading-8 text-slate-800">
            {paragraphs.map((text, idx) => {
              const pno = idx + 1
              const anns = annsByPara.get(pno) || []
              const ranges = buildHighlights(text, anns)
              const topSev = anns.length ? anns.slice().sort((a, b) => sevRank(a.severity) - sevRank(b.severity))[0].severity : null
              const st = topSev ? SEV_STYLE[topSev] : null
              const isActive = activePara === pno
              return (
                <div
                  key={pno}
                  ref={(el) => { paraRefs.current[pno] = el }}
                  className={`rounded-lg border-l-4 px-3 py-2 transition-all duration-300 ${
                    isActive ? 'ring-2 ring-[#ef7d00] ring-offset-1' : ''
                  } ${st ? st.soft : 'border-transparent'}`}
                  style={{ borderLeftColor: st ? undefined : 'transparent' }}
                >
                  <div className="mb-0.5 flex items-center gap-2 font-sans">
                    <span className="select-none text-[11px] font-medium text-slate-400">P{pno}</span>
                    {anns.length > 0 && (
                      <button
                        onClick={() => onBadgeClick(pno)}
                        className={`ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ${
                          st ? st.badge : 'bg-slate-100 text-slate-500'
                        }`}
                        title="查看该段全部意见"
                      >
                        <AlertTriangle className="h-3 w-3" />
                        {anns.length} 条意见
                      </button>
                    )}
                  </div>
                  <p className="whitespace-pre-wrap">
                    {ranges.length === 0 ? text : (
                      (() => {
                        const parts: React.ReactNode[] = []
                        let cursor = 0
                        ranges.forEach((r, i) => {
                          if (r.start > cursor) parts.push(<span key={`t${i}`}>{text.slice(cursor, r.start)}</span>)
                          const rSt = SEV_STYLE[r.severity] || SEV_STYLE['一般']
                          const involved = r.annIds.includes(activeAnn || -1)
                          parts.push(
                            <mark
                              key={`m${i}`}
                              onClick={() => onMarkClick(r.annIds[0])}
                              className={`cursor-pointer ${rSt.mark} ${involved ? 'ring-2 ring-[#ef7d00]' : ''} hover:brightness-95`}
                              title="点击查看审阅意见"
                            >
                              {text.slice(r.start, r.end)}
                            </mark>
                          )
                          cursor = r.end
                        })
                        if (cursor < text.length) parts.push(<span key="tail">{text.slice(cursor)}</span>)
                        return parts
                      })()
                    )}
                  </p>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// 右栏 Tab：总体与评分
// ---------------------------------------------------------------------------
function OverallTab({ assessment, depthItems, averageScore }: {
  assessment: OverallAssessment
  depthItems: { label: string; score: number; note: string }[]
  averageScore: number
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-[#f1eadb] bg-[#fffdf9] p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-500">文稿类型</div>
            <div className="text-sm font-medium text-slate-800">{assessment.document_type}</div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold text-[#d06a00]">{averageScore}<span className="text-sm text-slate-400">/100</span></div>
            <div className="text-xs text-slate-400">综合评分</div>
          </div>
        </div>
        <p className="mt-3 text-sm leading-7 text-slate-700">{assessment.completion_level}</p>
        {assessment.priority && (
          <div className="mt-3 rounded-xl border-l-4 border-[#ef7d00] bg-[#fef7eb] px-3 py-2 text-sm text-[#8a4f00]">
            <span className="font-semibold">最优先修改：</span>{assessment.priority}
          </div>
        )}
      </div>

      {depthItems.length > 0 && (
        <div className="rounded-2xl border border-[#f1eadb] p-4">
          <div className="mb-1 text-sm font-semibold text-slate-900">八维度评分</div>
          <RadarChart data={depthItems.map((d) => ({ label: d.label, score: d.score }))} />
          <div className="mt-2 space-y-2.5">
            {depthItems.map((item, idx) => (
              <div key={idx}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-slate-700">{item.label}</span>
                  <span className="font-semibold text-[#d06a00]">{item.score}/100</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-[#ef7d00]" style={{ width: `${item.score}%` }} />
                </div>
                {item.note && <p className="mt-1 text-xs leading-5 text-slate-500">{item.note}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-3">
          <p className="mb-1.5 flex items-center gap-1 text-xs font-semibold text-emerald-700">
            <CheckCircle2 className="h-3.5 w-3.5" /> 主要优点
          </p>
          <ul className="space-y-1.5">
            {assessment.strengths.map((s, i) => (
              <li key={i} className="flex gap-1.5 text-xs leading-5 text-slate-700">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-emerald-500" />{s}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-2xl border border-amber-100 bg-amber-50/60 p-3">
          <p className="mb-1.5 flex items-center gap-1 text-xs font-semibold text-amber-700">
            <AlertTriangle className="h-3.5 w-3.5" /> 主要短板
          </p>
          <ul className="space-y-1.5">
            {assessment.weaknesses.map((w, i) => (
              <li key={i} className="flex gap-1.5 text-xs leading-5 text-slate-700">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-amber-500" />{w}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 右栏 Tab：修改清单 / 风险 / 改写
// ---------------------------------------------------------------------------
function ChecklistTab({ checklist, risks, rewrites }: {
  checklist: ChecklistItem[]
  risks: RiskWarning[]
  rewrites: RewriteExample[]
}) {
  const priStyle: Record<string, string> = {
    '高': 'bg-red-100 text-red-700',
    '中': 'bg-amber-100 text-amber-700',
    '低': 'bg-slate-100 text-slate-600',
  }
  return (
    <div className="space-y-5">
      <div>
        <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-900">
          <ListChecks className="h-4 w-4 text-[#d06a00]" /> 修改行动清单
        </h3>
        {checklist.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-200 p-5 text-center text-xs text-slate-400">暂无修改清单</p>
        ) : (
          <div className="space-y-2">
            {checklist.map((item, idx) => (
              <div key={idx} className="flex items-start gap-3 rounded-xl border border-[#f1eadb] bg-[#fffdf9] p-3">
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${priStyle[item.priority] || priStyle['低']}`}>
                  {item.priority}
                </span>
                <div className="text-xs leading-6">
                  <div className="text-sm font-medium text-slate-800">{item.category ? `【${item.category}】` : ''}{item.action}</div>
                  {item.detail && <div className="mt-0.5 text-slate-500">{item.detail}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {risks.length > 0 && (
        <div>
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-900">
            <ShieldAlert className="h-4 w-4 text-[#d06a00]" /> 风险提示
          </h3>
          <div className="space-y-2">
            {risks.map((r, idx) => (
              <div key={idx} className="rounded-xl border border-red-100 bg-red-50/50 p-3 text-xs leading-6">
                <div className="text-sm font-medium text-slate-800">
                  <span className={`mr-1.5 rounded px-1.5 py-0.5 ${priStyle[r.severity] || priStyle['中']}`}>{r.severity}</span>
                  {r.risk_type}
                </div>
                <p className="mt-1 text-slate-600">{r.description}</p>
                {r.suggestion && <p className="mt-0.5 text-slate-500">应对：{r.suggestion}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {rewrites.length > 0 && (
        <div>
          <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-900">
            <PencilLine className="h-4 w-4 text-[#d06a00]" /> 学术化改写示例
          </h3>
          <div className="space-y-3">
            {rewrites.map((ex, idx) => (
              <div key={idx} className="overflow-hidden rounded-xl border border-[#f1eadb]">
                <div className="bg-[#fbf8f0] px-3 py-1.5 text-xs font-medium text-slate-800">{ex.section}</div>
                <div className="grid gap-2 p-3 md:grid-cols-2">
                  <div>
                    <div className="mb-1 text-[11px] font-medium text-slate-400">原文</div>
                    <div className="rounded-lg bg-slate-50 p-2.5 text-xs leading-6 text-slate-600">{ex.original}</div>
                  </div>
                  <div>
                    <div className="mb-1 text-[11px] font-medium text-emerald-600">改写</div>
                    <div className="rounded-lg bg-emerald-50/60 p-2.5 text-xs leading-6 text-slate-700">{ex.rewritten}</div>
                  </div>
                </div>
                {ex.notes && <div className="border-t border-[#f1eadb] px-3 py-1.5 text-[11px] text-slate-500">{ex.notes}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 雷达图
// ---------------------------------------------------------------------------
function RadarChart({ data }: { data: { label: string; score: number }[] }) {
  if (!data.length) return null
  const cx = 140; const cy = 140; const r = 108
  const levels = 5; const sides = data.length
  const angle = (idx: number) => (Math.PI * 2 * idx) / sides - Math.PI / 2
  const getPoint = (idx: number, value: number) => {
    const a = angle(idx)
    const dist = (value / 100) * r
    return `${cx + dist * Math.cos(a)},${cy + dist * Math.sin(a)}`
  }
  const gridPolygons = Array.from({ length: levels }, (_, i) => {
    const pts = Array.from({ length: sides }, (_, j) => getPoint(j, ((i + 1) / levels) * 100))
    return `<polygon points="${pts.join(' ')}" fill="none" stroke="#e0d5c0" stroke-width="0.5"/>`
  }).join('')
  const dataPoints = Array.from({ length: sides }, (_, i) => getPoint(i, data[i]?.score || 0))
  const dataPolygon = `<polygon points="${dataPoints.join(' ')}" fill="rgba(239,125,0,0.2)" stroke="#ef7d00" stroke-width="2"/>`
  const labels = data.map((d, i) => {
    const a = angle(i)
    const lx = cx + (r + 28) * Math.cos(a)
    const ly = cy + (r + 28) * Math.sin(a)
    const anchor = lx < cx - 10 ? 'end' : lx > cx + 10 ? 'start' : 'middle'
    return `<text x="${lx}" y="${ly}" text-anchor="${anchor}" font-size="10.5" fill="#555">${d.label}</text>`
  }).join('')
  const dots = dataPoints.map((pt, i) =>
    `<circle cx="${pt.split(',')[0]}" cy="${pt.split(',')[1]}" r="3.5" fill="#ef7d00" stroke="white" stroke-width="1.5"><title>${data[i].label}: ${data[i].score}</title></circle>`
  ).join('')
  return (
    <div className="flex justify-center">
      <svg viewBox="0 0 280 280" className="w-full max-w-[320px] h-auto">
        <g dangerouslySetInnerHTML={{ __html: gridPolygons + dataPolygon + labels + dots }} />
      </svg>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 参考建议模块面板（文献方向 / 期刊 / 审稿人 / 过刊比较 / 翻译）
// ---------------------------------------------------------------------------
function ModulePanel({ module }: { module: ModuleResult }) {
  const { module_key, module_name, summary, items } = module

  if (module_key === 'journals' && items.length > 0) {
    return (
      <div className="rounded-2xl border border-[#f1eadb] p-4">
        <div className="text-sm font-semibold text-slate-900">{module_name}</div>
        {summary && <p className="mt-1 text-xs leading-6 text-slate-500">{summary}</p>}
        <div className="mt-2 space-y-2">
          {items.map((item: Record<string, any>, idx) => (
            <div key={idx} className="rounded-xl border border-[#f1eadb] bg-[#fffdf9] p-3">
              <div className="text-sm font-medium text-slate-800">{item.level || item.label}</div>
              <p className="mt-1 text-xs leading-6 text-slate-600">{item.note || item.detail || item.content}</p>
            </div>
          ))}
        </div>
        <p className="mt-2 rounded-lg bg-emerald-50 p-2 text-[11px] leading-5 text-emerald-800">
          期刊层级建议仅供参考，不代表录用承诺；具体投稿要求请对照目标期刊最新稿约。
        </p>
      </div>
    )
  }

  if (module_key === 'comparison' && items.length > 0) {
    return (
      <div className="rounded-2xl border border-[#f1eadb] p-4">
        <div className="text-sm font-semibold text-slate-900">{module_name}</div>
        {summary && <p className="mt-1 text-xs leading-6 text-slate-500">{summary}</p>}
        <div className="mt-2 overflow-hidden rounded-xl border border-[#f1eadb]">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#fbf6ea] text-slate-600">
              <tr>
                <th className="px-2.5 py-2">维度</th>
                <th className="px-2.5 py-2">本文当前情况</th>
                <th className="px-2.5 py-2">目标风格要求</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row: Record<string, any>, idx) => (
                <tr key={idx} className="border-t border-[#f1eadb]">
                  <td className="px-2.5 py-2 font-medium text-slate-800">{row.col0}</td>
                  <td className="px-2.5 py-2 text-slate-600">{row.col1}</td>
                  <td className="px-2.5 py-2 text-slate-600">{row.col2}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  if (module_key === 'translation' && items.length > 0) {
    const t = items[0] as Record<string, any>
    const dirLabel = t?.direction === 'cn2en' ? '中→英' : t?.direction === 'en2cn' ? '英→中' : '自动检测'
    return (
      <div className="rounded-2xl border border-[#f1eadb] p-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold text-slate-900">{module_name}</div>
          <span className="rounded-full bg-[#fef0d6] px-3 py-1 text-xs text-[#9a5c00]">{dirLabel}</span>
        </div>
        <div className="mt-2 grid gap-2">
          <div className="rounded-xl border border-[#f1eadb] p-3">
            <div className="mb-1 text-[11px] font-medium text-slate-400">原文</div>
            <pre className="max-h-52 overflow-y-auto whitespace-pre-wrap text-xs leading-6 text-slate-700">{t?.original || ''}</pre>
          </div>
          <div className="rounded-xl border border-emerald-100 bg-emerald-50/50 p-3">
            <div className="mb-1 text-[11px] font-medium text-emerald-600">译文</div>
            <pre className="max-h-52 overflow-y-auto whitespace-pre-wrap text-xs leading-6 text-slate-700">{t?.translated || ''}</pre>
          </div>
        </div>
      </div>
    )
  }

  // 默认：文献方向 / 审稿人方向等列表
  return (
    <div className="rounded-2xl border border-[#f1eadb] p-4">
      <div className="text-sm font-semibold text-slate-900">{module_name}</div>
      {summary && <p className="mt-1 text-xs leading-6 text-slate-500">{summary}</p>}
      <ul className="mt-2 space-y-1.5">
        {items.map((item: Record<string, any>, idx) => (
          <li key={idx} className="flex gap-2 rounded-xl border border-[#f1eadb] bg-[#fffdf9] p-2.5 text-xs leading-6 text-slate-700">
            <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#d06a00]" />
            <span>{typeof item === 'string' ? item : item.content || item.detail || item.note || ''}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 小控件
// ---------------------------------------------------------------------------
function TabButton({ active, onClick, icon: Icon, children }: {
  active: boolean
  onClick: () => void
  icon: LucideIcon
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-t-lg border-b-2 px-3 py-2 text-xs font-medium transition ${
        active ? 'border-[#ef7d00] text-[#d56d00]' : 'border-transparent text-slate-500 hover:bg-slate-50'
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </button>
  )
}

function FilterChip({ active, onClick, children }: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-2.5 py-1 text-xs transition ${
        active ? 'bg-[#ef7d00] text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
      }`}
    >
      {children}
    </button>
  )
}
