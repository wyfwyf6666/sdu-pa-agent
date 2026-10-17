// src/app/history/page.tsx

'use client';

import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import {
  Calendar,
  Clock,
  User,
  FileText,
  Upload,
  MessageSquare,
  CheckCircle,
  XCircle,
  Search
} from 'lucide-react';
import MainLayout from '@/components/layout/MainLayout';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchHistory, HistoryItem } from '@/services/history';

// —— 在这里定义每种类型对应的图标组件 ——
const TYPE_ICONS: Record<HistoryItem['type'], JSX.Element> = {
  document: <FileText className="w-5 h-5" />,
  chat: <MessageSquare className="w-5 h-5" />,
  login: <User className="w-5 h-5" />,
  upload: <Upload className="w-5 h-5" />,
  approval: <CheckCircle className="w-5 h-5" />,  // 审批成功默认用 CheckCircle，状态不同可后续调整
};

const TYPE_STYLES = {
  document: {
    bg: 'bg-blue-50',
    text: 'text-blue-600',
    border: 'border-blue-100',
    hover: 'hover:bg-blue-100/50',
  },
  chat: {
    bg: 'bg-green-50',
    text: 'text-green-600',
    border: 'border-green-100',
    hover: 'hover:bg-green-100/50',
  },
  login: {
    bg: 'bg-purple-50',
    text: 'text-purple-600',
    border: 'border-purple-100',
    hover: 'hover:bg-purple-100/50',
  },
  upload: {
    bg: 'bg-orange-50',
    text: 'text-orange-600',
    border: 'border-orange-100',
    hover: 'hover:bg-orange-100/50',
  },
  approval: {
    bg: 'bg-rose-50',
    text: 'text-rose-600',
    border: 'border-rose-100',
    hover: 'hover:bg-rose-100/50',
  },
};

export default function HistoryPage() {
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  const [filter, setFilter] = useState<'all' | 'document' | 'chat' | 'login' | 'upload' | 'approval'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [dateRange, setDateRange] = useState<{ start: Date; end: Date }>({
    start: new Date(new Date().setDate(new Date().getDate() - 30)),
    end: new Date(),
  });

  useEffect(() => {
    setLoading(true);
    fetchHistory({
      start: dateRange.start.toISOString(),
      end: dateRange.end.toISOString(),
      type: filter === 'all' ? undefined : filter,
      query: searchQuery || undefined,
    })
      .then((data) => setHistory(data))
      .catch((err) => console.error('加载历史记录失败', err))
      .finally(() => setLoading(false));
  }, [filter, searchQuery, dateRange]);

  const filteredHistory = history;

  return (
    <MainLayout>
      <div className="gradient-bg min-h-screen">
        <div className="max-w-7xl mx-auto px-4 py-8">
          {/* 头部 */}
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 border border-gray-100 mb-6"
          >
            <h1 className="text-2xl font-semibold text-gray-900 bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-blue-800 mb-4">
              操作历史
            </h1>
            {/* 搜索和筛选 */}
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex-1 min-w-[300px] relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
                <input
                  type="text"
                  placeholder="搜索历史记录..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 bg-white/50 backdrop-blur-sm border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>
              <div
                className="flex items-center gap-2 bg-white/50 backdrop-blur-sm px-4 py-2 rounded-xl border border-gray-200 cursor-pointer hover:bg-white/70"
                onClick={() => {
                  setDateRange({
                    start: new Date(new Date().setDate(new Date().getDate() - 30)),
                    end: new Date(),
                  });
                }}
              >
                <Calendar className="w-5 h-5 text-gray-500" />
                <span className="text-gray-600">
                  {format(dateRange.start, 'yyyy-MM-dd')} - {format(dateRange.end, 'yyyy-MM-dd')}
                </span>
              </div>
            </div>
          </motion.div>

          {/* 过滤器 */}
          <div className="flex flex-wrap gap-2 mb-6">
            {[
              { value: 'all', label: '全部' },
              { value: 'document', label: '文档' },
              { value: 'chat', label: '对话' },
              { value: 'approval', label: '审批' },
              { value: 'upload', label: '上传' },
              { value: 'login', label: '登录' },
            ].map((item) => (
              <button
                key={item.value}
                onClick={() => setFilter(item.value as any)}
                className={`px-4 py-2 rounded-xl transition-all duration-200 ${
                  filter === item.value
                    ? 'bg-blue-500 text-white shadow-sm'
                    : 'bg-white/80 hover:bg-white text-gray-600'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          {/* 历史记录列表 */}
          <motion.div layout className="space-y-4">
            <AnimatePresence>
              {loading ? (
                <div className="text-center py-4 text-gray-500">加载中...</div>
              ) : filteredHistory.length > 0 ? (
                filteredHistory.map((item) => {
                  const styles = TYPE_STYLES[item.type];
                  return (
                    <motion.div
                      key={item.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -20 }}
                      className={`bg-white/80 backdrop-blur-sm rounded-xl border ${styles.border} p-4 hover:shadow-sm transition-all duration-200 ${styles.hover}`}
                    >
                      <div className="flex items-start gap-4">
                        <div className={`${styles.bg} ${styles.text} p-3 rounded-xl`}>
                          {TYPE_ICONS[item.type]}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium text-gray-900">{item.title}</h3>
                            {item.status && (
                              <span
                                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                  item.status === 'success'
                                    ? 'bg-green-100 text-green-800'
                                    : item.status === 'error'
                                    ? 'bg-red-100 text-red-800'
                                    : 'bg-yellow-100 text-yellow-800'
                                }`}
                              >
                                {item.status === 'success'
                                  ? '成功'
                                  : item.status === 'error'
                                  ? '失败'
                                  : '处理中'}
                              </span>
                            )}
                          </div>
                          <p className="text-gray-600 mt-1">{item.description}</p>
                          {item.details && (
                            <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
                              {item.details.fileSize && (
                                <span className="flex items-center gap-1">
                                  <FileText className="w-4 h-4" />
                                  {item.details.fileSize}
                                </span>
                              )}
                              {item.details.duration && (
                                <span className="flex items-center gap-1">
                                  <Clock className="w-4 h-4" />
                                  {item.details.duration}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                        <div className="flex flex-col items-end gap-2">
                          <div className="flex items-center text-sm text-gray-500">
                            <User className="w-4 h-4 mr-1" />
                            {item.user}
                          </div>
                          <div className="text-sm text-gray-500">
                            {format(new Date(item.timestamp), 'yyyy-MM-dd HH:mm')}
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  );
                })
              ) : (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-center py-12 bg-white/80 backdrop-blur-sm rounded-2xl"
                >
                  <Clock className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    暂无历史记录
                  </h3>
                  <p className="text-gray-500">
                    该时间范围内没有符合筛选条件的操作记录
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </div>
    </MainLayout>
  );
}
