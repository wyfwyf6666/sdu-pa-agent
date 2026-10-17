'use client'

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react'
import {
  Upload,
  Search,
  Grid,
  List,
  Download,
  Eye,
  Pencil,
  RefreshCcw,
  Loader2,
  Trash2,
  Check,
  FileText,
  X,
  AlertCircle,
  Database,
} from 'lucide-react'
import { toast, Toaster } from 'react-hot-toast'
import KnowledgeGroupSidebar from '@/components/documents/KnowledgeGroupSidebar'
import { apiFetch } from '@/lib/api'
import { fetchWithTimeout, TIMEOUT } from '@/lib/fetchWithTimeout'

interface DocumentMeta {
  filename: string
  title: string
  size: number
  upload_time: string
  updated_time?: string
  category: string
  tags: string[]
  type: string
  path: string
  processed: boolean
  knowledge_group_id?: string
  effectiveness_level?: string
  document_type?: string
  discipline?: string
  region?: string
  main_topic?: string
  data_metadata?: {
    rows?: number
    columns?: number
    headers?: string[]
    data_type?: string
    sheets?: Array<{
      name: string
      rows: number
      columns: number
      headers: string[]
    }>
    sheet_count?: number
  }
}

interface KnowledgeGroup {
  id: string
  name: string
  description: string
  created_time: string
  updated_time: string
  document_count: number
  storage_path: string
  vector_path: string
}

interface UploadCandidate {
  file: File
  title: string
  category: string
  autoTag: boolean
  manualTags: string
  effectiveness_level?: string
  document_type?: string
  discipline?: string
  region?: string
  main_topic?: string
}

interface PreviewState {
  open: boolean
  loading: boolean
  title: string
  content: string
  filename: string
}

interface EditState {
  filename: string
  title: string
  category: string
  tagsText: string
  saving: boolean
  regenerating: boolean
  effectiveness_level?: string
  document_type?: string
  discipline?: string
  region?: string
  main_topic?: string
}

const CATEGORY_OPTIONS = ['论文', '案例', '政策', '数据']

