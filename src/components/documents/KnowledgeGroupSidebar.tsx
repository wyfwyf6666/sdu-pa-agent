'use client'

import { useState } from 'react'
import { Plus, FolderOpen, Pencil, Trash2, X, Check, Loader2 } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { apiFetch } from '@/lib/api'

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

interface KnowledgeGroupSidebarProps {
  groups: KnowledgeGroup[]
  selectedGroupId: string | null
  onSelectGroup: (groupId: string | null) => void
  onRefresh: () => void
}

export default function KnowledgeGroupSidebar({
  groups,
  selectedGroupId,
  onSelectGroup,
  onRefresh,
}: KnowledgeGroupSidebarProps) {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingGroup, setEditingGroup] = useState<KnowledgeGroup | null>(null)
  const [formData, setFormData] = useState({ name: '', description: '' })
  const [saving, setSaving] = useState(false)

  const handleCreate = async () => {
    if (!formData.name.trim()) {
      toast.error('请输入知识组名称')
      return
    }

    setSaving(true)
    try {
      const response = await apiFetch('/api/v1/knowledge-groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name.trim(),
          description: formData.description.trim(),
        }),
      })

      if (!response.ok) throw new Error('创建知识组失败')
      const data = await response.json()
      if (data.status !== 'success') throw new Error(data.message || '创建知识组失败')

      toast.success('知识组创建成功')
      setShowCreateModal(false)
      setFormData({ name: '', description: '' })
      onRefresh()
    } catch (error) {
      toast.error((error as Error).message || '创建知识组失败')
    } finally {
      setSaving(false)
    }
  }

  const handleUpdate = async () => {
    if (!editingGroup || !formData.name.trim()) {
      toast.error('请输入知识组名称')
      return
    }

    setSaving(true)
    try {
      const response = await apiFetch(`/api/v1/knowledge-groups/${editingGroup.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: formData.name.trim(),
          description: formData.description.trim(),
        }),
      })

      if (!response.ok) throw new Error('更新知识组失败')
      const data = await response.json()
      if (data.status !== 'success') throw new Error(data.message || '更新知识组失败')

      toast.success('知识组更新成功')
      setEditingGroup(null)
      setFormData({ name: '', description: '' })
      onRefresh()
    } catch (error) {
      toast.error((error as Error).message || '更新知识组失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (group: KnowledgeGroup) => {
    const confirmMsg =
      group.document_count > 0
        ? `知识组"${group.name}"中有 ${group.document_count} 个文档，确定要删除吗？文档也将被删除。`
        : `确定删除知识组"${group.name}"吗？`

    if (!confirm(confirmMsg)) return

    try {
      const response = await apiFetch(
        `/api/v1/knowledge-groups/${group.id}?force=${group.document_count > 0}`,
        {
          method: 'DELETE',
        }
      )

      if (!response.ok) throw new Error('删除知识组失败')
      const data = await response.json()
      if (data.status !== 'success') throw new Error(data.message || '删除知识组失败')

      toast.success('知识组删除成功')
      if (selectedGroupId === group.id) {
        onSelectGroup(null)
      }
      onRefresh()
    } catch (error) {
      toast.error((error as Error).message || '删除知识组失败')
    }
  }

  const openEditModal = (group: KnowledgeGroup) => {
    setEditingGroup(group)
    setFormData({
      name: group.name,
      description: group.description || '',
    })
  }

  const closeModals = () => {
    setShowCreateModal(false)
    setEditingGroup(null)
    setFormData({ name: '', description: '' })
    setSaving(false)
  }

  return (
    <>
      <div className="flex h-full flex-col rounded-2xl border border-gray-100 bg-white shadow-sm">
        <div className="border-b border-gray-100 p-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-gray-900">知识组</h3>
            <button
              onClick={() => setShowCreateModal(true)}
              className="rounded-lg bg-blue-500 p-2 text-white hover:bg-blue-600"
              title="创建知识组"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {groups.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-gray-500">
              暂无知识组
              <br />
              点击上方按钮创建
            </div>
          ) : (
            <div className="space-y-1">
              {groups.map((group) => (
                <div
                  key={group.id}
                  className={`group relative rounded-lg p-3 transition-colors ${
                    selectedGroupId === group.id
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <button
                    onClick={() => onSelectGroup(group.id)}
                    className="flex w-full items-start gap-3 text-left"
                  >
                    <FolderOpen className="mt-0.5 h-5 w-5 flex-shrink-0" />
                    <div className="flex-1 overflow-hidden">
                      <div className="truncate font-medium">{group.name}</div>
                      {group.description && (
                        <div className="mt-0.5 truncate text-xs text-gray-500">
                          {group.description}
                        </div>
                      )}
                      <div className="mt-1 text-xs text-gray-500">
                        {group.document_count} 个文档
                      </div>
                    </div>
                  </button>

                  <div className="absolute right-2 top-2 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        openEditModal(group)
                      }}
                      className="rounded p-1 text-gray-400 hover:bg-white hover:text-blue-600"
                      title="编辑"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDelete(group)
                      }}
                      className="rounded p-1 text-gray-400 hover:bg-white hover:text-red-600"
                      title="删除"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
              <h2 className="text-lg font-semibold text-gray-900">创建知识组</h2>
              <button
                onClick={closeModals}
                className="rounded-full p-2 text-gray-400 hover:bg-gray-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4 px-6 py-5">
              <label className="block text-sm text-gray-700">
                知识组名称 *
                <input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="如：城市治理研究"
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  autoFocus
                />
              </label>
              <label className="block text-sm text-gray-700">
                描述
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="简要描述这个知识组的用途"
                  rows={3}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                />
              </label>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-6 py-4">
              <button
                onClick={closeModals}
                className="rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700 hover:bg-gray-200"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={saving || !formData.name.trim()}
                className={`inline-flex items-center rounded-lg px-4 py-2 text-sm text-white ${
                  saving || !formData.name.trim() ? 'bg-blue-300' : 'bg-blue-500 hover:bg-blue-600'
                }`}
              >
                {saving ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    创建中...
                  </>
                ) : (
                  <>
                    <Check className="mr-2 h-4 w-4" />
                    创建
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editingGroup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-6">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
              <h2 className="text-lg font-semibold text-gray-900">编辑知识组</h2>
              <button
                onClick={closeModals}
                className="rounded-full p-2 text-gray-400 hover:bg-gray-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4 px-6 py-5">
              <label className="block text-sm text-gray-700">
                知识组名称 *
                <input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="如：城市治理研究"
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                  autoFocus
                />
              </label>
              <label className="block text-sm text-gray-700">
                描述
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="简要描述这个知识组的用途"
                  rows={3}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
                />
              </label>
              <div className="rounded-lg bg-gray-50 p-3 text-xs text-gray-600">
                <div>ID: {editingGroup.id}</div>
                <div>文档数: {editingGroup.document_count}</div>
                <div>创建时间: {new Date(editingGroup.created_time).toLocaleString()}</div>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-gray-100 px-6 py-4">
              <button
                onClick={closeModals}
                className="rounded-lg bg-gray-100 px-4 py-2 text-sm text-gray-700 hover:bg-gray-200"
              >
                取消
              </button>
              <button
                onClick={handleUpdate}
                disabled={saving || !formData.name.trim()}
                className={`inline-flex items-center rounded-lg px-4 py-2 text-sm text-white ${
                  saving || !formData.name.trim() ? 'bg-blue-300' : 'bg-blue-500 hover:bg-blue-600'
                }`}
              >
                {saving ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    保存中...
                  </>
                ) : (
                  <>
                    <Check className="mr-2 h-4 w-4" />
                    保存
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
