"use client"

import React, { useRef, useEffect } from "react"

interface Highlight {
  issueId: string
  category: string
  startChar: number
  endChar: number
  severity: string
}

interface Props {
  text: string
  highlights: Highlight[]
  activeIssueId: string | null
  onHighlightClick: (issueId: string) => void
}

const CATEGORY_COLORS: Record<string, { bg: string; border: string; label: string }> = {
  plagiarism_high: { bg: "#fecaca", border: "#dc2626", label: "高相似度" },
  plagiarism_medium: { bg: "#fed7aa", border: "#ea580c", label: "中相似度" },
  data_source: { bg: "#bfdbfe", border: "#2563eb", label: "数据来源" },
  verified_ref: { bg: "#bbf7d0", border: "#16a34a", label: "已验证" },
  suspicious_ref: { bg: "#fecaca", border: "#dc2626", label: "疑似异常" },
  not_found_ref: { bg: "#e5e7eb", border: "#6b7280", label: "需核验" },
}

export default function DocumentPreview({ text, highlights, activeIssueId, onHighlightClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const refMap = useRef<Map<string, HTMLSpanElement>>(new Map())

  useEffect(() => {
    if (activeIssueId) {
      const el = refMap.current.get(activeIssueId)
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" })
        el.classList.add("ring-2", "ring-amber-500")
        const t = setTimeout(() => el.classList.remove("ring-2", "ring-amber-500"), 2000)
        return () => clearTimeout(t)
      }
    }
  }, [activeIssueId])

  if (!text) {
    return <div className="flex items-center justify-center h-full text-gray-400 text-sm">暂无文本内容</div>
  }

  const sorted = [...highlights].filter(h => h.startChar < h.endChar).sort((a, b) => a.startChar - b.startChar)
  if (sorted.length === 0) {
    return (
      <div ref={containerRef} className="h-full overflow-y-auto p-6 bg-white">
        <div className="max-w-3xl mx-auto text-base leading-7 text-gray-800 whitespace-pre-wrap font-serif">
          {text}
        </div>
        <div className="mt-4 p-3 bg-gray-50 rounded text-xs text-gray-500 text-center">
          暂无高亮标记。完成检测后在此查看问题定位。
        </div>
      </div>
    )
  }

  const segments: React.ReactNode[] = []
  let pos = 0
  for (const h of sorted) {
    if (h.startChar > pos) segments.push(<span key={`t-${pos}`}>{text.slice(pos, h.startChar)}</span>)
    if (h.endChar > h.startChar) {
      const c = CATEGORY_COLORS[h.category] || CATEGORY_COLORS.not_found_ref
      segments.push(
        <mark
          key={h.issueId}
          ref={el => { if (el) refMap.current.set(h.issueId, el) }}
          data-issue-id={h.issueId}
          className="cursor-pointer rounded-sm px-0.5 transition-colors hover:ring-1 hover:ring-amber-400"
          style={{ background: c.bg, borderBottom: `2px solid ${c.border}` }}
          title={c.label}
          onClick={() => onHighlightClick(h.issueId)}
        >
          {text.slice(h.startChar, h.endChar)}
        </mark>
      )
      pos = h.endChar
    }
  }
  if (pos < text.length) segments.push(<span key={`t-${pos}`}>{text.slice(pos)}</span>)

  return (
    <div ref={containerRef} className="h-full overflow-y-auto p-6 bg-white">
      <div className="max-w-3xl mx-auto text-base leading-7 text-gray-800 whitespace-pre-wrap font-serif">
        {segments}
      </div>
    </div>
  )
}