const formatFileSize = (bytes: number) => {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, exponent)).toFixed(2)} ${units[exponent]}`
}

const formatDate = (value?: string) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

const sanitizeFilename = (name: string) => {
  if (!name) return ''
  const parts = name.split(/[/\\]+/)
  return parts[parts.length - 1] || name
}

const extractFilenameFromDisposition = (value: string | null) => {
  if (!value) return null
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match) return decodeURIComponent(utf8Match[1])
  const match = value.match(/filename="?([^";]+)"?/i)
  return match ? decodeURIComponent(match[1]) : null
}

export default function PrivateDocumentsPage() {
  const [knowledgeGroups, setKnowledgeGroups] = useState<KnowledgeGroup[]>([])
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null)
  const [documents, setDocuments] = useState<DocumentMeta[]>([])
  const [categories, setCategories] = useState<string[]>(CATEGORY_OPTIONS)
  const [tags, setTags] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [searchInput, setSearchInput] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('')
  const [selectedTag, setSelectedTag] = useState('')
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadQueue, setUploadQueue] = useState<UploadCandidate[]>([])
  const [uploading, setUploading] = useState(false)
  const [previewState, setPreviewState] = useState<PreviewState>({
    open: false,
    loading: false,
    title: '',
    content: '',
    filename: '',
  })
  const [editState, setEditState] = useState<EditState | null>(null)
  const [isBuildingIndex, setIsBuildingIndex] = useState(false)
  const [isLoadingIndex, setIsLoadingIndex] = useState(false)

  const filteredTags = useMemo(() => tags.filter(Boolean).sort(), [tags])
  const anySelected = selectedFiles.length > 0
  const allSelected = documents.length > 0 && selectedFiles.length === documents.length

  const selectedGroup = knowledgeGroups.find((g) => g.id === selectedGroupId)

  const fetchKnowledgeGroups = async () => {
    try {
      const response = await apiFetch('/api/v1/knowledge-groups')
      if (!response.ok) throw new Error('获取知识组列表失败')
      const data = await response.json()
      setKnowledgeGroups(data.data || [])
    } catch (error) {
      toast.error((error as Error).message || '获取知识组列表失败')
    }
  }

  const fetchDocuments = async () => {
    if (!selectedGroupId) {
      setDocuments([])
      return
    }

    try {
      setLoading(true)
      let url = '/api/v1/documents'
      const params = new URLSearchParams()
      params.append('library_type', 'private')
      params.append('knowledge_group_id', selectedGroupId)
      if (selectedCategory) params.append('category', selectedCategory)
      if (selectedTag) params.append('tag', selectedTag)
      if (searchQuery) params.append('search', searchQuery)
      url += `?${params.toString()}`

      const response = await apiFetch(url)
      if (!response.ok) throw new Error('获取文档列表失败')
      const data = await response.json()
      const list: DocumentMeta[] = data.data || []
      setDocuments(list)
      setSelectedFiles((prev) => prev.filter((name) => list.some((doc) => doc.filename === name)))
    } catch (error) {
      toast.error((error as Error).message || '获取文档列表失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchCategories = async () => {
    try {
      const response = await apiFetch('/api/v1/documents/categories?library_type=private')
      if (!response.ok) throw new Error('获取分类列表失败')
      const data = await response.json()
      setCategories(data.data || CATEGORY_OPTIONS)
    } catch (error) {
      toast.error((error as Error).message || '获取分类列表失败')
    }
  }

  const fetchTags = async () => {
    try {
      const response = await apiFetch('/api/v1/documents/tags?library_type=private')
      if (!response.ok) throw new Error('获取标签列表失败')
      const data = await response.json()
      setTags(data.data || [])
    } catch (error) {
      toast.error((error as Error).message || '获取标签列表失败')
    }
  }

  useEffect(() => {
    fetchKnowledgeGroups()
    fetchCategories()
    fetchTags()
  }, [])

  useEffect(() => {
    fetchDocuments()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedGroupId, selectedCategory, selectedTag, searchQuery])

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSearchQuery(searchInput.trim())
  }

  const resetFilters = () => {
    setSearchInput('')
    setSearchQuery('')
    setSelectedCategory('')
    setSelectedTag('')
    setSelectedFiles([])
    fetchDocuments()
  }

  const toggleFileSelection = (filename: string, value?: boolean) => {
    const normalized = sanitizeFilename(filename)
    setSelectedFiles((prev) => {
      const exists = prev.includes(normalized)
      const shouldSelect = typeof value === 'boolean' ? value : !exists
      if (shouldSelect && !exists) return [...prev, normalized]
      if (!shouldSelect && exists) return prev.filter((item) => item !== normalized)
      return prev
    })
  }

  const handleFilesSelected = (event: ChangeEvent<HTMLInputElement>) => {
    if (!selectedGroupId) {
      toast.error('请先选择一个知识组')
      event.target.value = ''
      return
    }

    const files = event.target.files
    if (!files || !files.length) return
    const nextQueue: UploadCandidate[] = Array.from(files).map((file) => ({
      file,
      title: file.name.replace(/\.[^/.]+$/, '') || file.name,
      category: CATEGORY_OPTIONS[0],
      autoTag: true,
      manualTags: '',
      effectiveness_level: '',
      document_type: '',
      discipline: '',
      region: '',
      main_topic: '',
    }))
    setUploadQueue((prev) => [...prev, ...nextQueue])
    event.target.value = ''
    setShowUploadModal(true)
  }

  const updateUploadCandidate = (index: number, updater: Partial<UploadCandidate>) => {
    setUploadQueue((prev) =>
      prev.map((item, idx) => (idx === index ? { ...item, ...updater } : item))
    )
  }

  const removeUploadCandidate = (index: number) => {
    setUploadQueue((prev) => prev.filter((_, idx) => idx !== index))
  }

  const submitUpload = async () => {
    if (!selectedGroupId) {
      toast.error('请先选择知识组')
      return
    }

    if (!uploadQueue.length) {
      toast.error('请先选择文件')
      return
    }

    setUploading(true)
    try {
      const formData = new FormData()
      const metadataPayload = uploadQueue.map((item) => {
        const meta: any = {
          filename: item.file.name,
          title: item.title,
          category: item.category,
          autoTag: item.autoTag,
          tags: item.autoTag
            ? undefined
            : item.manualTags
                .split(',')
                .map((tag) => tag.trim())
                .filter(Boolean),
        }

        if (!item.autoTag) {
          if (item.category === '政策') {
            meta.effectiveness_level = item.effectiveness_level || ''
            meta.document_type = item.document_type || ''
          } else if (item.category === '论文') {
            meta.discipline = item.discipline || ''
            meta.main_topic = item.main_topic || ''
          } else if (item.category === '案例') {
            meta.region = item.region || ''
            meta.main_topic = item.main_topic || ''
          }
        }

        return meta
      })

      uploadQueue.forEach((item) => formData.append('files', item.file))
      formData.append('metadata_json', JSON.stringify(metadataPayload))
      formData.append('library_type', 'private')
      formData.append('knowledge_group_id', selectedGroupId)

      // 手动添加token
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      // 使用超长超时（5分钟）用于文档上传和处理
      const response = await fetchWithTimeout(
        '/api/v1/documents/upload',
        {
          method: 'POST',
          headers,
          body: formData,
        },
        TIMEOUT.VERY_LONG
      )
      if (!response.ok) throw new Error('文件上传失败')
      const data = await response.json()
      if (data.status !== 'success') throw new Error(data.message || '文件上传失败')

      toast.success(`成功上传 ${data.data.length} 个文件`)
      setUploadQueue([])
      setShowUploadModal(false)
      await Promise.all([fetchDocuments(), fetchTags(), fetchKnowledgeGroups()])
    } catch (error) {
      toast.error((error as Error).message || '文件上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handlePreview = async (doc: DocumentMeta) => {
    setPreviewState({
      open: true,
      loading: true,
      title: doc.title,
      content: '',
      filename: doc.filename,
    })
    try {
      const response = await apiFetch(
        `/api/v1/documents/${encodeURIComponent(doc.filename)}/preview?library_type=private`
      )
      if (!response.ok) throw new Error('获取预览失败')
      const data = await response.json()
      setPreviewState((prev) => ({
        ...prev,
        loading: false,
        content: data.data?.preview || '',
      }))
    } catch (error) {
      setPreviewState((prev) => ({ ...prev, loading: false }))
      toast.error((error as Error).message || '获取预览失败')
    }
  }

  const handleDownload = (doc: DocumentMeta) => {
    window.open(
      `/api/v1/documents/${encodeURIComponent(doc.filename)}/download?library_type=private`,
      '_blank'
    )
  }

  const openEditModal = (doc: DocumentMeta) => {
    setEditState({
      filename: doc.filename,
      title: doc.title,
      category: doc.category || CATEGORY_OPTIONS[0],
      tagsText: doc.tags.join(', '),
      saving: false,
      regenerating: false,
      effectiveness_level: doc.effectiveness_level || '',
      document_type: doc.document_type || '',
      discipline: doc.discipline || '',
      region: doc.region || '',
      main_topic: doc.main_topic || '',
    })
  }

  const submitEdit = async () => {
    if (!editState) return
    setEditState((prev) => (prev ? { ...prev, saving: true } : prev))
    try {
      const payload: any = {
        title: editState.title,
        category: editState.category,
        tags: editState.tagsText
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
      }

      if (editState.category === '政策') {
        payload.effectiveness_level = editState.effectiveness_level || ''
        payload.document_type = editState.document_type || ''
      } else if (editState.category === '论文') {
        payload.discipline = editState.discipline || ''
        payload.main_topic = editState.main_topic || ''
      } else if (editState.category === '案例') {
        payload.region = editState.region || ''
        payload.main_topic = editState.main_topic || ''
      }

      const response = await apiFetch(
        `/api/v1/documents/${encodeURIComponent(editState.filename)}?library_type=private`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      )
      if (!response.ok) throw new Error('更新失败')
      const data = await response.json()
      if (data.status !== 'success') throw new Error(data.message || '更新失败')

      toast.success('文档信息已更新')
      setDocuments((prev) =>
        prev.map((doc) => (doc.filename === editState.filename ? data.data : doc))
      )
      await fetchTags()
      setEditState(null)
    } catch (error) {
      toast.error((error as Error).message || '更新失败')
      setEditState((prev) => (prev ? { ...prev, saving: false } : prev))
    }
  }

  const regenerateTags = async () => {
    if (!editState) return
    setEditState((prev) => (prev ? { ...prev, regenerating: true } : prev))
    try {
      const payload = {
        title: editState.title,
        category: editState.category,
        regenerate_tags: true,
      }
      const response = await apiFetch(
        `/api/v1/documents/${encodeURIComponent(editState.filename)}?library_type=private`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      )
      if (!response.ok) throw new Error('自动生成标签失败')
      const data = await response.json()
      if (data.status !== 'success') throw new Error(data.message || '自动生成标签失败')

      const updatedDoc = data.data
      const newTags: string[] = updatedDoc.tags || []
      toast.success('已重新生成标签和分类字段')
      setDocuments((prev) =>
        prev.map((doc) => (doc.filename === editState.filename ? updatedDoc : doc))
      )

      setEditState((prev) => {
        if (!prev) return prev
        return {
          ...prev,
          tagsText: newTags.join(', '),
          regenerating: false,
          effectiveness_level: updatedDoc.effectiveness_level || '',
          document_type: updatedDoc.document_type || '',
          discipline: updatedDoc.discipline || '',
          region: updatedDoc.region || '',
          main_topic: updatedDoc.main_topic || '',
        }
      })

      await fetchTags()
    } catch (error) {
      toast.error((error as Error).message || '自动生成标签失败')
      setEditState((prev) => (prev ? { ...prev, regenerating: false } : prev))
    }
  }

  const deleteDocument = async (doc: DocumentMeta) => {
    if (!confirm(`确定删除 ${doc.title} 吗？该操作不可恢复。`)) return
    try {
      const response = await apiFetch(
        `/api/v1/documents/${encodeURIComponent(doc.filename)}?library_type=private`,
        {
          method: 'DELETE',
        }
      )
      if (!response.ok) throw new Error('删除失败')
      const data = await response.json()
      if (data.status !== 'success') throw new Error(data.message || '删除失败')

      toast.success('文档已删除')
      setDocuments((prev) => prev.filter((item) => item.filename !== doc.filename))
      setSelectedFiles((prev) => prev.filter((name) => name !== doc.filename))
      await Promise.all([fetchTags(), fetchKnowledgeGroups()])
    } catch (error) {
      toast.error((error as Error).message || '删除失败')
    }
  }

  const handleBatchDownload = async () => {
    if (!selectedFiles.length) return
    try {
      const response = await apiFetch('/api/v1/documents/batch-download?library_type=private', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames: selectedFiles }),
      })
      if (!response.ok) throw new Error('批量下载失败')
      const blob = await response.blob()
      const disposition = response.headers.get('Content-Disposition')
      const downloadName =
        extractFilenameFromDisposition(disposition) || `documents-${Date.now()}.zip`
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = downloadName
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      toast.success('批量下载任务已开始')
    } catch (error) {
      toast.error((error as Error).message || '批量下载失败')
    }
  }

  const handleBatchDelete = async () => {
    if (!selectedFiles.length) return
    if (!confirm(`确认删除选中的 ${selectedFiles.length} 个文件吗？该操作不可恢复。`)) return
    try {
      const response = await apiFetch('/api/v1/documents/batch-delete?library_type=private', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames: selectedFiles }),
      })
      if (!response.ok) throw new Error('批量删除失败')
      const data = await response.json()
      if (data.status !== 'success') throw new Error(data.message || '批量删除失败')

      const deleted: string[] = data.data?.deleted || []
      const missing: string[] = data.data?.missing || []
      toast.success(`已删除 ${deleted.length} 个文件`)
      if (missing.length) {
        toast(`以下文件未找到: ${missing.join(', ')}`)
      }
      setSelectedFiles((prev) => prev.filter((filename) => !deleted.includes(filename)))
      await Promise.all([fetchDocuments(), fetchTags(), fetchKnowledgeGroups()])
    } catch (error) {
      toast.error((error as Error).message || '批量删除失败')
    }
  }

  const handleBuildMergedIndex = async () => {
    if (!selectedGroupId) {
      toast.error('请先选择知识组')
      return
    }

    try {
      setIsBuildingIndex(true)

      // 私人库构建索引
      const response = await fetch('/api/v1/chat/build-merged-index', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          library_type: 'private',
          knowledge_group_id: selectedGroupId,
        }),
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(errorText || '启动构建失败')
      }

      const data = await response.json()
      const taskId = data.task_id

      toast.loading('正在后台构建索引，可能需要30-60秒...', { id: 'build-index' })

      // 轮询任务状态
      const pollInterval = setInterval(async () => {
        try {
          const statusResponse = await fetch(`/api/v1/chat/build-merged-index/${taskId}`)
          if (!statusResponse.ok) {
            throw new Error('查询状态失败')
          }

          const status = await statusResponse.json()

          if (status.status === 'completed') {
            clearInterval(pollInterval)
            setIsBuildingIndex(false)
            toast.success('索引构建成功！', { id: 'build-index' })
          } else if (status.status === 'failed') {
            clearInterval(pollInterval)
            setIsBuildingIndex(false)
            toast.error(`构建失败: ${status.message}`, { id: 'build-index' })
          } else {
            // 更新进度提示
            toast.loading(`${status.message || '正在构建索引...'}`, { id: 'build-index' })
          }
        } catch (pollError) {
          console.error('轮询状态失败:', pollError)
        }
      }, 2000) // 每2秒轮询一次

      // 设置最大轮询时间（3分钟）
      setTimeout(() => {
        clearInterval(pollInterval)
        if (isBuildingIndex) {
          setIsBuildingIndex(false)
          toast.error('构建超时，请稍后重试', { id: 'build-index' })
        }
      }, 180000)
    } catch (error) {
      console.error('构建索引失败:', error)
      toast.error('构建索引失败: ' + (error as Error).message, { id: 'build-index' })
      setIsBuildingIndex(false)
    }
  }

  const handleLoadIndex = async () => {
    if (!selectedGroupId) {
      toast.error('请先选择知识组')
      return
    }

    try {
      setIsLoadingIndex(true)
      toast.loading('正在加载索引到内存，首次加载可能需要2-3分钟...', { id: 'load-index' })

      // 创建超时控制器，设置 5 分钟超时
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 300000) // 5分钟 = 300000ms

      try {
        const response = await fetch('/api/v1/chat/load-index', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            library_type: 'private',
            knowledge_group_id: selectedGroupId,
          }),
          signal: controller.signal,
        })

        clearTimeout(timeoutId) // 清除超时定时器

        if (!response.ok) {
          const errorText = await response.text()
          throw new Error(errorText || '加载索引失败')
        }

        const data = await response.json()
        if (data.status === 'success') {
          toast.success('索引已加载到内存缓存！', { id: 'load-index' })
        } else {
          throw new Error(data.message || '加载索引失败')
        }
      } catch (fetchError) {
        clearTimeout(timeoutId)
        if ((fetchError as Error).name === 'AbortError') {
          throw new Error('加载索引超时（超过5分钟），请检查网络连接或联系管理员')
        }
        throw fetchError
      }
    } catch (error) {
      console.error('加载索引失败:', error)
      toast.error('加载索引失败: ' + (error as Error).message, { id: 'load-index' })
    } finally {
      setIsLoadingIndex(false)
    }
  }

  const renderTags = (doc: DocumentMeta) => {
    if (!doc.tags?.length) {
      return (
        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
          暂无标签
        </span>
      )
    }
    return doc.tags.map((tag) => (
      <span
        key={`${doc.filename}-${tag}`}
        className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
      >
        {tag}
      </span>
    ))
  }

  const renderCategoryFields = (doc: DocumentMeta) => {
    const fields: { label: string; value: string }[] = []

    if (doc.category === '政策') {
      if (doc.effectiveness_level) {
        fields.push({ label: '效力层级', value: doc.effectiveness_level })
      }
      if (doc.document_type) {
        fields.push({ label: '文件类型', value: doc.document_type })
      }
    } else if (doc.category === '论文') {
      if (doc.discipline) {
        fields.push({ label: '学科维度', value: doc.discipline })
      }
      if (doc.main_topic) {
        fields.push({ label: '主体内容', value: doc.main_topic })
      }
    } else if (doc.category === '案例') {
      if (doc.region) {
        fields.push({ label: '地区', value: doc.region })
      }
      if (doc.main_topic) {
        fields.push({ label: '主体内容', value: doc.main_topic })
      }
    } else if (doc.category === '数据' && doc.data_metadata) {
      // 数据文件显示元信息而不是分类字段
      const meta = doc.data_metadata
      if (meta.rows !== undefined) {
        fields.push({ label: '行数', value: meta.rows.toString() })
      }
      if (meta.columns !== undefined) {
        fields.push({ label: '列数', value: meta.columns.toString() })
      }
      if (meta.sheet_count !== undefined && meta.sheet_count > 1) {
        fields.push({ label: '工作表数', value: meta.sheet_count.toString() })
      }
      if (meta.data_type) {
        fields.push({ label: '类型', value: meta.data_type })
      }
    }

    if (fields.length === 0) return null

    return (
      <div className="mt-2 flex flex-wrap gap-2">
        {fields.map((field, idx) => (
          <span
            key={`${doc.filename}-field-${idx}`}
            className="inline-flex items-center rounded-full bg-green-50 px-2 py-0.5 text-xs text-green-700"
          >
            {field.label}: {field.value}
          </span>
        ))}
      </div>
    )
  }

  const renderDataHeaders = (doc: DocumentMeta) => {
    if (doc.category !== '数据' || !doc.data_metadata?.headers?.length) {
      return null
    }

    const headers = doc.data_metadata.headers.slice(0, 5) // 最多显示5个表头
    const hasMore = doc.data_metadata.headers.length > 5

    return (
      <div className="mt-2">
        <div className="text-xs text-gray-500 mb-1">表头:</div>
        <div className="flex flex-wrap gap-1">
          {headers.map((header, idx) => (
            <span
              key={`${doc.filename}-header-${idx}`}
              className="inline-flex items-center rounded bg-blue-50 px-2 py-0.5 text-xs text-blue-700"
            >
              {header}
            </span>
          ))}
          {hasMore && (
            <span className="inline-flex items-center rounded bg-gray-50 px-2 py-0.5 text-xs text-gray-500">
              +{doc.data_metadata.headers.length - 5}
            </span>
          )}
        </div>
      </div>
    )
  }

  return (
    <>
      <Toaster position="top-right" />

      <div className="flex gap-6">
        {/* Left Sidebar */}
        <div className="w-64 flex-shrink-0">
          <KnowledgeGroupSidebar
            groups={knowledgeGroups}
            selectedGroupId={selectedGroupId}
            onSelectGroup={setSelectedGroupId}
            onRefresh={fetchKnowledgeGroups}
          />
        </div>

        {/* Main Content */}
        <div className="flex-1">
          {!selectedGroupId ? (
            <div className="flex h-96 items-center justify-center rounded-2xl border border-dashed border-gray-200 bg-white">
              <div className="text-center">
                <AlertCircle className="mx-auto h-12 w-12 text-gray-400" />
                <h3 className="mt-4 text-lg font-medium text-gray-900">请选择知识组</h3>
                <p className="mt-2 text-sm text-gray-500">
                  从左侧选择一个知识组来查看和管理其中的文档
                  <br />
                  如果还没有知识组，请先创建一个
                </p>
              </div>
            </div>
          ) : (
            <>
              <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h1 className="text-2xl font-semibold text-gray-900">{selectedGroup?.name}</h1>
                    <p className="mt-1 text-sm text-gray-500">
                      {selectedGroup?.description || '管理此知识组的文档'}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 p-1">
                      <button
                        onClick={() => setViewMode('grid')}
                        className={`rounded-md px-3 py-1 text-sm ${
                          viewMode === 'grid' ? 'bg-blue-500 text-white' : 'text-gray-500'
                        }`}
                      >
                        <Grid className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setViewMode('list')}
                        className={`rounded-md px-3 py-1 text-sm ${
                          viewMode === 'list' ? 'bg-blue-500 text-white' : 'text-gray-500'
                        }`}
                      >
                        <List className="h-4 w-4" />
                      </button>
                    </div>
                    {documents.length > 0 && (
                      <label className="flex items-center gap-2 text-sm text-gray-600">
                        <input
                          type="checkbox"
                          checked={allSelected}
                          onChange={(event) =>
                            setSelectedFiles(
                              event.target.checked ? documents.map((doc) => doc.filename) : []
                            )
                          }
                          className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <span>{allSelected ? '取消全选' : '全选当前列表'}</span>
                      </label>
                    )}
                    <input
                      type="file"
                      id="document-upload-private"
                      className="hidden"
                      multiple
                      accept=".pdf,.docx,.txt,.csv,.xlsx,.xls,.json"
                      onChange={handleFilesSelected}
                    />
                    <button
                      onClick={() => document.getElementById('document-upload-private')?.click()}
                      className="inline-flex items-center rounded-lg bg-blue-500 px-4 py-2 text-sm text-white hover:bg-blue-600 transition-colors"
                    >
                      <Upload className="mr-2 h-5 w-5" />
                      上传文档
                    </button>
                    <button
                      onClick={handleLoadIndex}
                      disabled={isLoadingIndex}
                      className="inline-flex items-center rounded-lg border border-green-200 px-4 py-2 text-sm text-green-600 hover:bg-green-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title="将索引文件加载到内存缓存，避免首次检索时的长时间等待"
                    >
                      {isLoadingIndex ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          加载中...
                        </>
                      ) : (
                        <>
                          <Download className="mr-2 h-4 w-4" />
                          加载索引
                        </>
                      )}
                    </button>
                    <button
                      onClick={handleBuildMergedIndex}
                      disabled={isBuildingIndex}
                      className="inline-flex items-center rounded-lg border border-blue-200 px-4 py-2 text-sm text-blue-600 hover:bg-blue-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      title="手动构建合并索引以加速RAG搜索"
                    >
                      {isBuildingIndex ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          构建中...
                        </>
                      ) : (
                        <>
                          <Database className="mr-2 h-4 w-4" />
                          构建索引
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <form onSubmit={handleSearch} className="mt-6 flex flex-wrap items-center gap-3">
                  <div className="flex flex-1 items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-4 py-2">
                    <Search className="h-4 w-4 text-gray-400" />
                    <input
                      value={searchInput}
                      onChange={(event) => setSearchInput(event.target.value)}
                      placeholder="搜索文档标题或关键词"
                      className="flex-1 bg-transparent text-sm focus:outline-none"
                    />
                  </div>
                  <select
                    value={selectedCategory}
                    onChange={(event) => setSelectedCategory(event.target.value)}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  >
                    <option value="">全部分类</option>
                    {categories.map((category) => (
                      <option key={category} value={category}>
                        {category}
                      </option>
                    ))}
                  </select>
                  <select
                    value={selectedTag}
                    onChange={(event) => setSelectedTag(event.target.value)}
                    className="rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  >
                    <option value="">全部标签</option>
                    {filteredTags.map((tag) => (
                      <option key={tag} value={tag}>
                        {tag}
                      </option>
                    ))}
                  </select>
                  <button type="submit" className="rounded-lg bg-blue-500 px-4 py-2 text-sm text-white">
                    搜索
                  </button>
                  <button
                    type="button"
                    onClick={resetFilters}
                    className="rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700"
                  >
                    重置
                  </button>
                </form>
              </div>

              {anySelected && (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3">
                  <div className="text-blue-700">已选择 {selectedFiles.length} 个文件</div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleBatchDownload}
                      className="rounded-lg border border-blue-200 px-3 py-1.5 text-sm text-blue-600"
                    >
                      批量下载
                    </button>
                    <button
                      onClick={handleBatchDelete}
                      className="rounded-lg bg-red-500 px-3 py-1.5 text-sm text-white"
                    >
                      批量删除
                    </button>
                    <button
                      onClick={() => setSelectedFiles([])}
                      className="rounded-lg px-3 py-1.5 text-sm text-blue-600"
                    >
                      清除
                    </button>
                  </div>
                </div>
              )}

              {loading ? (
                <div className="flex items-center justify-center py-16 text-gray-600">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  加载中...
                </div>
              ) : documents.length === 0 ? (
                <div className="mt-6 rounded-2xl border border-dashed border-gray-200 bg-white px-8 py-16 text-center text-sm text-gray-500">
                  此知识组暂无文档，点击"上传文档"开始添加。
                </div>
              ) : viewMode === 'grid' ? (
                <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
                  {documents.map((doc) => {
                    const selected = selectedFiles.includes(doc.filename)
                    return (
                      <div
                        key={doc.filename}
                        className={`rounded-xl border bg-white p-5 shadow-sm ${
                          selected ? 'border-blue-300' : 'border-gray-100'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={(event) => toggleFileSelection(doc.filename, event.target.checked)}
                              className="mt-1 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                            />
                            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                              <FileText className="h-5 w-5" />
                            </div>
                            <div>
                              <h3 className="text-base font-medium text-gray-900 line-clamp-2">{doc.title}</h3>
                              <div className="mt-1 text-xs text-gray-500">
                                {formatDate(doc.upload_time)} · {formatFileSize(doc.size)}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <button onClick={() => handlePreview(doc)} className="text-gray-500 hover:text-blue-600">
                              <Eye className="h-5 w-5" />
                            </button>
                            <button onClick={() => handleDownload(doc)} className="text-gray-500 hover:text-blue-600">
                              <Download className="h-5 w-5" />
                            </button>
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-gray-600">
                          <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-blue-700">
                            {doc.category || '未分类'}
                          </span>
                          {doc.category !== '数据' && renderTags(doc)}
                        </div>
                        {renderCategoryFields(doc)}
                        {renderDataHeaders(doc)}
                        <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
                          <span>处理状态：{doc.processed ? '已向量化' : '处理中'}</span>
                          <div className="flex items-center gap-2 text-sm">
                            <button onClick={() => openEditModal(doc)} className="text-blue-600">
                              <Pencil className="mr-1 inline h-4 w-4" />
                              编辑
                            </button>
                            <button onClick={() => deleteDocument(doc)} className="text-red-500">
                              <Trash2 className="mr-1 inline h-4 w-4" />
                              删除
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="mt-6 divide-y divide-gray-200 rounded-2xl border border-gray-100 bg-white">
                  {documents.map((doc) => {
                    const selected = selectedFiles.includes(doc.filename)
                    return (
                      <div
                        key={doc.filename}
                        className={`flex flex-wrap items-center gap-4 px-6 py-4 ${
                          selected ? 'bg-blue-50' : ''
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={(event) => toggleFileSelection(doc.filename, event.target.checked)}
                            className="mt-1 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600">
                            <FileText className="h-4 w-4" />
                          </div>
                          <div>
                            <h3 className="text-sm font-medium text-gray-900">{doc.title}</h3>
                            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                              <span>{formatDate(doc.upload_time)}</span>
                              <span>·</span>
                              <span>{formatFileSize(doc.size)}</span>
                              <span>·</span>
                              <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-blue-700">
                                {doc.category || '未分类'}
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex-1">
                          <div className="flex flex-wrap gap-2 text-xs text-gray-600">{doc.category !== '数据' && renderTags(doc)}</div>
                          {renderCategoryFields(doc)}
                          {renderDataHeaders(doc)}
                        </div>
                        <div className="flex items-center gap-2 text-sm">
                          <button onClick={() => handlePreview(doc)} className="text-gray-500 hover:text-blue-600">
                            <Eye className="h-4 w-4" />
                          </button>
                          <button onClick={() => handleDownload(doc)} className="text-gray-500 hover:text-blue-600">
                            <Download className="h-4 w-4" />
                          </button>
                          <button onClick={() => openEditModal(doc)} className="text-blue-600">
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button onClick={() => deleteDocument(doc)} className="text-red-500">
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Upload Modal - Same as public library */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6">
          <div className="w-full max-w-3xl rounded-2xl bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
              <h2 className="text-lg font-semibold text-gray-900">批量上传文档</h2>
              <button
                onClick={() => setShowUploadModal(false)}
                className="rounded-full p-2 text-gray-400 hover:bg-gray-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto px-6 py-4">
              {uploadQueue.length === 0 ? (
                <div className="rounded-xl border border-dashed border-gray-200 p-10 text-center text-sm text-gray-500">
                  请选择文件后开始配置。
                </div>
              ) : (
                <div className="space-y-4">
                  {uploadQueue.map((item, index) => (
                    <div key={`${item.file.name}-${index}`} className="rounded-xl border border-gray-200 p-4">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="text-sm font-medium text-gray-900">{item.file.name}</h3>
                          <p className="text-xs text-gray-500">
                            {formatFileSize(item.file.size)} · {item.file.type || '未知类型'}
                          </p>
                        </div>
                        <button onClick={() => removeUploadCandidate(index)} className="text-gray-400 hover:text-red-500">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-2">
                        <label className="text-xs text-gray-600">
                          文档标题
                          <input
                            value={item.title}
                            onChange={(event) => updateUploadCandidate(index, { title: event.target.value })}
                            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                          />
                        </label>
                        <label className="text-xs text-gray-600">
                          分类
                          <select
                            value={item.category}
                            onChange={(event) => updateUploadCandidate(index, { category: event.target.value })}
                            className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                          >
                            {CATEGORY_OPTIONS.map((category) => (
                              <option key={category} value={category}>
                                {category}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                      <div className="mt-3 space-y-2">
                        <label className="flex items-center gap-2 text-sm text-gray-600">
                          <input
                            type="checkbox"
                            checked={item.autoTag}
                            onChange={(event) => updateUploadCandidate(index, { autoTag: event.target.checked })}
                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          自动生成标签和分类字段
                        </label>
                        {!item.autoTag && (
                          <>
                            <input
                              value={item.manualTags}
                              onChange={(event) => updateUploadCandidate(index, { manualTags: event.target.value })}
                              placeholder="使用逗号分隔多个标签"
                              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                            />

                            {item.category === '政策' && (
                              <div className="grid gap-2 md:grid-cols-2">
                                <label className="text-xs text-gray-600">
                                  效力层级
                                  <select
                                    value={item.effectiveness_level || ''}
                                    onChange={(event) => updateUploadCandidate(index, { effectiveness_level: event.target.value })}
                                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                                  >
                                    <option value="">请选择</option>
                                    <option value="中央">中央</option>
                                    <option value="地方">地方</option>
                                  </select>
                                </label>
                                <label className="text-xs text-gray-600">
                                  文件类型
                                  <input
                                    value={item.document_type || ''}
                                    onChange={(event) => updateUploadCandidate(index, { document_type: event.target.value })}
                                    placeholder="如：条例、指导意见"
                                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                                  />
                                </label>
                              </div>
                            )}

                            {item.category === '论文' && (
                              <div className="grid gap-2 md:grid-cols-2">
                                <label className="text-xs text-gray-600">
                                  学科维度
                                  <input
                                    value={item.discipline || ''}
                                    onChange={(event) => updateUploadCandidate(index, { discipline: event.target.value })}
                                    placeholder="如：法学、管理学"
                                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                                  />
                                </label>
                                <label className="text-xs text-gray-600">
                                  主体内容
                                  <input
                                    value={item.main_topic || ''}
                                    onChange={(event) => updateUploadCandidate(index, { main_topic: event.target.value })}
                                    placeholder="如：社区治理"
                                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                                  />
                                </label>
                              </div>
                            )}

                            {item.category === '案例' && (
                              <div className="grid gap-2 md:grid-cols-2">
                                <label className="text-xs text-gray-600">
                                  地区
                                  <input
                                    value={item.region || ''}
                                    onChange={(event) => updateUploadCandidate(index, { region: event.target.value })}
                                    placeholder="如：北京市"
                                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                                  />
                                </label>
                                <label className="text-xs text-gray-600">
                                  主体内容
                                  <input
                                    value={item.main_topic || ''}
                                    onChange={(event) => updateUploadCandidate(index, { main_topic: event.target.value })}
                                    placeholder="如：社区建设"
                                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                                  />
                                </label>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center justify-between border-t border-gray-100 px-6 py-4">
              <button onClick={() => setShowUploadModal(false)} className="rounded-lg px-4 py-2 text-sm text-gray-600">
                取消
              </button>
              <div className="flex items-center gap-2">
                <button onClick={() => document.getElementById('document-upload-private')?.click()} className="rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700">
                  继续添加
                </button>
                <button
                  onClick={submitUpload}
                  disabled={uploading || uploadQueue.length === 0}
                  className={`inline-flex items-center rounded-lg px-4 py-2 text-sm text-white ${uploading || uploadQueue.length === 0 ? 'bg-blue-200' : 'bg-blue-500'}`}
                >
                  {uploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Check className="mr-2 h-4 w-4" />}
                  {uploading ? '上传中...' : '开始上传'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal - Same as public library */}
      {previewState.open && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6">
          <div className="w-full max-w-2xl rounded-2xl bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">文档预览</h3>
                <p className="text-sm text-gray-500">{previewState.title}</p>
              </div>
              <button onClick={() => setPreviewState((prev) => ({ ...prev, open: false }))} className="rounded-full p-2 text-gray-400 hover:bg-gray-100">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="max-h-[60vh] overflow-y-auto px-6 py-5">
              {previewState.loading ? (
                <div className="flex items-center justify-center py-10 text-gray-500">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  加载预览中...
                </div>
              ) : previewState.content ? (
                <pre className="whitespace-pre-wrap text-sm leading-6 text-gray-700">{previewState.content}</pre>
              ) : (
                <div className="py-10 text-center text-sm text-gray-500">该文件暂无预览内容</div>
              )}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-6 py-4">
              <button onClick={() => setPreviewState((prev) => ({ ...prev, open: false }))} className="rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700">
                关闭
              </button>
              <button
                onClick={() => {
                  const doc = documents.find((item) => item.filename === previewState.filename)
                  if (doc) handleDownload(doc)
                }}
                className="rounded-lg bg-blue-500 px-4 py-2 text-sm text-white"
              >
                下载原文件
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal - Same structure as public library, includes category-specific fields */}
      {editState && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6">
          <div className="w-full max-w-2xl rounded-2xl bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">编辑文档信息</h3>
                <p className="text-sm text-gray-500">{editState.title}</p>
              </div>
              <button onClick={() => setEditState(null)} className="rounded-full p-2 text-gray-400 hover:bg-gray-100">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4 px-6 py-5">
              <label className="text-xs text-gray-600">
                文档标题
                <input
                  value={editState.title}
                  onChange={(event) => setEditState((prev) => (prev ? { ...prev, title: event.target.value } : prev))}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
              </label>
              <label className="text-xs text-gray-600">
                分类
                <select
                  value={editState.category}
                  onChange={(event) => setEditState((prev) => (prev ? { ...prev, category: event.target.value } : prev))}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                >
                  {CATEGORY_OPTIONS.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </label>

              {editState.category === '政策' && (
                <>
                  <label className="text-xs text-gray-600">
                    效力层级
                    <select
                      value={editState.effectiveness_level || ''}
                      onChange={(event) => setEditState((prev) => (prev ? { ...prev, effectiveness_level: event.target.value } : prev))}
                      className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    >
                      <option value="">请选择</option>
                      <option value="中央">中央</option>
                      <option value="地方">地方</option>
                    </select>
                  </label>
                  <label className="text-xs text-gray-600">
                    文件类型
                    <input
                      value={editState.document_type || ''}
                      onChange={(event) => setEditState((prev) => (prev ? { ...prev, document_type: event.target.value } : prev))}
                      placeholder="如：条例、指导意见、通知等"
                      className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    />
                  </label>
                </>
              )}

              {editState.category === '论文' && (
                <>
                  <label className="text-xs text-gray-600">
                    学科维度
                    <input
                      value={editState.discipline || ''}
                      onChange={(event) => setEditState((prev) => (prev ? { ...prev, discipline: event.target.value } : prev))}
                      placeholder="如：法学、工学、管理学等"
                      className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    />
                  </label>
                  <label className="text-xs text-gray-600">
                    主体内容
                    <input
                      value={editState.main_topic || ''}
                      onChange={(event) => setEditState((prev) => (prev ? { ...prev, main_topic: event.target.value } : prev))}
                      placeholder="如：社区治理、智慧城市等"
                      className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    />
                  </label>
                </>
              )}

              {editState.category === '案例' && (
                <>
                  <label className="text-xs text-gray-600">
                    地区
                    <input
                      value={editState.region || ''}
                      onChange={(event) => setEditState((prev) => (prev ? { ...prev, region: event.target.value } : prev))}
                      placeholder="如：北京市、上海市等"
                      className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    />
                  </label>
                  <label className="text-xs text-gray-600">
                    主体内容
                    <input
                      value={editState.main_topic || ''}
                      onChange={(event) => setEditState((prev) => (prev ? { ...prev, main_topic: event.target.value } : prev))}
                      placeholder="如：社区建设、服务优化等"
                      className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    />
                  </label>
                </>
              )}

              <label className="text-xs text-gray-600">
                标签（逗号分隔）
                <textarea
                  value={editState.tagsText}
                  onChange={(event) => setEditState((prev) => (prev ? { ...prev, tagsText: event.target.value } : prev))}
                  rows={3}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
                />
              </label>
            </div>
            <div className="flex items-center justify-between border-t border-gray-100 px-6 py-4">
              <button
                onClick={regenerateTags}
                disabled={editState.regenerating}
                className={`inline-flex items-center rounded-lg px-3 py-2 text-sm ${
                  editState.regenerating ? 'bg-blue-100 text-blue-500' : 'bg-blue-50 text-blue-600'
                }`}
              >
                {editState.regenerating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
                {editState.regenerating ? '生成中...' : '自动生成标签'}
              </button>
              <div className="flex items-center gap-2">
                <button onClick={() => setEditState(null)} className="rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700">
                  取消
                </button>
                <button
                  onClick={submitEdit}
                  disabled={editState.saving}
                  className={`inline-flex items-center rounded-lg px-4 py-2 text-sm text-white ${
                    editState.saving ? 'bg-blue-200' : 'bg-blue-500'
                  }`}
                >
                  {editState.saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Check className="mr-2 h-4 w-4" />}
                  {editState.saving ? '保存中...' : '保存修改'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
