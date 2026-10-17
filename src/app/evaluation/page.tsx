'use client'

import { useEffect, useMemo, useState } from 'react'
import MainLayout from '@/components/layout/MainLayout'
import { motion } from 'framer-motion'
import {
  Gauge,
  Target,
  BookOpenCheck,
  Layers3,
  RefreshCw,
  PlayCircle,
  FileSearch,
  Award,
  ListChecks,
  BarChart3,
  ChevronRight,
  ExternalLink,
  CheckCircle2
} from 'lucide-react'
import {
  fetchUrbanGovEvalTasks,
  fetchUrbanGovEvalSummary,
  fetchUrbanGovEvalLeaderboard,
  fetchUrbanGovEvalPerTask,
  runUrbanGovEval,
  UrbanGovEvalTask,
  UrbanGovEvalSummary,
  LeaderboardItem,
  UrbanGovEvalPerTaskResult
} from '@/services/evaluation'
import { toast, Toaster } from 'react-hot-toast'
import clsx from 'clsx'

type NormalizationMethod = 'ratio' | 'relative'
const MANUAL_SCORE_STORAGE_KEY = 'urban-gov-eval-manual-scores'
const DEFAULT_MANUAL_SCORE = 85
const MANUAL_SCORE_WEIGHT = 0.15

