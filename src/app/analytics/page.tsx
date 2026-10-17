'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  BarChart2,
  TrendingUp,
  Users,
  AlertTriangle,
  Brain,
  FileText,
  MessageSquare,
  Activity,
  Calendar,
  ArrowUp,
  ArrowDown,
} from 'lucide-react'
import MainLayout from '@/components/layout/MainLayout'
import ContentLayout from '@/components/layout/ContentLayout'
import Link from 'next/link'
import { motion } from 'framer-motion'

// 模拟数据
const kpiData = {
  serviceEfficiency: { value: 92.5, trend: 'up', change: 5.2 },
  satisfaction: { value: 88.7, trend: 'up', change: 3.8 },
  processTime: { value: 2.3, trend: 'down', change: 15.4 },
  riskIndex: { value: 1.2, trend: 'down', change: 8.9 },
}

const aiInsights = [
  {
    title: '政策执行效果预测',
    description: '基于历史数据分析，新版行政审批制度预计将提升效率约25%',
    type: 'prediction',
    confidence: 89,
  },
  {
    title: '民意反馈分析',
    description: '近期群众反馈主要集中在办事流程简化方面，建议优化线上服务',
    type: 'sentiment',
    confidence: 92,
  },
  {
    title: '异常预警提示',
    description: '检测到某些部门审批时间异常延长，建议及时干预',
    type: 'warning',
    confidence: 85,
  },
]

const departmentPerformance = [
  { id: '1', name: '市民服务中心', efficiency: 94, satisfaction: 92, workload: 456 },
  { id: '2', name: '税务管理部门', efficiency: 88, satisfaction: 85, workload: 389 },
  { id: '3', name: '社会保障部门', efficiency: 91, satisfaction: 89, workload: 567 },
  { id: '4', name: '公共事业部门', efficiency: 86, satisfaction: 88, workload: 423 },
]

export default function AnalyticsPage() {
  const [timeRange, setTimeRange] = useState('month')

  return (
    <MainLayout>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* 头部 */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white/80 backdrop-blur-sm rounded-2xl p-6 border border-gray-100 mb-6"
        >
          <h1 className="text-2xl font-semibold text-gray-900 bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-blue-800">
            业务数据
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            全面的数据分析和可视化，助您洞察业务趋势
          </p>
        </motion.div>

        {/* 时间范围选择 */}
        <div className="mb-6 flex justify-end">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="week">本周</option>
            <option value="month">本月</option>
            <option value="quarter">本季度</option>
            <option value="year">本年度</option>
          </select>
        </div>

        {/* KPI指标卡片 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">服务效率指数</p>
                <p className="text-2xl font-semibold text-blue-600">{kpiData.serviceEfficiency.value}%</p>
                <div className="flex items-center mt-1">
                  {kpiData.serviceEfficiency.trend === 'up' ? (
                    <ArrowUp className="h-4 w-4 text-green-500" />
                  ) : (
                    <ArrowDown className="h-4 w-4 text-red-500" />
                  )}
                  <span className="text-sm text-green-500">+{kpiData.serviceEfficiency.change}%</span>
                </div>
              </div>
              <Activity className="h-8 w-8 text-blue-500" />
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">群众满意度</p>
                <p className="text-2xl font-semibold text-green-600">{kpiData.satisfaction.value}%</p>
                <div className="flex items-center mt-1">
                  {kpiData.satisfaction.trend === 'up' ? (
                    <ArrowUp className="h-4 w-4 text-green-500" />
                  ) : (
                    <ArrowDown className="h-4 w-4 text-red-500" />
                  )}
                  <span className="text-sm text-green-500">+{kpiData.satisfaction.change}%</span>
                </div>
              </div>
              <Users className="h-8 w-8 text-green-500" />
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">平均办理时长</p>
                <p className="text-2xl font-semibold text-orange-600">{kpiData.processTime.value}天</p>
                <div className="flex items-center mt-1">
                  {kpiData.processTime.trend === 'down' ? (
                    <ArrowDown className="h-4 w-4 text-green-500" />
                  ) : (
                    <ArrowUp className="h-4 w-4 text-red-500" />
                  )}
                  <span className="text-sm text-green-500">-{kpiData.processTime.change}%</span>
                </div>
              </div>
              <Calendar className="h-8 w-8 text-orange-500" />
            </div>
          </div>
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">风险指数</p>
                <p className="text-2xl font-semibold text-red-600">{kpiData.riskIndex.value}</p>
                <div className="flex items-center mt-1">
                  {kpiData.riskIndex.trend === 'down' ? (
                    <ArrowDown className="h-4 w-4 text-green-500" />
                  ) : (
                    <ArrowUp className="h-4 w-4 text-red-500" />
                  )}
                  <span className="text-sm text-green-500">-{kpiData.riskIndex.change}%</span>
                </div>
              </div>
              <AlertTriangle className="h-8 w-8 text-red-500" />
            </div>
          </div>
        </div>

        {/* AI 洞察 */}
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center">
            <Brain className="h-5 w-5 mr-2 text-purple-500" />
            AI 智能洞察
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {aiInsights.map((insight, index) => (
              <div
                key={index}
                className="bg-white p-4 rounded-lg border border-gray-200 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-medium text-gray-900">{insight.title}</h3>
                    <p className="mt-1 text-sm text-gray-500">{insight.description}</p>
                    <div className="mt-2 flex items-center">
                      <div className="text-xs text-gray-500">AI 置信度：</div>
                      <div className="ml-2 flex items-center">
                        <div className="w-24 h-2 bg-gray-200 rounded-full">
                          <div
                            className="h-2 bg-purple-500 rounded-full"
                            style={{ width: `${insight.confidence}%` }}
                          ></div>
                        </div>
                        <span className="ml-2 text-xs text-gray-500">{insight.confidence}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 部门绩效 */}
        <div className="mb-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center">
            <BarChart2 className="h-5 w-5 mr-2 text-blue-500" />
            部门绩效分析
          </h2>
          <div className="overflow-x-auto">
            <table className="min-w-full bg-white rounded-lg">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    部门名称
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    办事效率
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    满意度
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    工作量
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    AI 建议
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {departmentPerformance.map((dept, index) => (
                  <tr key={index}>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {dept.name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="w-24 h-2 bg-gray-200 rounded-full">
                          <div
                            className="h-2 bg-blue-500 rounded-full"
                            style={{ width: `${dept.efficiency}%` }}
                          ></div>
                        </div>
                        <span className="ml-2 text-sm text-gray-500">{dept.efficiency}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div className="w-24 h-2 bg-gray-200 rounded-full">
                          <div
                            className="h-2 bg-green-500 rounded-full"
                            style={{ width: `${dept.satisfaction}%` }}
                          ></div>
                        </div>
                        <span className="ml-2 text-sm text-gray-500">{dept.satisfaction}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {dept.workload}件
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-blue-600">
                      <Link 
                        href={`/analytics/${dept.id}`}
                        className="text-blue-600 hover:text-blue-800"
                      >
                        查看AI分析报告
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </MainLayout>
  )
}
