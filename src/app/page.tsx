'use client'

import Link from 'next/link'
import { motion } from 'framer-motion'
import { MessageSquare, Lightbulb, ScrollText, BookOpen, Database, GraduationCap, ArrowRight, Sparkles, Zap, FileSearch, Library } from 'lucide-react'

const modules = [
  {
    title: 'AI 智能问答',
    desc: '基于 DeepSeek 大模型，支持基础对话、深度研究和数据分析，知识库文档自动关联引用。',
    icon: MessageSquare,
    color: 'from-blue-500 to-blue-600',
    bg: 'bg-blue-50',
    iconColor: 'text-blue-600',
    href: '/chat'
  },
  {
    title: '概念解析',
    desc: '输入公共管理学科术语，AI 生成结构化解析卡片——定义、要素、理论渊源、案例与推荐阅读。',
    icon: Lightbulb,
    color: 'from-amber-500 to-orange-500',
    bg: 'bg-amber-50',
    iconColor: 'text-amber-600',
    href: '/concepts'
  },
  {
    title: '论文阅读',
    desc: '上传 PDF/Word/TXT，AI 自动生成结构化速读摘要与论文写作大纲。',
    icon: ScrollText,
    color: 'from-emerald-500 to-teal-600',
    bg: 'bg-emerald-50',
    iconColor: 'text-emerald-600',
    href: '/papers'
  },
  {
    title: '案例分析',
    desc: '按公共管理分析框架深度解析案例——利益相关方、政策工具、治理机制与效果评估。',
    icon: BookOpen,
    color: 'from-violet-500 to-purple-600',
    bg: 'bg-violet-50',
    iconColor: 'text-violet-600',
    href: '/cases'
  },
  {
    title: '知识库管理',
    desc: '163+ 篇公共管理学术论文，支持 PDF 上传、分类标签、向量检索与 RAG 增强问答。',
    icon: Database,
    color: 'from-indigo-500 to-indigo-600',
    bg: 'bg-indigo-50',
    iconColor: 'text-indigo-600',
    href: '/documents'
  },
  {
    title: '教学工具',
    desc: '随堂测验生成 + 教案智能生成——基于知识库内容，一键生成试卷与教学方案。',
    icon: Zap,
    color: 'from-rose-500 to-pink-600',
    bg: 'bg-rose-50',
    iconColor: 'text-rose-600',
    href: '/teaching'
  },
  {
    title: '智能预审稿',
    desc: '千章预审稿系统——论文提交前的最后一道防线，10 模块全方位审查文献、深度、语言、格式。',
    icon: FileSearch,
    color: 'from-orange-500 to-red-600',
    bg: 'bg-orange-50',
    iconColor: 'text-orange-600',
    href: '/pre-review'
  },
  {
    title: '选题综述',
    desc: '输入选题，AI 给出选题建议、检索中英文献并生成文献综述，一键导出文献 Excel 表。',
    icon: Library,
    color: 'from-cyan-500 to-sky-600',
    bg: 'bg-cyan-50',
    iconColor: 'text-cyan-600',
    href: '/topic-review'
  }
]

export default function Home() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Background */}
      <div className="fixed inset-0 -z-10">
        {/* Background image */}
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: 'url(/bg.jpg)' }}
        />
        {/* Dark overlay for text readability */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900/90 via-indigo-950/85 to-blue-950/90" />
        {/* Subtle grid pattern */}
        <div className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='1'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
            backgroundSize: '60px 60px'
          }}
        />
      </div>

      {/* Content */}
      <div className="relative max-w-6xl mx-auto px-6 py-16">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="text-center mb-20"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.2 }}
            className="inline-flex items-center gap-2 px-4 py-1.5 bg-white/10 backdrop-blur-sm border border-white/10 rounded-full mb-8"
          >
            <Sparkles className="w-3.5 h-3.5 text-blue-400" />
            <span className="text-xs text-blue-200">山东大学政治学与公共管理学院</span>
          </motion.div>

          <h1 className="text-5xl md:text-6xl font-extrabold text-white mb-6 tracking-tight leading-tight">
            山大公管
            <span className="bg-gradient-to-r from-blue-400 via-indigo-300 to-violet-400 bg-clip-text text-transparent">
              智能体
            </span>
          </h1>
          <p className="text-lg text-blue-200/80 max-w-2xl mx-auto leading-relaxed mb-10">
            面向公共管理学科的 AI 教学助手 ——
            融合大语言模型与学科专业知识，
            为课程学习、论文写作、案例分析提供智能支持
          </p>

          <div className="flex items-center justify-center gap-4">
            <Link
              href="/chat"
              className="group inline-flex items-center gap-2 px-6 py-3.5 bg-gradient-to-r from-blue-500 to-indigo-600 text-white rounded-xl text-sm font-semibold hover:from-blue-400 hover:to-indigo-500 shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 transition-all"
            >
              <MessageSquare className="w-4 h-4" />
              开始对话
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <Link
              href="/pre-review"
              className="inline-flex items-center gap-2 px-6 py-3.5 bg-gradient-to-r from-orange-500 to-red-600 text-white rounded-xl text-sm font-semibold hover:from-orange-400 hover:to-red-500 shadow-lg shadow-orange-500/25 hover:shadow-orange-500/40 transition-all"
            >
              <FileSearch className="w-4 h-4" />
              千章预审稿
            </Link>
            <Link
              href="/documents"
              className="inline-flex items-center gap-2 px-6 py-3.5 bg-white/10 backdrop-blur-sm text-white border border-white/10 rounded-xl text-sm font-semibold hover:bg-white/15 hover:border-white/20 transition-all"
            >
              <Database className="w-4 h-4" />
              浏览知识库
            </Link>
          </div>

          {/* Stats */}
          <div className="flex items-center justify-center gap-8 mt-12">
            {[
              { value: '163+', label: '学术论文' },
              { value: '3109', label: '知识三元组' },
              { value: 'DeepSeek', label: '驱动模型' },
              { value: '8', label: '功能模块' }
            ].map(s => (
              <div key={s.label} className="text-center">
                <div className="text-2xl font-bold text-white">{s.value}</div>
                <div className="text-xs text-blue-300/60 mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        </motion.div>

        {/* Feature Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {modules.map((mod, i) => (
            <motion.div
              key={mod.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 * (i + 1), duration: 0.5 }}
            >
              <Link href={mod.href}>
                <div className="group bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 hover:bg-white/10 hover:border-white/20 transition-all duration-300 h-full">
                  <div className={`w-10 h-10 ${mod.bg} ${mod.iconColor} rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                    <mod.icon className="w-5 h-5" />
                  </div>
                  <h3 className="text-base font-bold text-white mb-2">{mod.title}</h3>
                  <p className="text-sm text-blue-200/60 leading-relaxed">{mod.desc}</p>
                  <div className="mt-4 flex items-center gap-1 text-xs font-medium text-blue-300/40 group-hover:text-blue-400 transition-colors">
                    进入 <ArrowRight className="w-3 h-3" />
                  </div>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>

        {/* Footer */}
        <div className="text-center mt-20 pb-6">
          <div className="inline-flex items-center gap-2 text-xs text-blue-300/30">
            <GraduationCap className="w-3.5 h-3.5" />
            公共管理+信息双学位实训项目
          </div>
        </div>
      </div>
    </div>
  )
}
