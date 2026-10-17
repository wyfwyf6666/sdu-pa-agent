"use client"

import React from "react"
import { Tag, Button, Badge } from "antd"
import { EyeOutlined, ExclamationCircleOutlined, CheckCircleOutlined } from "@ant-design/icons"

interface Issue {
  id: string; category: string; severity: string; title: string
  message: string; suggestion: string; evidence_quote: string
  page: number; section: string; start_offset: number; end_offset: number
  dedupe_key: string; score_delta: number; provider_trace?: any[]
  manual_review_required: boolean; folded?: boolean; affected_count?: number
}

interface Props {
  issues: Issue[]
  activeIssueId: string | null
  onIssueClick: (issueId: string, offset: number) => void
  filterCategory: string | null
  onFilterChange: (cat: string | null) => void
}

const CATEGORY_TABS = [
  { key: "all", label: "全部" },
  { key: "plagiarism", label: "查重" },
  { key: "data_sources", label: "数据来源" },
  { key: "references", label: "文献核验" },
  { key: "manual_review", label: "人工核验" },
]

const SEV_TAGS: Record<string, { color: string; label: string }> = {
  high: { color: "red", label: "高" },
  medium: { color: "orange", label: "中" },
  low: { color: "green", label: "低" },
  critical: { color: "magenta", label: "严重" },
}

export default function IssuePanel({ issues, activeIssueId, onIssueClick, filterCategory, onFilterChange }: Props) {
  const filtered = filterCategory === "manual_review"
    ? issues.filter(i => i.manual_review_required)
    : filterCategory && filterCategory !== "all"
      ? issues.filter(i => i.category === filterCategory)
      : issues

  const counts: Record<string, number> = {}
  for (const t of CATEGORY_TABS) {
    counts[t.key] = t.key === "all" ? issues.length
      : t.key === "manual_review" ? issues.filter(i => i.manual_review_required).length
      : issues.filter(i => i.category === t.key).length
  }

  return (
    <div className="h-full flex flex-col bg-white">
      <div className="p-3 border-b border-gray-100">
        <h3 className="text-sm font-semibold text-gray-800 mb-2">问题列表</h3>
        <div className="flex flex-wrap gap-1">
          {CATEGORY_TABS.map(tab => (
            <Button key={tab.key} size="small"
              type={filterCategory === tab.key || (tab.key === "all" && !filterCategory) ? "primary" : "default"}
              onClick={() => onFilterChange(tab.key === "all" ? null : tab.key)}
              style={tab.key === "all" && !filterCategory ? { background: "#ef7d00", borderColor: "#ef7d00" } : {}}
            >
              {tab.label}
              {counts[tab.key] > 0 && <Badge count={counts[tab.key]} size="small" style={{ marginLeft: 4 }} />}
            </Button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            <CheckCircleOutlined style={{ fontSize: 32, marginBottom: 8 }} />
            <p className="text-sm">该分类下暂无问题</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-50">
            {filtered.map(issue => {
              const sev = SEV_TAGS[issue.severity] || { color: "default", label: issue.severity }
              const active = activeIssueId === issue.id
              return (
                <div key={issue.id}
                  className={`p-3 cursor-pointer transition-colors hover:bg-amber-50 ${active ? "bg-amber-50 border-l-2 border-amber-500" : ""} ${issue.folded ? "opacity-50" : ""}`}
                  onClick={() => onIssueClick(issue.id, issue.start_offset)}
                >
                  <div className="flex items-start gap-1.5 mb-1">
                    <Tag color={sev.color} style={{ fontSize: 10, lineHeight: "16px", margin: 0 }}>{sev.label}</Tag>
                    <span className="text-[10px] text-gray-400">
                      {issue.category === "plagiarism" ? "相似度" : issue.category === "data_sources" ? "数据来源" : "参考文献"}
                    </span>
                    {issue.manual_review_required && (
                      <Tag icon={<ExclamationCircleOutlined />} color="warning" style={{ fontSize: 10, margin: 0 }}>需核验</Tag>
                    )}
                    {issue.folded && <Tag color="default" style={{ fontSize: 10, margin: 0 }}>已折叠</Tag>}
                    {issue.affected_count && issue.affected_count > 1 && (
                      <span className="text-[10px] text-gray-400">×{issue.affected_count}</span>
                    )}
                  </div>
                  <div className="text-xs font-medium text-gray-800 mb-1">{issue.title}</div>
                  {issue.evidence_quote && (
                    <div className="text-[11px] text-gray-500 mb-1.5 bg-gray-50 rounded p-1.5 italic leading-relaxed">
                      &ldquo;{issue.evidence_quote.slice(0, 150)}{issue.evidence_quote.length > 150 ? "..." : ""}&rdquo;
                    </div>
                  )}
                  <div className="text-[11px] text-gray-600 mb-1.5 leading-relaxed">{issue.suggestion}</div>
                  <div className="flex items-center gap-2">
                    {issue.start_offset > 0 && (
                      <Button type="link" size="small" icon={<EyeOutlined />}
                        onClick={e => { e.stopPropagation(); onIssueClick(issue.id, issue.start_offset) }}
                        style={{ color: "#2563eb", padding: 0, height: 20, fontSize: 11 }}
                      >跳转原文</Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
