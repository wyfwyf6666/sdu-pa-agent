'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import dynamic from 'next/dynamic'
import { toast, Toaster } from 'react-hot-toast'
import { apiFetch } from '@/lib/api'
import {
  Loader2,
  RefreshCcw,
  Search,
  SlidersHorizontal,
  Target,
} from 'lucide-react'

const ReactECharts = dynamic(() => import('echarts-for-react'), {
  ssr: false,
}) as any

const PAGE_SIZE = 15

interface GraphOverview {
  node_count: number
  triple_count: number
  predicate_count: number
  top_predicates: { predicate: string; count: number }[]
  top_entities: { name: string; degree: number }[]
  last_loaded?: string | null
  source_file: string
}

interface GraphNode {
  id: string
  name: string
  degree: number
  category: string
  symbol_size?: number
  is_center?: boolean
}

interface GraphEdge {
  id: string
  source: string
  target: string
  label: string
  is_inferred?: boolean
}

interface GraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
  categories: string[]
  center?: string | null
  total_nodes: number
}

interface TripleItem {
  id: string
  subject: string
  predicate: string
  object: string
}

interface PredicateStat {
  predicate: string
  count: number
}

interface TriplesResponse {
  items: TripleItem[]
  total: number
  page: number
  page_size: number
  predicates: PredicateStat[]
}

