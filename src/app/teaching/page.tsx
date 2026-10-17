'use client'

import { useState } from 'react'
import { Zap, FileText, PenLine, Loader2, Download, Clock, BookOpen, GraduationCap, CheckCircle2, XCircle, ChevronDown, ChevronUp, Lightbulb, AlertTriangle, Target, PieChart, RotateCcw } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

type Tab = 'quiz' | 'plan'

interface QuizQuestion {
  id: number; type: string; question: string; options?: string[]; answer: string
  scoring_points?: string[]; explanation: string
}
interface QuizData {
  title: string; topic: string; difficulty: string; total_score: number; time_minutes: number
  questions: QuizQuestion[]
}

interface GradingResult {
  loading?: boolean; score?: number; feedback?: string
  covered_points?: string[]; partial_points?: string[]; missed_points?: string[]
}

interface PlanData {
  objectives: { knowledge: string[]; ability: string[]; literacy: string[] }
  key_points: { point: string; method: string }[]
  difficult_points: { point: string; breakthrough: string }[]
  teaching_steps: { stage: string; duration_min: number; activity: string; intent: string }[]
  case_materials: { name: string; relevance: string }[]
  homework: { type: string; content: string }[]
  extended_readings: { title: string; author: string }[]
  reflection_tips: string[]
}

function parseJson(raw: string): any | null {
  try { const d = JSON.parse(raw); if (d && typeof d === 'object') return d } catch {}
  const m = raw.match(/```(?:json)?\s*([\s\S]*?)```/)
  if (m) try { return JSON.parse(m[1]) } catch { return null }
  return null
}

