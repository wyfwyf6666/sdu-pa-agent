'use client'

import { useState } from 'react'
import { Search, Lightbulb, BookOpen, Loader2, Link2, FileText, MapPin } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

const SUGGESTIONS = ['协同治理', '政策扩散', '多源流框架', '街头官僚', '元治理', '数字政府', '城市更新', '公众参与阶梯']

interface ConceptData {
  definition: string
  core_elements: { element: string; explanation: string }[]
  theory_origin: string
  classic_case: string
  related_concepts: { name: string; relation: string }[]
  readings: { title: string; author: string; reason: string }[]
}

function parseConceptJson(raw: string): ConceptData | null {
  try {
    const d = JSON.parse(raw)
    if (d.definition) return d
    // Try extracting from markdown code block
    const m = raw.match(/```(?:json)?\s*([\s\S]*?)```/)
    if (m) return JSON.parse(m[1])
    return null
  } catch { return null }
}

export default function ConceptsPage() {
  const [concept, setConcept] = useState('')
  const [context, setContext] = useState('')
  const [data, setData] = useState<ConceptData | null>(null)
  const [rawContent, setRawContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!concept.trim()) return
    setLoading(true); setError(''); setData(null); setRawContent('')
    try {
      const res = await fetch('/api/v1/teaching/concept', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept: concept.trim(), context: context.trim() || undefined })
      })
      const r = await res.json()
      if (r.success) {
        const parsed = parseConceptJson(r.content)
        if (parsed) setData(parsed)
        else setRawContent(r.content)
      } else setError(r.detail || '解析失败')
    } catch { setError('请求失败') }
    finally { setLoading(false) }
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
            <Lightbulb className="w-5 h-5 text-amber-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-800">概念解析</h1>
        </div>
        <p className="text-gray-500 ml-13">输入公共管理学科概念，获取结构化解析卡片</p>
      </div>

      <form onSubmit={handleSearch} className="mb-6">
        <div className="flex gap-3 mb-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input type="text" value={concept} onChange={e => setConcept(e.target.value)}
              placeholder="输入概念名称，如：协同治理..."
              className="w-full pl-10 pr-4 py-3 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/20 focus:border-amber-500" />
          </div>
          <button type="submit" disabled={loading || !concept.trim()}
            className="px-6 py-3 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-xl text-sm font-medium hover:from-amber-600 hover:to-orange-600 disabled:opacity-50 transition-all flex items-center gap-2">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}解析
          </button>
        </div>
        <input type="text" value={context} onChange={e => setContext(e.target.value)}
          placeholder="可选：补充背景信息"
          className="w-full px-4 py-2 bg-gray-50 border border-gray-100 rounded-lg text-xs text-gray-500 focus:outline-none focus:ring-2 focus:ring-amber-500/10" />
      </form>

      {!data && !rawContent && !loading && (
        <div className="mb-6">
          <p className="text-xs text-gray-400 mb-3">常见概念：</p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map(s => (
              <button key={s} onClick={() => { setConcept(s); handleSearch() }}
                className="px-3 py-1.5 bg-gray-50 hover:bg-amber-50 text-gray-600 hover:text-amber-700 rounded-lg text-xs transition-colors border border-gray-100 hover:border-amber-200">{s}</button>
            ))}
          </div>
        </div>
      )}

      {error && <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600 mb-6">{error}</div>}

      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-amber-500" />
          <span className="ml-3 text-gray-500">解析「{concept}」中...</span>
        </div>
      )}

      {/* Structured concept card */}
      {data && (
        <div className="space-y-5">
          {/* Definition */}
          <div className="bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 rounded-2xl p-6">
            <h3 className="text-sm font-semibold text-amber-800 mb-2 flex items-center gap-2"><BookOpen className="w-4 h-4" />定义</h3>
            <p className="text-gray-700 text-sm leading-relaxed">{data.definition}</p>
          </div>

          {/* Core Elements */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {data.core_elements?.map((el, i) => (
              <div key={i} className="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
                <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center mb-2">
                  <span className="text-amber-700 font-bold text-sm">{i + 1}</span>
                </div>
                <h4 className="text-sm font-semibold text-gray-800 mb-1">{el.element}</h4>
                <p className="text-xs text-gray-500">{el.explanation}</p>
              </div>
            ))}
          </div>

          {/* Theory + Case */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2"><Link2 className="w-4 h-4 text-indigo-500" />理论渊源</h3>
              <p className="text-sm text-gray-600">{data.theory_origin}</p>
            </div>
            <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2"><MapPin className="w-4 h-4 text-emerald-500" />经典案例</h3>
              <p className="text-sm text-gray-600">{data.classic_case}</p>
            </div>
          </div>

          {/* Related Concepts */}
          <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 mb-3">相关概念</h3>
            <div className="flex flex-wrap gap-2">
              {data.related_concepts?.map((rc, i) => (
                <div key={i} className="bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2">
                  <span className="text-sm font-medium text-indigo-700">{rc.name}</span>
                  <span className="text-xs text-indigo-500 ml-2">— {rc.relation}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Readings */}
          <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2"><FileText className="w-4 h-4 text-blue-500" />推荐阅读</h3>
            <div className="space-y-2">
              {data.readings?.map((rd, i) => (
                <div key={i} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                  <span className="text-xs font-bold text-blue-500 mt-0.5">{i + 1}</span>
                  <div>
                    <p className="text-sm font-medium text-gray-700">{rd.title}</p>
                    <p className="text-xs text-gray-500">{rd.author} · {rd.reason}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Fallback Markdown */}
      {rawContent && !data && (
        <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm">
          <div className="prose prose-gray max-w-none text-sm"><ReactMarkdown>{rawContent}</ReactMarkdown></div>
        </div>
      )}
    </div>
  )
}
