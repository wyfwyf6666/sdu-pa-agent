'use client'

import { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react'
import { Send, Mic, StopCircle, FileText, RotateCcw, Book, X, Volume2, Eye, EyeOff, Loader2, Database, Globe, Lock, ChevronDown, ChevronUp, ExternalLink, Play } from 'lucide-react'
import MainLayout from '@/components/layout/MainLayout'
import { toast, Toaster } from 'react-hot-toast'
import { motion, AnimatePresence } from 'framer-motion'
import { apiFetch } from '@/lib/api'
import { fetchWithTimeout, TIMEOUT } from '@/lib/fetchWithTimeout'
import ReactMarkdown, { type Components as MarkdownComponents } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'

// 添加类型定义
interface ApiError extends Error {
  message: string;
}

interface MessageReference {
  title: string;
  content: string;
  filename?: string;
  category?: string;
  tags?: string[];
  size?: number;
  upload_time?: string;
  chunk_index?: number;
  library_type?: string;
  knowledge_group_id?: string;
  knowledge_group_name?: string;
  type?: string;  // "web_search" for web results
  url?: string;   // URL for web search results
  score?: number; // 相似度分数
  // 分类特定字段
  effectiveness_level?: string; // 政策类
  document_type?: string;       // 政策类
  discipline?: string;          // 论文类
  region?: string;              // 案例类
  main_topic?: string;          // 论文和案例类
}

interface RagScope {
  includePublic: boolean;
  includePrivate: boolean;
  selectedGroupIds: string[];
}

interface KnowledgeGroup {
  id: string;
  name: string;
  description: string;
  document_count: number;
  created_time: string;
  updated_time: string;
}

interface DataFileInfo {
  filename: string;
  file_type: string;
  file_path: string;
  file_size?: number;
}

interface RunResult {
  stdout?: string;
  stderr?: string;
  exit_code?: number;
  summary?: string;
  interpretation?: string;  // LLM对结果的解释
  generated_images?: Array<{
    filename: string;
    path: string;
    size: number;
  }>;
}

interface AnalysisPayload {
  action: 'generate' | 'run';
  language: 'python' | 'r';
  code: string;
  description?: string;
  data_files?: DataFileInfo[];
  knowledge_group_id?: string;
  run_result?: RunResult;
  instruction?: string;
}

interface Message {
  role: 'user' | 'assistant' | 'system';
  content: string;
  references?: MessageReference[];
  citation_map?: Record<number, { source: string; snippet: string }>;
  trace?: WorkflowTrace;
  analysis?: AnalysisPayload;
}

interface WorkflowReference {
  source: string;
  content: string;
  score?: number;
  chunk_index?: number;
}

interface PlanTaskTrace {
  task_name: string;
  objective: string;
  requires_vector_search?: boolean;
  requires_tool?: boolean;
  tool_name?: string;
  tool_arguments?: Record<string, any>;
  model_preference?: 'general' | 'reasoning';
}

interface PlanData {
  overall_strategy: string;
  tasks: PlanTaskTrace[];
}

interface TaskExecutionTrace {
  task_index: number;
  task: PlanTaskTrace;
  output: string;
  references_used?: WorkflowReference[];
}

interface IterationDecisionTrace {
  status: string;
  reason: string;
  missing_information?: string[];
}

interface IterationTrace {
  iteration: number;
  plan: {
    overall_strategy: string;
    tasks: PlanTaskTrace[];
  };
  tasks: TaskExecutionTrace[];
  synthesis: string;
  decision: IterationDecisionTrace;
  iteration_summary?: string;
  references?: WorkflowReference[];
}

interface ComplexityDecisionTrace {
  level: 'simple' | 'complex';
  rationale: string;
}

interface WorkflowTrace {
  complexity_decision?: ComplexityDecisionTrace;
  iterations?: IterationTrace[];
}

interface ProgressUpdate {
  id: string;
  phase: string;
  title: string;
  message?: string;
  data?: Record<string, any>;
  timestamp: string;
}

interface ProgressState {
  status: 'running' | 'finished' | 'error' | 'cancelled';
  updates: ProgressUpdate[];
  final_trace?: WorkflowTrace | null;
  error?: string | null;
}

type StatusCategory = 'document' | 'tool';
type StatusState = 'muted' | 'success' | 'warning' | 'error';

interface StatusChip {
  category: StatusCategory;
  state: StatusState;
  text: string;
}

const STATUS_CATEGORY_STYLES: Record<StatusCategory, Record<StatusState, string>> = {
  document: {
    muted: 'text-sky-600 border-sky-200 bg-sky-50/60',
    success: 'text-sky-700 border-sky-300 bg-sky-100',
    warning: 'text-sky-600 border-sky-200 bg-sky-50/60',
    error: 'text-sky-700 border-sky-300 bg-sky-100/80',
  },
  tool: {
    muted: 'text-amber-600 border-amber-200 bg-amber-50/60',
    success: 'text-emerald-600 border-emerald-200 bg-emerald-50/80',
    warning: 'text-amber-600 border-amber-200 bg-amber-50/60',
    error: 'text-red-600 border-red-200 bg-red-50/70',
  },
};

const CHIP_TEXT_MAX_LENGTH = 18;
const VALID_STATUS_STATES: StatusState[] = ['muted', 'success', 'warning', 'error'];

// ── 引用标记预处理 ──
// 在传给 ReactMarkdown 之前，将 [N] 替换为自定义 HTML 标签
function preprocessCitations(
  content: string,
  citationMap?: Record<number, { source: string; snippet: string }>
): string {
  if (!citationMap || Object.keys(citationMap).length === 0) return content
  return content.replace(/\[(\d+)\]/g, (match, idStr) => {
    const id = parseInt(idStr)
    const info = citationMap[id]
    if (info) {
      const source = info.source.replace(/"/g, '&quot;')
      const snippet = info.snippet.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      return `<cite-badge data-cite-id="${id}" data-source="${source}" data-snippet="${snippet}">[${id}]</cite-badge>`
    }
    return match // 无对应 citation_map 时保留原文
  })
}

// ── JSON 自动检测与格式化 ──
// 防止 LLM 意外输出 JSON 被原样展示
function safeFormatContent(content: string): string {
  const trimmed = content.trim()
  // 检测是否以 { 或 [ 开头（可能的 JSON 输出）
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return content

  try {
    const parsed = JSON.parse(trimmed)

    // 处理数组
    if (Array.isArray(parsed)) {
      return parsed.map((item: any, i: number) => {
        if (typeof item === 'object' && item !== null) {
          return formatJsonItem(item, i + 1)
        }
        return `- ${String(item)}`
      }).join('\n\n')
    }

    // 处理对象
    if (typeof parsed === 'object' && parsed !== null) {
      return formatJsonObject(parsed)
    }

    return content
  } catch {
    return content // 不是合法 JSON，返回原内容
  }
}

function formatJsonItem(item: Record<string, any>, index: number): string {
  const lines: string[] = []
  // 尝试识别中文语义字段并格式化
  const titleLike = item.topic || item.trend || item.title || item.name || ''
  const descLike = item.evidence || item.analysis || item.description || item.content || item.detail || ''
  // 如果有 topic/trend 这类字段，用标题+段落格式
  if (titleLike && descLike) {
    lines.push(`**${index}. ${titleLike}**`)
    lines.push('')
    lines.push(descLike)
  } else {
    // 通用格式：逐字段展示
    lines.push(`**${index}.**`)
    for (const [k, v] of Object.entries(item)) {
      if (typeof v === 'string') {
        lines.push(`- **${k}**：${v}`)
      } else if (Array.isArray(v)) {
        lines.push(`- **${k}**：${v.join('、')}`)
      } else if (typeof v === 'object' && v !== null) {
        lines.push(`- **${k}**：${JSON.stringify(v)}`)
      }
    }
  }
  return lines.join('\n')
}

function formatJsonObject(obj: Record<string, any>): string {
  const lines: string[] = []
  const keys = Object.keys(obj)

  // 检查是否是热点/趋势类结构：有数组值且数组元素含 topic/trend 字段
  const hasArrays = keys.filter(k => Array.isArray(obj[k]))
  if (hasArrays.length > 0) {
    for (const key of keys) {
      const val = obj[key]
      if (Array.isArray(val) && val.length > 0) {
        // 中英文字段名映射
        const sectionTitle: Record<string, string> = {
          hot_topics: '## 研究热点',
          future_trends: '## 未来趋势',
          topics: '## 主题',
          trends: '## 趋势',
          references: '## 参考文献',
          findings: '## 研究发现',
          recommendations: '## 建议',
          highlights: '## 要点',
        }
        const title = sectionTitle[key] || `## ${key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}`
        lines.push(title)
        lines.push('')
        val.forEach((item: any, i: number) => {
          if (typeof item === 'object' && item !== null) {
            lines.push(formatJsonItem(item, i + 1))
          } else {
            lines.push(`- ${String(item)}`)
          }
          lines.push('')
        })
      } else {
        lines.push(`- **${key}**：${typeof val === 'string' ? val : JSON.stringify(val)}`)
      }
    }
  } else {
    // 普通对象
    for (const [k, v] of Object.entries(obj)) {
      if (typeof v === 'string') {
        lines.push(`- **${k}**：${v}`)
      } else {
        lines.push(`- **${k}**：${JSON.stringify(v)}`)
      }
    }
  }
  return lines.join('\n')
}

const markdownComponents: MarkdownComponents = {
  // ── 标题 ──
  h1({ children, ...props }) {
    return <h1 className="text-xl font-bold mt-6 mb-3 text-gray-900 border-b border-gray-200 pb-2" {...props}>{children}</h1>
  },
  h2({ children, ...props }) {
    return <h2 className="text-lg font-bold mt-5 mb-2 text-gray-900 border-b border-gray-100 pb-1.5" {...props}>{children}</h2>
  },
  h3({ children, ...props }) {
    return <h3 className="text-base font-semibold mt-4 mb-2 text-gray-800" {...props}>{children}</h3>
  },
  h4({ children, ...props }) {
    return <h4 className="text-sm font-semibold mt-3 mb-1.5 text-gray-800" {...props}>{children}</h4>
  },
  h5({ children, ...props }) {
    return <h5 className="text-sm font-medium mt-3 mb-1 text-gray-700" {...props}>{children}</h5>
  },
  h6({ children, ...props }) {
    return <h6 className="text-xs font-medium mt-2 mb-1 text-gray-600 uppercase tracking-wide" {...props}>{children}</h6>
  },
  // ── 代码 ──
  code({ inline, className, children, ...props }: any) {
    if (inline) {
      return (
        <code className="rounded-md bg-gray-100 px-1.5 py-0.5 font-mono text-[0.9em] text-rose-700" {...props}>
          {children}
        </code>
      )
    }
    const match = /language-(\w+)/.exec(className || '')
    return (
      <div className="relative my-4">
        {match && (
          <div className="absolute right-3 top-2 text-[10px] text-gray-400 uppercase font-mono">
            {match[1]}
          </div>
        )}
        <pre className="bg-gray-900 text-gray-100 rounded-xl p-4 pt-7 overflow-x-auto text-[0.85em] leading-relaxed">
          <code className={className} {...props}>{children}</code>
        </pre>
      </div>
    )
  },
  // ── 链接 ──
  a({ children, ...props }) {
    return (
      <a className="text-blue-600 underline underline-offset-2 break-words hover:text-blue-800" target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    )
  },
  // ── 列表 ──
  ul({ children, ...props }) {
    return <ul className="list-disc pl-5 space-y-1 my-2" {...props}>{children}</ul>
  },
  ol({ children, ...props }) {
    return <ol className="list-decimal pl-5 space-y-1 my-2" {...props}>{children}</ol>
  },
  li({ children, ...props }) {
    return <li className="text-sm leading-relaxed" {...props}>{children}</li>
  },
  // ── 引用块 ──
  blockquote({ children, ...props }) {
    return (
      <blockquote className="border-l-4 border-blue-300 bg-blue-50/50 pl-4 py-2 my-3 italic text-gray-600 rounded-r-lg" {...props}>
        {children}
      </blockquote>
    )
  },
  // ── 分割线 ──
  hr(props) {
    return <hr className="my-6 border-0 h-px bg-gradient-to-r from-transparent via-gray-300 to-transparent" {...props} />
  },
  // ── 表格 ──
  table({ children, ...props }) {
    return (
      <div className="my-4 overflow-x-auto rounded-xl border border-gray-200">
        <table className="min-w-full text-sm" {...props}>{children}</table>
      </div>
    )
  },
  thead({ children, ...props }) {
    return <thead className="bg-gray-50 border-b border-gray-200" {...props}>{children}</thead>
  },
  tbody({ children, ...props }) {
    return <tbody className="divide-y divide-gray-100" {...props}>{children}</tbody>
  },
  tr({ children, ...props }) {
    return <tr className="even:bg-gray-50/50" {...props}>{children}</tr>
  },
  th({ children, ...props }) {
    return <th className="px-4 py-2.5 text-left font-semibold text-gray-700 whitespace-nowrap" {...props}>{children}</th>
  },
  td({ children, ...props }) {
    return <td className="px-4 py-2.5 text-gray-600" {...props}>{children}</td>
  },
  // ── 强调 ──
  strong({ children, ...props }) {
    return <strong className="font-semibold text-gray-900" {...props}>{children}</strong>
  },
  em({ children, ...props }) {
    return <em className="italic text-gray-700" {...props}>{children}</em>
  },
  // ── 图片 ──
  img({ ...props }) {
    return <img className="max-w-full h-auto rounded-lg my-3" {...props} />
  },
  // ── 段落 ──
  p({ children, ...props }) {
    return <p className="mb-3 last:mb-0 text-sm leading-relaxed" {...props}>{children}</p>
  },
  // ── 引用标记（由 preprocessCitations 生成）──
  // @ts-expect-error cite-badge is a custom element for rehype-raw
  'cite-badge': ({ 'data-cite-id': citeId, 'data-source': source, 'data-snippet': snippet, children, ...props }: any) => {
    const handleClick = (e: React.MouseEvent) => {
      e.stopPropagation()
      // 触发自定义事件，由消息容器捕获
      const event = new CustomEvent('citation-click', { bubbles: true, detail: { citeId: parseInt(citeId) } })
      ;(e.target as HTMLElement).dispatchEvent(event)
    }
    const handleMouseEnter = (e: React.MouseEvent) => {
      const event = new CustomEvent('citation-hover', { bubbles: true, detail: { citeId: parseInt(citeId), source, snippet, x: e.clientX, y: e.clientY } })
      ;(e.target as HTMLElement).dispatchEvent(event)
    }
    const handleMouseLeave = () => {
      const event = new CustomEvent('citation-leave', { bubbles: true })
      document.dispatchEvent(event)
    }
    return (
      <sup className="inline-block cursor-pointer mx-0.5" onClick={handleClick} onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave}>
        <span
          className="inline-flex items-center justify-center min-w-[20px] h-[20px] px-[4px] text-[11px] font-semibold leading-none rounded-full bg-blue-100 text-blue-700 hover:bg-blue-200 border border-blue-300 transition-colors align-top"
          title={source ? `${source}: ${(snippet || '').slice(0, 120)}` : undefined}
        >
          {citeId}
        </span>
      </sup>
    )
  },
}

const safeTrim = (value?: unknown): string => (typeof value === 'string' ? value.trim() : '');

const inferStatusState = (message?: string): StatusState => {
  const content = safeTrim(message);
  if (!content) {
    return 'muted';
  }
  const lowered = content.toLowerCase();
  if (content.includes('失败') || content.includes('错误') || lowered.includes('error')) {
    return 'error';
  }
  if (content.includes('未启用') || content.includes('未触发')) {
    return 'muted';
  }
  if (
    content.includes('命中') ||
    content.includes('成功') ||
    content.includes('完成')
  ) {
    return 'success';
  }
  if (
    content.includes('检索中') ||
    content.includes('执行中') ||
    content.includes('准备') ||
    content.includes('等待') ||
    content.includes('未命中') ||
    content.includes('没有找到') ||
    content.includes('暂无')
  ) {
    return 'warning';
  }
  return 'muted';
};

const buildChipText = (category: StatusCategory, message?: string): string => {
  const content = safeTrim(message);
  if (!content) {
    return category === 'document' ? '未触发' : '未触发';
  }
  if (category === 'document') {
    const hitMatch = content.match(/(\d+)\s*条/);
    if (content.includes('成功') && hitMatch) {
      return `命中 ${hitMatch[1]}`;
    }
    if (content.includes('命中')) {
      return '检索命中';
    }
    if (content.includes('未命中') || content.includes('没有找到')) {
      return '未命中';
    }
    if (content.includes('失败')) {
      return '检索失败';
    }
    if (content.includes('检索中') || content.includes('准备')) {
      return '检索中';
    }
  } else {
    const toolMatch = content.match(/工具\s*([^\s，,。]+)/);
    if (content.includes('成功')) {
      return toolMatch ? `${toolMatch[1]} 成功` : '调用成功';
    }
    if (content.includes('失败')) {
      return toolMatch ? `${toolMatch[1]} 失败` : '调用失败';
    }
    if (content.includes('执行中') || content.includes('准备')) {
      return '执行中';
    }
  }
  return content.length > CHIP_TEXT_MAX_LENGTH ? `${content.slice(0, CHIP_TEXT_MAX_LENGTH - 1)}…` : content;
};

const normalizeStatusChips = (update: ProgressUpdate): StatusChip[] => {
  const normalized = new Map<StatusCategory, StatusChip>();
  const task = update.data?.task;
  const requiresDocument = Boolean(task?.requires_vector_search);
  const requiresTool = Boolean(task?.requires_tool);

  const isCategoryAllowed = (category: StatusCategory) => {
    if (category === 'document') {
      return requiresDocument;
    }
    return requiresTool;
  };

  const rawChips = Array.isArray(update.data?.status_chips) ? update.data!.status_chips : [];
  rawChips.forEach((raw: any) => {
    if (!raw || typeof raw !== 'object') {
      return;
    }
    const category: StatusCategory = raw.category === 'tool' ? 'tool' : 'document';
    if (!isCategoryAllowed(category)) {
      return;
    }
    const rawText = safeTrim(raw.text ?? raw.label ?? raw.status);
    const rawState = safeTrim(raw.state);
    const state: StatusState = VALID_STATUS_STATES.includes(rawState as StatusState)
      ? (rawState as StatusState)
      : inferStatusState(rawText);
    const text = rawText || buildChipText(category, rawText);
    if (!text) {
      return;
    }
    normalized.set(category, {
      category,
      state,
      text,
    });
  });

  const ensureChip = (category: StatusCategory, required: boolean, statusMessage?: string) => {
    if (!required) {
      return;
    }
    const existing = normalized.get(category);
    const message = safeTrim(statusMessage);
    if (existing) {
      if (!safeTrim(existing.text)) {
        normalized.set(category, {
          ...existing,
          state: existing.state ?? inferStatusState(message),
          text: buildChipText(category, message),
        });
      }
      return;
    }
    normalized.set(category, {
      category,
      state: inferStatusState(message),
      text: buildChipText(category, message),
    });
  };

  ensureChip(
    'document',
    requiresDocument,
    typeof update.data?.vector_status === 'string' ? update.data.vector_status : undefined
  );
  ensureChip(
    'tool',
    requiresTool,
    typeof update.data?.tool_status === 'string' ? update.data.tool_status : undefined
  );

  return Array.from(normalized.values()).filter((chip) => chip.text && chip.text.trim());
};

type ModelType = 'deepseek' | 'deepseek-reasoner' | 'qwen' | 'gpt' | 'gemini' | 'grok' | 'custom' | 'local';
type ModelSource = 'cloud' | 'local';
type CloudPresetKey = 'deepseek' | 'qwen' | 'gpt' | 'gemini' | 'grok' | 'custom';

const MODEL_SOURCE_OPTIONS: Array<{ value: ModelSource; label: string; disabled?: boolean }> = [
  { value: 'cloud', label: '云端模型' },
  { value: 'local', label: '本地模型（暂不可用）', disabled: true },
];

const CLOUD_MODEL_PRESETS: Record<Exclude<CloudPresetKey, 'custom'>, { label: string; general: string; reasoning: string; baseUrl: string }> = {
  deepseek: { label: 'DeepSeek', general: 'deepseek-chat', reasoning: 'deepseek-reasoner', baseUrl: 'https://api.deepseek.com/v1' },
  qwen: { label: 'Qwen', general: 'qwen-plus', reasoning: 'qwen-plus', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  gpt: { label: 'GPT', general: 'gpt-4o', reasoning: 'gpt-4o-mini', baseUrl: '' },
  gemini: { label: 'Gemini', general: 'gemini-2.5-pro', reasoning: 'gemini-2.5-flash', baseUrl: '' },
  grok: { label: 'Grok', general: 'grok-4-0709', reasoning: 'grok-3-mini', baseUrl: '' },
};

const CLOUD_MODEL_PRESET_OPTIONS: Array<{ value: CloudPresetKey; label: string }> = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: 'Qwen' },
  { value: 'gpt', label: 'GPT' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'grok', label: 'Grok' },
  { value: 'custom', label: '自定义' },
];

