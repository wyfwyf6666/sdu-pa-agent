'use client';

import { useState } from 'react';
import { File, MessageSquare, Star, Trash2 } from 'lucide-react';
import MainLayout from '@/components/layout/MainLayout';
import { motion } from 'framer-motion';

interface FavoriteItem {
  id: string;
  type: 'document' | 'chat';
  title: string;
  description: string;
  date: Date;
  icon: JSX.Element;
}

const mockFavorites: FavoriteItem[] = [
  {
    id: '1',
    type: 'document',
    title: '2024年政策规划.pdf',
    description: '关于2024年度政策实施的详细规划文件',
    date: new Date('2024-01-10'),
    icon: <File className="w-5 h-5" />,
  },
  {
    id: '2',
    type: 'chat',
    title: '预算规划讨论',
    description: '与AI助手关于部门预算编制的重要对话',
    date: new Date('2024-01-12'),
    icon: <MessageSquare className="w-5 h-5" />,
  },
];

export default function FavoritesPage() {
  const [favorites, setFavorites] = useState<FavoriteItem[]>(mockFavorites);
  const [filter, setFilter] = useState<'all' | 'document' | 'chat'>('all');

  const filteredFavorites = favorites.filter(
    item => filter === 'all' || item.type === filter
  );

  const removeFavorite = (id: string) => {
    setFavorites(favorites.filter(item => item.id !== id));
  };

  return (
    <MainLayout>
      <div className="bg-white rounded-lg shadow-sm p-6">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 border border-gray-100 mb-6"
        >
          <h1 className="text-2xl font-semibold text-gray-900 bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-blue-800">
            我的收藏
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            快速访问您收藏的文档和对话记录
          </p>
        </motion.div>

        {/* 过滤器 */}
        <div className="mb-8 bg-gray-50 p-4 rounded-lg">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setFilter('all')}
              className={`px-4 py-2 rounded-lg transition-all duration-200 ${
                filter === 'all'
                  ? 'bg-blue-500 text-white shadow-md'
                  : 'bg-white hover:bg-gray-100'
              }`}
            >
              全部
            </button>
            <button
              onClick={() => setFilter('document')}
              className={`px-4 py-2 rounded-lg transition-all duration-200 ${
                filter === 'document'
                  ? 'bg-blue-500 text-white shadow-md'
                  : 'bg-white hover:bg-gray-100'
              }`}
            >
              文档
            </button>
            <button
              onClick={() => setFilter('chat')}
              className={`px-4 py-2 rounded-lg transition-all duration-200 ${
                filter === 'chat'
                  ? 'bg-blue-500 text-white shadow-md'
                  : 'bg-white hover:bg-gray-100'
              }`}
            >
              对话
            </button>
          </div>
        </div>

        {/* 收藏列表 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredFavorites.map((item) => (
            <div
              key={item.id}
              className="bg-gray-50 rounded-lg p-4 group hover:bg-gray-100 transition-all duration-200"
            >
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center shadow-sm">
                    {item.icon}
                  </div>
                  <div>
                    <h3 className="font-medium text-gray-900">{item.title}</h3>
                    <span className="text-sm text-gray-500">
                      {item.type === 'document' ? '文档' : '对话'}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => removeFavorite(item.id)}
                  className="text-gray-400 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100"
                >
                  <Trash2 className="w-5 h-5" />
                </button>
              </div>
              <p className="text-gray-600 text-sm mb-4 line-clamp-2">{item.description}</p>
              <div className="flex justify-between items-center text-sm text-gray-500">
                <div className="flex items-center gap-1">
                  <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                  <span>已收藏</span>
                </div>
                <span>
                  {item.date.toLocaleDateString('zh-CN', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                  })}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* 空状态 */}
        {filteredFavorites.length === 0 && (
          <div className="text-center py-12">
            <Star className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              暂无收藏内容
            </h3>
            <p className="text-gray-500">
              浏览文档或对话时，点击星标即可添加到收藏夹
            </p>
          </div>
        )}
      </div>
    </MainLayout>
  );
}