export default function UrbanGovEvalPage() {
  const [tasks, setTasks] = useState<UrbanGovEvalTask[]>([])
  const [leaderboard, setLeaderboard] = useState<LeaderboardItem[]>([])
  const [summary, setSummary] = useState<UrbanGovEvalSummary | null>(null)
  const [modelInput, setModelInput] = useState('qwen3-8b-it-sft-dpo-t')
  const [activeModel, setActiveModel] = useState('qwen3-8b-it-sft-dpo-t')
  const [normalization, setNormalization] = useState<NormalizationMethod>('ratio')
  const [loadingInit, setLoadingInit] = useState(true)
  const [runningEval, setRunningEval] = useState(false)
  const [fetchingSummary, setFetchingSummary] = useState(false)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [perTaskCache, setPerTaskCache] = useState<Record<string, UrbanGovEvalPerTaskResult>>({})
  const [fetchingTaskDetail, setFetchingTaskDetail] = useState(false)
  const [detailAnchorId] = useState('task-detail-anchor')
  const [manualScores, setManualScores] = useState<Record<string, number>>({})
  const renderModelName = (name: string) => (name === 'qwen-plus' ? 'qwen-max' : name)
  const domainBadge = (domain: string) => {
    const map: Record<string, string> = {
      城市更新: 'bg-blue-50 text-blue-700 border-blue-200',
      公共安全: 'bg-rose-50 text-rose-700 border-rose-200',
      数字治理: 'bg-amber-50 text-amber-700 border-amber-200',
      城市交通: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      医疗保障: 'bg-purple-50 text-purple-700 border-purple-200',
      环境治理: 'bg-teal-50 text-teal-700 border-teal-200'
    }
    return map[domain] ?? 'bg-gray-50 text-gray-700 border-gray-200'
  }
  const difficultyBadge = (difficulty: string) => {
    const map: Record<string, string> = {
      easy: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      medium: 'bg-amber-50 text-amber-700 border-amber-200',
      hard: 'bg-rose-50 text-rose-700 border-rose-200'
    }
    return map[difficulty] ?? 'bg-gray-50 text-gray-700 border-gray-200'
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        const [taskData, leaderboardData] = await Promise.all([
          fetchUrbanGovEvalTasks(),
          fetchUrbanGovEvalLeaderboard()
        ])
        setTasks(taskData)
        setLeaderboard(leaderboardData)
      } catch (err) {
        console.error(err)
        toast.error('加载 UrbanGovEval 基础数据失败')
      } finally {
        setLoadingInit(false)
      }
    }
    bootstrap()
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(MANUAL_SCORE_STORAGE_KEY)
      if (raw) {
        const parsed = JSON.parse(raw)
        if (parsed && typeof parsed === 'object') {
          setManualScores(parsed)
        }
      }
    } catch (err) {
      console.error('加载人工评分失败', err)
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(MANUAL_SCORE_STORAGE_KEY, JSON.stringify(manualScores))
    } catch (err) {
      console.error('保存人工评分失败', err)
    }
  }, [manualScores])

  useEffect(() => {
    async function loadSummary(targetModel: string) {
      if (!targetModel) {
        setSummary(null)
        return
      }
      setFetchingSummary(true)
      try {
        const data = await fetchUrbanGovEvalSummary(targetModel)
        setSummary(data)
        setActiveModel(targetModel)
      } catch (err: any) {
        if (err?.response?.status === 404) {
          setSummary(null)
        } else {
          toast.error('获取模型评测摘要失败')
        }
      } finally {
        setFetchingSummary(false)
      }
    }
    loadSummary(activeModel)
  }, [activeModel])

  const perModelManualAverage = useMemo(() => {
    const buckets: Record<string, { sum: number; count: number }> = {}
    Object.entries(manualScores).forEach(([key, value]) => {
      const [model] = key.split('::')
      if (!model) return
      if (!buckets[model]) {
        buckets[model] = { sum: 0, count: 0 }
      }
      buckets[model].sum += value
      buckets[model].count += 1
    })
    const averages: Record<string, number> = {}
    Object.entries(buckets).forEach(([model, stats]) => {
      if (stats.count > 0) {
        averages[model] = Number((stats.sum / stats.count).toFixed(2))
      }
    })
    return averages
  }, [manualScores])

  const computeBlendedScore = (autoScore: number, manualAvg: number | undefined | null) => {
    if (manualAvg === undefined || manualAvg === null) {
      return Number(autoScore.toFixed(2))
    }
    return Number(
      (autoScore * (1 - MANUAL_SCORE_WEIGHT) + manualAvg * MANUAL_SCORE_WEIGHT).toFixed(2)
    )
  }

  const currentManualAverage = summary ? perModelManualAverage[summary.model_name] : undefined

  const overviewCards = useMemo(() => {
    const blended = summary ? computeBlendedScore(summary.overall_score, currentManualAverage) : null
    const manualValue = currentManualAverage ?? null
    return [
      {
        label: '综合得分（含人工）',
        value: blended !== null ? blended.toFixed(2) : '--',
        description: summary
          ? `自动 ${summary.overall_score.toFixed(2)}，人工权重 ${Math.round(MANUAL_SCORE_WEIGHT * 100)}%`
          : '完成评测与人工质检后生成',
        icon: Gauge,
        gradient: 'from-blue-500 to-sky-500'
      },
      {
        label: 'RACE-UG 质量线',
        value: summary ? summary.race_score.toFixed(2) : '--',
        description: summary
          ? `95% CI ${summary.race_ci.lower.toFixed(2)} - ${summary.race_ci.upper.toFixed(2)}`
          : '按任务自适应标准转化为 0-100',
        icon: Target,
        gradient: 'from-indigo-500 to-purple-500'
      },
      {
        label: '任务专属指标',
        value: summary ? summary.task_metrics_norm.toFixed(2) : '--',
        description: summary
          ? `指标平均值 ${summary.task_metrics_norm.toFixed(2)}，关注多轮稳定性`
          : '统一换算为 0-100，关注任务稳定性',
        icon: Layers3,
        gradient: 'from-amber-500 to-orange-500'
      },
      {
        label: '人工质检均分',
        value: manualValue !== null ? manualValue.toFixed(2) : '--',
        description:
          manualValue !== null
            ? '记录本地人工评审的平均分，实时参与综合得分'
            : '手动打分后自动纳入综合得分',
        icon: CheckCircle2,
        gradient: 'from-blue-400 to-indigo-500'
      }
    ]
  }, [summary, currentManualAverage])

  const handleRunEvaluation = async () => {
    if (!modelInput.trim()) {
      toast.error('请先填写模型名称')
      return
    }
    setRunningEval(true)
    try {
      const result = await runUrbanGovEval(modelInput.trim(), normalization)
      setSummary(result)
      setActiveModel(result.model_name)
      toast.success(`模型 ${result.model_name} 评测完成`)
      const refreshed = await fetchUrbanGovEvalLeaderboard()
      setLeaderboard(refreshed)
    } catch (err) {
      console.error(err)
      toast.error('执行评测失败，请稍后再试')
    } finally {
      setRunningEval(false)
    }
  }

  const handleSelectLeaderboardModel = (modelName: string) => {
    setActiveModel(modelName)
    setSelectedTaskId(null)
  }

  const handleSelectTask = async (taskId: string) => {
    if (!activeModel) {
      toast('请先选择或运行一次模型评测')
      return
    }
    const cacheKey = `${activeModel}::${taskId}`
    setSelectedTaskId(taskId)
    if (perTaskCache[cacheKey]) {
      return
    }
    setFetchingTaskDetail(true)
    try {
      const data = await fetchUrbanGovEvalPerTask(activeModel, taskId)
      setPerTaskCache((prev) => ({ ...prev, [cacheKey]: data }))
    } catch (err: any) {
      if (err?.response?.status === 404) {
        toast.error('尚未生成该模型的此题评测结果')
      } else {
        toast.error('加载题目评测详情失败')
      }
    } finally {
      setFetchingTaskDetail(false)
    }
  }

  const selectedTaskDefinition = useMemo(() => {
    if (!selectedTaskId) return null
    return tasks.find((task) => task.task_id === selectedTaskId) ?? null
  }, [tasks, selectedTaskId])

  const selectedTaskData = useMemo(() => {
    if (!selectedTaskId || !activeModel) return null
    const cacheKey = `${activeModel}::${selectedTaskId}`
    return perTaskCache[cacheKey] ?? null
  }, [perTaskCache, selectedTaskId, activeModel])

  const manualScoreKey = useMemo(() => {
    if (!activeModel || !selectedTaskId) return null
    return `${activeModel}::${selectedTaskId}`
  }, [activeModel, selectedTaskId])

  const leaderboardWithManual = useMemo(() => {
    const mapped = leaderboard.map((item) => {
      const manualAvg = perModelManualAverage[item.model_name]
      const blendedOverall = computeBlendedScore(item.overall_score, manualAvg)
      return {
        ...item,
        manualAvg,
        blendedOverall
      }
    })
    return mapped.sort((a, b) => b.blendedOverall - a.blendedOverall)
  }, [leaderboard, perModelManualAverage])

  const manualScoreValue =
    manualScoreKey && manualScores[manualScoreKey] !== undefined
      ? manualScores[manualScoreKey]
      : null

  const handleManualScoreChange = (value: number) => {
    if (!manualScoreKey) return
    const clamped = Math.max(0, Math.min(100, Math.round(value)))
    setManualScores((prev) => ({ ...prev, [manualScoreKey]: clamped }))
  }

  const clearManualScore = () => {
    if (!manualScoreKey) return
    setManualScores((prev) => {
      const updated = { ...prev }
      delete updated[manualScoreKey]
      return updated
    })
  }

  const handleManualScoreInput = (value: string) => {
    if (!manualScoreKey) return
    if (value.trim() === '') {
      clearManualScore()
      return
    }
    const parsed = Number(value)
    if (Number.isNaN(parsed)) return
    handleManualScoreChange(parsed)
  }

  useEffect(() => {
    if (selectedTaskId && document) {
      const el = document.getElementById(detailAnchorId)
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }
  }, [selectedTaskId, detailAnchorId])

  return (
    <MainLayout>
      <Toaster position="top-right" />
      <div className="max-w-7xl mx-auto py-6 space-y-6">
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white/80 backdrop-blur-sm border border-gray-200 rounded-2xl p-6"
        >
          <div className="flex flex-col lg:flex-row gap-6 justify-between">
            <div>
              <h1 className="text-2xl font-semibold text-gray-900">
                UrbanGovEval 模型性能测评
              </h1>
              <p className="text-sm text-gray-600 mt-2 leading-6">
                围绕政务问答、政策解析、场景推演与多轮咨询等关键任务，构建贴近实务、可复现、可扩展的城市治理大模型评测基准。
                评测流程覆盖任务数据集构建、自适应标准生成、RACE-UG 质量评分、FACT-UG 证据校验、任务专属指标、人工复核触发、汇总与分析全链路。
              </p>
            </div>
            <div className="shrink-0 flex flex-col gap-3 w-full lg:w-80">
              <div className="flex gap-3">
                <input
                  value={modelInput}
                  onChange={(e) => setModelInput(e.target.value)}
                  placeholder="参评模型名称，如 qwen-max"
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button
                  onClick={handleRunEvaluation}
                  disabled={runningEval}
                  className={clsx(
                    'inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-all',
                    runningEval ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700'
                  )}
                >
                  {runningEval ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      评测中
                    </>
                  ) : (
                    <>
                      <PlayCircle className="w-4 h-4" />
                      运行评测
                    </>
                  )}
                </button>
              </div>
              <div className="flex gap-3">
                <select
                  value={normalization}
                  onChange={(e) => setNormalization(e.target.value as NormalizationMethod)}
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="ratio">比例法：对齐参考上限</option>
                  <option value="relative">相对优势法：正负对称</option>
                </select>
                <button
                  onClick={() => setActiveModel(modelInput.trim())}
                  className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100"
                >
                  查看模型
                </button>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Overview */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4"
        >
          {overviewCards.map((card) => {
            const Icon = card.icon
            return (
              <div
                key={card.label}
                className="rounded-2xl border border-gray-200 bg-white/80 backdrop-blur-sm p-5 shadow-sm"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-500">{card.label}</p>
                    <p className="mt-2 text-3xl font-semibold text-gray-900">{card.value}</p>
                  </div>
                  <div className={`rounded-xl p-3 text-white bg-gradient-to-br ${card.gradient}`}>
                    <Icon className="w-6 h-6" />
                  </div>
                </div>
                <p className="mt-3 text-xs text-gray-500 leading-5">{card.description}</p>
              </div>
            )
          })}
        </motion.div>

        {/* Leaderboard & Domain breakdown */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="lg:col-span-2 rounded-2xl border border-gray-200 bg-white/80 backdrop-blur-sm p-5"
          >
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                  <Award className="w-5 h-5 text-amber-500" />
                  模型排行榜
                </h2>
                <p className="text-sm text-gray-500">支持点击切换查看不同模型的完整评测摘要</p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-200">
                    <th className="py-2">模型</th>
                    <th className="py-2">综合分*</th>
                    <th className="py-2">人工质检</th>
                    <th className="py-2">RACE</th>
                    <th className="py-2">EC*</th>
                    <th className="py-2">Task*</th>
                  </tr>
                </thead>
                <tbody>
                  {leaderboardWithManual.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-gray-400">
                        暂无评测记录，运行评测后自动生成
                      </td>
                    </tr>
                  ) : (
                    leaderboardWithManual.map((item) => (
                      <tr
                        key={item.model_name}
                        onClick={() => handleSelectLeaderboardModel(item.model_name)}
                        className={clsx(
                          'border-b border-gray-100 cursor-pointer hover:bg-blue-50/40 transition-colors',
                          activeModel === item.model_name ? 'bg-blue-50/60 font-medium' : ''
                        )}
                      >
                        <td className="py-3">{renderModelName(item.model_name)}</td>
                        <td className="py-3 text-gray-900">{item.blendedOverall.toFixed(2)}</td>
                        <td className="py-3">
                          {item.manualAvg !== undefined ? item.manualAvg.toFixed(2) : '--'}
                        </td>
                        <td className="py-3">{item.race_score.toFixed(2)}</td>
                        <td className="py-3">{item.effective_citations_norm.toFixed(2)}</td>
                        <td className="py-3">{item.task_metrics_norm.toFixed(2)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-gray-400">
              *综合分含人工质检 {Math.round(MANUAL_SCORE_WEIGHT * 100)}% 权重；EC：有效引用归一化；Task：任务专属指标归一化
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="rounded-2xl border border-gray-200 bg-white/80 backdrop-blur-sm p-5 space-y-3"
          >
            <div className="flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-blue-500" />
              <h2 className="text-lg font-semibold text-gray-900">主题域表现</h2>
            </div>
            {summary ? (
              summary.domain_breakdown.length > 0 ? (
                summary.domain_breakdown.map((domain) => (
                  <div
                    key={domain.domain}
                    className="rounded-xl border border-gray-100 p-3 bg-white/70"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-gray-900">{domain.domain}</p>
                        <p className="text-xs text-gray-500 mt-1">题量：{domain.task_count}</p>
                      </div>
                      <span className="text-lg font-semibold text-blue-600">
                        {domain.overall.toFixed(1)}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 mt-3">
                      <span>RACE {domain.race.toFixed(1)}</span>
                      <span>EC* {domain.effective_citations_norm.toFixed(1)}</span>
                      <span>Task* {domain.task_metrics_norm.toFixed(1)}</span>
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-sm text-gray-500">暂无主题域得分</p>
              )
            ) : (
              <p className="text-sm text-gray-500">
                运行一次评测后，将在此展示覆盖/深度/遵循/可读等维度的主题域拆解。
              </p>
            )}
          </motion.div>
        </div>

        {/* Task dataset */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border border-gray-200 bg-white/80 backdrop-blur-sm p-6"
        >
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
            <div className="flex items-center gap-2">
              <FileSearch className="w-5 h-5 text-green-500" />
              <div>
                <h2 className="text-lg font-semibold text-gray-900">任务数据集（Task Dataset）</h2>
                <p className="text-xs text-gray-500">
                  训练-评估严格隔离，每题自带输出要求、参考报告与权威来源。
                </p>
              </div>
            </div>
            <div className="flex items-center text-xs text-gray-500 gap-2">
              <ListChecks className="w-4 h-4" />
              当前任务：{tasks.length} 条
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-200">
                  <th className="py-2 px-3 whitespace-nowrap border-r border-gray-100">任务</th>
                  <th className="py-2 px-3 whitespace-nowrap border-r border-gray-100">主题域</th>
                  <th className="py-2 px-3 whitespace-nowrap border-r border-gray-100">难度</th>
                  <th className="py-2 px-3 whitespace-nowrap border-r border-gray-100">标准条目</th>
                  <th className="py-2 px-3 whitespace-nowrap border-r border-gray-100">引用期望</th>
                  <th className="py-2 px-3 text-right whitespace-nowrap">查看评测</th>
                </tr>
              </thead>
              <tbody>
                {loadingInit ? (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-gray-400">
                      正在加载任务数据...
                    </td>
                  </tr>
                ) : tasks.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-gray-400">
                      暂无任务，请补充 UrbanGovEval 数据集
                    </td>
                  </tr>
                ) : (
                  tasks.map((task) => (
                    <tr
                      key={task.task_id}
                      className={clsx(
                        'border-b border-gray-100 hover:bg-blue-50/30 transition-colors',
                        selectedTaskId === task.task_id ? 'bg-blue-50/40' : ''
                      )}
                    >
                      <td className="py-3 px-3 border-r border-gray-100">
                        <p className="font-medium text-gray-900">{task.title}</p>
                        <p className="text-xs text-gray-500 mt-1 line-clamp-2">{task.query}</p>
                      </td>
                      <td className="py-3 px-3 text-gray-600 whitespace-nowrap border-r border-gray-100">
                        <span
                          className={clsx(
                            'inline-flex items-center px-2 py-1 text-xs font-medium rounded-full border',
                            domainBadge(task.domain)
                          )}
                        >
                          {task.domain}
                        </span>
                      </td>
                      <td className="py-3 px-3 capitalize text-gray-600 whitespace-nowrap border-r border-gray-100">
                        <span
                          className={clsx(
                            'inline-flex items-center px-2 py-1 text-xs font-medium rounded-full border',
                            difficultyBadge(task.difficulty)
                          )}
                        >
                          {task.difficulty}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-gray-600 whitespace-nowrap border-r border-gray-100">
                        <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-gray-50 border border-gray-200 text-gray-700">
                          {task.criteria.length} 条
                        </span>
                      </td>
                      <td className="py-3 px-3 text-gray-600 whitespace-nowrap border-r border-gray-100">
                        {task.fact_expectation ? (
                          <div className="flex flex-col gap-1">
                            <span className="inline-flex items-center px-2 py-1 text-xs font-medium rounded-full bg-blue-50 border border-blue-200 text-blue-700">
                              {task.fact_expectation.expected_pairs} 对
                            </span>
                            <span className="inline-flex items-center px-2 py-1 text-[11px] font-medium rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700">
                              权威≥{Math.round(task.fact_expectation.min_authority_ratio * 100)}%
                            </span>
                          </div>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="py-3 px-3 text-right whitespace-nowrap">
                        <button
                          onClick={() => handleSelectTask(task.task_id)}
                          className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-700 text-sm"
                        >
                          查看
                          <ChevronRight className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </motion.div>

        {/* Per-task detail */}
        {selectedTaskId && (
          <motion.div
            id={detailAnchorId}
            key={selectedTaskId}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-2xl border border-gray-200 bg-white/90 backdrop-blur-sm p-6 space-y-4"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Target className="w-5 h-5 text-blue-600" />
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">
                    题目详情：{selectedTaskId}
                  </h3>
                  <p className="text-xs text-gray-500">
                    展示 RACE 评分拆解、FACT 证据线和任务专属指标，配合人工复核触发逻辑。
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedTaskId(null)}
                className="text-xs text-gray-500 hover:text-gray-700"
              >
                收起
              </button>
            </div>
            {fetchingTaskDetail && !selectedTaskData ? (
              <p className="text-sm text-gray-500">正在加载评测结果...</p>
            ) : selectedTaskData ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="rounded-xl border border-gray-100 p-4 bg-white/80">
                    <p className="text-sm text-gray-500">RACE-UG</p>
                    <p className="text-2xl font-semibold text-gray-900 mt-1">
                      {selectedTaskData.race.normalized_score.toFixed(2)}
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                      比例法：{selectedTaskData.race.ratio_score.toFixed(2)}，相对优势法：
                      {selectedTaskData.race.relative_advantage_score.toFixed(2)}
                    </p>
                  </div>
                  <div className="rounded-xl border border-gray-100 p-4 bg-white/80">
                    <p className="text-sm text-gray-500">引用准确率</p>
                    <p className="text-2xl font-semibold text-gray-900 mt-1">
                      {selectedTaskData.fact.citation_accuracy.toFixed(2)}%
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                      有效引用 {selectedTaskData.fact.effective_citations} /
                      总计 {selectedTaskData.fact.total_pairs}，误用率{' '}
                      {selectedTaskData.fact.misuse_rate.toFixed(2)}%
                    </p>
                  </div>
                  <div className="rounded-xl border border-gray-100 p-4 bg-white/80">
                    <p className="text-sm text-gray-500">任务专属指标</p>
                    <p className="text-2xl font-semibold text-gray-900 mt-1">
                      {selectedTaskData.task_metrics.length > 0
                        ? (
                            selectedTaskData.task_metrics.reduce((acc, cur) => acc + cur.normalized, 0) /
                            selectedTaskData.task_metrics.length
                          ).toFixed(2)
                        : '--'}
                    </p>
                    <p className="text-xs text-gray-500 mt-2">
                      指标数量：{selectedTaskData.task_metrics.length}
                    </p>
                  </div>
                </div>

                {selectedTaskDefinition && (
                  <div className="rounded-2xl border border-gray-200 bg-white/85 p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <FileSearch className="w-4 h-4 text-slate-500" />
                      <h4 className="font-semibold text-gray-900 text-sm">题目原始要求</h4>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-gray-600">
                      <div>
                        <p className="text-gray-500">领域 / 难度</p>
                        <p className="font-medium text-gray-900">
                          {selectedTaskDefinition.domain} · {selectedTaskDefinition.difficulty}
                        </p>
                      </div>
                      <div>
                        <p className="text-gray-500">时间参考</p>
                        <p className="font-medium text-gray-900">{selectedTaskDefinition.time_ref}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">输出要求</p>
                        <p className="font-medium text-gray-900">{selectedTaskDefinition.deliverable}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">参考报告</p>
                        <p className="font-medium text-gray-900">{selectedTaskDefinition.reference_report}</p>
                      </div>
                    </div>
                    <div>
                      <p className="text-gray-500 text-xs mb-1">原始问题</p>
                      <p className="text-sm text-gray-900 leading-6 whitespace-pre-line">
                        {selectedTaskDefinition.query}
                      </p>
                    </div>
                  </div>
                )}

                {manualScoreKey && (
                  <div className="rounded-2xl border border-blue-100 bg-blue-50/40 p-4 space-y-4">
                    <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                      <div className="flex items-center gap-2">
                        <CheckCircle2 className="w-4 h-4 text-blue-600" />
                        <h4 className="font-semibold text-gray-900 text-sm">人工质检（主观评分）</h4>
                      </div>
                      <span className="text-xs text-gray-500">
                        {manualScoreValue !== null ? `当前得分：${manualScoreValue}/100` : '尚未评分'}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500">
                      针对事实正确性、合规性、可执行性与表达清晰度进行一次人工感知评估，弥补纯自动指标的盲区。
                    </p>
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      <div className="space-y-4">
                        <div>
                          <label className="text-xs text-gray-500">拖动滑块或输入 0-100 分</label>
                          <input
                            type="range"
                            min={0}
                            max={100}
                            step={1}
                            value={manualScoreValue ?? DEFAULT_MANUAL_SCORE}
                            onChange={(e) => handleManualScoreChange(Number(e.target.value))}
                            className="w-full accent-blue-600 mt-2"
                          />
                          <div className="flex items-center gap-2 mt-3">
                            <input
                              type="number"
                              min={0}
                              max={100}
                              value={manualScoreValue ?? ''}
                              placeholder="未评分"
                              onChange={(e) => handleManualScoreInput(e.target.value)}
                              className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            />
                            {manualScoreValue !== null && (
                              <button
                                onClick={clearManualScore}
                                className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100"
                              >
                                清空
                              </button>
                            )}
                          </div>
                        </div>
                        <ul className="text-xs text-gray-600 space-y-1 bg-white rounded-lg border border-gray-100 p-3 leading-5">
                          <li>• 事实正确性：主观感知与引用材料是否一致。</li>
                          <li>• 合规性：是否存在政策/安全/隐私方面的潜在风险。</li>
                          <li>• 可执行性：步骤是否明确、可落地，能否指导实际办理。</li>
                          <li>• 表达清晰度：结构与语言是否清晰、便于阅读。</li>
                        </ul>
                      </div>
                      <div className="rounded-lg border border-gray-100 bg-white p-3">
                        <div className="flex items-center justify-between text-xs text-gray-500">
                          <span>模型回答（供打分参考）</span>
                          {selectedTaskData.metadata?.candidate_answer && (
                            <span className="text-gray-400">
                              字符 {selectedTaskData.metadata.candidate_answer.length}
                            </span>
                          )}
                        </div>
                        <div className="mt-2 max-h-64 overflow-y-auto text-sm text-gray-800 whitespace-pre-wrap leading-6">
                          {selectedTaskData.metadata?.candidate_answer ?? '暂无模型回答内容'}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div className="rounded-xl border border-gray-100 p-4 bg-white/80 space-y-3">
                    <div className="flex items-center gap-2">
                      <ListChecks className="w-4 h-4 text-blue-500" />
                      <h4 className="font-semibold text-gray-900 text-sm">自适应标准得分</h4>
                    </div>
                    <div className="space-y-2 max-h-72 overflow-y-auto pr-2">
                      {selectedTaskData.criteria.map((criterion) => (
                        <div
                          key={criterion.criterion_id}
                          className="border border-gray-100 rounded-lg p-3 bg-white"
                        >
                          <div className="flex items-center justify-between">
                            <p className="font-medium text-gray-900 text-sm">
                              {criterion.name} ({criterion.dimension})
                            </p>
                            <span className="text-xs text-gray-500">权重 {criterion.weight}</span>
                          </div>
                          <div className="flex items-center gap-3 mt-1 text-sm">
                            <span className="text-blue-600">
                              模型 {criterion.target_score.toFixed(1)}
                            </span>
                            <span className="text-gray-400">vs</span>
                            <span className="text-gray-500">
                              参考 {criterion.reference_score.toFixed(1)}
                            </span>
                            <span
                              className={clsx(
                                'text-xs px-2 py-0.5 rounded-full',
                                criterion.gap >= 0
                                  ? 'bg-green-50 text-green-600'
                                  : 'bg-rose-50 text-rose-600'
                              )}
                            >
                              {criterion.gap >= 0 ? '+' : ''}
                              {criterion.gap.toFixed(2)}
                            </span>
                          </div>
                          <p className="text-xs text-gray-500 mt-2 leading-5">{criterion.explanation}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-xl border border-gray-100 p-4 bg-white/80 space-y-3">
                    <div className="flex items-center gap-2">
                      <BookOpenCheck className="w-4 h-4 text-emerald-500" />
                      <h4 className="font-semibold text-gray-900 text-sm">证据链校验 (FACT-UG)</h4>
                    </div>
                    <div className="space-y-2 max-h-72 overflow-y-auto pr-2">
                      {selectedTaskData.fact.pairs.map((pair) => (
                        <div
                          key={pair.statement}
                          className="border border-gray-100 rounded-lg p-3 bg-white"
                        >
                          <p className="text-sm text-gray-900">{pair.statement}</p>
                          <a
                            href={pair.citation}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-blue-600 inline-flex items-center gap-1 mt-1"
                          >
                            {pair.normalized_citation}
                            <ExternalLink className="w-3 h-3" />
                          </a>
                          <div className="flex flex-wrap gap-2 mt-2 text-xs">
                            <span
                              className={clsx(
                                'px-2 py-0.5 rounded-full',
                                pair.support ? 'bg-green-100 text-green-700' : 'bg-rose-100 text-rose-600'
                              )}
                            >
                              {pair.support ? '支撑' : '未支撑'}
                            </span>
                            <span
                              className={clsx(
                                'px-2 py-0.5 rounded-full',
                                pair.authority ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'
                              )}
                            >
                              权威
                            </span>
                            <span
                              className={clsx(
                                'px-2 py-0.5 rounded-full',
                                pair.timeliness ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-500'
                              )}
                            >
                              时效
                            </span>
                            {pair.misuse && (
                              <span className="px-2 py-0.5 rounded-full bg-rose-100 text-rose-600">
                                Misuse
                              </span>
                            )}
                          </div>
                          {pair.notes && (
                            <p className="text-xs text-gray-500 mt-1">{pair.notes}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {selectedTaskData.task_metrics.length > 0 && (
                  <div className="rounded-xl border border-gray-100 p-4 bg-white/80">
                    <div className="flex items-center gap-2 mb-3">
                      <Layers3 className="w-4 h-4 text-purple-500" />
                      <h4 className="font-semibold text-gray-900 text-sm">任务专属指标拆解</h4>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-xs">
                        <thead>
                          <tr className="text-left text-gray-500 border-b border-gray-200">
                            <th className="py-2">指标</th>
                            <th className="py-2">得分</th>
                            <th className="py-2">归一化</th>
                            <th className="py-2">方向</th>
                            <th className="py-2">参考值</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedTaskData.task_metrics.map((metric) => (
                            <tr key={metric.metric} className="border-b border-gray-100">
                              <td className="py-2 text-gray-700">{metric.metric}</td>
                              <td className="py-2">{metric.value.toFixed(3)}</td>
                              <td className="py-2 text-blue-600">{metric.normalized.toFixed(2)}</td>
                              <td className="py-2 text-gray-500">
                                {metric.direction === 'higher_is_better' ? '↑ 越高越好' : '↓ 越低越好'}
                              </td>
                              <td className="py-2">
                                {metric.reference_value !== undefined ? metric.reference_value : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-gray-500">
                尚未找到该模型在此题的评测记录。请先运行评测或选择其他模型。
              </p>
            )}
          </motion.div>
        )}

        {/* Evaluation pipeline snapshot */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-2xl border border-gray-200 bg-white/80 backdrop-blur-sm p-6 space-y-4"
        >
          <div className="flex items-center gap-2">
            <RefreshCw className="w-5 h-5 text-slate-500" />
            <h2 className="text-lg font-semibold text-gray-900">评估流程概览</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {[
              {
                title: '1. Task Dataset',
                icon: FileSearch,
                description:
                  '根据 22 个主题域构建深度研究任务池，过滤闲聊与不可核验问题，形成 query.jsonl 与参考报告。'
              },
              {
                title: '2. RACE-UG',
                icon: Target,
                description:
                  'Judge LLM 基于“自适应标准”对 Target 与 Reference 逐 Criterion 0-10 打分，计算质量线分数并输出解释。'
              },
              {
                title: '3. FACT-UG & Task 指标',
                icon: BookOpenCheck,
                description:
                  '抽取声明-引用对，进行支持性、权威性、时效性判定，计算 CA/EC/SAR/TT；叠加题型专属指标、人工复核触发。'
              }
            ].map((item) => {
              const Icon = item.icon
              return (
                <div key={item.title} className="rounded-xl border border-gray-100 bg-white/80 p-4 space-y-2">
                  <div className="flex items-center gap-2 text-sm font-semibold text-gray-900">
                    <Icon className="w-4 h-4 text-blue-500" />
                    {item.title}
                  </div>
                  <p className="text-xs text-gray-500 leading-5">{item.description}</p>
                </div>
              )
            })}
          </div>
        </motion.div>
      </div>
    </MainLayout>
  )
}
