'use client';

import { useState, useRef } from 'react';
import { Upload, X, FileText, AlertCircle } from 'lucide-react';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (formData: FormData) => Promise<void>;
}

export default function UploadDialog({ isOpen, onClose, onUpload }: Props) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [category, setCategory] = useState('未分类');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      setSelectedFile(droppedFile);
      setTitle(droppedFile.name.split('.')[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setTitle(file.name.split('.')[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    try {
      setUploading(true);
      setError(null);
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('title', title);
      formData.append('category', category);
      await onUpload(formData);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败');
    } finally {
      setUploading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />

      {/* 上传对话框 */}
      <div className="relative bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
        >
          <X className="h-5 w-5" />
        </button>

        <h2 className="text-xl font-semibold mb-4">上传文件</h2>

        <form onSubmit={handleSubmit}>
          {/* 拖放区域 */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            className="border-2 border-dashed border-gray-300 rounded-lg p-8 mb-4 text-center cursor-pointer"
            onClick={() => fileInputRef.current?.click()}
          >
            {selectedFile ? (
              <div className="flex items-center justify-center space-x-3">
                <FileText className="h-6 w-6 text-blue-500" />
                <span className="text-gray-600">{selectedFile.name}</span>
              </div>
            ) : (
              <div>
                <Upload className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                <p className="text-gray-600">拖放文件到此处或点击选择文件</p>
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.csv,.xlsx,.xls,.json"
            onChange={handleFileSelect}
            className="hidden"
          />

          {/* 文件信息表单 */}
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                标题
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                分类
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="未分类">未分类</option>
                <option value="政策文件">政策文件</option>
                <option value="流程文档">流程文档</option>
                <option value="会议记录">会议记录</option>
                <option value="数据报表">数据报表</option>
              </select>
            </div>

            {error && (
              <div className="flex items-center space-x-2 text-red-500 text-sm">
                <AlertCircle className="h-4 w-4" />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={!selectedFile || uploading}
              className={`w-full py-2 px-4 rounded-md text-white font-medium 
                ${
                  !selectedFile || uploading
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-blue-500 hover:bg-blue-600'
                }
              `}
            >
              {uploading ? '上传中...' : '上传'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
