export type ModuleKey =
  | 'references'
  | 'depth'
  | 'language'
  | 'literature'
  | 'reviewers'
  | 'journals'
  | 'comparison'
  | 'translation'
  | 'format'
  | 'data_methods'

export interface OverallAssessment {
  document_type: string
  completion_level: string
  overall_score: number
  strengths: string[]
  weaknesses: string[]
  priority: string
}

export interface MainIssue {
  severity: string
  description: string
  reason: string
}

export interface Annotation {
  id: number
  module: string
  module_name: string
  severity: string
  paragraph: number
  quote: string
  quote_matched: boolean
  issue: string
  suggestion: string
  page?: number | null
  bbox?: number[] | null
}

export interface ModuleResult {
  module_key: string
  module_name: string
  summary: string
  items: Record<string, any>[]
}

export interface ChecklistItem {
  priority: string
  category: string
  action: string
  detail: string
}

export interface RiskWarning {
  risk_type: string
  severity: string
  description: string
  suggestion: string
}

export interface RewriteExample {
  section: string
  original: string
  rewritten: string
  notes: string
}

export interface PreReviewResponse {
  request_id: string
  title: string
  document_type: string
  raw_text: string
  paragraphs?: string[]
  overall_assessment: OverallAssessment
  main_issues: MainIssue[]
  annotations?: Annotation[]
  module_results: ModuleResult[]
  modification_checklist: ChecklistItem[]
  risk_warnings: RiskWarning[]
  rewrite_examples: RewriteExample[]
  created_at: string
  pdf_url?: string
}

export interface ReviewHistoryItem {
  request_id: string
  title: string
  document_type: string
  overall_score: number
  created_at: string
}

export interface TranslateResult {
  original: string
  translated: string
  direction: string
}

export const MODULE_NAMES: Record<ModuleKey, string> = {
  references: '文献核查',
  depth: '深度审稿',
  language: '语言检查',
  literature: '建议文献',
  reviewers: '建议审稿人',
  journals: '建议期刊',
  comparison: '过刊比较',
  translation: '文档翻译',
  format: '格式规范检查',
  data_methods: '数据来源与研究方法建议',
}

export const ALL_MODULES: ModuleKey[] = [
  'references',
  'depth',
  'language',
  'literature',
  'reviewers',
  'journals',
  'comparison',
  'translation',
  'format',
  'data_methods',
]