interface CloudConfigState {
  apiKey: string;
  baseUrl: string;
  generalModel: string;
  reasoningModel: string;
}

const DEFAULT_PRESET: Exclude<CloudPresetKey, 'custom'> = 'deepseek';

type ChatMode = 'basic' | 'deep_research' | 'data_analysis';

const MODE_OPTIONS: Array<{ value: ChatMode; label: string }> = [
  { value: 'basic', label: '普通对话' },
  { value: 'deep_research', label: '深度研究' },
  { value: 'data_analysis', label: '数据分析' },
];

const INITIAL_ASSISTANT_MESSAGE: Message = {
  role: 'assistant',
  content: '您好！我是山大公管智能体，由山东大学政治学与公共管理学院开发，专注于公共管理学科的教学与科研辅助。\n\n**我目前支持以下功能：**\n\n| 功能模块 | 说明 |\n|---------|------|\n| 📚 智能对话 | 公管学科概念解析、理论讲解、政策分析 |\n| 🔍 知识库检索 | 基于163+篇学术文献的RAG增强回答 |\n| 🌐 联网搜索 | 实时网络信息检索与整合 |\n| 📝 深度研究 | 多步骤自主研究，含任务分解与迭代精炼 |\n| 📊 数据分析 | Python/R代码生成与沙盒执行 |\n| 🎤 语音交互 | 语音输入与语音播报 |\n\n请问有什么可以帮您的？',
};

