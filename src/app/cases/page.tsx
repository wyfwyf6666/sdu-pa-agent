'use client'

import { useState } from 'react'
import { BookOpen, Loader2, Lightbulb, ChevronDown, ChevronUp, Users, Target, Settings, TrendingUp, MessageCircle } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

interface CaseData {
  background: { event: string; time: string; location: string; actors: string[]; policy_context: string }
  stakeholders: { name: string; demand: string; resources: string; strategy: string }[]
  policy_tools: { tool: string; type: string; assessment: string }[]
  governance_mechanism: { collaboration: string; information_flow: string; conflict_resolution: string }
  effect_evaluation: { goal_achievement: string; unintended_consequences: string; sustainability: string }
  insights: { theoretical: string[]; practical: string[]; scalability: string }
  discussion_questions: string[]
}

function parseJson(raw: string): any | null {
  try { const d = JSON.parse(raw); if (d && typeof d === 'object' && d.background) return d } catch {}
  const m = raw.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (m) try { return JSON.parse(m[1]) } catch { return null }
  return null
}

const TEMPLATES = [
  { label: '全面分析', value: '全面分析' },
  { label: '聚焦利益相关方', value: '重点分析各利益相关方的诉求、资源和行动策略' },
  { label: '聚焦政策工具', value: '重点分析政策工具的选择、使用和效果' },
  { label: '聚焦治理机制', value: '重点分析多元主体协作、信息流通和冲突协调机制' },
]

const EXAMPLES = [
  { title: '上海垃圾分类政策实施', text: '2019年7月，上海市正式实施《上海市生活垃圾管理条例》，成为全国首个全面推行生活垃圾强制分类的城市...' },
  { title: '杭州城市大脑交通治理', text: '杭州市自2016年起建设"城市大脑"系统，通过整合交通摄像头、信号灯、公交地铁等多源数据，实现城市交通的智能化管理...' },
]