export default function KnowledgeGraphPage() {
  const [overview, setOverview] = useState<GraphOverview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(false)
  const [graphData, setGraphData] = useState<GraphResponse | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [triples, setTriples] = useState<TripleItem[]>([])
  const [triplesLoading, setTriplesLoading] = useState(false)
  const [predicateOptions, setPredicateOptions] = useState<PredicateStat[]>([])
  const [totalTriples, setTotalTriples] = useState(0)

  const [graphCenterInput, setGraphCenterInput] = useState('')
  const [graphDepth, setGraphDepth] = useState(1)
  const [graphLimit, setGraphLimit] = useState(120)
  const [minDegree, setMinDegree] = useState(0)

  const [tripleSearchInput, setTripleSearchInput] = useState('')
  const [activeTripleSearch, setActiveTripleSearch] = useState('')
  const [predicateFilter, setPredicateFilter] = useState('')
  const [page, setPage] = useState(1)

  const totalPages = Math.max(1, Math.ceil(totalTriples / PAGE_SIZE))

  const loadOverview = useCallback(async () => {
    setOverviewLoading(true)
    try {
      const response = await apiFetch('/api/v1/knowledge-graph/overview')
      if (!response.ok) throw new Error('获取知识图谱概览失败')
      const result = await response.json()
      setOverview(result.data || null)
    } catch (error) {
      toast.error((error as Error).message || '无法加载概览信息')
    } finally {
      setOverviewLoading(false)
    }
  }, [])

  const loadGraphData = useCallback(
    async (center?: string, depth?: number, limit?: number) => {
      setGraphLoading(true)
      try {
        const params = new URLSearchParams()
        if (center) params.append('center', center)
        params.append('depth', String(depth ?? 1))
        params.append('limit', String(limit ?? 120))

        const response = await apiFetch(`/api/v1/knowledge-graph/graph?${params.toString()}`)
        if (!response.ok) throw new Error('获取图谱数据失败')
        const result = await response.json()
        setGraphData(result.data || null)
      } catch (error) {
        toast.error((error as Error).message || '无法加载图谱数据')
      } finally {
        setGraphLoading(false)
      }
    },
    [],
  )

  const loadTriples = useCallback(async (targetPage: number, query: string, predicate: string) => {
    setTriplesLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(targetPage))
      params.append('page_size', String(PAGE_SIZE))
      if (query) params.append('q', query)
      if (predicate) params.append('predicate', predicate)

      const response = await apiFetch(`/api/v1/knowledge-graph/triples?${params.toString()}`)
      if (!response.ok) throw new Error('获取三元组失败')
      const result = await response.json()
      const payload = (result.data || {}) as TriplesResponse

      setTriples(payload.items || [])
      setTotalTriples(payload.total || 0)
      setPredicateOptions(payload.predicates || [])
    } catch (error) {
      toast.error((error as Error).message || '无法加载三元组数据')
    } finally {
      setTriplesLoading(false)
    }
  }, [])

  useEffect(() => {
    loadOverview()
    loadGraphData(undefined, 1, 120)
  }, [loadGraphData, loadOverview])

  useEffect(() => {
    loadTriples(page, activeTripleSearch, predicateFilter)
  }, [page, activeTripleSearch, predicateFilter, loadTriples])

  const handleGraphSubmit = async () => {
    await loadGraphData(graphCenterInput.trim() || undefined, graphDepth, graphLimit)
  }

  const handleResetGraph = async () => {
    setGraphCenterInput('')
    setGraphDepth(1)
    setGraphLimit(120)
    await loadGraphData(undefined, 1, 120)
  }

  const handleTripleSearch = (event: React.FormEvent) => {
    event.preventDefault()
    setPage(1)
    setActiveTripleSearch(tripleSearchInput.trim())
  }

  const handlePredicateChange = (value: string) => {
    setPredicateFilter(value)
    setPage(1)
  }

  const handleReloadGraph = async () => {
    try {
      const response = await apiFetch('/api/v1/knowledge-graph/reload', { method: 'POST' })
      if (!response.ok) throw new Error('重新加载知识图谱失败')
      await response.json()
      toast.success('知识图谱数据已刷新')
      await loadOverview()
      await loadGraphData(graphCenterInput.trim() || undefined, graphDepth, graphLimit)
      await loadTriples(1, activeTripleSearch, predicateFilter)
      setPage(1)
    } catch (error) {
      toast.error((error as Error).message || '无法重新加载知识图谱')
    }
  }

  const focusNode = async (name: string) => {
    setGraphCenterInput(name)
    await loadGraphData(name, graphDepth, graphLimit)
  }

  const filteredGraphData = useMemo<GraphResponse | null>(() => {
    if (!graphData) return null
    if (minDegree <= 0) return graphData
    const allowed = new Set(
      graphData.nodes.filter((node) => node.degree >= minDegree).map((node) => node.id),
    )
    if (allowed.size === graphData.nodes.length) return graphData
    return {
      ...graphData,
      nodes: graphData.nodes.filter((node) => allowed.has(node.id)),
      edges: graphData.edges.filter(
        (edge) => allowed.has(edge.source) && allowed.has(edge.target),
      ),
    }
  }, [graphData, minDegree])

  const chartOption = useMemo(() => {
    if (!filteredGraphData || filteredGraphData.nodes.length === 0) {
      return {
        title: { text: '知识图谱', left: 'center' },
        tooltip: {},
        series: [],
      }
    }

    const categories = filteredGraphData.categories.map((item) => ({ name: item }))

    return {
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          if (params.dataType === 'edge') {
            return `${params.data.source} — ${params.data.label} → ${params.data.target}`
          }
          return `${params.data.name}<br/>连接度：${params.data.degree}`
        },
      },
      legend: {
        data: filteredGraphData.categories,
        orient: 'horizontal',
        top: 0,
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          focusNodeAdjacency: true,
          zoom: 1.05,
          scaleLimit: { min: 0.4, max: 2.5 },
          edgeSymbol: ['circle', 'arrow'],
          edgeSymbolSize: [2, 8],
          label: {
            show: true,
            formatter: '{b}',
          },
          data: filteredGraphData.nodes.map((node) => ({
            id: node.id,
            name: node.name,
            value: node.degree,
            category: node.category,
            degree: node.degree,
            symbolSize: node.symbol_size ?? Math.max(12, node.degree * 1.4),
            itemStyle: node.is_center
              ? { color: '#2563eb', borderColor: '#93c5fd', borderWidth: 2 }
              : undefined,
          })),
          links: filteredGraphData.edges.map((edge) => ({
            source: edge.source,
            target: edge.target,
            label: edge.label,
            lineStyle: {
              color: edge.is_inferred ? '#f97316' : '#94a3b8',
              opacity: edge.is_inferred ? 0.9 : 0.7,
              type: edge.is_inferred ? 'dashed' : 'solid',
              width: edge.is_inferred ? 2 : 1,
            },
          })),
          categories,
          emphasis: {
            focus: 'adjacency',
            lineStyle: { width: 2 },
          },
          force: {
            repulsion: 360,
            edgeLength: [120, 220],
            gravity: 0.05,
          },
          lineStyle: {
            width: 1.2,
            curveness: 0.18,
          },
          animationDuration: 1200,
          animationEasing: 'cubicOut',
        },
      ],
    }
  }, [filteredGraphData])

  return (
    <div className="space-y-8">
      <Toaster />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-3xl font-semibold text-gray-900">知识图谱中心</h1>
        </div>
        <button
          onClick={handleReloadGraph}
          className="inline-flex items-center rounded-xl border border-blue-100 bg-white px-4 py-2 text-sm font-medium text-blue-600 shadow-sm hover:bg-blue-50"
        >
          <RefreshCcw className="mr-2 h-4 w-4" />
          重新加载
        </button>
      </div>

      {/* 概览卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[
          {
            label: '实体总数',
            value: overview?.node_count ?? '-',
            hint: 'Graph nodes',
          },
          {
            label: '三元组',
            value: overview?.triple_count ?? '-',
            hint: 'Edges/relationships',
          },
          {
            label: '谓词种类',
            value: overview?.predicate_count ?? '-',
            hint: 'Unique relations',
          },
          {
            label: '最近更新',
            value: overview?.last_loaded
              ? new Date(overview.last_loaded).toLocaleString()
              : '暂无记录',
            hint:
              overview?.source_file
                ? overview.source_file.split(/[/\\]+/).slice(-2).join('/')
                : 'city.json',
          },
        ].map((card) => (
          <div
            key={card.label}
            className="rounded-2xl border border-gray-100 bg-white p-4 shadow-sm"
          >
            <div className="text-sm text-gray-500">{card.label}</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900">
              {overviewLoading ? <Loader2 className="h-6 w-6 animate-spin text-gray-400" /> : card.value}
            </div>
            <div className="text-xs text-gray-400 mt-1">{card.hint}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-500">
            <Target className="h-4 w-4 text-blue-500" />
            高频谓词
          </div>
          <ul className="mt-3 space-y-2">
            {(overview?.top_predicates || []).map((item) => (
              <li
                key={item.predicate}
                className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-2 text-sm"
              >
                <span className="text-gray-700">{item.predicate}</span>
                <span className="text-gray-500">{item.count} 次</span>
              </li>
            ))}
            {!overview?.top_predicates?.length && (
              <li className="text-sm text-gray-400">暂无数据</li>
            )}
          </ul>
        </div>
        <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-500">
            <SlidersHorizontal className="h-4 w-4 text-emerald-500" />
            活跃实体
          </div>
          <ul className="mt-3 space-y-2">
            {(overview?.top_entities || []).map((item) => (
              <li
                key={item.name}
                className="flex items-center justify-between rounded-xl bg-slate-50 px-4 py-2 text-sm"
              >
                <span className="text-gray-700">{item.name}</span>
                <span className="text-gray-500">度 {item.degree}</span>
              </li>
            ))}
            {!overview?.top_entities?.length && (
              <li className="text-sm text-gray-400">暂无数据</li>
            )}
          </ul>
        </div>
      </div>

      <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">图谱可视化</h3>
            <p className="text-sm text-gray-500">
              当前中心：{graphData?.center || '自动选择'}（原始 {graphData?.total_nodes || 0} 个实体，过滤后展示 {filteredGraphData?.nodes.length || 0} 个，节点越大表示连接越多，虚线代表推理关联）
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleGraphSubmit}
              className="inline-flex items-center rounded-xl bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-500"
            >
              <Search className="mr-2 h-4 w-4" />
              应用视图
            </button>
            <button
              onClick={handleResetGraph}
              className="inline-flex items-center rounded-xl border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
            >
              重置视图
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <div>
            <label className="text-xs font-medium text-gray-500">中心实体（模糊匹配）</label>
            <input
              type="text"
              className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              placeholder="如：互联网+政务服务平台"
              value={graphCenterInput}
              onChange={(event) => setGraphCenterInput(event.target.value)}
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500">扩散深度</label>
            <select
              className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              value={graphDepth}
              onChange={(event) => setGraphDepth(Number(event.target.value))}
            >
              {[1, 2, 3, 4, 5].map((item) => (
                <option key={item} value={item}>
                  {item} 层
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500">最大节点数</label>
            <select
              className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              value={graphLimit}
              onChange={(event) => setGraphLimit(Number(event.target.value))}
            >
              {[60, 90, 120, 180, 240, 300].map((item) => (
                <option key={item} value={item}>
                  {item} 个
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-500">最小连接度过滤</label>
            <select
              className="mt-1 w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              value={minDegree}
              onChange={(event) => setMinDegree(Number(event.target.value))}
            >
              {[0, 1, 2, 3, 4].map((item) => (
                <option key={item} value={item}>
                  {item === 0 ? '不过滤' : `≥ ${item}`}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-6 h-[640px] w-full overflow-hidden rounded-2xl border border-dashed border-gray-200">
          {graphLoading ? (
            <div className="flex h-full items-center justify-center text-gray-400">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              正在加载图谱...
            </div>
          ) : (
            <ReactECharts option={chartOption} style={{ height: '100%', width: '100%' }} />
          )}
        </div>
      </div>

      <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">三元组检索</h3>
            <p className="text-sm text-gray-500">
              共 {totalTriples} 条匹配结果，支持关键词与谓词过滤。
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-3 md:flex-row">
          <form onSubmit={handleTripleSearch} className="flex flex-1 items-center gap-2 rounded-xl border border-gray-200 px-3 py-2">
            <Search className="h-4 w-4 text-gray-400" />
            <input
              className="flex-1 border-none text-sm focus:outline-none focus:ring-0"
              placeholder="输入关键词，支持主体/谓词/客体模糊匹配"
              value={tripleSearchInput}
              onChange={(event) => setTripleSearchInput(event.target.value)}
            />
            <button
              type="submit"
              className="rounded-lg bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-500"
            >
              搜索
            </button>
          </form>
          <select
            value={predicateFilter}
            onChange={(event) => handlePredicateChange(event.target.value)}
            className="rounded-xl border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          >
            <option value="">全部谓词</option>
            {predicateOptions.map((item) => (
              <option key={item.predicate} value={item.predicate}>
                {item.predicate}（{item.count}）
              </option>
            ))}
          </select>
          <button
            onClick={() => {
              setTripleSearchInput('')
              setActiveTripleSearch('')
              setPredicateFilter('')
              setPage(1)
            }}
            className="rounded-xl border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            清空筛选
          </button>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="whitespace-nowrap px-3 py-2 text-left font-medium text-gray-500">#</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500">主体</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500">谓词</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500">客体</th>
                <th className="px-3 py-2 text-left font-medium text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {triples.map((item, index) => (
                <tr key={item.id} className="hover:bg-slate-50">
                  <td className="whitespace-nowrap px-3 py-2 text-gray-500">
                    {(page - 1) * PAGE_SIZE + index + 1}
                  </td>
                  <td className="px-3 py-2 text-gray-800">{item.subject}</td>
                  <td className="px-3 py-2 text-blue-600">{item.predicate}</td>
                  <td className="px-3 py-2 text-gray-800">{item.object}</td>
                  <td className="px-3 py-2">
                    <button
                      onClick={() => focusNode(item.subject)}
                      className="rounded-lg border border-blue-100 px-3 py-1 text-xs text-blue-600 hover:bg-blue-50"
                    >
                      聚焦主体
                    </button>
                  </td>
                </tr>
              ))}
              {!triplesLoading && triples.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-gray-400">
                    暂无匹配结果
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {triplesLoading && (
            <div className="flex items-center justify-center py-6 text-gray-400">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              正在加载三元组...
            </div>
          )}
        </div>

        <div className="mt-4 flex flex-col gap-3 text-sm text-gray-500 md:flex-row md:items-center md:justify-between">
          <div>
            显示第{' '}
            {totalTriples === 0
              ? 0
              : `${(page - 1) * PAGE_SIZE + 1} - ${Math.min(page * PAGE_SIZE, totalTriples)}`}
            条，共 {totalTriples} 条记录
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={page === 1}
              className="rounded-lg border border-gray-200 px-3 py-1 disabled:opacity-40"
            >
              上一页
            </button>
            <span>
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={page >= totalPages}
              className="rounded-lg border border-gray-200 px-3 py-1 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
