'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react'
import type { Annotation } from '@/types/pre-review'
import { API_BASE_URL } from '@/config'

const SEV_BORDER: Record<string, string> = {
  '严重': '#ef4444',
  '一般': '#f59e0b',
  '建议': '#3b82f6',
}
const SEV_FILL: Record<string, string> = {
  '严重': 'rgba(239,68,68,0.22)',
  '一般': 'rgba(245,158,11,0.28)',
  '建议': 'rgba(59,130,246,0.22)',
}

// 动态加载 pdf.js，避免 SSR 问题
let pdfjsPromise: Promise<any> | null = null
function getPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import('pdfjs-dist').then((mod: any) => {
      mod.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'
      return mod
    })
  }
  return pdfjsPromise
}

interface JumpTarget {
  page: number
  annId: number | null
}

interface Props {
  pdfPath: string
  title: string
  annotations: Annotation[]
  activeAnn: number | null
  jump: JumpTarget | null
  onMarkClick: (annId: number) => void
  // 可选：覆盖默认的固定视口高度（用于顶部工具栏更高的页面，保证左右两栏等高）
  viewportHeight?: string
  // 完整露出整页：面板高度跟随“当前页”PDF 的实际渲染高度，把一整页完整显示出来、
  // 不在 PDF 框内部再滚动（由外层页面负责滚动）；右侧意见栏与 PDF 等高。
  // 默认 false：沿用固定视口高度（千章预审稿）。
  fitToPage?: boolean
}