export default function CasesPage() {
  const [caseText, setCaseText] = useState('')
  const [dimensions, setDimensions] = useState(TEMPLATES[0].value)
  const [showTemplates, setShowTemplates] = useState(false)
  const [data, setData] = useState<CaseData | null>(null)
  const [rawContent, setRawContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleAnalyze = async () => {
    if (!caseText.trim()) return
    setLoading(true); setError(''); setData(null); setRawContent('')
    try {
      const res = await fetch('/api/v1/teaching/case-analysis', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ case_description: caseText.trim(), analysis_dimensions: dimensions })
      })
      const r = await res.json()
      if (r.success) {
        const parsed = parseJson(r.content)
        if (parsed?.background) setData(parsed as CaseData)
        else setRawContent(r.content)
      } else setError(r.detail || '分析失败')
    } catch { setError('请求失败') }
    finally { setLoading(false) }
  }

  return (
    <div className="max-w-5xl mx-auto p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-lg bg-violet-100 flex items-center justify-center"><BookOpen className="w-5 h-5 text-violet-600" /></div>
          <h1 className="text-2xl font-bold text-gray-800">案例分析</h1>
        </div>
        <p className="text-gray-500 ml-13">结构化框架 + 可视化数据表格 + 时间轴</p>
      </div>

      <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm mb-6">
        <textarea value={caseText} onChange={e => setCaseText(e.target.value)}
          placeholder="请输入公共管理案例，包括事件背景、参与主体、政策措施和关键结果..."
          rows={8} className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500 resize-none" />

        <div className="mt-4">
          <button onClick={() => setShowTemplates(!showTemplates)}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-violet-600">
            <Lightbulb className="w-3 h-3" />分析维度：{TEMPLATES.find(t=>t.value===dimensions)?.label||'自定义'}
            {showTemplates?<ChevronUp className="w-3 h-3"/>:<ChevronDown className="w-3 h-3"/>}
          </button>
          {showTemplates && (
            <div className="mt-2 grid grid-cols-2 gap-2">
              {TEMPLATES.map(t=>(<button key={t.label} onClick={()=>{setDimensions(t.value);setShowTemplates(false)}}
                className={`text-left px-3 py-2 rounded-lg text-xs ${dimensions===t.value?'bg-violet-50 text-violet-700 border border-violet-200':'bg-gray-50 text-gray-600 border border-gray-100 hover:bg-violet-50'}`}>{t.label}</button>))}
            </div>
          )}
        </div>
        <button onClick={handleAnalyze} disabled={loading||!caseText.trim()}
          className="mt-4 w-full py-3 bg-gradient-to-r from-violet-500 to-purple-600 text-white rounded-xl text-sm font-medium hover:from-violet-600 hover:to-purple-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2">
          {loading?<Loader2 className="w-4 h-4 animate-spin"/>:<BookOpen className="w-4 h-4"/>}开始分析</button>
      </div>

      {!data && !rawContent && !loading && (
        <div className="mb-6"><p className="text-xs text-gray-400 mb-3">快速示例：</p>
          <div className="grid grid-cols-2 gap-3">{EXAMPLES.map(c=>(
            <button key={c.title} onClick={()=>setCaseText(c.text)}
              className="text-left p-4 bg-white border border-gray-100 rounded-xl hover:border-violet-200 hover:bg-violet-50/50 transition-all">
              <h4 className="text-sm font-medium text-gray-700 group-hover:text-violet-700 mb-1">{c.title}</h4>
              <p className="text-xs text-gray-400 line-clamp-2">{c.text}</p></button>))}
          </div></div>
      )}

      {error && <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600 mb-6">{error}</div>}
      {loading && <div className="flex items-center justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-violet-500"/><span className="ml-3 text-gray-500">结构化分析中...</span></div>}

      {data && (
        <div className="space-y-5">
          {/* Background - Timeline style */}
          <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2"><Target className="w-4 h-4 text-violet-500"/>背景概述</h3>
            <div className="relative pl-6 border-l-2 border-violet-200 space-y-4">
              <div className="relative"><div className="absolute -left-[25px] w-3 h-3 rounded-full bg-violet-400 border-2 border-white"/><p className="text-sm text-gray-700"><strong>事件：</strong>{data.background?.event}</p></div>
              <div className="relative"><div className="absolute -left-[25px] w-3 h-3 rounded-full bg-violet-300 border-2 border-white"/><p className="text-xs text-gray-500">{data.background?.time} · {data.background?.location}</p></div>
              <div className="relative"><div className="absolute -left-[25px] w-3 h-3 rounded-full bg-violet-200 border-2 border-white"/><div className="flex flex-wrap gap-1.5">{data.background?.actors?.map((a,i)=>(<span key={i} className="px-2 py-0.5 bg-violet-50 text-violet-700 rounded text-xs">{a}</span>))}</div></div>
              <div className="relative"><div className="absolute -left-[25px] w-3 h-3 rounded-full bg-gray-200 border-2 border-white"/><p className="text-xs text-gray-500">{data.background?.policy_context}</p></div>
            </div>
          </div>

          {/* Stakeholder Table */}
          <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm overflow-x-auto">
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2"><Users className="w-4 h-4 text-blue-500"/>利益相关方分析</h3>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-gray-100"><th className="text-left py-2 px-3 text-xs font-medium text-gray-500">利益相关方</th><th className="text-left py-2 px-3 text-xs font-medium text-gray-500">诉求</th><th className="text-left py-2 px-3 text-xs font-medium text-gray-500">资源/权力</th><th className="text-left py-2 px-3 text-xs font-medium text-gray-500">行动策略</th></tr></thead>
              <tbody>{data.stakeholders?.map((s,i)=>(
                <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50">
                  <td className="py-2.5 px-3 font-medium text-gray-700">{s.name}</td>
                  <td className="py-2.5 px-3 text-gray-600">{s.demand}</td>
                  <td className="py-2.5 px-3 text-gray-600">{s.resources}</td>
                  <td className="py-2.5 px-3 text-gray-600">{s.strategy}</td></tr>))}
              </tbody>
            </table>
          </div>

          {/* Policy Tools */}
          <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2"><Settings className="w-4 h-4 text-emerald-500"/>政策工具分析</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {data.policy_tools?.map((pt,i)=>(
                <div key={i} className="border border-gray-100 rounded-xl p-4">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${pt.type.includes('规制')?'bg-red-50 text-red-700':pt.type.includes('激励')?'bg-emerald-50 text-emerald-700':pt.type.includes('信息')?'bg-blue-50 text-blue-700':'bg-gray-50 text-gray-700'}`}>{pt.type}</span>
                  <p className="text-sm font-medium text-gray-700 mt-2">{pt.tool}</p>
                  <p className="text-xs text-gray-500 mt-1">{pt.assessment}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Governance + Effect */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">治理机制</h3>
              <div className="space-y-3">
                <div><span className="text-xs text-gray-400">协作机制</span><p className="text-sm text-gray-700">{data.governance_mechanism?.collaboration}</p></div>
                <div><span className="text-xs text-gray-400">信息流通</span><p className="text-sm text-gray-700">{data.governance_mechanism?.information_flow}</p></div>
                <div><span className="text-xs text-gray-400">冲突协调</span><p className="text-sm text-gray-700">{data.governance_mechanism?.conflict_resolution}</p></div>
              </div>
            </div>
            <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-rose-500"/>效果评估</h3>
              <div className="space-y-3">
                <div><span className="text-xs text-gray-400">目标达成</span><p className="text-sm text-gray-700">{data.effect_evaluation?.goal_achievement}</p></div>
                <div><span className="text-xs text-gray-400">意外后果</span><p className="text-sm text-gray-700">{data.effect_evaluation?.unintended_consequences}</p></div>
                <div><span className="text-xs text-gray-400">可持续性</span><p className="text-sm text-gray-700">{data.effect_evaluation?.sustainability}</p></div>
              </div>
            </div>
          </div>

          {/* Insights + Discussion */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-200 rounded-xl p-5">
              <h3 className="text-sm font-semibold text-indigo-800 mb-2">理论启示</h3>
              <ul className="space-y-1">{data.insights?.theoretical?.map((t,i)=>(<li key={i} className="text-sm text-indigo-700">• {t}</li>))}</ul>
              <h3 className="text-sm font-semibold text-indigo-800 mb-2 mt-4">实践启示</h3>
              <ul className="space-y-1">{data.insights?.practical?.map((p,i)=>(<li key={i} className="text-sm text-indigo-700">• {p}</li>))}</ul>
              <p className="text-xs text-indigo-600 mt-2"><strong>可推广性：</strong>{data.insights?.scalability}</p>
            </div>
            <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2"><MessageCircle className="w-4 h-4 text-amber-500"/>课堂讨论</h3>
              <div className="space-y-2">{data.discussion_questions?.map((q,i)=>(
                <div key={i} className="flex gap-3 p-3 bg-amber-50 rounded-lg"><span className="text-amber-500 font-bold text-sm">Q{i+1}</span><p className="text-sm text-gray-700">{q}</p></div>))}
              </div>
            </div>
          </div>
        </div>
      )}

      {rawContent && !data && (
        <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm">
          <div className="prose prose-gray max-w-none text-sm"><ReactMarkdown>{rawContent}</ReactMarkdown></div>
        </div>
      )}
    </div>
  )
}
