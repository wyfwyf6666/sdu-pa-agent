'use client'

import { useState, useRef } from 'react'
import { ScrollText, FileText, PenLine, Loader2, Upload, X, FileUp, Search, Lightbulb, BarChart3, AlertTriangle, Target } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

type Tab = 'upload' | 'text' | 'outline'

interface SummaryData {
  research_question: string
  method: { type: string; data_source: string; sample: string }
  findings: { finding: string; evidence: string }[]
  theory_contribution: string
  policy_implications: string[]
  limitations: string[]
  keywords: string[]
}

interface OutlineData {
  title: string
  abstract: string
  sections: { heading: string; subsections: string[]; key_points: string[] }[]
  references_direction: { title: string; relevance: string }[]
}

function parseJson(raw: string): any | null {
  try { const d = JSON.parse(raw); if (d && typeof d === 'object') return d } catch {}
  const m = raw.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (m) try { return JSON.parse(m[1]) } catch { return null }
  return null
}

export default function PapersPage() {
  const [tab, setTab] = useState<Tab>('upload')
  const [error, setError] = useState('')

  const [file, setFile] = useState<File | null>(null)
  const [summaryData, setSummaryData] = useState<SummaryData | null>(null)
  const [uploadRaw, setUploadRaw] = useState('')
  const [uploadLoading, setUploadLoading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [paperText, setPaperText] = useState('')
  const [textData, setTextData] = useState<SummaryData | null>(null)
  const [textRaw, setTextRaw] = useState('')
  const [textLoading, setTextLoading] = useState(false)

  const [topic, setTopic] = useState('')
  const [requirements, setRequirements] = useState('')
  const [outlineData, setOutlineData] = useState<OutlineData | null>(null)
  const [outlineRaw, setOutlineRaw] = useState('')
  const [outlineLoading, setOutlineLoading] = useState(false)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    const ext = f.name.split('.').pop()?.toLowerCase()
    if (!['pdf', 'docx', 'doc', 'txt'].includes(ext || '')) { setError('仅支持PDF/Word/TXT'); return }
    if (f.size > 20*1024*1024) { setError('文件不超过20MB'); return }
    setFile(f); setError('')
  }

  const handleUpload = async () => {
    if (!file) return
    setUploadLoading(true); setError(''); setSummaryData(null); setUploadRaw('')
    try {
      const fd = new FormData(); fd.append('file', file)
      const token = localStorage.getItem('token')
      const res = await fetch('/api/v1/teaching/paper-summary-upload', {
        method: 'POST', headers: token ? { Authorization: `Bearer ${token}` } : {}, body: fd })
      const r = await res.json()
      if (r.success) {
        const parsed = parseJson(r.content)
        if (parsed?.research_question) setSummaryData(parsed as SummaryData)
        else setUploadRaw(r.content)
      } else setError(r.detail || '分析失败')
    } catch { setError('请求失败') }
    finally { setUploadLoading(false) }
  }

  const handleText = async () => {
    if (!paperText.trim()) return
    setTextLoading(true); setError(''); setTextData(null); setTextRaw('')
    try {
      const res = await fetch('/api/v1/teaching/paper-summary', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: paperText.trim() }) })
      const r = await res.json()
      if (r.success) {
        const parsed = parseJson(r.content)
        if (parsed?.research_question) setTextData(parsed as SummaryData)
        else setTextRaw(r.content)
      } else setError(r.detail || '生成失败')
    } catch { setError('请求失败') }
    finally { setTextLoading(false) }
  }

  const handleOutline = async () => {
    if (!topic.trim()) return
    setOutlineLoading(true); setError(''); setOutlineData(null); setOutlineRaw('')
    try {
      const res = await fetch('/api/v1/teaching/paper-outline', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topic.trim(), requirements: requirements.trim() || undefined }) })
      const r = await res.json()
      if (r.success) {
        const parsed = parseJson(r.content)
        if (parsed?.sections) setOutlineData(parsed as OutlineData)
        else setOutlineRaw(r.content)
      } else setError(r.detail || '生成失败')
    } catch { setError('请求失败') }
    finally { setOutlineLoading(false) }
  }

  const SummaryCards = ({ data }: { data: SummaryData }) => (
    <div className="space-y-5">
      {/* Research Question */}
      <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl p-5">
        <h3 className="text-sm font-semibold text-blue-800 mb-2 flex items-center gap-2"><Target className="w-4 h-4" />研究问题</h3>
        <p className="text-gray-700 text-sm">{data.research_question}</p>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {data.keywords?.map((kw, i) => (
            <span key={i} className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">{kw}</span>
          ))}
        </div>
      </div>

      {/* Method */}
      <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-indigo-500" />研究方法</h3>
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div><span className="text-gray-400 text-xs">类型</span><p className="font-medium text-gray-700">{data.method?.type}</p></div>
          <div><span className="text-gray-400 text-xs">数据来源</span><p className="font-medium text-gray-700">{data.method?.data_source}</p></div>
          <div><span className="text-gray-400 text-xs">样本</span><p className="font-medium text-gray-700">{data.method?.sample}</p></div>
        </div>
      </div>

      {/* Findings */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2"><Lightbulb className="w-4 h-4 text-amber-500" />核心发现</h3>
        {data.findings?.map((f, i) => (
          <div key={i} className="bg-white border border-gray-100 rounded-xl p-4 shadow-sm flex gap-4">
            <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0">
              <span className="text-amber-700 font-bold text-sm">{i+1}</span>
            </div>
            <div>
              <p className="text-sm font-medium text-gray-800">{f.finding}</p>
              <p className="text-xs text-gray-500 mt-1">{f.evidence}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Theory + Policy */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">理论贡献</h3>
          <p className="text-sm text-gray-600">{data.theory_contribution}</p>
        </div>
        <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">政策启示</h3>
          <ul className="space-y-1">
            {data.policy_implications?.map((p, i) => (
              <li key={i} className="text-sm text-gray-600 flex gap-2"><span className="text-emerald-500">•</span>{p}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Limitations */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
        <h3 className="text-sm font-semibold text-amber-800 mb-2 flex items-center gap-2"><AlertTriangle className="w-4 h-4" />研究局限</h3>
        <ul className="space-y-1">
          {data.limitations?.map((l, i) => (
            <li key={i} className="text-sm text-amber-700 flex gap-2"><span className="text-amber-400">•</span>{l}</li>
          ))}
        </ul>
      </div>
    </div>
  )

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-lg bg-emerald-100 flex items-center justify-center"><ScrollText className="w-5 h-5 text-emerald-600" /></div>
          <h1 className="text-2xl font-bold text-gray-800">论文阅读</h1>
        </div>
        <p className="text-gray-500 ml-13">上传 PDF/Word/TXT，AI 结构化速读 + 论文大纲生成</p>
      </div>

      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 mb-6">
        {([{ k: 'upload' as Tab, i: FileUp, l: '文件上传' }, { k: 'text' as Tab, i: FileText, l: '文本粘贴' }, { k: 'outline' as Tab, i: PenLine, l: '提纲生成' }] as const).map(t => (
          <button key={t.k} onClick={() => setTab(t.k)}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all ${tab===t.k ? 'bg-white text-emerald-700 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
            <t.i className="w-4 h-4" />{t.l}</button>
        ))}
      </div>

      {error && <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600 mb-6 flex justify-between">{error}<button onClick={()=>setError('')}><X className="w-4 h-4"/></button></div>}

      {/* Upload Tab */}
      {tab === 'upload' && (
        <div>
          <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm mb-6">
            <div onClick={()=>fileInputRef.current?.click()}
              onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault(); const f=e.dataTransfer.files?.[0]; if(f){const dt=new DataTransfer();dt.items.add(f);if(fileInputRef.current){fileInputRef.current.files=dt.files;handleFileChange({target:{files:dt.files}} as any)}}}}
              className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all ${file?'border-emerald-300 bg-emerald-50/50':'border-gray-200 hover:border-emerald-300 hover:bg-gray-50'}`}>
              <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.txt" onChange={handleFileChange} className="hidden"/>
              {file ? (
                <div className="space-y-2">
                  <div className="w-12 h-12 mx-auto rounded-xl bg-emerald-100 flex items-center justify-center"><FileText className="w-6 h-6 text-emerald-600"/></div>
                  <p className="text-sm font-medium text-gray-700">{file.name}</p>
                  <p className="text-xs text-gray-400">{(file.size/1024).toFixed(1)} KB</p>
                  <button onClick={e=>{e.stopPropagation();setFile(null)}} className="text-xs text-gray-400 hover:text-red-500">移除</button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="w-12 h-12 mx-auto rounded-xl bg-gray-100 flex items-center justify-center"><Upload className="w-6 h-6 text-gray-400"/></div>
                  <p className="text-sm text-gray-500">点击或拖拽上传论文文件</p>
                  <p className="text-xs text-gray-400">PDF / Word / TXT — 最大20MB</p>
                </div>
              )}
            </div>
            <button onClick={handleUpload} disabled={uploadLoading||!file}
              className="mt-4 w-full py-3 bg-gradient-to-r from-emerald-500 to-teal-600 text-white rounded-xl text-sm font-medium hover:from-emerald-600 hover:to-teal-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2">
              {uploadLoading?<Loader2 className="w-4 h-4 animate-spin"/>:<ScrollText className="w-4 h-4"/>}{uploadLoading?'分析中...':'上传并分析'}</button>
          </div>
          {summaryData && <SummaryCards data={summaryData}/>}
          {uploadRaw && !summaryData && <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm"><div className="prose prose-gray max-w-none text-sm"><ReactMarkdown>{uploadRaw}</ReactMarkdown></div></div>}
        </div>
      )}

      {/* Text Tab */}
      {tab === 'text' && (
        <div>
          <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm mb-6">
            <textarea value={paperText} onChange={e=>setPaperText(e.target.value)} placeholder="粘贴论文内容（最多8000字）..." rows={10}
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 resize-none"/>
            <div className="flex justify-between mt-3"><span className="text-xs text-gray-400">{paperText.length}/8000</span>{paperText&&<button onClick={()=>setPaperText('')} className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1"><X className="w-3 h-3"/>清空</button>}</div>
            <button onClick={handleText} disabled={textLoading||!paperText.trim()}
              className="mt-4 w-full py-3 bg-gradient-to-r from-emerald-500 to-teal-600 text-white rounded-xl text-sm font-medium hover:from-emerald-600 hover:to-teal-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2">
              {textLoading?<Loader2 className="w-4 h-4 animate-spin"/>:<ScrollText className="w-4 h-4"/>}生成速读摘要</button>
          </div>
          {textData && <SummaryCards data={textData}/>}
          {textRaw && !textData && <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm"><div className="prose prose-gray max-w-none text-sm"><ReactMarkdown>{textRaw}</ReactMarkdown></div></div>}
        </div>
      )}

      {/* Outline Tab */}
      {tab === 'outline' && (
        <div>
          <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">选题</label>
            <input type="text" value={topic} onChange={e=>setTopic(e.target.value)} placeholder="如：数字技术赋能城市社区治理的机制研究"
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 mb-3"/>
            <label className="block text-sm font-medium text-gray-700 mb-1">要求（可选）</label>
            <textarea value={requirements} onChange={e=>setRequirements(e.target.value)} placeholder="如：定量分析、以深圳为例..." rows={3}
              className="w-full px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 resize-none"/>
            <button onClick={handleOutline} disabled={outlineLoading||!topic.trim()}
              className="mt-4 w-full py-3 bg-gradient-to-r from-emerald-500 to-teal-600 text-white rounded-xl text-sm font-medium hover:from-emerald-600 hover:to-teal-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2">
              {outlineLoading?<Loader2 className="w-4 h-4 animate-spin"/>:<PenLine className="w-4 h-4"/>}生成大纲</button>
          </div>
          {outlineData && (
            <div className="space-y-4">
              <div className="bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-200 rounded-2xl p-6">
                <h2 className="text-lg font-bold text-gray-800 mb-2">{outlineData.title}</h2>
                <p className="text-sm text-gray-600">{outlineData.abstract}</p>
              </div>
              {outlineData.sections?.map((sec, i) => (
                <div key={i} className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                  <h3 className="text-sm font-bold text-gray-800 mb-2 flex items-center gap-2">
                    <span className="w-6 h-6 rounded bg-emerald-100 flex items-center justify-center text-xs text-emerald-700">{i+1}</span>
                    {sec.heading}
                  </h3>
                  {sec.subsections?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {sec.subsections.map((s,j)=><span key={j} className="px-2 py-0.5 bg-gray-50 rounded text-xs text-gray-600">{s}</span>)}
                    </div>
                  )}
                  {sec.key_points?.length > 0 && (
                    <ul className="space-y-1">{sec.key_points.map((p,j)=><li key={j} className="text-xs text-gray-500 flex gap-2"><span className="text-emerald-400">•</span>{p}</li>)}</ul>
                  )}
                </div>
              ))}
              {outlineData.references_direction?.length > 0 && (
                <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                  <h3 className="text-sm font-semibold text-gray-700 mb-2">参考文献方向</h3>
                  {outlineData.references_direction.map((r,i)=>(<p key={i} className="text-xs text-gray-600 mb-1"><span className="text-blue-500">•</span> {r.title} — {r.relevance}</p>))}
                </div>
              )}
            </div>
          )}
          {outlineRaw && !outlineData && <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm"><div className="prose prose-gray max-w-none text-sm"><ReactMarkdown>{outlineRaw}</ReactMarkdown></div></div>}
        </div>
      )}
    </div>
  )
}