export default function TeachingToolsPage() {
  const [tab, setTab] = useState<Tab>('quiz')
  const [error, setError] = useState('')

  // Quiz
  const [quizTopic, setQuizTopic] = useState('')
  const [difficulty, setDifficulty] = useState('中等')
  const [questionTypes, setQuestionTypes] = useState('选择题,简答题,辨析题')
  const [quizCount, setQuizCount] = useState(10)
  const [quizReqs, setQuizReqs] = useState('')
  const [quizData, setQuizData] = useState<QuizData | null>(null)
  const [quizRaw, setQuizRaw] = useState('')
  const [quizLoading, setQuizLoading] = useState(false)
  const [userAnswers, setUserAnswers] = useState<Record<number, string>>({})
  const [shortAnsGrading, setShortAnsGrading] = useState<Record<number, GradingResult>>({})
  const [showExplanations, setShowExplanations] = useState<Record<number, boolean>>({})
  const [score, setScore] = useState<number | null>(null)

  // Plan
  const [planTopic, setPlanTopic] = useState('')
  const [planHours, setPlanHours] = useState(2)
  const [planLevel, setPlanLevel] = useState('本科')
  const [planReqs, setPlanReqs] = useState('')
  const [planData, setPlanData] = useState<PlanData | null>(null)
  const [planRaw, setPlanRaw] = useState('')
  const [planLoading, setPlanLoading] = useState(false)

  const handleQuiz = async () => {
    if (!quizTopic.trim()) return
    setQuizLoading(true); setError(''); setQuizData(null); setQuizRaw('')
    setUserAnswers({}); setShowExplanations({}); setShortAnsGrading({}); setScore(null)
    try {
      const res = await fetch('/api/v1/teaching/quiz', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: quizTopic.trim(), difficulty, question_types: questionTypes, count: quizCount, requirements: quizReqs.trim() || undefined })
      })
      const r = await res.json()
      if (r.success) {
        const parsed = parseJson(r.content)
        if (parsed?.questions) setQuizData(parsed as QuizData)
        else setQuizRaw(r.content)
      } else setError(r.detail || '生成失败')
    } catch { setError('请求失败') }
    finally { setQuizLoading(false) }
  }

  const answerChoice = (qid: number, answer: string) => {
    setUserAnswers(prev => ({ ...prev, [qid]: answer }))
    setShowExplanations(prev => ({ ...prev, [qid]: true }))
  }

  const submitShortAnswer = async (qid: number, question: string, referenceAnswer: string, scoringPoints?: string[]) => {
    const userAnswer = userAnswers[qid] || ''
    if (!userAnswer.trim()) return

    setShortAnsGrading(prev => ({ ...prev, [qid]: { loading: true } }))
    try {
      const res = await fetch('/api/v1/teaching/grade-answer', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, reference_answer: referenceAnswer, user_answer: userAnswer, scoring_points: scoringPoints || [] })
      })
      const r = await res.json()
      setShortAnsGrading(prev => ({ ...prev, [qid]: { loading: false, score: r.score, feedback: r.feedback, covered_points: r.covered_points || [], partial_points: r.partial_points || [], missed_points: r.missed_points || [] } }))
      setShowExplanations(prev => ({ ...prev, [qid]: true }))
    } catch {
      setShortAnsGrading(prev => ({ ...prev, [qid]: { loading: false, feedback: '评分失败' } }))
    }
  }

  const retryShortAnswer = (qid: number) => {
    setShortAnsGrading(prev => { const n = { ...prev }; delete n[qid]; return n })
    setShowExplanations(prev => { const n = { ...prev }; delete n[qid]; return n })
  }

  const calculateScore = () => {
    if (!quizData) return
    let total = 0; let earned = 0
    quizData.questions.forEach(q => {
      total += 10
      if (q.type === 'choice' && q.options?.length) {
        if (userAnswers[q.id] === q.answer) earned += 10
      } else {
        const g = shortAnsGrading[q.id]
        if (g?.score !== undefined) earned += g.score
      }
    })
    setScore(Math.round(earned / total * 100))
  }

  const handlePlan = async () => {
    if (!planTopic.trim()) return
    setPlanLoading(true); setError(''); setPlanData(null); setPlanRaw('')
    try {
      const res = await fetch('/api/v1/teaching/plan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: planTopic.trim(), hours: planHours, level: planLevel, requirements: planReqs.trim() || undefined })
      })
      const r = await res.json()
      if (r.success) {
        const parsed = parseJson(r.content)
        if (parsed?.objectives) setPlanData(parsed as PlanData)
        else setPlanRaw(r.content)
      } else setError(r.detail || '生成失败')
    } catch { setError('请求失败') }
    finally { setPlanLoading(false) }
  }

  const handleExport = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = filename; a.click()
  }

  const handleExportFile = async (jsonData: object, format: 'docx'|'pptx', title: string) => {
    try {
      const res = await fetch('/api/v1/teaching/export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ json_content: JSON.stringify(jsonData), format, title })
      })
      if (!res.ok) { const err = await res.text(); throw new Error(err) }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${title}.${format}`
      a.click()
    } catch (e) { setError('导出失败: ' + String(e)) }
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-lg bg-rose-100 flex items-center justify-center"><Zap className="w-5 h-5 text-rose-600" /></div>
          <h1 className="text-2xl font-bold text-gray-800">教学工具</h1>
        </div>
        <p className="text-gray-500 ml-13">交互式随堂测验 + 教案智能生成与可视化</p>
      </div>

      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 mb-6">
        {[{ k: 'quiz' as Tab, i: PenLine, l: '随堂测验' }, { k: 'plan' as Tab, i: BookOpen, l: '教案生成' }].map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-medium transition-all ${tab===t.k?'bg-white text-rose-700 shadow-sm':'text-gray-500 hover:text-gray-700'}`}><t.i className="w-4 h-4"/>{t.l}</button>
        ))}
      </div>

      {error && <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-600 mb-6">{error}</div>}

      {/* ── Quiz Tab ── */}
      {tab === 'quiz' && (
        <div>
          {!quizData && !quizRaw && (
            <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm mb-6">
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="col-span-2"><label className="block text-sm font-medium text-gray-700 mb-1">课程主题</label><input type="text" value={quizTopic} onChange={e=>setQuizTopic(e.target.value)} placeholder="如：城市治理中的公众参与" className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/20 focus:border-rose-500"/></div>
                <div><label className="block text-sm font-medium text-gray-700 mb-1">难度</label><select value={difficulty} onChange={e=>setDifficulty(e.target.value)} className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm"><option>简单</option><option>中等</option><option>较难</option><option>混合</option></select></div>
                <div><label className="block text-sm font-medium text-gray-700 mb-1">题量</label><input type="number" value={quizCount} onChange={e=>setQuizCount(Number(e.target.value))} min={3} max={30} className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm"/></div>
                <div className="col-span-2"><label className="block text-sm font-medium text-gray-700 mb-1">题型</label><input type="text" value={questionTypes} onChange={e=>setQuestionTypes(e.target.value)} className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm"/></div>
                <div className="col-span-2"><label className="block text-sm font-medium text-gray-700 mb-1">补充要求</label><textarea value={quizReqs} onChange={e=>setQuizReqs(e.target.value)} rows={2} className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm resize-none"/></div>
              </div>
              <button onClick={handleQuiz} disabled={quizLoading||!quizTopic.trim()} className="w-full py-3 bg-gradient-to-r from-rose-500 to-pink-600 text-white rounded-xl text-sm font-medium hover:from-rose-600 hover:to-pink-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2">
                {quizLoading?<Loader2 className="w-4 h-4 animate-spin"/>:<PenLine className="w-4 h-4"/>}{quizLoading?'生成中...':'生成随堂测验'}</button>
            </div>
          )}

          {quizData && (
            <div className="space-y-5">
              {/* Quiz header */}
              <div className="bg-gradient-to-r from-rose-500 to-pink-600 rounded-2xl p-6 text-white">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold">{quizData.title}</h2>
                    <p className="text-rose-100 text-sm mt-1">{quizData.topic} · {quizData.difficulty} · {quizData.time_minutes}分钟 · {quizData.total_score}分</p>
                  </div>
                  {score !== null && (
                    <div className="text-center bg-white/20 rounded-xl px-4 py-2">
                      <div className="text-2xl font-bold">{score}/{quizData.questions.length}</div>
                      <div className="text-xs text-rose-100">{Math.round(score/quizData.questions.length*100)}%</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Questions */}
              {quizData.questions.map((q) => {
                const isChoice = q.type === 'choice' && q.options && q.options.length > 0
                const isShortAns = q.type === 'short_answer' || q.type === 'essay' || (!isChoice && !q.options)
                const answered = isChoice ? (q.id in userAnswers) : (shortAnsGrading[q.id]?.score !== undefined)
                const graded = shortAnsGrading[q.id]
                const isCorrect = isChoice
                  ? userAnswers[q.id] === q.answer
                  : ((graded?.score || 0) >= 6)
                const showExp = showExplanations[q.id]
                return (
                  <div key={q.id} className={`bg-white border rounded-xl p-5 shadow-sm transition-all ${answered?(isCorrect?'border-emerald-300 bg-emerald-50/30':'border-red-300 bg-red-50/30'):'border-gray-100'}`}>
                    <div className="flex items-start gap-3">
                      <span className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold flex-shrink-0 ${answered?(isCorrect?'bg-emerald-100 text-emerald-700':'bg-red-100 text-red-700'):'bg-gray-100 text-gray-600'}`}>{q.id}</span>
                      <div className="flex-1">
                        <p className="text-sm font-medium text-gray-800 mb-3">
                          <span className="text-xs text-gray-400 mr-2 uppercase">{q.type==='choice'?'选择题':q.type==='short_answer'?'简答题':'辨析题'}</span>
                          {q.question}
                        </p>
                        {/* Choice options */}
                        {isChoice && (
                          <div className="space-y-2 mb-3">
                            {q.options!.map((opt) => {
                              const optLetter = opt.trim().charAt(0)
                              return (
                                <button key={optLetter} onClick={() => !answered && answerChoice(q.id, optLetter)}
                                  disabled={answered}
                                  className={`w-full text-left px-4 py-3 rounded-lg text-sm transition-all ${
                                    answered
                                      ? optLetter === q.answer ? 'bg-emerald-100 border border-emerald-300 text-emerald-800'
                                      : optLetter === userAnswers[q.id] ? 'bg-red-100 border border-red-300 text-red-800'
                                      : 'bg-gray-50 text-gray-500'
                                      : 'bg-gray-50 hover:bg-blue-50 hover:border-blue-200 border border-transparent text-gray-700'
                                  }`}>
                                  <span className="font-medium mr-2">{optLetter}.</span>{opt.slice(2).trim() || opt}
                                  {answered && optLetter === q.answer && <CheckCircle2 className="w-4 h-4 inline ml-2 text-emerald-600"/>}
                                  {answered && optLetter === userAnswers[q.id] && optLetter !== q.answer && <XCircle className="w-4 h-4 inline ml-2 text-red-600"/>}
                                </button>
                              )
                            })}
                          </div>
                        )}
                        {/* Short answer / essay input */}
                        {isShortAns && (
                          <div>
                            {!answered && (
                              <div className="space-y-2">
                                <textarea
                                  placeholder="输入你的答案..." rows={3}
                                  value={userAnswers[q.id] || ''}
                                  onChange={e => setUserAnswers(prev => ({ ...prev, [q.id]: e.target.value }))}
                                  className="w-full px-4 py-3 rounded-lg text-sm border border-gray-200 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-rose-500/20 focus:border-rose-400 resize-none"
                                />
                                <button
                                  onClick={() => submitShortAnswer(q.id, q.question, String(q.answer), q.scoring_points)}
                                  disabled={!userAnswers[q.id]?.trim() || shortAnsGrading[q.id]?.loading}
                                  className="px-4 py-2 bg-rose-500 hover:bg-rose-600 disabled:opacity-50 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                                >
                                  {shortAnsGrading[q.id]?.loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                                  提交答案
                                </button>
                              </div>
                            )}
                            {answered && shortAnsGrading[q.id] && (
                              <div className="space-y-2">
                                {/* Grading result */}
                                <div className={`p-3 rounded-lg text-sm ${
                                  (shortAnsGrading[q.id].score || 0) >= 8 ? 'bg-emerald-50 border border-emerald-200 text-emerald-800' :
                                  (shortAnsGrading[q.id].score || 0) >= 6 ? 'bg-amber-50 border border-amber-200 text-amber-800' :
                                  'bg-red-50 border border-red-200 text-red-800'
                                }`}>
                                  <div className="flex items-center gap-2 font-medium mb-1">
                                    <span>得分：{shortAnsGrading[q.id].score}/10</span>
                                    {(shortAnsGrading[q.id].score || 0) >= 6
                                      ? <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                      : <XCircle className="w-4 h-4 text-red-600" />}
                                  </div>
                                  <p className="text-xs opacity-80">{shortAnsGrading[q.id].feedback}</p>
                                </div>
                                {/* Scoring points coverage */}
                                {((shortAnsGrading[q.id].covered_points?.length || 0) > 0 || (shortAnsGrading[q.id].missed_points?.length || 0) > 0 || (shortAnsGrading[q.id].partial_points?.length || 0) > 0) && (
                                  <div className="grid grid-cols-1 gap-1 text-xs">
                                    {shortAnsGrading[q.id].covered_points?.map((p, i) => (
                                      <div key={`cov-${i}`} className="flex items-center gap-1.5 px-2 py-1.5 bg-emerald-50 border border-emerald-100 rounded">
                                        <CheckCircle2 className="w-3 h-3 text-emerald-500 flex-shrink-0" /><span className="text-emerald-700">{p}</span>
                                      </div>
                                    ))}
                                    {shortAnsGrading[q.id].partial_points?.map((p, i) => (
                                      <div key={`par-${i}`} className="flex items-center gap-1.5 px-2 py-1.5 bg-amber-50 border border-amber-100 rounded">
                                        <AlertTriangle className="w-3 h-3 text-amber-500 flex-shrink-0" /><span className="text-amber-700">{p}</span>
                                      </div>
                                    ))}
                                    {shortAnsGrading[q.id].missed_points?.map((p, i) => (
                                      <div key={`mis-${i}`} className="flex items-center gap-1.5 px-2 py-1.5 bg-red-50 border border-red-100 rounded">
                                        <XCircle className="w-3 h-3 text-red-400 flex-shrink-0" /><span className="text-red-600">{p}</span>
                                      </div>
                                    ))}
                                  </div>
                                )}
                                {/* User answer */}
                                <div className="bg-gray-50 rounded-lg p-3 text-sm">
                                  <p className="text-xs text-gray-400 mb-1">你的答案：</p>
                                  <p className="text-gray-700 whitespace-pre-wrap">{userAnswers[q.id]}</p>
                                </div>
                                {/* Reference answer & scoring points */}
                                <div className="bg-blue-50 rounded-lg p-3 text-sm">
                                  <p className="text-xs text-gray-400 mb-1">参考答案：</p>
                                  <p className="text-gray-700 mb-2">{Array.isArray(q.answer) ? q.answer.join('；') : String(q.answer)}</p>
                                  {q.scoring_points && q.scoring_points.length > 0 && (
                                    <div>
                                      <p className="text-xs text-blue-400 mb-1">得分要点：</p>
                                      <div className="flex flex-wrap gap-1">
                                        {q.scoring_points.map((sp, i) => (
                                          <span key={i} className="inline-block px-1.5 py-0.5 bg-white border border-blue-100 rounded text-xs text-blue-600">{i + 1}. {sp}</span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                                {/* Retry button */}
                                <button
                                  onClick={() => retryShortAnswer(q.id)}
                                  className="px-3 py-1.5 text-xs text-gray-500 hover:text-rose-600 border border-gray-200 hover:border-rose-200 rounded-lg transition-colors flex items-center gap-1"
                                >
                                  <RotateCcw className="w-3 h-3" />重新作答
                                </button>
                              </div>
                            )}
                          </div>
                        )}
                        {/* Explanation toggle */}
                        {answered && q.explanation && (
                          <div className="mt-3">
                            <button onClick={() => setShowExplanations(prev=>({...prev,[q.id]:!prev[q.id]}))}
                              className="flex items-center gap-1 text-xs text-gray-500 hover:text-blue-600">
                              <Lightbulb className="w-3 h-3"/>解析 {showExp?<ChevronUp className="w-3 h-3"/>:<ChevronDown className="w-3 h-3"/>}
                            </button>
                            {showExp && <p className="mt-2 text-xs text-gray-600 bg-amber-50 rounded-lg p-3">{q.explanation}</p>}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}

              {/* Submit button */}
              <div className="flex gap-3">
                <button onClick={calculateScore}
                  disabled={!quizData.questions.every(q => (q.type === 'choice' && q.options?.length) ? (q.id in userAnswers) : (shortAnsGrading[q.id]?.score !== undefined))}
                  className="flex-1 py-3 bg-gradient-to-r from-rose-500 to-pink-600 text-white rounded-xl text-sm font-medium hover:from-rose-600 hover:to-pink-700 disabled:opacity-50 transition-all">
                  计算总分（已评 {quizData.questions.filter(q => (q.type === 'choice' && q.options?.length) ? (q.id in userAnswers) : (shortAnsGrading[q.id]?.score !== undefined)).length}/{quizData.questions.length}）
                </button>
                <button onClick={() => handleExportFile(quizData, 'docx', quizData.title || quizTopic)}
                  className="px-4 py-3 bg-blue-500 hover:bg-blue-600 text-white rounded-xl text-sm font-medium transition-colors flex items-center gap-2"><Download className="w-4 h-4"/>导出 Word</button>
              </div>
            </div>
          )}

          {quizRaw && !quizData && <div className="bg-white rounded-xl p-6 shadow-sm"><div className="prose prose-gray max-w-none text-sm"><ReactMarkdown>{quizRaw}</ReactMarkdown></div></div>}
        </div>
      )}

      {/* ── Plan Tab ── */}
      {tab === 'plan' && (
        <div>
          {!planData && !planRaw && (
            <div className="bg-white border border-gray-100 rounded-xl p-6 shadow-sm mb-6">
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="col-span-2"><label className="block text-sm font-medium text-gray-700 mb-1">课程主题</label><input type="text" value={planTopic} onChange={e=>setPlanTopic(e.target.value)} placeholder="如：公共政策分析导论" className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-rose-500/20 focus:border-rose-500"/></div>
                <div><label className="block text-sm font-medium text-gray-700 mb-1">课时</label><input type="number" value={planHours} onChange={e=>setPlanHours(Number(e.target.value))} min={1} max={8} className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm"/></div>
                <div><label className="block text-sm font-medium text-gray-700 mb-1">对象</label><select value={planLevel} onChange={e=>setPlanLevel(e.target.value)} className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm"><option>本科</option><option>硕士</option><option>MPA</option><option>博士</option></select></div>
                <div className="col-span-2"><label className="block text-sm font-medium text-gray-700 mb-1">补充要求</label><textarea value={planReqs} onChange={e=>setPlanReqs(e.target.value)} rows={2} className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm resize-none"/></div>
              </div>
              <button onClick={handlePlan} disabled={planLoading||!planTopic.trim()} className="w-full py-3 bg-gradient-to-r from-rose-500 to-pink-600 text-white rounded-xl text-sm font-medium hover:from-rose-600 hover:to-pink-700 disabled:opacity-50 transition-all flex items-center justify-center gap-2">
                {planLoading?<Loader2 className="w-4 h-4 animate-spin"/>:<BookOpen className="w-4 h-4"/>}{planLoading?'生成中...':'生成教案'}</button>
            </div>
          )}

          {planData && (
            <div className="space-y-5">
              {/* Objectives */}
              <div className="grid grid-cols-3 gap-4">
                {[
                  { t: '知识目标', items: planData.objectives?.knowledge, icon: BookOpen, color: 'blue' },
                  { t: '能力目标', items: planData.objectives?.ability, icon: Target, color: 'emerald' },
                  { t: '素养目标', items: planData.objectives?.literacy, icon: Lightbulb, color: 'amber' }
                ].map(g => (
                  <div key={g.t} className={`bg-${g.color}-50 border border-${g.color}-200 rounded-xl p-4`}>
                    <h4 className={`text-sm font-semibold text-${g.color}-700 mb-2 flex items-center gap-1.5`}><g.icon className="w-4 h-4"/>{g.t}</h4>
                    <ul className="space-y-1.5">{g.items?.map((item,i)=>(<li key={i} className={`text-xs text-${g.color}-700 flex gap-1.5`}><span className={`text-${g.color}-400`}>•</span>{item}</li>))}</ul>
                  </div>
                ))}
              </div>

              {/* Time distribution bar chart */}
              <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2"><PieChart className="w-4 h-4 text-rose-500"/>教学环节时间分配（共{planHours*60}分钟）</h3>
                <div className="flex h-8 rounded-lg overflow-hidden">
                  {['bg-blue-400','bg-emerald-400','bg-amber-400','bg-violet-400','bg-rose-400','bg-indigo-400'].map((c,i)=>(
                    i < (planData.teaching_steps?.length||0) && (
                      <div key={i} className={`${c} flex items-center justify-center text-xs text-white font-medium`}
                        style={{width:`${((planData.teaching_steps?.[i]?.duration_min||0)/(planHours*60))*100}%`}}>
                        {planData.teaching_steps[i].duration_min}'
                      </div>
                    )
                  ))}
                </div>
                <div className="flex flex-wrap gap-3 mt-3">
                  {planData.teaching_steps?.map((s,i)=>(
                    <div key={i} className="flex items-center gap-1.5 text-xs text-gray-500">
                      <span className={`w-3 h-3 rounded ${['bg-blue-400','bg-emerald-400','bg-amber-400','bg-violet-400','bg-rose-400','bg-indigo-400'][i%6]}`}/>
                      {s.stage}({s.duration_min}min)
                    </div>
                  ))}
                </div>
              </div>

              {/* Teaching steps timeline */}
              <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-2"><Clock className="w-4 h-4 text-blue-500"/>教学环节设计</h3>
                <div className="relative pl-8 border-l-2 border-blue-200 space-y-6">
                  {planData.teaching_steps?.map((s,i)=>(
                    <div key={i} className="relative">
                      <div className="absolute -left-[33px] w-4 h-4 rounded-full bg-blue-500 border-2 border-white"/>
                      <div className="flex items-start justify-between">
                        <div>
                          <span className="text-sm font-semibold text-gray-800">{s.stage}</span>
                          <span className="text-xs text-gray-500 ml-2">{s.duration_min}分钟</span>
                        </div>
                      </div>
                      <p className="text-sm text-gray-600 mt-1"><strong>活动：</strong>{s.activity}</p>
                      <p className="text-xs text-gray-400 mt-0.5"><strong>意图：</strong>{s.intent}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Key & Difficult points */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-emerald-500"/>教学重点</h3>
                  <div className="space-y-3">{planData.key_points?.map((kp,i)=>(
                    <div key={i} className="p-3 bg-emerald-50 rounded-lg">
                      <p className="text-sm font-medium text-emerald-800">{kp.point}</p>
                      <p className="text-xs text-emerald-600 mt-1">方法：{kp.method}</p>
                    </div>
                  ))}</div>
                </div>
                <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                  <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-amber-500"/>教学难点</h3>
                  <div className="space-y-3">{planData.difficult_points?.map((dp,i)=>(
                    <div key={i} className="p-3 bg-amber-50 rounded-lg">
                      <p className="text-sm font-medium text-amber-800">{dp.point}</p>
                      <p className="text-xs text-amber-600 mt-1">突破：{dp.breakthrough}</p>
                    </div>
                  ))}</div>
                </div>
              </div>

              {/* Case materials + Homework + Readings */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
                  <h3 className="text-xs font-semibold text-gray-500 mb-2">📋 案例素材</h3>
                  {planData.case_materials?.map((cm,i)=>(<p key={i} className="text-xs text-gray-600 mb-1"><strong>{cm.name}</strong><br/>{cm.relevance}</p>))}
                </div>
                <div className="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
                  <h3 className="text-xs font-semibold text-gray-500 mb-2">✏️ 课后作业</h3>
                  {planData.homework?.map((h,i)=>(<p key={i} className="text-xs text-gray-600 mb-1"><strong>[{h.type}]</strong> {h.content}</p>))}
                </div>
                <div className="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
                  <h3 className="text-xs font-semibold text-gray-500 mb-2">📖 推荐阅读</h3>
                  {planData.extended_readings?.map((er,i)=>(<p key={i} className="text-xs text-gray-600 mb-1">{er.title} — {er.author}</p>))}
                </div>
              </div>

              {/* Export */}
              <div className="flex gap-3">
                <button onClick={()=>handleExportFile(planData,'docx',planTopic)}
                  className="flex-1 py-3 bg-blue-500 hover:bg-blue-600 text-white rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-2"><Download className="w-4 h-4"/>导出 Word</button>
                <button onClick={()=>handleExportFile(planData,'pptx',planTopic)}
                  className="flex-1 py-3 bg-orange-500 hover:bg-orange-600 text-white rounded-xl text-sm font-medium transition-colors flex items-center justify-center gap-2"><Download className="w-4 h-4"/>导出 PPT</button>
              </div>
            </div>
          )}

          {planRaw && !planData && <div className="bg-white rounded-xl p-6 shadow-sm"><div className="prose prose-gray max-w-none text-sm"><ReactMarkdown>{planRaw}</ReactMarkdown></div></div>}
        </div>
      )}
    </div>
  )
}
