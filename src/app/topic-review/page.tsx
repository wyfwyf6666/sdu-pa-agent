'use client'

import { useState } from 'react'
import MainLayout from '@/components/layout/MainLayout'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Lightbulb,
  Send,
  Loader2,
  FileText,
  Download,
  BookOpen,
  Globe,
  Library,
  ExternalLink,
  Search,
  Sparkles,
  RefreshCw,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type Paper = {
  title: string
  authors: string[]
  year?: number | null
  journal: string
  abstract: string
  doi: string
  url: string
  source: string
  language: string
}

type Result = {
  topic: string
  suggestion: string
  review: string
  papers: Paper[]
  stats: { total: number; en: number; zh: number }
}

type Phase = 'input' | 'loading' | 'result' | 'error'

const LOADING_STEPS = [
  '正在评估选题价值与可行性…',
  '正在搜集英文文献（OpenAlex）…',
  '正在检索中文学术库（知网/国家哲社/万方）…',
  '正在撰写文献综述…',
]

export default function TopicReviewPage() {
  const [topic, setTopic] = useState('')
  const [phase, setPhase] = useState<Phase>('input')
  const [loadingStep, setLoadingStep] = useState(0)
  const [result, setResult] = useState<Result | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [exporting, setExporting] = useState(false)

  const runGenerate = async () => {
    if (!topic.trim() || phase === 'loading') return
    setPhase('loading')
    setLoadingStep(0)
    const timer = setInterval(() => {
      setLoadingStep((s) => Math.min(s + 1, LOADING_STEPS.length - 1))
    }, 4000)

    try {
      const res = await fetch('/api/v1/topic-review/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topic.trim(), en_limit: 8, zh_limit: 8 }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `请求失败（${res.status}）`)
      }
      const data = (await res.json()) as Result
      setResult(data)
      setPhase('result')
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err))
      setPhase('error')
    } finally {
      clearInterval(timer)
    }
  }

  const exportExcel = async () => {
    if (!result || exporting) return
    setExporting(true)
    try {
      const res = await fetch('/api/v1/topic-review/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: result.topic, papers: result.papers }),
      })
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `文献总结表_${result.topic.slice(0, 20)}.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      alert(err instanceof Error ? err.message : '导出失败')
    } finally {
      setExporting(false)
    }
  }

  const reset = () => {
    setPhase('input')
    setResult(null)
    setErrorMsg('')
    setTopic('')
  }

  const enPapers = result?.papers.filter((p) => p.language === 'en') ?? []
  const zhPapers = result?.papers.filter((p) => p.language === 'zh') ?? []

  return (
    <MainLayout>
      <div className="min-h-full p-6 bg-gray-50">
        {/* 页头 */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-1">
            <Library className="w-5 h-5 text-[#7A1014]" />
            <h1 className="text-xl font-semibold text-gray-900">选题建议与文献综述</h1>
          </div>
          <p className="text-sm text-gray-500">
            输入你的研究选题，智能体将给出选题建议、搜集中英文文献并生成文献综述，点击链接可直达原文
          </p>
        </div>

        {/* 输入区 */}
        {phase !== 'result' && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-6"
          >
            <textarea
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="例如：政策扩散理论在基层治理中的应用研究"
              rows={3}
              className="w-full resize-none rounded-lg border border-gray-300 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#7A1014]/30 focus:border-[#7A1014]"
            />
            <div className="flex items-center justify-between mt-3">
              <p className="text-xs text-gray-400">支持中文 / 英文选题</p>
              <div className="flex gap-2">
                <button
                  onClick={reset}
                  className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50"
                >
                  清空
                </button>
                <button
                  onClick={runGenerate}
                  disabled={!topic.trim() || phase === 'loading'}
                  className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white bg-[#7A1014] rounded-lg hover:bg-[#8f1419] disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {phase === 'loading' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  生成选题综述
                </button>
              </div>
            </div>

            {/* 加载中步骤提示 */}
            <AnimatePresence>
              {phase === 'loading' && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="mt-4 rounded-lg bg-gray-50 border border-gray-200 p-4"
                >
                  <div className="flex items-center gap-2 text-sm text-gray-700 font-medium">
                    <Sparkles className="w-4 h-4 text-[#7A1014]" />
                    {LOADING_STEPS[loadingStep]}
                  </div>
                  <div className="mt-2 h-1.5 rounded-full bg-gray-200 overflow-hidden">
                    <motion.div
                      className="h-full bg-[#7A1014]"
                      animate={{ width: `${((loadingStep + 1) / LOADING_STEPS.length) * 100}%` }}
                    />
                  </div>
                  <p className="mt-2 text-xs text-gray-400">
                    通常需要 30-60 秒：选题建议 → 文献搜集 → 综述生成
                  </p>
                </motion.div>
              )}
            </AnimatePresence>

            {phase === 'error' && (
              <div className="mt-4 rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
                生成失败：{errorMsg}。请检查后端是否运行、网络是否可用后重试。
              </div>
            )}
          </motion.div>
        )}

        {/* 结果区 */}
        {phase === 'result' && result && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            {/* 工具栏 */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <BookOpen className="w-4 h-4" />
                选题：
                <span className="font-medium text-gray-800">{result.topic}</span>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={exportExcel}
                  disabled={exporting}
                  className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-[#7A1014] text-[#7A1014] hover:bg-[#7A1014]/5 disabled:opacity-40"
                >
                  {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                  导出文献Excel
                </button>
                <button
                  onClick={reset}
                  className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50"
                >
                  <RefreshCw className="w-4 h-4" />
                  换一个选题
                </button>
              </div>
            </div>

            {/* 选题建议 */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-5">
              <div className="flex items-center gap-2 mb-3">
                <Lightbulb className="w-4 h-4 text-amber-500" />
                <h2 className="text-base font-semibold text-gray-900">一、选题建议</h2>
              </div>
              <div className="prose prose-sm max-w-none text-gray-700">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.suggestion}</ReactMarkdown>
              </div>
            </div>

            {/* 文献列表 */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5 mb-5">
              <div className="flex items-center gap-2 mb-1">
                <Search className="w-4 h-4 text-[#7A1014]" />
                <h2 className="text-base font-semibold text-gray-900">
                  二、相关文献（共 {result.stats.total} 篇 · 中文 {result.stats.zh} · 英文 {result.stats.en}）
                </h2>
              </div>
              <p className="text-xs text-gray-400 mb-3">点击「查看原文」可跳转文献原文页面</p>

              {zhPapers.length > 0 && (
                <PaperGroup title="中文文献" papers={zhPapers} accent="bg-[#7A1014] text-white" />
              )}
              {enPapers.length > 0 && (
                <PaperGroup title="英文文献" papers={enPapers} accent="bg-blue-600 text-white" />
              )}
              {result.papers.length === 0 && (
                <p className="text-sm text-gray-500 py-4">未检索到文献，可尝试更换关键词或扩大选题范围。</p>
              )}
            </div>

            {/* 文献综述 */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="w-4 h-4 text-green-600" />
                <h2 className="text-base font-semibold text-gray-900">三、文献综述</h2>
              </div>
              <div className="prose prose-sm max-w-none text-gray-700">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.review}</ReactMarkdown>
              </div>
            </div>
          </motion.div>
        )}
      </div>
    </MainLayout>
  )
}

function PaperGroup({
  title,
  papers,
  accent,
}: {
  title: string
  papers: Paper[]
  accent: string
}) {
  return (
    <div className="mb-4 last:mb-0">
      <div className="flex items-center gap-2 mb-2">
        <Globe className="w-4 h-4 text-gray-400" />
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        <span className={`text-xs px-2 py-0.5 rounded-full ${accent}`}>{papers.length} 篇</span>
      </div>
      <div className="space-y-2">
        {papers.map((p, i) => (
          <div key={i} className="rounded-lg border border-gray-200 p-3 hover:bg-gray-50 transition-colors">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900">{p.title}</p>
                <p className="text-xs text-gray-500 mt-0.5">
                  {p.authors.slice(0, 3).join('、') || '佚名'}
                  {p.year ? ` · ${p.year}` : ''}
                  {p.journal ? ` · ${p.journal}` : ''}
                  <span className="ml-1.5 text-gray-400">({p.source})</span>
                </p>
              </div>
              {p.url && (
                <a
                  href={p.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 shrink-0 text-xs font-medium text-[#7A1014] hover:underline"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  查看原文
                </a>
              )}
            </div>
            {p.abstract && <p className="text-xs text-gray-500 mt-1.5 line-clamp-2">{p.abstract}</p>}
            {p.doi && <p className="text-xs text-gray-400 mt-1">DOI: {p.doi}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}