export default function PdfManuscript({ pdfPath, title, annotations, activeAnn, jump, onMarkClick, viewportHeight, fitToPage }: Props) {
  const [pdfDoc, setPdfDoc] = useState<any>(null)
  const [numPages, setNumPages] = useState(0)
  const [pageNum, setPageNum] = useState(1)
  const [ptSize, setPtSize] = useState<[number, number]>([595, 842])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const overlayRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const scrollBoxRef = useRef<HTMLDivElement>(null)
  // pdf.js 同一 canvas 严禁并发 render；以下 ref 组成“渲染队列”，
  // 快速翻页/跳页时串行渲染，避免 renderTask 竞态把画布清空成白屏。
  const renderTaskRef = useRef<any>(null)
  const renderingRef = useRef(false)
  const pendingPageRef = useRef<number | null>(null)
  const aliveRef = useRef(true)

  // 该页有标注的条目
  const pageAnns = useMemo(
    () => annotations.filter((a) => a.page === pageNum && Array.isArray(a.bbox) && a.bbox.length === 4),
    [annotations, pageNum]
  )

  // 哪些页有标注
  const pagesWithMarks = useMemo(() => {
    const s = new Set<number>()
    for (const a of annotations) if (a.page && a.page > 0) s.add(a.page)
    return s
  }, [annotations])

  // 加载 PDF 文档
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(false)
    getPdfjs()
      .then(async (pdfjs: any) => {
        const url = pdfPath.startsWith('http') ? pdfPath : `${API_BASE_URL}${pdfPath}`
        const task = pdfjs.getDocument({ url })
        const doc = await task.promise
        if (cancelled) return
        setPdfDoc(doc)
        setNumPages(doc.numPages)
        setLoading(false)
      })
      .catch((e) => {
        console.error('pdf load failed', e)
        if (!cancelled) {
          setError(true)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [pdfPath])

  // 串行渲染某一页：若上一页仍在渲染，则把目标页排队，等其结束后再渲染，
  // 从根本上避免多个 render() 争抢同一 canvas 造成的白屏。
  const renderPage = useCallback(
    async (num: number) => {
      if (!pdfDoc) return
      if (renderingRef.current) {
        pendingPageRef.current = num
        return
      }
      renderingRef.current = true
      try {
        const page = await pdfDoc.getPage(num)
        const canvas = canvasRef.current
        if (!canvas) {
          renderingRef.current = false
          return
        }
        const base = page.getViewport({ scale: 1 })
        setPtSize([base.width, base.height])
        const scale = 1.3
        const viewport = page.getViewport({ scale })
        const ctx = canvas.getContext('2d')
        canvas.width = Math.floor(viewport.width)
        canvas.height = Math.floor(viewport.height)
        const task = page.render({ canvasContext: ctx, viewport })
        renderTaskRef.current = task
        try {
          await task.promise
        } catch (e: any) {
          // 翻页 / 卸载触发的取消属于正常行为，不计为渲染失败
          if (e?.name !== 'RenderingCancelledException' && aliveRef.current) {
            console.error('render page failed', e)
            setError(true)
          }
        }
      } catch (e) {
        console.error('getPage failed', e)
        if (aliveRef.current) setError(true)
      } finally {
        renderingRef.current = false
        const next = pendingPageRef.current
        if (next !== null) {
          pendingPageRef.current = null
          void renderPage(next)
        }
      }
    },
    [pdfDoc]
  )

  // 当前页或文档变化时触发渲染
  useEffect(() => {
    aliveRef.current = true
    if (pdfDoc) void renderPage(pageNum)
  }, [pdfDoc, pageNum, renderPage])

  // 卸载时取消在途渲染任务
  useEffect(() => {
    return () => {
      aliveRef.current = false
      try {
        renderTaskRef.current?.cancel()
      } catch {
        /* noop */
      }
    }
  }, [])

  // 跳转目标（点右侧意见）
  useEffect(() => {
    if (!jump) return
    if (jump.page >= 1 && jump.page <= numPages) {
      setPageNum(jump.page)
    }
    const annId = jump.annId
    if (annId != null) {
      const t = setTimeout(() => {
        overlayRefs.current[annId]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 260)
      return () => clearTimeout(t)
    }
  }, [jump, numPages])

  const go = useCallback(
    (p: number) => setPageNum((cur) => Math.min(numPages, Math.max(1, p))),
    [numPages]
  )

  if (error) {
    return (
      <section className="flex min-h-[680px] flex-col rounded-2xl border border-[#eadbbf] bg-white p-6 shadow-sm">
        <p className="text-sm text-slate-500">原始 PDF 在当前环境下渲染失败，已切换为文字视图。</p>
      </section>
    )
  }

  const [ptW, ptH] = ptSize

  return (
    <section
      className={
        fitToPage
          ? 'flex flex-col overflow-hidden rounded-2xl border border-[#eadbbf] bg-white shadow-sm'
          : 'flex min-h-[680px] flex-col overflow-hidden rounded-2xl border border-[#eadbbf] bg-white shadow-sm lg:h-[calc(100vh-150px)]'
      }
      style={!fitToPage && viewportHeight ? { height: viewportHeight, minHeight: viewportHeight } : undefined}
    >
      <div className="border-b border-[#f0eadc] px-5 py-3">
        <div className="truncate text-base font-semibold text-slate-900">{title}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
          <span>原始 PDF 视图（荧光笔为问题定位）</span>
          <span className="font-medium text-[#d06a00]">{annotations.filter((a) => a.page).length} 处已标注</span>
        </div>
      </div>

      {/* 页码导航 */}
      <div className="flex items-center justify-between gap-2 border-b border-[#f7f1e4] bg-[#fdfaf3] px-4 py-2 text-xs text-slate-600">
        <div className="flex items-center gap-1">
          <button
            onClick={() => go(pageNum - 1)}
            disabled={pageNum <= 1}
            className="rounded p-1 hover:bg-slate-100 disabled:opacity-30"
            title="上一页"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="tabular-nums">
            第 {pageNum} / {numPages || '—'} 页
          </span>
          <button
            onClick={() => go(pageNum + 1)}
            disabled={pageNum >= numPages}
            className="rounded p-1 hover:bg-slate-100 disabled:opacity-30"
            title="下一页"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center gap-1 overflow-x-auto">
          {Array.from({ length: numPages }, (_, i) => i + 1)
            .filter((p) => pagesWithMarks.has(p))
            .map((p) => (
              <button
                key={p}
                onClick={() => setPageNum(p)}
                className={`h-4 w-4 shrink-0 rounded-full text-[9px] leading-4 ${
                  p === pageNum ? 'bg-[#d06a00] text-white' : 'bg-amber-100 text-amber-700'
                }`}
                title={`第 ${p} 页（有标注）`}
              >
                {p}
              </button>
            ))}
        </div>
      </div>

      {/* PDF 画布 + 荧光笔 overlay */}
      <div ref={scrollBoxRef} className={fitToPage ? 'bg-[#ece7db] px-4 py-4' : 'min-h-0 flex-1 overflow-y-auto bg-[#ece7db] px-4 py-4'}>
        {loading ? (
          <div className="p-10 text-center text-sm text-slate-400">正在加载原始 PDF…</div>
        ) : (
          <div className="relative mx-auto w-fit max-w-full shadow-md">
            <canvas ref={canvasRef} className="block w-auto max-w-full bg-white" />
            {pageAnns.map((a) => {
              const [x0, y0, x1, y1] = a.bbox!
              const left = (x0 / ptW) * 100
              const top = (y0 / ptH) * 100
              const w = ((x1 - x0) / ptW) * 100
              const h = ((y1 - y0) / ptH) * 100
              const border = SEV_BORDER[a.severity] || '#f59e0b'
              const fill = SEV_FILL[a.severity] || 'rgba(245,158,11,0.28)'
              const isActive = activeAnn === a.id
              return (
                <div
                  key={a.id}
                  ref={(el) => {
                    overlayRefs.current[a.id] = el
                  }}
                  onClick={() => onMarkClick(a.id)}
                  className={`absolute cursor-pointer rounded-sm transition-shadow ${
                    isActive ? 'ring-2 ring-[#ef7d0b] ring-offset-1' : 'hover:brightness-95'
                  }`}
                  style={{
                    left: `${left}%`,
                    top: `${top}%`,
                    width: `${w}%`,
                    height: `${h}%`,
                    background: fill,
                    boxShadow: `inset 0 0 0 1.5px ${border}`,
                  }}
                  title={`【${a.severity}】${a.issue.slice(0, 40)}…`}
                />
              )
            })}
          </div>
        )}
      </div>

      {/* 图例 */}
      <div className="flex items-center gap-3 border-t border-[#f0eadc] bg-[#fdfaf3] px-4 py-1.5 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-red-300" />严重</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-300" />一般</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-blue-300" />建议</span>
        <span className="ml-auto inline-flex items-center gap-1">
          <AlertTriangle className="h-3 w-3" />点击色块可跳转右侧意见
        </span>
      </div>
    </section>
  )
}