export default function ChatPage() {
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState<Message[]>([INITIAL_ASSISTANT_MESSAGE])
  const [chatMode, setChatMode] = useState<ChatMode>('basic')
  const [progressId, setProgressId] = useState<string | null>(null)
  const [progressData, setProgressData] = useState<ProgressState | null>(null)
  const [workflowTrace, setWorkflowTrace] = useState<WorkflowTrace | null>(null)
  const [referencePreview, setReferencePreview] = useState<{
    open: boolean
    loading: boolean
    title: string
    content: string
    filename?: string
  }>({
    open: false,
    loading: false,
    title: '',
    content: '',
    filename: undefined,
  })
  const [modelSource, setModelSource] = useState<ModelSource>('cloud')
  const [cloudPreset, setCloudPreset] = useState<CloudPresetKey>(DEFAULT_PRESET)
  const [cloudConfig, setCloudConfig] = useState<CloudConfigState>({
    apiKey: '',
    baseUrl: CLOUD_MODEL_PRESETS[DEFAULT_PRESET].baseUrl,
    generalModel: CLOUD_MODEL_PRESETS[DEFAULT_PRESET].general,
    reasoningModel: CLOUD_MODEL_PRESETS[DEFAULT_PRESET].reasoning,
  })
  const [cloudConfigLoaded, setCloudConfigLoaded] = useState(false)
  const [envApiConfig, setEnvApiConfig] = useState<{
    openai_api_key: string;
    openai_base_url: string;
    dashscope_api_key: string;
    dashscope_base_url: string;
  } | null>(null)
  const [showApiKey, setShowApiKey] = useState(false)
  const [showBaseUrl, setShowBaseUrl] = useState(false)
  const [maxIterations, setMaxIterations] = useState<number>(3)
  const [llmType, setLlmType] = useState<ModelType>(DEFAULT_PRESET)
  const [isRecording, setIsRecording] = useState(false)
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const currentRequestIdRef = useRef<string | null>(null)
  const cancelTriggeredRef = useRef(false)
  const activeProgressIdRef = useRef<string | null>(null)
  const [audioChunks, setAudioChunks] = useState<Blob[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [recordingTime, setRecordingTime] = useState(0)
  const [recordingTimer, setRecordingTimer] = useState<NodeJS.Timeout | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const audioStreamRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const audioProcessorRef = useRef<ScriptProcessorNode | null>(null)
  const audioDataRef = useRef<Float32Array[]>([])
  const progressPollerRef = useRef<NodeJS.Timeout | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  // RAG scope selection state
  const [ragScope, setRagScope] = useState<RagScope>({
    includePublic: true,
    includePrivate: false,
    selectedGroupIds: []
  })
  const [showScopePopover, setShowScopePopover] = useState(false)
  const [knowledgeGroups, setKnowledgeGroups] = useState<KnowledgeGroup[]>([])
  const [knowledgeGroupsLoaded, setKnowledgeGroupsLoaded] = useState(false)
  const [analysisLanguage, setAnalysisLanguage] = useState<'python' | 'r'>('python')
  const [analysisGroupId, setAnalysisGroupId] = useState('')
  const [analysisDataFiles, setAnalysisDataFiles] = useState<DataFileInfo[]>([])
  const [analysisGroupMessage, setAnalysisGroupMessage] = useState('')
  const [analysisGroupValid, setAnalysisGroupValid] = useState(false)
  const [analysisGroupChecking, setAnalysisGroupChecking] = useState(false)
  const [analysisRunLoading, setAnalysisRunLoading] = useState<Record<number, boolean>>({})
  const [analysisEditor, setAnalysisEditor] = useState<{
    open: boolean;
    code: string;
    messageIndex: number | null;
    language: 'python' | 'r';
    groupId?: string;
  }>({
    open: false,
    code: '',
    messageIndex: null,
    language: 'python',
  })

  // Cloud config collapse state
  const [showCloudConfig, setShowCloudConfig] = useState(false)

  // Web search state
  const [enableWebSearch, setEnableWebSearch] = useState(false)

  // References collapse state - track expanded state for each message
  const [expandedReferences, setExpandedReferences] = useState<Set<number>>(new Set())

  // Plan editor modal state
  const [showPlanEditor, setShowPlanEditor] = useState(false)
  const [editingPlan, setEditingPlan] = useState<PlanData | null>(null)
  const [pendingProgressId, setPendingProgressId] = useState<string | null>(null)
  const [planEditorTriggered, setPlanEditorTriggered] = useState(false)
  const [citationTooltip, setCitationTooltip] = useState<{show:boolean;x:number;y:number;source:string;snippet:string;id:number}|null>(null)

  // ── 引用标记事件处理 ──
  useEffect(() => {
    const handleCitationClick = (e: Event) => {
      const detail = (e as CustomEvent).detail as { citeId: number }
      // 展开第一条包含该引用的消息的参考资料面板
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].citation_map?.[detail.citeId]) {
          setExpandedReferences(prev => { const next = new Set(prev); next.add(i); return next })
          break
        }
      }
    }
    const handleCitationHover = (e: Event) => {
      const detail = (e as CustomEvent).detail as { citeId: number; source: string; snippet: string; x: number; y: number }
      setCitationTooltip({ show: true, x: detail.x, y: detail.y, source: detail.source, snippet: detail.snippet, id: detail.citeId })
    }
    const handleCitationLeave = () => {
      setCitationTooltip(null)
    }
    document.addEventListener('citation-click', handleCitationClick)
    document.addEventListener('citation-hover', handleCitationHover)
    document.addEventListener('citation-leave', handleCitationLeave)
    return () => {
      document.removeEventListener('citation-click', handleCitationClick)
      document.removeEventListener('citation-hover', handleCitationHover)
      document.removeEventListener('citation-leave', handleCitationLeave)
    }
  }, [messages])

  const isCloudModel = modelSource === 'cloud'

  const loadKnowledgeGroups = useCallback(async () => {
    if (knowledgeGroupsLoaded) return

    console.log('开始加载知识组列表...')

    try {
      const response = await apiFetch('/api/v1/knowledge-groups')
      console.log('知识组API响应状态', response.ok)

      if (!response.ok) {
        const errorText = await response.text()
        console.error('知识组API错误:', errorText)
        throw new Error('加载知识组失败')
      }

      const data = await response.json()
      console.log('知识组数据', data)

      if (data.status === 'success') {
        setKnowledgeGroups(data.data || [])
        setKnowledgeGroupsLoaded(true)
        console.log('成功加载', (data.data || []).length, '个知识组')
      } else {
        throw new Error(data.message || '加载知识组失败')
      }
    } catch (error) {
      console.error('加载知识组失败', error)
      toast.error('加载知识组失败，请确保已登录')
    }
  }, [knowledgeGroupsLoaded])

  useLayoutEffect(() => {
    const element = textareaRef.current
    if (!element) {
      return
    }
    element.style.height = 'auto'
    const nextHeight = Math.min(160, Math.max(42, element.scrollHeight))
    element.style.height = `${nextHeight}px`
  }, [message])

  useEffect(() => {
    if (typeof window === 'undefined') return

    // 首先尝试从后端加载环境变量配置
    const loadEnvConfig = async () => {
      try {
        const response = await fetch('/api/v1/chat/env-config')
        if (response.ok) {
          const envConfig = await response.json()

          // 保存环境变量配置到状态
          setEnvApiConfig(envConfig)

          // 如果后端有配置，优先使用后端的配置
          if (envConfig.openai_api_key || envConfig.dashscope_api_key) {
            // 根据当前预设选择对应的配置
            let apiKey = ''
            let baseUrl = ''

            if (cloudPreset === 'qwen' && envConfig.dashscope_api_key) {
              apiKey = envConfig.dashscope_api_key
              baseUrl = envConfig.dashscope_base_url || CLOUD_MODEL_PRESETS['qwen'].baseUrl
            } else if (cloudPreset === 'deepseek' && envConfig.openai_api_key) {
              apiKey = envConfig.openai_api_key
              baseUrl = envConfig.openai_base_url || CLOUD_MODEL_PRESETS['deepseek'].baseUrl
            } else if (envConfig.openai_api_key) {
              apiKey = envConfig.openai_api_key
              baseUrl = envConfig.openai_base_url || CLOUD_MODEL_PRESETS[DEFAULT_PRESET].baseUrl
            }

            if (apiKey) {
              setCloudConfig({
                apiKey: apiKey,
                baseUrl: baseUrl,
                generalModel: CLOUD_MODEL_PRESETS[DEFAULT_PRESET].general,
                reasoningModel: CLOUD_MODEL_PRESETS[DEFAULT_PRESET].reasoning,
              })
              console.log('已从环境变量加载API配置')
              setCloudConfigLoaded(true)
              return
            }
          }
        }
      } catch (error) {
        console.warn('从后端加载环境变量配置失败：', error)
      }

      // 如果后端没有配置，尝试从 localStorage 加载
      try {
        const stored = window.localStorage.getItem('chat_cloud_config')
        if (stored) {
          const parsed = JSON.parse(stored) as Partial<CloudConfigState>
          setCloudConfig({
            apiKey: parsed.apiKey || '',
            baseUrl: parsed.baseUrl || CLOUD_MODEL_PRESETS[DEFAULT_PRESET].baseUrl,
            generalModel: parsed.generalModel || CLOUD_MODEL_PRESETS[DEFAULT_PRESET].general,
            reasoningModel:
              parsed.reasoningModel || CLOUD_MODEL_PRESETS[DEFAULT_PRESET].reasoning,
          })
        }
      } catch (error) {
        console.warn('加载云端配置失败：', error)
      } finally {
        setCloudConfigLoaded(true)
      }
    }

    loadEnvConfig()
  }, [])

  useEffect(() => {
    if (!cloudConfigLoaded || typeof window === 'undefined') return
    try {
      window.localStorage.setItem('chat_cloud_config', JSON.stringify(cloudConfig))
    } catch (error) {
      console.warn('保存云端配置失败：', error)
    }
  }, [cloudConfig, cloudConfigLoaded])

  // RAG scope localStorage persistence - restore
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const stored = window.localStorage.getItem('chat_rag_scope')
      if (stored) setRagScope(JSON.parse(stored))
    } catch (error) {
      console.warn('恢复RAG范围选择失败:', error)
    }
  }, [])

  // RAG scope localStorage persistence - save
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem('chat_rag_scope', JSON.stringify(ragScope))
    } catch (error) {
      console.warn('保存RAG范围选择失败:', error)
    }
  }, [ragScope])

  // Web search localStorage persistence - restore
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const stored = window.localStorage.getItem('chat_enable_web_search')
      if (stored !== null) setEnableWebSearch(JSON.parse(stored))
    } catch (error) {
      console.warn('恢复联网搜索开关失败:', error)
    }
  }, [])

  // Web search localStorage persistence - save
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem('chat_enable_web_search', JSON.stringify(enableWebSearch))
    } catch (error) {
      console.warn('保存联网搜索开关失败:', error)
    }
  }, [enableWebSearch])

  // Load knowledge groups when popover opens
  useEffect(() => {
    if (showScopePopover && !knowledgeGroupsLoaded) {
      loadKnowledgeGroups()
    }
  }, [showScopePopover, knowledgeGroupsLoaded, loadKnowledgeGroups])

  useEffect(() => {
    if (chatMode === 'data_analysis' && !knowledgeGroupsLoaded) {
      loadKnowledgeGroups()
    }
  }, [chatMode, knowledgeGroupsLoaded, loadKnowledgeGroups])

  useEffect(() => {
    if (chatMode === 'data_analysis') {
      setEnableWebSearch(false)
    } else {
      setAnalysisGroupValid(false)
      setAnalysisGroupMessage('')
      setAnalysisDataFiles([])
    }
  }, [chatMode])

  const validateAnalysisGroup = useCallback(
    async (groupId: string, quiet = false) => {
      if (!groupId) {
        setAnalysisGroupValid(false)
        setAnalysisDataFiles([])
        setAnalysisGroupMessage('请选择包含CSV/Excel的知识组')
        return false
      }

      setAnalysisGroupChecking(true)
      try {
        const response = await apiFetch(`/api/v1/knowledge-groups/${groupId}/data-files`)
        const data = await response.json()
        const isValid = response.ok && !!data.valid
        setAnalysisGroupValid(isValid)
        setAnalysisDataFiles(data.data || [])
        setAnalysisGroupMessage(data.message || '')
        if (!isValid && !quiet) {
          toast.error(data.message || '所选知识组不满足数据分析要求')
        }
        return isValid
      } catch (error) {
        console.error('校验知识组失败', error)
        setAnalysisGroupValid(false)
        setAnalysisDataFiles([])
        setAnalysisGroupMessage('校验知识组失败，请稍后重试')
        if (!quiet) {
          toast.error('校验知识组失败，请稍后重试')
        }
        return false
      } finally {
        setAnalysisGroupChecking(false)
      }
    },
    []
  )

  const handleModelSourceChange = (value: ModelSource) => {
    setModelSource(value)
    if (value === 'local') {
      setLlmType('local')
    } else {
      setLlmType(cloudPreset === 'custom' ? 'custom' : cloudPreset)
    }
  }

  const handlePresetChange = (value: CloudPresetKey) => {
    setCloudPreset(value)
    if (value === 'custom') {
      setLlmType('custom')
      setCloudConfig((prev) => ({
        ...prev,
        generalModel: '',
        reasoningModel: '',
      }))
      return
    }
    const preset = CLOUD_MODEL_PRESETS[value]
    setLlmType(value)

    // 根据预设选择对应的环境变量配置
    let apiKey = ''
    let baseUrl = preset.baseUrl

    if (envApiConfig) {
      if (value === 'qwen' && envApiConfig.dashscope_api_key) {
        apiKey = envApiConfig.dashscope_api_key
        baseUrl = envApiConfig.dashscope_base_url || preset.baseUrl
      } else if (value === 'deepseek' && envApiConfig.openai_api_key) {
        apiKey = envApiConfig.openai_api_key
        baseUrl = envApiConfig.openai_base_url || preset.baseUrl
      } else if (envApiConfig.openai_api_key) {
        apiKey = envApiConfig.openai_api_key
        baseUrl = envApiConfig.openai_base_url || preset.baseUrl
      }
    }

    setCloudConfig((prev) => ({
      ...prev,
      apiKey: apiKey || prev.apiKey, // 如果没有环境变量配置，保留原有的apiKey
      baseUrl: baseUrl,
      generalModel: preset.general,
      reasoningModel: preset.reasoning,
    }))

    if (apiKey) {
      console.log(`已自动加载 ${value} 预设的环境变量配置`)
    }
  }

  useEffect(() => {
    if (chatMode !== 'deep_research') {
      setWorkflowTrace(null);
      setProgressId(null);
      setProgressData(null);
      activeProgressIdRef.current = null;
      if (progressPollerRef.current) {
        clearInterval(progressPollerRef.current);
        progressPollerRef.current = null;
      }
    }
  }, [chatMode]);

  useEffect(() => {
    return () => {
      if (progressPollerRef.current) {
        clearInterval(progressPollerRef.current);
        progressPollerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (progressData?.status === 'finished' && progressData.final_trace) {
      setWorkflowTrace(progressData.final_trace);
    }
  }, [progressData]);

  // 监听plan_awaiting_approval事件，显示计划编辑窗口
  useEffect(() => {
    if (!progressData || chatMode !== 'deep_research') return;

    // 如果计划编辑器已经被触发过，不再重复触发
    if (planEditorTriggered) return;

    // 检查是否已经进入后续阶段（计划已批准或超时）
    const hasApprovedOrTimeout = progressData.updates.some(
      (update) => update.phase === 'plan_approved' || update.phase === 'plan_timeout'
    );

    // 如果已经进入后续阶段，不再弹出编辑窗口
    if (hasApprovedOrTimeout) {
      setPlanEditorTriggered(true); // 标记为已触发，避免后续再弹出
      return;
    }

    // 检查是否有等待确认的计划
    const awaitingUpdate = progressData.updates.find(
      (update) => update.phase === 'plan_awaiting_approval'
    );

    if (awaitingUpdate && awaitingUpdate.data?.plan) {
      const planData: PlanData = {
        overall_strategy: awaitingUpdate.data.plan.overall_strategy || '',
        tasks: awaitingUpdate.data.plan.tasks || [],
      };
      setEditingPlan(planData);
      setPendingProgressId(progressId);
      setShowPlanEditor(true);
      setPlanEditorTriggered(true); // 标记为已触发
    }
  }, [progressData, chatMode, progressId, planEditorTriggered]);

  useEffect(() => {
    if (chatMode !== 'deep_research' || !progressId) {
      return;
    }

    const fetchProgress = async () => {
      try {
        const res = await fetch(`/api/v1/chat/progress/${progressId}`);
        if (!res.ok) {
          if (res.status !== 404) {
            throw new Error(await res.text());
          }
          return;
        }
        const data = await res.json() as ProgressState;
        setProgressData(data);
        if (data.status === 'finished' || data.status === 'error' || data.status === 'cancelled') {
          if (progressPollerRef.current) {
            clearInterval(progressPollerRef.current);
            progressPollerRef.current = null;
          }
          activeProgressIdRef.current = null;
        }
      } catch (err) {
        console.error('进度轮询失败:', err);
      }
    };

    fetchProgress();
    if (progressPollerRef.current) {
      clearInterval(progressPollerRef.current);
    }
    progressPollerRef.current = setInterval(fetchProgress, 1500);

    return () => {
      if (progressPollerRef.current) {
        clearInterval(progressPollerRef.current);
        progressPollerRef.current = null;
      }
    };
  }, [progressId, chatMode]);


  const startTimer = () => {
    const timer = setInterval(() => {
      setRecordingTime((prev) => prev + 1)
    }, 1000)
    setRecordingTimer(timer)
  }

  const stopTimer = () => {
    if (recordingTimer) {
      clearInterval(recordingTimer)
      setRecordingTimer(null)
    }
    setRecordingTime(0)
  }

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  // 将references按文档分组
  const groupReferencesByDocument = (references: MessageReference[]) => {
    const grouped = new Map<string, {
      key: string;
      isWeb: boolean;
      title: string;
      filename?: string;
      url?: string;
      library_type?: string;
      knowledge_group_id?: string;
      knowledge_group_name?: string;
      category?: string;
      tags?: string[];
      upload_time?: string;
      size?: number;
      // 分类特定字段
      effectiveness_level?: string;
      document_type?: string;
      discipline?: string;
      region?: string;
      main_topic?: string;
      chunks: Array<{
        content: string;
        chunk_index?: number;
        score?: number;
      }>;
    }>();

    references.forEach((ref) => {
      const isWeb = ref.type === 'web_search';
      const key = isWeb ? ref.url || ref.title : ref.filename || ref.title;

      if (grouped.has(key)) {
        // 同一文档，添加新片段
        grouped.get(key)!.chunks.push({
          content: ref.content,
          chunk_index: ref.chunk_index,
          score: ref.score,
        });
      } else {
        // 新文档
        grouped.set(key, {
          key,
          isWeb,
          title: ref.title,
          filename: ref.filename,
          url: ref.url,
          library_type: ref.library_type,
          knowledge_group_id: ref.knowledge_group_id,
          knowledge_group_name: ref.knowledge_group_name,
          category: ref.category,
          tags: ref.tags,
          upload_time: ref.upload_time,
          size: ref.size,
          effectiveness_level: ref.effectiveness_level,
          document_type: ref.document_type,
          discipline: ref.discipline,
          region: ref.region,
          main_topic: ref.main_topic,
          chunks: [{
            content: ref.content,
            chunk_index: ref.chunk_index,
            score: ref.score,
          }],
        });
      }
    });

    return Array.from(grouped.values());
  };

  const summarizeText = (input: string, limit = 160) => {
    if (!input) return '';
    return input.length > limit ? `${input.slice(0, limit)}…` : input;
  };

  const formatTimestamp = (isoString?: string) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleTimeString();
  };

  const floatTo16BitPCM = (input: Float32Array): Int16Array => {
    const output = new Int16Array(input.length)
    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]))
      output[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
    }
    return output
  }

  const writeString = (view: DataView, offset: number, string: string): number => {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i))
    }
    return offset + string.length
  }

  const createWavFile = (audioData: Float32Array[]): Blob => {
    const numChannels = 1
    const sampleRate = 16000
    const totalLength = audioData.reduce((acc, curr) => acc + curr.length, 0)
    const buffer = new ArrayBuffer(44 + totalLength * 2)
    const view = new DataView(buffer)

    // Write WAV header
    writeString(view, 0, 'RIFF')
    view.setUint32(4, 36 + totalLength * 2, true)
    writeString(view, 8, 'WAVE')
    writeString(view, 12, 'fmt ')
    view.setUint32(16, 16, true)
    view.setUint16(20, 1, true)
    view.setUint16(22, numChannels, true)
    view.setUint32(24, sampleRate, true)
    view.setUint32(28, sampleRate * numChannels * 2, true)
    view.setUint16(32, numChannels * 2, true)
    view.setUint16(34, 16, true)
    writeString(view, 36, 'data')
    view.setUint32(40, totalLength * 2, true)

    // Write audio data
    let offset = 44
    for (const channelData of audioData) {
      const samples = floatTo16BitPCM(channelData)
      for (let i = 0; i < samples.length; i++, offset += 2) {
        view.setInt16(offset, samples[i], true)
      }
    }

    return new Blob([buffer], { type: 'audio/wav' })
  }

  const handleVoiceRecord = async () => {
    if (!isRecording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            channelCount: 1,
            sampleRate: 16000,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          }
        })

        // 初始化 AudioContext
        audioContextRef.current = new AudioContext({ sampleRate: 16000 })
        audioStreamRef.current = audioContextRef.current.createMediaStreamSource(stream)
        audioProcessorRef.current = audioContextRef.current.createScriptProcessor(4096, 1, 1)
        audioDataRef.current = []

        // 处理音频数据
        audioProcessorRef.current.onaudioprocess = (e) => {
          const inputData = e.inputBuffer.getChannelData(0)
          audioDataRef.current.push(new Float32Array(inputData))
        }

        // 连接音频节点
        audioStreamRef.current.connect(audioProcessorRef.current)
        audioProcessorRef.current.connect(audioContextRef.current.destination)

        setIsRecording(true)
        startTimer()
        toast.success('开始录音...')

      } catch (err) {
        const error = err as ApiError;
        console.error('录音错误:', error);
        toast.error('无法启动录音: ' + error.message);
      }
    } else {
      try {
        // 停止录音
        if (audioProcessorRef.current) {
          audioProcessorRef.current.disconnect()
          audioStreamRef.current?.disconnect()
          audioContextRef.current?.close()
        }

        setIsRecording(false)
        stopTimer()
        toast.success('录音结束，正在转换...', { duration: 2000 })

        // 创建 WAV 文件
        const wavBlob = createWavFile(audioDataRef.current)
        
        // 发送到服务器
        try {
          setIsLoading(true)

          const formData = new FormData()
          formData.append('audio', wavBlob, 'recording.wav')

          // 使用长超时（3分钟）用于语音识别
          const response = await fetchWithTimeout(
            '/api/v1/speech-to-text',
            {
              method: 'POST',
              body: formData,
            },
            TIMEOUT.LONG
          )

          if (!response.ok) {
            throw new Error(await response.text())
          }

          const data = await response.json()
          console.log('语音识别结果:', data)  // 添加日志

          if (data.success && data.text) {
            setMessage(data.text)
            toast.success('语音识别成功')
          } else {
            throw new Error(data.error || '语音识别失败')
          }
        } catch (err) {
          const error = err as ApiError;
          console.error('语音识别错误:', error);
          toast.error('语音识别失败: ' + error.message);
        } finally {
          setIsLoading(false)
          audioDataRef.current = []
        }
      } catch (err) {
        const error = err as ApiError;
        console.error('停止录音错误:', error);
        toast.error('停止录音失败: ' + error.message);
      }
    }
  }

  const getScopeSummary = (): string => {
    const parts: string[] = []
    if (ragScope.includePublic) parts.push("公共库")
    if (ragScope.includePrivate) parts.push("私人库")
    if (ragScope.selectedGroupIds.length > 0) {
      parts.push(`${ragScope.selectedGroupIds.length}个知识组`)
    }
    return parts.length > 0 ? parts.join(" + ") : "未选择"
  }

  const toggleReferences = (messageIndex: number) => {
    setExpandedReferences(prev => {
      const newSet = new Set(prev)
      if (newSet.has(messageIndex)) {
        newSet.delete(messageIndex)
      } else {
        newSet.add(messageIndex)
      }
      return newSet
    })
  }

  // 计划编辑相关函数
  const handleUpdateStrategy = (strategy: string) => {
    if (!editingPlan) return;
    setEditingPlan({ ...editingPlan, overall_strategy: strategy });
  };

  const handleAddTask = () => {
    if (!editingPlan) return;
    const newTask: PlanTaskTrace = {
      task_name: '新任务',
      objective: '',
      requires_vector_search: false,
      requires_tool: false,
      model_preference: 'general',
    };
    setEditingPlan({
      ...editingPlan,
      tasks: [...editingPlan.tasks, newTask],
    });
  };

  const handleUpdateTask = (index: number, updatedTask: PlanTaskTrace) => {
    if (!editingPlan) return;
    const newTasks = [...editingPlan.tasks];
    newTasks[index] = updatedTask;
    setEditingPlan({ ...editingPlan, tasks: newTasks });
  };

  const handleDeleteTask = (index: number) => {
    if (!editingPlan) return;
    const newTasks = editingPlan.tasks.filter((_, i) => i !== index);
    setEditingPlan({ ...editingPlan, tasks: newTasks });
  };

  const handleSubmitPlan = async () => {
    if (!editingPlan || !pendingProgressId) {
      toast.error('无效的计划数据');
      return;
    }

    try {
      const response = await fetch('/api/v1/chat/approve-plan', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          progress_id: pendingProgressId,
          revised_plan: editingPlan,
        }),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || '提交计划失败');
      }

      toast.success('计划已确认，工作流将继续执行');
      setShowPlanEditor(false);
      setEditingPlan(null);
      setPendingProgressId(null);
      // 不重置 planEditorTriggered，保持为 true 避免再次弹出
    } catch (error) {
      const err = error as Error;
      console.error('提交计划失败:', err);
      toast.error('提交计划失败: ' + err.message);
    }
  };

  const handleCancelPlanEdit = () => {
    setShowPlanEditor(false);
    setEditingPlan(null);
    setPendingProgressId(null);
    // 不重置 planEditorTriggered，保持为 true 避免再次弹出
    toast.error('已取消计划编辑');
  };

  const ensureCloudConfigReady = () => {
    if (!isCloudModel) {
      return true
    }
    const apiKey = cloudConfig.apiKey.trim();
    const baseUrl = cloudConfig.baseUrl.trim();
    const generalModel = cloudConfig.generalModel.trim();
    const reasoningModel = cloudConfig.reasoningModel.trim();

    if (!apiKey) {
      toast.error('请先填写云端模型的 API KEY');
      return false;
    }
    if (!baseUrl) {
      toast.error('请先填写 Base URL');
      return false;
    }
    if (!generalModel) {
      toast.error('请先填写通用模型名称');
      return false;
    }
    if (chatMode === 'deep_research' && !reasoningModel) {
      toast.error('请先填写推理模型名称');
      return false;
    }
    return true;
  }

  const handleSend = async () => {
    if (!message.trim() || isLoading) return;

    if (!ensureCloudConfigReady()) {
      return;
    }

    const isDataAnalysisMode = chatMode === 'data_analysis'

    if (isDataAnalysisMode) {
      if (!analysisGroupId) {
        toast.error('请选择用于数据分析的私人知识组');
        return;
      }
      const valid = await validateAnalysisGroup(analysisGroupId, true)
      if (!valid) {
        toast.error(analysisGroupMessage || '所选知识组未通过数据文件校验');
        return;
      }
    }

    // Build RAG scope parameters
    let library_type: string | undefined = undefined
    let knowledge_group_ids: string[] | undefined = undefined

    // Check if any scope is selected
    const hasRagSelection = !isDataAnalysisMode && (ragScope.includePublic || ragScope.includePrivate || ragScope.selectedGroupIds.length > 0)

    if (hasRagSelection) {
      // Convert ragScope to API parameters
      if (ragScope.includePublic && ragScope.includePrivate) {
        // Search all libraries
        library_type = undefined
      } else if (ragScope.includePublic) {
        library_type = "public"
      } else if (ragScope.includePrivate) {
        library_type = "private"
      } else if (ragScope.selectedGroupIds.length > 0) {
        library_type = "private"
        knowledge_group_ids = ragScope.selectedGroupIds
      }
    }

    let currentProgressId: string | null = null;
    if (chatMode === 'deep_research') {
      if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        currentProgressId = crypto.randomUUID();
      } else {
        currentProgressId = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      }
      if (progressPollerRef.current) {
        clearInterval(progressPollerRef.current);
        progressPollerRef.current = null;
      }
      activeProgressIdRef.current = currentProgressId;
      setProgressId(currentProgressId);
      setProgressData({ status: 'running', updates: [], final_trace: null, error: null });
      setWorkflowTrace(null);
      setPlanEditorTriggered(false); // 重置计划编辑标志
    } else {
      if (progressPollerRef.current) {
        clearInterval(progressPollerRef.current);
        progressPollerRef.current = null;
      }
      activeProgressIdRef.current = null;
      setProgressId(null);
      setProgressData(null);
    }

    const requestId = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    currentRequestIdRef.current = requestId;
    cancelTriggeredRef.current = false;

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const targetModel = llmType;

    setMessages(prev => [...prev, { role: 'user' as const, content: message }]);
    setMessage('');
    setIsLoading(true);

    let wasCancelled = false;

    try {
      const payload: Record<string, any> = {
        message,
        llm_type: targetModel,
        mode: chatMode,
        progress_id: currentProgressId,
        request_id: requestId,
        model_source: modelSource,
      };

      if (isCloudModel) {
        const trimmedApiKey = cloudConfig.apiKey.trim();
        const trimmedBaseUrl = cloudConfig.baseUrl.trim();
        const trimmedGeneral = cloudConfig.generalModel.trim();
        const trimmedReasoning = cloudConfig.reasoningModel.trim();

        payload.cloud_config = {
          preset: cloudPreset,
          api_key: trimmedApiKey || undefined,
          base_url: trimmedBaseUrl || undefined,
          general_model: trimmedGeneral || undefined,
          reasoning_model: trimmedReasoning || undefined,
          max_iterations: maxIterations || undefined,
        };
        payload.max_iterations = maxIterations || undefined;
      }

      if (isDataAnalysisMode) {
        payload.analysis_language = analysisLanguage
        payload.analysis_action = 'generate'
        payload.analysis_knowledge_group_id = analysisGroupId
        payload.enable_rag = false
        payload.enable_web_search = false
      } else {
        // Add RAG scope parameters if selected
        if (hasRagSelection) {
          if (library_type !== undefined) {
            payload.library_type = library_type
          }
          if (knowledge_group_ids !== undefined && knowledge_group_ids.length > 0) {
            payload.knowledge_group_ids = knowledge_group_ids
          }
        }

        // Add web search and RAG flags - they are independent
        payload.enable_rag = hasRagSelection
        payload.enable_web_search = enableWebSearch
      }

      const response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });

      if (response.status === 499) {
        wasCancelled = true;
        return;
      }

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      const trace: WorkflowTrace | null = data.trace ?? null;

      if (chatMode === 'deep_research') {
        if (trace) {
          setWorkflowTrace(trace);
        } else if (progressData?.final_trace) {
          setWorkflowTrace(progressData.final_trace);
        }
        setProgressData((prev) =>
          prev
            ? { ...prev, final_trace: trace ?? prev.final_trace ?? null }
            : (trace
              ? { status: 'finished', updates: [], final_trace: trace, error: null }
              : prev)
        );
      } else {
        setWorkflowTrace(null);
      }

      setMessages(prev => [...prev, {
        role: 'assistant' as const,
        content: data.response,
        references: data.references,
        citation_map: data.citation_map,
        trace: trace ?? undefined,
        analysis: data.analysis,
      }]);
    } catch (err) {
      const error = err as ApiError;
      if ((error as Error).name === 'AbortError') {
        wasCancelled = true;
      } else {
        console.error('发送消息失败:', error);
        toast.error('发送消息失败，请重试');
        if (chatMode === 'deep_research' && currentProgressId) {
          setProgressData((prev) =>
            prev
              ? { ...prev, status: 'error', error: error.message }
              : { status: 'error', updates: [], error: error.message, final_trace: null }
          );
        }
      }
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
      currentRequestIdRef.current = null;
      setIsLoading(false);

      if (wasCancelled) {
        if (!cancelTriggeredRef.current) {
          toast.success('已停止当前回答');
        }
        if (currentProgressId) {
          setProgressData((prev) =>
            prev
              ? { ...prev, status: 'cancelled' }
              : { status: 'cancelled', updates: [], final_trace: null, error: null }
          );
          if (progressPollerRef.current) {
            clearInterval(progressPollerRef.current);
            progressPollerRef.current = null;
          }
        }
      }
      cancelTriggeredRef.current = false;
    }
  };

  const handleStop = async () => {
    if (!isLoading) return;

    cancelTriggeredRef.current = true;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    const payload: Record<string, string> = {};
    if (currentRequestIdRef.current) {
      payload.request_id = currentRequestIdRef.current;
    }
    const progressToken = activeProgressIdRef.current || progressId;
    if (progressToken) {
      payload.progress_id = progressToken;
    }

    if (Object.keys(payload).length > 0) {
      try {
        await fetch('/api/v1/chat/cancel', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });
      } catch (error) {
        console.warn('取消请求失败:', error);
      }
    }

    if (progressToken) {
      setProgressData((prev) =>
        prev
          ? { ...prev, status: 'cancelled' }
          : { status: 'cancelled', updates: [], final_trace: null, error: null }
      );
      if (progressPollerRef.current) {
        clearInterval(progressPollerRef.current);
        progressPollerRef.current = null;
      }
      activeProgressIdRef.current = null;
    }

    setIsLoading(false);
    toast.success('已停止当前回答');
  };



  const openAnalysisEditor = (messageIndex: number, code: string, language: 'python' | 'r', groupId?: string) => {
    setAnalysisEditor({
      open: true,
      code,
      language,
      messageIndex,
      groupId,
    })
  }

  const runAnalysisFromMessage = async (params: { messageIndex: number; code: string; language: 'python' | 'r'; groupId?: string; instruction?: string }) => {
    const { messageIndex, code, language, groupId, instruction } = params
    if (!ensureCloudConfigReady()) {
      return
    }
    if (!groupId) {
      toast.error('缺少用于运行的知识组信息');
      return;
    }

    const valid = await validateAnalysisGroup(groupId, true)
    if (!valid) {
      toast.error('所选知识组未通过校验，无法运行代码');
      return;
    }

    setAnalysisRunLoading((prev) => ({ ...prev, [messageIndex]: true }))
    const requestId = typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

    try {
      const payload: Record<string, any> = {
        message: instruction || '运行数据分析代码',
        llm_type: llmType,
        mode: 'data_analysis',
        request_id: requestId,
        model_source: modelSource,
        analysis_language: language,
        analysis_action: 'run',
        analysis_code: code,
        analysis_knowledge_group_id: groupId,
        enable_rag: false,
        enable_web_search: false,
      }

      if (isCloudModel) {
        payload.cloud_config = {
          preset: cloudPreset,
          api_key: cloudConfig.apiKey.trim() || undefined,
          base_url: cloudConfig.baseUrl.trim() || undefined,
          general_model: cloudConfig.generalModel.trim() || undefined,
          reasoning_model: cloudConfig.reasoningModel.trim() || undefined,
        }
      }

      const response = await fetch('/api/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(errorText || '运行代码失败')
      }

      const data = await response.json()
      console.log('运行代码返回的数据:', data)
      console.log('analysis对象:', data.analysis)
      console.log('knowledge_group_id:', data.analysis?.knowledge_group_id)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant' as const,
          content: data.response,
          analysis: data.analysis,
        },
      ])
    } catch (error) {
      const err = error as Error
      console.error('运行代码失败:', err)
      toast.error(`运行代码失败：${err.message}`)
    } finally {
      setAnalysisRunLoading((prev) => {
        const next = { ...prev }
        delete next[messageIndex]
        return next
      })
      setAnalysisEditor((prev) => ({ ...prev, open: false }))
    }
  }


  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const toggleRecording = () => {
    handleVoiceRecord();
  }

  const clearChat = async () => {
    try {
      const response = await fetch('/api/v1/chat/clear-history', {
        method: 'POST',
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || '清空会话失败');
      }

      setMessages([{ ...INITIAL_ASSISTANT_MESSAGE }]);
      setWorkflowTrace(null);
      setProgressId(null);
      setProgressData(null);
      if (progressPollerRef.current) {
        clearInterval(progressPollerRef.current);
        progressPollerRef.current = null;
      }
      toast.success('会话历史已清空');
    } catch (err) {
      const error = err as ApiError;
      console.error('清空聊天失败:', error);
      toast.error('清空聊天失败: ' + error.message);
    }
  }

  // 播放语音
  const playText = async (text: string) => {
    try {
      // 使用中等超时（1分钟）用于文字转语音
      const response = await fetchWithTimeout(
        '/api/v1/text-to-speech',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            text,
            rate: "+0%",
            volume: "+0%"
          }),
        },
        TIMEOUT.MEDIUM
      );

      if (!response.ok) {
        const error = await response.text();
        throw new Error(error);
      }

      const blob = await response.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      await audio.play();
    } catch (error) {
      console.error('语音播放失败:', error);
      toast.error('语音播放失败，请重试');
    }
  };

  // 在 ChatPage 组件中添加文件上传处理函数
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', file.name);

      const response = await fetch('/api/v1/documents/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('文件上传失败');
      }

      const data = await response.json();
      if (data.status === 'success') {
        toast.success('文件上传成功！');
      } else {
        throw new Error(data.message);
      }
    } catch (err) {
      const error = err as ApiError;
      console.error('上传错误:', error);
      toast.error('文件上传失败: ' + error.message);
    }
  };

  const handleReferenceDownload = (reference: MessageReference) => {
    if (!reference.filename) {
      toast.error('该参考资料暂无关联的文件');
      return;
    }
    // 构建URL时添加library_type参数
    const libraryType = reference.library_type || 'public';
    const url = `/api/v1/documents/${encodeURIComponent(reference.filename)}/download?library_type=${libraryType}`;
    window.open(url, '_blank');
  };

  const openReferencePreview = async (reference: MessageReference) => {
    if (!reference.filename) {
      toast.error('该参考资料暂无关联的文件');
      return;
    }

    setReferencePreview({
      open: true,
      loading: true,
      title: reference.title || reference.filename,
      content: '',
      filename: reference.filename,
    });

    try {
      // 添加library_type参数，使用长超时（3分钟）用于大文档预览
      const libraryType = reference.library_type || 'public';
      const response = await fetchWithTimeout(
        `/api/v1/documents/${encodeURIComponent(reference.filename)}/preview?max_chars=1500&library_type=${libraryType}`,
        {},
        TIMEOUT.LONG
      );
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const data = await response.json();
      setReferencePreview((prev) => ({
        ...prev,
        loading: false,
        content: data.data?.preview || '暂无预览内容',
      }));
    } catch (error) {
      const err = error as Error;
      toast.error(`获取文档预览失败：${err.message}`);
      setReferencePreview({
        open: false,
        loading: false,
        title: '',
        content: '',
        filename: undefined,
      });
    }
  };

  const closeReferencePreview = () => {
    setReferencePreview({
      open: false,
      loading: false,
      title: '',
      content: '',
      filename: undefined,
    });
  };

  return (
    <MainLayout>
      <div className="gradient-bg min-h-screen">
        <div className="max-w-6xl mx-auto p-4">
          <Toaster position="top-center" />
          
          {/* 聊天头部 */}
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white/80 backdrop-blur-sm rounded-2xl px-6 py-4 mb-4 border border-gray-100"
          >
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div>
                <h1 className="text-2xl font-semibold text-gray-900 bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-blue-800">
                  智能AI助手
                </h1>
                <p className="mt-1 text-sm text-gray-500">
                  融合大模型技术，通过智能问答为您提供城市治理科研全流程辅助
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-4">
                {/* 模式选择 */}
                <div className="flex items-center space-x-2">
                  <span className="text-sm text-gray-600">模式选择</span>
                  <select
                    value={chatMode}
                    onChange={(e) => setChatMode(e.target.value as ChatMode)}
                    className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm bg-white/50 backdrop-blur-sm"
                  >
                    {MODE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* 模型来源 */}
                <div className="flex items-center space-x-2">
                  <span className="text-sm text-gray-600">模型来源</span>
                  <select
                    value={modelSource}
                    onChange={(e) => handleModelSourceChange(e.target.value as ModelSource)}
                    className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm bg-white/50 backdrop-blur-sm"
                  >
                    {MODEL_SOURCE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value} disabled={option.disabled}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>

                {isCloudModel && (
                  <div className="flex items-center space-x-2">
                    <span className="text-sm text-gray-600">模型预设</span>
                    <select
                      value={cloudPreset}
                      onChange={(e) => handlePresetChange(e.target.value as CloudPresetKey)}
                      className="rounded-lg border border-gray-200 px-3 py-1.5 text-sm bg-white/50 backdrop-blur-sm"
                    >
                      {CLOUD_MODEL_PRESET_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {/* 清空聊天按钮 */}
                <button
                  onClick={clearChat}
                  className="p-2 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors"
                  title="清空聊天"
                >
                  <RotateCcw className="h-5 w-5" />
                </button>
              </div>

              {isCloudModel && (
                <>
                  {/* 折叠/展开按钮 */}
                  <button
                    onClick={() => setShowCloudConfig(!showCloudConfig)}
                    className="mt-4 flex items-center gap-2 text-sm text-blue-600 hover:text-blue-700 transition-colors"
                  >
                    {showCloudConfig ? (
                      <>
                        <ChevronUp className="h-4 w-4" />
                        <span>收起云端模型配置</span>
                      </>
                    ) : (
                      <>
                        <ChevronDown className="h-4 w-4" />
                        <span>展开云端模型配置</span>
                      </>
                    )}
                  </button>

                  <AnimatePresence>
                    {showCloudConfig && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div
                          className={`mt-4 grid gap-4 ${
                            chatMode === 'deep_research' ? 'lg:grid-cols-3' : 'lg:grid-cols-2'
                          }`}
                        >
                          <div className="space-y-3">
                            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                              <label className="text-xs font-medium text-gray-600 sm:w-28 sm:text-right whitespace-nowrap">
                                API KEY
                              </label>
                              <div className="flex flex-1 items-center gap-2">
                                <input
                                  type={showApiKey ? 'text' : 'password'}
                                  value={cloudConfig.apiKey}
                                  onChange={(e) =>
                                    setCloudConfig((prev) => ({ ...prev, apiKey: e.target.value }))
                                  }
                                  placeholder="请输入云端 API KEY"
                                  className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm bg-white/60 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                <button
                                  type="button"
                                  onClick={() => setShowApiKey((prev) => !prev)}
                                  className="p-2 text-gray-500 hover:text-blue-600 transition-colors"
                                  title={showApiKey ? '隐藏 API KEY' : '显示 API KEY'}
                                >
                                  {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                              </div>
                            </div>
                            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                              <label className="text-xs font-medium text-gray-600 sm:w-28 sm:text-right whitespace-nowrap">
                                Base URL
                              </label>
                              <div className="flex flex-1 items-center gap-2">
                                <input
                                  type={showBaseUrl ? 'text' : 'password'}
                                  value={cloudConfig.baseUrl}
                                  onChange={(e) =>
                                    setCloudConfig((prev) => ({ ...prev, baseUrl: e.target.value }))
                                  }
                                  placeholder="https://..."
                                  className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm bg-white/60 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                <button
                                  type="button"
                                  onClick={() => setShowBaseUrl((prev) => !prev)}
                                  className="p-2 text-gray-500 hover:text-blue-600 transition-colors"
                                  title={showBaseUrl ? '隐藏 Base URL' : '显示 Base URL'}
                                >
                                  {showBaseUrl ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                </button>
                              </div>
                            </div>
                          </div>

                          <div className="space-y-3">
                            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                              <label className="text-xs font-medium text-gray-600 sm:w-28 sm:text-right whitespace-nowrap">
                                回答模型
                              </label>
                              <div className="flex-1 flex flex-col gap-1">
                                <input
                                  type="text"
                                  value={cloudConfig.generalModel}
                                  onChange={(e) =>
                                    setCloudConfig((prev) => ({ ...prev, generalModel: e.target.value }))
                                  }
                                  placeholder="如 deepseek-chat"
                                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm bg-white/60 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                {chatMode === 'data_analysis' && cloudPreset === 'qwen' && (
                                  <p className="text-xs text-amber-600 flex items-center gap-1">
                                    <span className="font-medium">💡</span>
                                    <span>建议使用 qwen-plus 模型以获得更好效果</span>
                                  </p>
                                )}
                              </div>
                            </div>
                            {chatMode === 'deep_research' && (
                              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                                <label className="text-xs font-medium text-gray-600 sm:w-28 sm:text-right whitespace-nowrap">
                                  决策模型
                                </label>
                                <input
                                  type="text"
                                  value={cloudConfig.reasoningModel}
                                  onChange={(e) =>
                                    setCloudConfig((prev) => ({
                                      ...prev,
                                      reasoningModel: e.target.value,
                                    }))
                                  }
                                  placeholder="如 qwq-plus"
                                  className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm bg-white/60 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                              </div>
                            )}
                          </div>

                          {chatMode === 'deep_research' && (
                            <div className="space-y-3">
                              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                                <label className="text-xs font-medium text-gray-600 sm:w-28 sm:text-right whitespace-nowrap">
                                  最大迭代次数
                                </label>
                                <input
                                  type="number"
                                  min={1}
                                  value={maxIterations}
                                  onChange={(e) => {
                                    const numeric = Number(e.target.value)
                                    setMaxIterations(Number.isNaN(numeric) ? 1 : Math.max(numeric, 1))
                                  }}
                                  className="flex-1 sm:flex-none sm:w-28 max-w-[160px] rounded-lg border border-gray-200 px-3 py-2 text-sm bg-white/60 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                              </div>
                            </div>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </>
              )}
            </div>
          </motion.div>

          {/* 聊天内容区 */}
          <div className={`grid gap-4 mb-4 ${chatMode === 'deep_research' ? 'lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]' : ''}`}>
            <div className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 h-[calc(100vh-280px)] overflow-auto">
              <AnimatePresence>
                {messages.map((msg, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                    className={`flex items-start space-x-3 mb-6 ${msg.role === 'user' ? 'justify-end' : ''}`}
                  >
                    {msg.role === 'assistant' && (
                      <div className="w-8 h-8 rounded-md bg-[#F9ECEC] flex items-center justify-center flex-shrink-0 overflow-hidden border border-[#E0E4E8]">
                        <img src="/logo.jpg" alt="SDU" className="w-5 h-5 object-contain" />
                      </div>
                    )}
                    
                    <div className={`flex-1 max-w-[80%] space-y-2 ${msg.role === 'user' ? 'ml-auto' : ''}`}>
                      {/* 对于助手消息，如果没有analysis或者是直接回答，显示普通回复框 */}
                      {!(msg.role === 'assistant' && msg.analysis) && (
                        <div className={`
                          rounded-2xl shadow-sm p-4
                          ${msg.role === 'user'
                            ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white'
                            : 'bg-gradient-to-br from-gray-50 to-white text-gray-700 border border-gray-100'}
                        `}>
                          <ReactMarkdown
                            className="text-sm leading-relaxed break-words"
                            components={markdownComponents}
                            remarkPlugins={[remarkGfm]}
                            rehypePlugins={[rehypeRaw]}
                          >
                            {preprocessCitations(safeFormatContent(msg.content), msg.citation_map)}
                          </ReactMarkdown>
                        </div>
                      )}

                      {/* Citation chips for assistant messages with references */}
                      {msg.role === 'assistant' && msg.references && msg.references.length > 0 && (() => {
                        const docRefs = msg.references.filter((r: any) => r.type !== 'web_search')
                        if (docRefs.length === 0) return null
                        const uniqueDocs = docRefs.reduce((acc: any[], r: any) => {
                          if (!acc.find(a => a.filename === r.filename)) acc.push(r)
                          return acc
                        }, [])
                        return (
                          <div className="flex flex-wrap gap-1.5 mt-1">
                            {uniqueDocs.slice(0, 5).map((ref: any, ci: number) => (
                              <button
                                key={ci}
                                onClick={() => {
                                  setExpandedReferences(prev => {
                                    const next = new Set(prev)
                                    if (next.has(index)) next.delete(index)
                                    else next.add(index)
                                    return next
                                  })
                                }}
                                className="group relative inline-flex items-center gap-1 px-2 py-1 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg text-xs text-blue-700 transition-colors"
                                title={ref.content?.slice(0, 200) || ''}
                              >
                                <Book className="w-3 h-3" />
                                <span className="max-w-[120px] truncate">{ref.title || ref.filename || `来源${ci + 1}`}</span>
                                {/* Hover tooltip */}
                                <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-50 pointer-events-none">
                                  <div className="bg-gray-900 text-white text-xs rounded-lg p-3 w-72 shadow-xl">
                                    <p className="font-medium mb-1 text-blue-300">{ref.title || ref.filename}</p>
                                    <p className="text-gray-300 leading-relaxed line-clamp-4">{ref.content?.slice(0, 300)}</p>
                                    <p className="text-gray-500 mt-1">点击查看详情</p>
                                  </div>
                                </div>
                              </button>
                            ))}
                            {(msg.references?.filter((r: any) => r.type === 'web_search').length || 0) > 0 && (
                              <button
                                onClick={() => {
                                  setExpandedReferences(prev => {
                                    const next = new Set(prev)
                                    if (next.has(index)) next.delete(index)
                                    else next.add(index)
                                    return next
                                  })
                                }}
                                className="inline-flex items-center gap-1 px-2 py-1 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-lg text-xs text-emerald-700 transition-colors"
                              >
                                <Globe className="w-3 h-3" />
                                网页来源
                              </button>
                            )}
                          </div>
                        )
                      })()}

                      {/* 数据分析相关显示 - 只在有analysis时显示 */}
                      {msg.analysis && (
                        <div className="rounded-xl border border-blue-100 bg-blue-50/60 p-3 space-y-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2 text-sm font-medium text-blue-700">
                              <Database className="h-4 w-4" />
                              <span>{msg.analysis.action === 'run' ? '运行结果' : '生成的分析代码'}</span>
                              <span className="px-2 py-0.5 rounded-full border border-blue-200 bg-white text-xs text-blue-700">
                                {msg.analysis.language.toUpperCase()}
                              </span>
                            </div>
                            {msg.analysis.knowledge_group_id && (
                              <span className="text-xs text-gray-600">
                                知识组：{knowledgeGroups.find(g => g.id === msg.analysis?.knowledge_group_id)?.name || msg.analysis.knowledge_group_id}
                              </span>
                            )}
                          </div>

                          {/* 代码生成时显示简洁的描述提示 */}
                          {msg.analysis.action === 'generate' && (
                            <div className="text-xs text-gray-600 bg-white/50 rounded px-3 py-2">
                              💡 <span className="font-medium">代码说明：</span>
                              {msg.analysis.description || '已根据您的需求生成可运行的分析代码'}
                            </div>
                          )}

                          {/* 代码运行时显示详细的执行结果 */}
                          {msg.analysis.action === 'run' && msg.analysis.run_result && (
                            <div className="space-y-2">
                              {/* LLM智能解释 - 优先显示 */}
                              {msg.analysis.run_result.interpretation && (
                                <div className="rounded-lg bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 p-3">
                                  <div className="flex items-center gap-2 text-xs font-semibold text-blue-700 mb-2">
                                    <span>🤖</span>
                                    <span>智能解释</span>
                                  </div>
                                  <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                                    {msg.analysis.run_result.interpretation}
                                  </div>
                                </div>
                              )}

                              {/* 运行结果详情 */}
                              <div className="rounded-lg bg-white border border-gray-200 p-3 space-y-2">
                                <div className="flex items-center gap-2 text-xs font-medium">
                                  <span className={`inline-block w-2 h-2 rounded-full ${msg.analysis.run_result.exit_code === 0 ? 'bg-green-500' : 'bg-red-500'}`}></span>
                                  <span className={msg.analysis.run_result.exit_code === 0 ? 'text-green-700' : 'text-red-700'}>
                                    {msg.analysis.run_result.exit_code === 0 ? '✓ 运行成功' : '✗ 运行失败'}
                                  </span>
                                  <span className="text-gray-400 ml-auto">退出码: {msg.analysis.run_result.exit_code ?? 'N/A'}</span>
                                </div>
                                {msg.analysis.run_result.stdout && (
                                  <div className="text-xs">
                                    <div className="flex items-center gap-1 text-gray-600 mb-1 font-medium">
                                      <span>📤</span>
                                      <span>标准输出：</span>
                                    </div>
                                    <pre className="text-gray-800 whitespace-pre-wrap overflow-auto max-h-60 bg-gray-50 border border-gray-100 rounded p-2 font-mono text-[11px]">{msg.analysis.run_result.stdout}</pre>
                                  </div>
                                )}
                                {msg.analysis.run_result.stderr && msg.analysis.run_result.stderr.trim() && (
                                  <div className="text-xs">
                                    <div className="flex items-center gap-1 text-red-600 mb-1 font-medium">
                                      <span>⚠️</span>
                                      <span>错误输出：</span>
                                    </div>
                                    <pre className="text-red-700 whitespace-pre-wrap overflow-auto max-h-40 bg-red-50 border border-red-100 rounded p-2 font-mono text-[11px]">{msg.analysis.run_result.stderr}</pre>
                                  </div>
                                )}
                                {msg.analysis.run_result.summary && (
                                  <div className="text-[11px] text-gray-500 border-t border-gray-100 pt-2">
                                    {msg.analysis.run_result.summary}
                                  </div>
                                )}
                              </div>

                              {/* 生成的图片预览 */}
                              {msg.analysis.run_result.generated_images && msg.analysis.run_result.generated_images.length > 0 && (() => {
                                // 获取知识组ID，优先使用analysis中的，否则使用当前选中的
                                const groupId = msg.analysis.knowledge_group_id || analysisGroupId;
                                console.log('图片显示调试信息:', {
                                  'msg.analysis.knowledge_group_id': msg.analysis.knowledge_group_id,
                                  'analysisGroupId': analysisGroupId,
                                  'groupId': groupId,
                                  'generated_images': msg.analysis.run_result.generated_images
                                });
                                if (!groupId) {
                                  return (
                                    <div className="text-xs text-amber-600 bg-amber-50 rounded p-2">
                                      ⚠️ 无法加载图片：缺少知识组信息
                                    </div>
                                  );
                                }
                                return (
                                  <div className="space-y-2">
                                    <div className="text-xs font-medium text-gray-700 flex items-center gap-2">
                                      <span>🖼️</span>
                                      <span>生成的图表 ({msg.analysis.run_result.generated_images.length})</span>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                      {msg.analysis.run_result.generated_images.map((image, imgIdx) => {
                                        // 添加时间戳参数防止浏览器缓存
                                        const timestamp = Date.now();
                                        const imageUrl = `/api/v1/chat/image-preview/${groupId}/${encodeURIComponent(image.filename)}?t=${timestamp}`;
                                        console.log('构建图片URL:', imageUrl);
                                        return (
                                          <div key={`image-${imgIdx}`} className="rounded-lg border border-gray-200 bg-white p-2 space-y-2">
                                            <div className="text-xs text-gray-600 font-medium truncate" title={image.filename}>
                                              {image.filename}
                                            </div>
                                            <div className="relative bg-gray-50 rounded overflow-hidden">
                                              <img
                                                src={imageUrl}
                                                alt={image.filename}
                                                className="w-full h-auto max-h-96 object-contain"
                                                onError={(e) => {
                                                  console.error('图片加载失败:', imageUrl);
                                                  (e.target as HTMLImageElement).src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><text x="50%" y="50%" text-anchor="middle" fill="gray">加载失败</text></svg>';
                                                }}
                                              />
                                            </div>
                                            <div className="flex items-center justify-between text-[11px] text-gray-500">
                                              <span>{(image.size / 1024).toFixed(1)} KB</span>
                                              <a
                                                href={imageUrl}
                                                download={image.filename}
                                                className="text-blue-600 hover:text-blue-700 hover:underline"
                                              >
                                                下载
                                              </a>
                                            </div>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  </div>
                                );
                              })()}
                            </div>
                          )}

                          {msg.analysis.data_files && msg.analysis.data_files.length > 0 && (
                            <div className="text-[11px] text-gray-600">
                              📊 数据文件：{msg.analysis.data_files.slice(0, 3).map(f => f.filename).join('、')}
                              {msg.analysis.data_files.length > 3 && ' 等'}
                            </div>
                          )}

                          {/* 显示代码和操作按钮 */}
                          {msg.analysis.code && (
                            <>
                              <div className="rounded-lg bg-white border border-gray-100 p-3">
                                <div className="text-xs font-medium text-gray-600 mb-2">
                                  {msg.analysis.action === 'run' ? '📝 已运行的代码' : '📝 可运行代码'}
                                </div>
                                <pre className="text-xs text-gray-800 whitespace-pre-wrap overflow-auto max-h-80">{msg.analysis.code}</pre>
                              </div>

                              {/* 只在生成阶段显示操作按钮，运行后不显示（避免重复运行） */}
                              {msg.analysis.action === 'generate' && (
                                <div className="flex flex-wrap gap-2">
                                  <button
                                    onClick={() => runAnalysisFromMessage({
                                      messageIndex: index,
                                      code: msg.analysis?.code || '',
                                      language: msg.analysis?.language || 'python',
                                      groupId: msg.analysis?.knowledge_group_id || analysisGroupId,
                                      instruction: msg.analysis?.instruction || msg.content,
                                    })}
                                    disabled={analysisRunLoading[index]}
                                    className="px-3 py-2 rounded-lg text-sm bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 flex items-center gap-2"
                                  >
                                    {analysisRunLoading[index] ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                                    运行代码
                                  </button>
                                  <button
                                    onClick={() => openAnalysisEditor(index, msg.analysis?.code || '', msg.analysis?.language || 'python', msg.analysis?.knowledge_group_id)}
                                    className="px-3 py-2 rounded-lg text-sm border border-gray-200 text-gray-700 hover:border-blue-300"
                                  >
                                    修订后运行
                                  </button>
                                </div>
                              )}

                              {/* 运行后也显示修订按钮，允许用户修改代码重新运行 */}
                              {msg.analysis.action === 'run' && (
                                <div className="flex flex-wrap gap-2">
                                  <button
                                    onClick={() => openAnalysisEditor(index, msg.analysis?.code || '', msg.analysis?.language || 'python', msg.analysis?.knowledge_group_id)}
                                    className="px-3 py-2 rounded-lg text-sm bg-blue-600 text-white hover:bg-blue-700 flex items-center gap-2"
                                  >
                                    <Play className="h-4 w-4" />
                                    修改并重新运行
                                  </button>
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      )}

                      {/* 文档/网页引用 - 可折叠，按文档分组 */}
                      {msg.references && msg.references.length > 0 && (() => {
                        const groupedDocs = groupReferencesByDocument(msg.references);
                        return (
                          <div className="bg-blue-50/80 backdrop-blur-sm rounded-xl border border-blue-100">
                            {/* 折叠/展开头部 */}
                            <button
                              onClick={() => toggleReferences(index)}
                              className="w-full flex items-center justify-between px-4 py-3 text-sm text-blue-600 hover:bg-blue-100/50 transition-colors rounded-t-xl"
                            >
                              <div className="flex items-center space-x-2">
                                <Book className="h-4 w-4" />
                                <span className="font-medium">
                                  相关资料引用 ({groupedDocs.length} 个来源，{msg.references.length} 个片段)
                                </span>
                              </div>
                              {expandedReferences.has(index) ? (
                                <ChevronUp className="h-4 w-4" />
                              ) : (
                                <ChevronDown className="h-4 w-4" />
                              )}
                            </button>

                            {/* 引用内容 - 可展开 */}
                            <AnimatePresence>
                              {expandedReferences.has(index) && (
                                <motion.div
                                  initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: 'auto', opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  transition={{ duration: 0.2 }}
                                  className="overflow-hidden"
                                >
                                  <div className="px-4 pb-4 space-y-3">
                                    {groupedDocs.map((doc, docIdx) => (
                                      <div
                                        key={`${doc.key}-${docIdx}`}
                                        className="rounded-lg bg-white border border-blue-100/60 px-3 py-3 text-sm shadow-sm"
                                      >
                                        {/* 网页引用 */}
                                        {doc.isWeb && (
                                          <>
                                            <div className="flex items-start gap-2 mb-2">
                                              <Globe className="h-4 w-4 text-emerald-600 mt-0.5 flex-shrink-0" />
                                              <div className="flex-1 min-w-0">
                                                {doc.url ? (
                                                  <a
                                                    href={doc.url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="font-medium text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1 break-words"
                                                  >
                                                    <span>{doc.title}</span>
                                                    <ExternalLink className="h-3 w-3 flex-shrink-0" />
                                                  </a>
                                                ) : (
                                                  <p className="font-medium text-gray-900">{doc.title}</p>
                                                )}
                                                {doc.url && (
                                                  <p className="text-xs text-gray-500 mt-0.5 truncate" title={doc.url}>
                                                    {doc.url}
                                                  </p>
                                                )}
                                              </div>
                                            </div>
                                            <p className="text-gray-600 whitespace-pre-wrap leading-relaxed">
                                              {doc.chunks[0].content}
                                            </p>
                                          </>
                                        )}

                                        {/* 文档引用 */}
                                        {!doc.isWeb && (
                                          <>
                                            <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                                              <div className="flex-1">
                                                {/* 来源标签和分类 */}
                                                <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                                                  {doc.library_type === 'public' && (
                                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 text-xs">
                                                      <Database className="h-3 w-3" />
                                                      公共库
                                                    </span>
                                                  )}
                                                  {doc.library_type === 'private' && (
                                                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 text-xs">
                                                      <Lock className="h-3 w-3" />
                                                      {doc.knowledge_group_name || '私人库'}
                                                    </span>
                                                  )}
                                                  {doc.category && (
                                                    <span className="inline-flex items-center rounded-full bg-purple-100 px-2 py-0.5 text-purple-700 text-xs">
                                                      {doc.category}
                                                    </span>
                                                  )}
                                                </div>
                                                <p className="font-medium text-gray-900">{doc.title}</p>
                                                {doc.filename && (
                                                  <p className="text-xs text-gray-500 mt-0.5">
                                                    文件：{doc.filename}
                                                  </p>
                                                )}
                                                {/* 显示基本信息 */}
                                                <div className="mt-1.5 flex items-center gap-3 text-xs text-gray-500">
                                                  {doc.size && (
                                                    <span>大小: {(doc.size / 1024).toFixed(1)} KB</span>
                                                  )}
                                                  {doc.upload_time && (
                                                    <span>上传: {new Date(doc.upload_time).toLocaleDateString('zh-CN')}</span>
                                                  )}
                                                </div>
                                                {/* 显示额外的metadata */}
                                                <div className="mt-2 space-y-1 text-xs text-gray-600">
                                                  {doc.discipline && (
                                                    <div>学科：{doc.discipline}</div>
                                                  )}
                                                  {doc.region && (
                                                    <div>地区：{doc.region}</div>
                                                  )}
                                                  {doc.main_topic && (
                                                    <div>主题：{doc.main_topic}</div>
                                                  )}
                                                  {doc.document_type && (
                                                    <div>文档类型：{doc.document_type}</div>
                                                  )}
                                                  {doc.effectiveness_level && (
                                                    <div>效力层级：{doc.effectiveness_level}</div>
                                                  )}
                                                </div>
                                              </div>
                                              {doc.filename && (
                                                <div className="flex items-center gap-2">
                                                  <button
                                                    onClick={() => openReferencePreview({
                                                      title: doc.title,
                                                      content: doc.chunks[0].content,
                                                      filename: doc.filename,
                                                      library_type: doc.library_type,
                                                    })}
                                                    className="rounded-md border border-blue-200 px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 transition-colors"
                                                  >
                                                    预览
                                                  </button>
                                                  <button
                                                    onClick={() => handleReferenceDownload({
                                                      title: doc.title,
                                                      content: doc.chunks[0].content,
                                                      filename: doc.filename,
                                                      library_type: doc.library_type,
                                                    })}
                                                    className="rounded-md border border-blue-200 px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 transition-colors"
                                                  >
                                                    下载
                                                  </button>
                                                </div>
                                              )}
                                            </div>

                                            {/* 显示所有片段 */}
                                            <div className="space-y-2">
                                              {doc.chunks.map((chunk, chunkIdx) => (
                                                <div key={`chunk-${chunkIdx}`} className="border-l-2 border-blue-200 pl-3 py-1">
                                                  <div className="flex items-center gap-2 mb-1">
                                                    <span className="text-xs text-gray-500">
                                                      片段 {typeof chunk.chunk_index === 'number' ? chunk.chunk_index + 1 : chunkIdx + 1}
                                                    </span>
                                                    {typeof chunk.score === 'number' && (
                                                      <span className="text-xs text-gray-400">
                                                        (距离: {chunk.score.toFixed(2)})
                                                      </span>
                                                    )}
                                                  </div>
                                                  <p className="text-gray-600 whitespace-pre-wrap leading-relaxed text-xs">
                                                    {chunk.content}
                                                  </p>
                                                </div>
                                              ))}
                                            </div>

                                            {/* 标签 */}
                                            {doc.tags && doc.tags.length > 0 && (
                                              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                                                {doc.tags.map((tag, tagIdx) => (
                                                  <span
                                                    key={`${doc.key}-tag-${tagIdx}`}
                                                    className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-gray-700"
                                                  >
                                                    {tag}
                                                  </span>
                                                ))}
                                              </div>
                                            )}
                                          </>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </motion.div>
                              )}
                            </AnimatePresence>
                          </div>
                        );
                      })()}
                    </div>
  
                    {msg.role === 'user' && (
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-gray-500 to-gray-600 flex items-center justify-center flex-shrink-0">
                        <span className="text-white font-medium text-sm">我</span>
                      </div>
                    )}
                  </motion.div>
                ))}

                {/* 加载状态 */}
                {isLoading && (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex items-start space-x-3"
                  >
                    <div className="w-8 h-8 rounded-md bg-[#F9ECEC] flex items-center justify-center overflow-hidden border border-[#E0E4E8]">
                      <img src="/logo.jpg" alt="SDU" className="w-5 h-5 object-contain" />
                    </div>
                    <div className="bg-white rounded-2xl shadow-sm p-4 flex space-x-2">
                      <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                      <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            {chatMode === 'deep_research' && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-white/60 backdrop-blur-sm rounded-2xl border border-dashed border-gray-200 p-4 text-sm text-gray-700 max-h-[calc(100vh-280px)] overflow-y-auto"
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-gray-800">深度研究动态</h3>
                  <span className="text-[11px] text-gray-400">(实时更新)</span>
                </div>
                {isLoading && (
                  <div className="mb-3 text-xs text-gray-500">正在分析，请稍候…</div>
                )}
                <div className="space-y-3">
                  {progressData?.updates?.length ? (
                    progressData.updates.map((update) => {
                      const statusChips = normalizeStatusChips(update);
                      return (
                        <div key={update.id} className="rounded-xl bg-gray-50 border border-gray-100 p-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold text-gray-800">{update.title}</span>
                          <span className="text-[11px] text-gray-400">{formatTimestamp(update.timestamp)}</span>
                        </div>
                        {update.message && (
                          <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">{update.message}</p>
                        )}
                        {update.phase === 'complexity_decision' && update.data && (
                          <div className="rounded-lg bg-white border border-gray-100 p-2">
                            <div className="text-xs font-semibold text-gray-700">判定结果</div>
                            <div className="text-xs text-gray-500 mt-0.5">等级：{update.data.level === 'complex' ? '复杂问题' : '简单问题'}</div>
                            {/* {update.data.rationale && (
                              <div className="text-xs text-gray-500 mt-0.5">{update.data.rationale}</div>
                            )} */}
                          </div>
                        )}
                        {update.phase === 'plan_generated' && (() => {
                          const planTasks = Array.isArray(update.data?.plan?.tasks)
                            ? update.data.plan.tasks
                            : (Array.isArray(update.data?.task_summaries) ? update.data.task_summaries : null);
                          if (!planTasks || planTasks.length === 0) {
                            return null;
                          }
                          return (
                            <div className="space-y-2">
                              {planTasks.map((task: PlanTaskTrace, idx: number) => (
                                <div key={`plan-task-${idx}`} className="rounded-lg bg-white border border-gray-100 p-3">
                                  <div className="text-[11px] text-gray-400">任务 {idx + 1}</div>
                                  <div className="text-sm font-semibold text-gray-800">{task.task_name}</div>
                                  {task.objective && (
                                    <div className="text-xs text-gray-500 mt-1">{task.objective}</div>
                                  )}
                                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-400">
                                    {task.requires_vector_search && (
                                      <span className="px-2 py-0.5 bg-blue-50 border border-blue-100 rounded-full">文档检索</span>
                                    )}
                                    {task.requires_tool && (
                                      <span className="px-2 py-0.5 bg-amber-50 border border-amber-100 rounded-full">外部工具</span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          );
                        })()}
                        {update.phase === 'plan_approved' && (() => {
                          const planTasks = Array.isArray(update.data?.plan?.tasks)
                            ? update.data.plan.tasks
                            : (Array.isArray(update.data?.task_summaries) ? update.data.task_summaries : null);
                          if (!planTasks || planTasks.length === 0) {
                            return null;
                          }
                          return (
                            <div className="space-y-2">
                              <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-2 mb-2">
                                <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700">
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                                  </svg>
                                  <span>用户已确认</span>
                                </div>
                              </div>
                              {planTasks.map((task: PlanTaskTrace, idx: number) => (
                                <div key={`approved-task-${idx}`} className="rounded-lg bg-white border border-gray-100 p-3">
                                  <div className="text-[11px] text-gray-400">任务 {idx + 1}</div>
                                  <div className="text-sm font-semibold text-gray-800">{task.task_name}</div>
                                  {task.objective && (
                                    <div className="text-xs text-gray-500 mt-1">{task.objective}</div>
                                  )}
                                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-400">
                                    {task.requires_vector_search && (
                                      <span className="px-2 py-0.5 bg-blue-50 border border-blue-100 rounded-full">文档检索</span>
                                    )}
                                    {task.requires_tool && (
                                      <span className="px-2 py-0.5 bg-amber-50 border border-amber-100 rounded-full">外部工具</span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          );
                        })()}
                        {update.phase === 'plan_timeout' && (() => {
                          const planTasks = Array.isArray(update.data?.plan?.tasks)
                            ? update.data.plan.tasks
                            : (Array.isArray(update.data?.task_summaries) ? update.data.task_summaries : null);
                          if (!planTasks || planTasks.length === 0) {
                            return null;
                          }
                          return (
                            <div className="space-y-2">
                              <div className="rounded-lg bg-amber-50 border border-amber-200 p-2 mb-2">
                                <div className="flex items-center gap-2 text-xs font-semibold text-amber-700">
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                                  </svg>
                                  <span>使用原始计划（等待超时）</span>
                                </div>
                              </div>
                              {planTasks.map((task: PlanTaskTrace, idx: number) => (
                                <div key={`timeout-task-${idx}`} className="rounded-lg bg-white border border-gray-100 p-3">
                                  <div className="text-[11px] text-gray-400">任务 {idx + 1}</div>
                                  <div className="text-sm font-semibold text-gray-800">{task.task_name}</div>
                                  {task.objective && (
                                    <div className="text-xs text-gray-500 mt-1">{task.objective}</div>
                                  )}
                                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-400">
                                    {task.requires_vector_search && (
                                      <span className="px-2 py-0.5 bg-blue-50 border border-blue-100 rounded-full">文档检索</span>
                                    )}
                                    {task.requires_tool && (
                                      <span className="px-2 py-0.5 bg-amber-50 border border-amber-100 rounded-full">外部工具</span>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          );
                        })()}
                        {update.phase === 'task_completed' && update.data?.task && (
                          <>
                            {statusChips.length > 0 && (
                              <div className="flex flex-wrap gap-2">
                                {statusChips.map((chip, chipIdx) => {
                                  const palette = STATUS_CATEGORY_STYLES[chip.category] || STATUS_CATEGORY_STYLES.document;
                                  const colorClass = palette[chip.state] || palette.muted;
                                  return (
                                    <span
                                      key={`status-chip-${chipIdx}`}
                                      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-medium ${colorClass}`}
                                    >
                                      {chip.text}
                                    </span>
                                  );
                                })}
                              </div>
                            )}
                            <div className="space-y-2">
                              <div className="rounded-lg bg-white border border-gray-100 p-2">
                                <div className="text-xs font-semibold text-gray-700">任务描述</div>
                                <div className="text-xs text-gray-500 mt-0.5 whitespace-pre-wrap">{update.data.task.objective}</div>
                              </div>
                              {update.data.references_used && update.data.references_used.length > 0 && (
                                <div className="rounded-lg bg-white border border-gray-100 p-2">
                                  <div className="text-xs font-semibold text-gray-700">文档引用</div>
                                  <div className="mt-1 space-y-1 text-[11px] text-gray-500">
                                    {update.data.references_used.map((ref: WorkflowReference, refIdx: number) => (
                                      <div key={`task-ref-${refIdx}`} className="flex items-start">
                                        <span className="mt-0.5 mr-1 text-gray-400">•</span>
                                        <div>
                                          <span className="font-medium text-gray-600">{ref.source}</span>
                                          {ref.content && <span className="ml-1">{ref.content}</span>}
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          </>
                        )}
                        {update.phase === 'iteration_decision' && update.data?.decision && (
                          <>
                            {update.data.synthesis && (
                              <div className="rounded-lg bg-white border border-gray-100 p-3">
                                <div className="text-xs font-semibold text-gray-700">本轮综合结论</div>
                                <div className="mt-1 text-xs text-gray-500 leading-relaxed whitespace-pre-wrap">
                                  {update.data.synthesis}
                                </div>
                              </div>
                            )}
                            <div className="mt-2 rounded-lg bg-white border border-gray-100 p-3">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-gray-700">迭代判断</span>
                                <span
                                  className={`text-xs font-medium ${
                                    update.data.decision.status === 'iterate'
                                      ? update.data.iteration_limit_reached
                                        ? 'text-gray-500'
                                        : 'text-orange-500'
                                      : 'text-emerald-600'
                                  }`}
                                >
                                  {update.data.decision.status === 'iterate'
                                    ? update.data.iteration_limit_reached
                                      ? '已达迭代上限，停止迭代'
                                      : '建议继续迭代'
                                    : '无需迭代'}
                                </span>
                              </div>
                              <div className="mt-1 text-xs text-gray-500 leading-relaxed">
                                {update.data.decision.reason}
                              </div>
                              {Array.isArray(update.data.decision.missing_information) &&
                                update.data.decision.missing_information.length > 0 && (
                                  <div className="mt-2 text-[11px] text-gray-500">
                                    <span className="font-medium text-gray-600">待补充信息：</span>
                                    {update.data.decision.missing_information.join('、')}
                                  </div>
                                )}
                              {update.data.iteration_limit_reached && (
                                <div className="mt-2 text-[11px] text-gray-500">
                                  已达到预设的迭代次数上限，本轮将作为最终输出。
                                </div>
                              )}
                            </div>
                          </>
                        )}
                        {/* {update.phase === 'final_response' && (
                          <div className="rounded-lg bg-white border border-gray-100 p-2">
                            <div className="text-xs font-semibold text-gray-700">最终结论</div>
                            <div className="text-xs text-gray-500 mt-0.5 leading-relaxed whitespace-pre-wrap">{update.message}</div>
                          </div>
                        )} */}
                      </div>
                    );
                  })
                  ) : (
                    <div className="rounded-xl bg-gray-50 border border-gray-100 p-3 text-xs text-gray-500">发送问题后会实时展示深度研究进度。</div>
                  )}
                </div>
                {progressData?.status === 'error' && (
                  <div className="mt-3 rounded-xl bg-red-50 border border-red-100 p-3 text-xs text-red-600">
                    {progressData.error || '深度研究过程中出现错误，请稍后重试。'}
                  </div>
                )}
                {progressData?.status === 'cancelled' && (
                  <div className="mt-3 rounded-xl bg-gray-100 border border-gray-200 p-3 text-xs text-gray-600">
                    当前深度研究已被手动中止。
                  </div>
                )}
              </motion.div>
            )}
          </div>

          {/* 输入区域 */}
          <motion.div
              initial={{opacity: 0, y: 20}}
              animate={{opacity: 1, y: 0}}
              className="bg-white/80 backdrop-blur-sm rounded-2xl p-4 border border-gray-100"
          >
            <div className="flex items-center space-x-4">
              {/* 语音输入按钮 */}
              <button
                  onClick={handleVoiceRecord}
                  disabled={isLoading}
                  className={`relative p-2 rounded-lg ${
                      isRecording
                          ? 'bg-red-500 hover:bg-red-600'
                          : 'bg-blue-500 hover:bg-blue-600'
                  } text-white transition-colors disabled:bg-gray-400 disabled:cursor-not-allowed`}
                  title={isRecording ? '停止录音' : '开始录音'}
              >
                {isRecording ? (
                    <>
                      <StopCircle className="w-6 h-6"/>
                      <span
                          className="absolute -top-8 left-1/2 transform -translate-x-1/2 bg-gray-800 text-white text-xs px-2 py-1 rounded">
                      {formatTime(recordingTime)}
                    </span>
                    </>
                ) : (
                    <Mic className="w-6 h-6"/>
                )}
              </button>

              {/* 文件上传按钮 */}
              {/*<input*/}
              {/*    type="file"*/}
              {/*    id="file-upload"*/}
              {/*    className="hidden"*/}
              {/*    onChange={handleFileUpload}*/}
              {/*    accept=".txt,.pdf,.doc,.docx"*/}
              {/*/>*/}
              {/*<button*/}
              {/*    onClick={() => document.getElementById('file-upload')?.click()}*/}
              {/*    className="p-2 rounded-lg hover:bg-gray-100 text-gray-600 transition-colors"*/}
              {/*    title="上传文件"*/}
              {/*>*/}
              {/*  <FileText className="h-5 w-5"/>*/}
              {/*</button>*/}

              {/* 文本输入框 */}
              <div className="flex-1 flex items-center">
                <textarea
                    ref={textareaRef}
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={handleKeyPress}
                    placeholder="输入您的问题..."
                    rows={1}
                    className="w-full px-4 py-2 bg-transparent border border-gray-200 rounded-l-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                    style={{
                      minHeight: '42px',
                      maxHeight: '160px',
                    }}
                />
                <button
                    onClick={isLoading ? handleStop : handleSend}
                    disabled={!isLoading && !message.trim()}
                    className={`
                    px-4 py-2 rounded-r-xl focus:outline-none transition-colors
                    ${isLoading
                        ? 'bg-red-500 text-white hover:bg-red-600 focus:ring-2 focus:ring-red-400'
                        : message.trim()
                            ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white hover:from-blue-600 hover:to-blue-700 focus:ring-2 focus:ring-blue-500'
                            : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    }
                  `}
                    title={isLoading ? '中止正在生成的回复' : '发送消息'}
                >
                  {isLoading ? (
                      <StopCircle className="h-5 w-5" />
                  ) : (
                      <Send className="h-5 w-5"/>
                  )}
                </button>
              </div>
            </div>

            {/* 快捷提示 */}
            <div className="mt-3 flex items-center space-x-2 text-sm">
              <span className="text-gray-500">快捷提问：</span>
              {['科研选题', '文献阅读', '基础写作', '深度研究测试'].map((tip) => (
                  <button
                      key={tip}
                      onClick={() => {
                        if (tip === '文献阅读') {
                          setMessage('请总结这篇城市治理文献的核心观点、方法和不足之处。');
                        } else if (tip === '基础写作') {
                          setMessage('帮我生成一个符合城市治理研究学术规范的论文框架。');
                        } else if (tip === '科研选题') {
                          setMessage('帮我分析当前城市治理研究领域的研究热点和未来趋势。');
                        } else if (tip === '深度研究测试') {
                          setMessage('请为我提供一个复杂的[补充]领域城市治理研究问题，以一段提问的形式给出。');
                        }
                      }}
                      className="px-3 py-1 rounded-full bg-gray-100/80 text-gray-700 hover:bg-gray-200/80 transition-colors"
                  >
                    {tip}
                  </button>
              ))}
            </div>
          </motion.div>

          {chatMode === 'data_analysis' && (
            <motion.div
              initial={{opacity: 0, y: 20}}
              animate={{opacity: 1, y: 0}}
              className="bg-white/80 backdrop-blur-sm rounded-2xl px-6 py-4 mb-4 border border-gray-100"
            >
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Database className="h-4 w-4 text-gray-600" />
                    <span className="text-sm font-medium text-gray-700">数据分析设置</span>
                  </div>
                  <span className="text-xs text-gray-500">请选择编程语言与仅含CSV/Excel的私人知识组</span>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="text-xs font-medium text-gray-600 mb-2">编程语言</div>
                    <div className="flex gap-2">
                      {(['python', 'r'] as Array<'python' | 'r'>).map((lang) => (
                        <button
                          key={lang}
                          onClick={() => setAnalysisLanguage(lang)}
                          className={`px-3 py-2 rounded-lg text-sm border transition-colors ${analysisLanguage === lang ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white border-gray-200 text-gray-700 hover:border-blue-300'}`}
                        >
                          {lang === 'python' ? 'Python' : 'R语言'}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between text-xs font-medium text-gray-600 mb-2">
                      <span>私人知识组</span>
                      <button
                        onClick={() => {
                          setKnowledgeGroupsLoaded(false)
                          setKnowledgeGroups([])
                          loadKnowledgeGroups()
                        }}
                        className="flex items-center gap-1 text-blue-600 hover:text-blue-700"
                      >
                        <RotateCcw className="h-3 w-3" /> 刷新
                      </button>
                    </div>
                    {!knowledgeGroupsLoaded ? (
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <Loader2 className="h-4 w-4 animate-spin" /> 正在加载知识组...
                      </div>
                    ) : knowledgeGroups.length === 0 ? (
                      <div className="text-xs text-gray-500">暂无知识组，请先在文档管理页面创建</div>
                    ) : (
                      <select
                        value={analysisGroupId}
                        onChange={async (e) => {
                          const value = e.target.value
                          setAnalysisGroupId(value)
                          setAnalysisGroupValid(false)
                          setAnalysisDataFiles([])
                          if (value) {
                            await validateAnalysisGroup(value)
                          }
                        }}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm bg-white/60 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        <option value="">请选择私人知识组</option>
                        {knowledgeGroups.map((group) => (
                          <option key={group.id} value={group.id}>
                            {group.name}（{group.document_count} 个文档）
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 text-xs">
                  {analysisGroupChecking && <Loader2 className="h-4 w-4 animate-spin text-blue-600" />}
                  <span className={analysisGroupValid ? 'text-emerald-600' : 'text-amber-600'}>
                    {analysisGroupMessage || '请选择知识组并完成校验后再发送指令'}
                  </span>
                </div>

                {analysisDataFiles.length > 0 && (
                  <div className="rounded-xl bg-gray-50 border border-gray-100 p-3">
                    <div className="text-xs font-medium text-gray-700 mb-2">
                      可用数据文件 ({analysisDataFiles.length})
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      {analysisDataFiles.map((file) => (
                        <div key={file.file_path || file.filename} className="rounded-lg bg-white border border-gray-100 px-3 py-2 text-xs text-gray-700">
                          <div className="font-semibold text-gray-800 truncate">{file.filename}</div>
                          <div className="text-[11px] text-gray-500">
                            {file.file_type?.toUpperCase?.() || file.file_type} {file.file_size ? `· ${(file.file_size / 1024).toFixed(1)} KB` : ''}
                          </div>
                          <div className="text-[11px] text-gray-400 truncate">{file.file_path}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          )}

          {/* RAG检索范围选择器 - 位于输入框下方 */}
          {chatMode !== 'data_analysis' && (
          <motion.div
            initial={{opacity: 0, y: 20}}
            animate={{opacity: 1, y: 0}}
            className="bg-white/80 backdrop-blur-sm rounded-2xl px-6 py-3 mb-4 border border-gray-100"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                {/* RAG检索范围标题 */}
                <Database className="h-4 w-4 text-gray-600" />
                <span className="text-sm font-medium text-gray-700">RAG检索范围</span>
              </div>

              <div className="flex items-center gap-4">
                {/* 知识组选择按钮 */}
                <div className="relative">
                  <button
                    onClick={() => setShowScopePopover(!showScopePopover)}
                    className="rounded-lg border border-gray-200 px-4 py-2 text-sm bg-white hover:bg-gray-50 flex items-center gap-2 transition-colors"
                  >
                    <span className="text-gray-700">{getScopeSummary()}</span>
                    <ChevronDown className="h-4 w-4 text-gray-500" />
                  </button>

                {showScopePopover && (
                  <>
                    {/* 遮罩层，点击关闭下拉框 */}
                    <div
                      className="fixed inset-0 z-[9998]"
                      onClick={() => setShowScopePopover(false)}
                    />
                    <div className="absolute bottom-full mb-2 right-0 z-[9999] w-80 rounded-xl border bg-white shadow-xl p-4 space-y-3">
                      {/* 公共库选项 */}
                      <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={ragScope.includePublic}
                          onChange={(e) => setRagScope({...ragScope, includePublic: e.target.checked})}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <div className="flex-1">
                          <div className="font-medium text-sm">公共知识库</div>
                          <div className="text-xs text-gray-500">所有公共文档</div>
                        </div>
                        <Database className="h-4 w-4 text-blue-500" />
                      </label>

                      {/* 私人库选项 */}
                      <label className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={ragScope.includePrivate}
                          onChange={(e) => setRagScope({...ragScope, includePrivate: e.target.checked})}
                          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <div className="flex-1">
                          <div className="font-medium text-sm">私人知识库（全部）</div>
                          <div className="text-xs text-gray-500">所有私人知识组</div>
                        </div>
                        <Lock className="h-4 w-4 text-amber-500" />
                      </label>

                      {/* 知识组列表 */}
                      <div className="border-t pt-3">
                        <div className="flex items-center justify-between mb-2">
                          <div className="text-xs font-medium text-gray-700">选择特定知识组</div>
                          <button
                            onClick={() => {
                              setKnowledgeGroupsLoaded(false)
                              setKnowledgeGroups([])
                            }}
                            className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1"
                            title="重新加载知识组"
                          >
                            <RotateCcw className="h-3 w-3" />
                            刷新
                          </button>
                        </div>
                        <div className="max-h-48 overflow-y-auto space-y-1">
                          {!knowledgeGroupsLoaded ? (
                            <div className="text-center py-4 text-xs text-gray-500">
                              <Loader2 className="h-4 w-4 animate-spin mx-auto mb-1" />
                              加载中...
                            </div>
                          ) : knowledgeGroups.length === 0 ? (
                            <div className="text-center py-4 text-xs text-gray-500">
                              暂无知识组，请先在文档管理页面创建
                            </div>
                          ) : (
                            knowledgeGroups.map((group) => (
                              <label key={group.id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                                <input
                                  type="checkbox"
                                  checked={ragScope.selectedGroupIds.includes(group.id)}
                                  onChange={(e) => {
                                    const newIds = e.target.checked
                                      ? [...ragScope.selectedGroupIds, group.id]
                                      : ragScope.selectedGroupIds.filter(id => id !== group.id)
                                    setRagScope({...ragScope, includePrivate: false, selectedGroupIds: newIds})
                                  }}
                                  className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                                <div className="flex-1 min-w-0">
                                  <div className="font-medium text-sm truncate">{group.name}</div>
                                  <div className="text-xs text-gray-500">{group.document_count} 个文档</div>
                                </div>
                              </label>
                            ))
                          )}
                        </div>
                      </div>

                      {/* 快捷操作 */}
                      <div className="flex justify-between pt-2 border-t">
                        <button
                          onClick={() => setRagScope({includePublic: true, includePrivate: true, selectedGroupIds: []})}
                          className="text-xs text-blue-600 hover:text-blue-700"
                        >
                          全选
                        </button>
                        <button
                          onClick={() => setRagScope({includePublic: false, includePrivate: false, selectedGroupIds: []})}
                          className="text-xs text-gray-500 hover:text-gray-700"
                        >
                          清空
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>

              {/* 联网搜索/外部工具开关 */}
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={enableWebSearch}
                  onChange={(e) => setEnableWebSearch(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <Globe className="h-4 w-4 text-gray-600" />
                <span className="text-sm font-medium text-gray-700">
                  {chatMode === 'deep_research' ? '外部工具(如联网搜索)' : '联网搜索'}
                </span>
              </label>
              </div>
            </div>
          </motion.div>
          )}
        </div>
      </div>
      {analysisEditor.open && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-3xl rounded-2xl bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">修订并运行代码</h3>
                <p className="text-sm text-gray-500">可直接编辑生成的 {analysisEditor.language.toUpperCase()} 代码，然后运行查看结果。</p>
              </div>
              <button
                onClick={() => setAnalysisEditor((prev) => ({ ...prev, open: false }))}
                className="rounded-full p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <textarea
                value={analysisEditor.code}
                onChange={(e) => setAnalysisEditor((prev) => ({ ...prev, code: e.target.value }))}
                className="w-full rounded-lg border border-gray-200 p-3 text-sm font-mono text-gray-800 bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                rows={14}
              />
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setAnalysisEditor((prev) => ({ ...prev, open: false }))}
                  className="px-4 py-2 rounded-lg border border-gray-200 text-gray-700 hover:border-gray-300"
                >
                  取消
                </button>
                <button
                  onClick={() => {
                    if (analysisEditor.messageIndex !== null) {
                      runAnalysisFromMessage({
                        messageIndex: analysisEditor.messageIndex,
                        code: analysisEditor.code,
                        language: analysisEditor.language,
                        groupId: analysisEditor.groupId || analysisGroupId,
                        instruction: '运行修订后的代码',
                      })
                    }
                  }}
                  disabled={
                    analysisEditor.messageIndex === null ||
                    analysisRunLoading[analysisEditor.messageIndex]
                  }
                  className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 flex items-center gap-2"
                >
                  {analysisEditor.messageIndex !== null && analysisRunLoading[analysisEditor.messageIndex] ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : null}
                  运行代码
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {referencePreview.open && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6">
          <div className="w-full max-w-2xl rounded-2xl bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">文档预览</h3>
                <p className="text-sm text-gray-500 truncate">{referencePreview.title}</p>
              </div>
              <button
                onClick={closeReferencePreview}
                className="rounded-full p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto px-6 py-5">
              {referencePreview.loading ? (
                <div className="flex items-center justify-center py-10 text-gray-500">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  正在加载文档预览...
                </div>
              ) : (
                <pre className="whitespace-pre-wrap text-sm leading-6 text-gray-700">
                  {referencePreview.content || '暂无预览内容'}
                </pre>
              )}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-6 py-4">
              <button
                onClick={closeReferencePreview}
                className="rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700 hover:bg-gray-200"
              >
                关闭
              </button>
              {referencePreview.filename && (
                <button
                  onClick={() =>
                    handleReferenceDownload({
                      title: referencePreview.title,
                      content: referencePreview.content,
                      filename: referencePreview.filename,
                    })
                  }
                  className="rounded-lg bg-blue-500 px-4 py-2 text-sm text-white hover:bg-blue-600"
                >
                  下载原文件
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 计划编辑模态窗口 */}
      {showPlanEditor && editingPlan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="w-full max-w-4xl rounded-2xl bg-white shadow-2xl max-h-[90vh] overflow-hidden flex flex-col"
          >
            {/* 标题栏 */}
            <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 bg-gradient-to-r from-blue-500 to-blue-600">
              <div>
                <h3 className="text-xl font-semibold text-white">编辑研究计划</h3>
                <p className="text-sm text-blue-100 mt-1">请查看并修改下方的研究计划，确认后将按照您的计划执行</p>
              </div>
              <button
                onClick={handleCancelPlanEdit}
                className="rounded-full p-2 text-white/80 hover:bg-white/20 hover:text-white transition-colors"
                title="取消编辑"
              >
                <X className="h-6 w-6" />
              </button>
            </div>

            {/* 内容区域 */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
              {/* 整体策略编辑 */}
              <div className="space-y-3">
                <label className="block text-sm font-semibold text-gray-800">
                  整体研究策略
                </label>
                <textarea
                  value={editingPlan.overall_strategy}
                  onChange={(e) => handleUpdateStrategy(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  rows={3}
                  placeholder="描述整体研究思路和方法..."
                />
              </div>

              {/* 任务列表编辑 */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <label className="block text-sm font-semibold text-gray-800">
                    研究任务列表 ({editingPlan.tasks.length} 个任务)
                  </label>
                  <button
                    onClick={handleAddTask}
                    className="flex items-center gap-2 rounded-lg bg-blue-500 px-4 py-2 text-sm text-white hover:bg-blue-600 transition-colors"
                  >
                    <span>+ 添加任务</span>
                  </button>
                </div>

                <div className="space-y-4">
                  {editingPlan.tasks.map((task, index) => (
                    <div
                      key={index}
                      className="rounded-xl border border-gray-200 bg-gray-50 p-4 space-y-3 hover:border-blue-300 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 space-y-3">
                          {/* 任务名称 */}
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">
                              任务 {index + 1} - 名称
                            </label>
                            <input
                              type="text"
                              value={task.task_name}
                              onChange={(e) =>
                                handleUpdateTask(index, { ...task, task_name: e.target.value })
                              }
                              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                              placeholder="任务名称..."
                            />
                          </div>

                          {/* 任务目标 */}
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">
                              任务目标
                            </label>
                            <textarea
                              value={task.objective}
                              onChange={(e) =>
                                handleUpdateTask(index, { ...task, objective: e.target.value })
                              }
                              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                              rows={2}
                              placeholder="描述这个任务要达成的目标..."
                            />
                          </div>

                          {/* 任务配置 */}
                          <div className="flex flex-wrap gap-3">
                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={task.requires_vector_search || false}
                                onChange={(e) =>
                                  handleUpdateTask(index, {
                                    ...task,
                                    requires_vector_search: e.target.checked,
                                  })
                                }
                                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                              />
                              <span className="text-xs text-gray-700">需要文档检索</span>
                            </label>

                            <label className="flex items-center gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={task.requires_tool || false}
                                onChange={(e) =>
                                  handleUpdateTask(index, {
                                    ...task,
                                    requires_tool: e.target.checked,
                                  })
                                }
                                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                              />
                              <span className="text-xs text-gray-700">需要外部工具</span>
                            </label>

                            <select
                              value={task.model_preference || 'general'}
                              onChange={(e) =>
                                handleUpdateTask(index, {
                                  ...task,
                                  model_preference: e.target.value as 'general' | 'reasoning',
                                })
                              }
                              className="rounded-lg border border-gray-300 px-3 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                            >
                              <option value="general">通用模型</option>
                              <option value="reasoning">推理模型</option>
                            </select>
                          </div>
                        </div>

                        {/* 删除按钮 */}
                        <button
                          onClick={() => handleDeleteTask(index)}
                          className="rounded-lg p-2 text-red-500 hover:bg-red-50 transition-colors"
                          title="删除此任务"
                        >
                          <X className="h-5 w-5" />
                        </button>
                      </div>
                    </div>
                  ))}

                  {editingPlan.tasks.length === 0 && (
                    <div className="text-center py-8 text-gray-500">
                      暂无任务，请点击"添加任务"按钮创建任务
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 底部按钮 */}
            <div className="flex items-center justify-end gap-3 border-t border-gray-200 px-6 py-4 bg-gray-50">
              <button
                onClick={handleCancelPlanEdit}
                className="rounded-lg border border-gray-300 bg-white px-6 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSubmitPlan}
                className="rounded-lg bg-gradient-to-r from-blue-500 to-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:from-blue-600 hover:to-blue-700 transition-colors shadow-sm"
              >
                确认并继续执行
              </button>
            </div>
          </motion.div>
        </div>
      )}
      {/* ── 引用悬浮提示 ── */}
      <AnimatePresence>
        {citationTooltip?.show && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="fixed z-[9999] pointer-events-none"
            style={{ left: Math.min(citationTooltip.x + 12, window.innerWidth - 340), top: citationTooltip.y - 10 }}
          >
            <div className="bg-gray-900 text-white text-xs rounded-xl p-3 w-80 shadow-2xl">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-[3px] text-[10px] font-bold rounded-full bg-blue-500 text-white">
                  {citationTooltip.id}
                </span>
                <span className="font-medium text-blue-300 truncate">{citationTooltip.source}</span>
              </div>
              <p className="text-gray-300 leading-relaxed line-clamp-3">{citationTooltip.snippet}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </MainLayout>
  )
}
