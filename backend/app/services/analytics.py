from typing import Dict, List, Any
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import json
from backend.app.services.chat import chat_service
import os

class AnalyticsService:
    def __init__(self):
        root_dir = Path(__file__).resolve().parents[3]
        self.data_dir = root_dir / "backend" / "data"
        self.excel_dir = self.data_dir / "excel"
        self.approvals_file = self.data_dir / "approvals.json"

        # 确保目录存在
        self.excel_dir.mkdir(parents=True, exist_ok=True)

    async def process_excel(self, file_path: str, sheet_name: str = None) -> Dict[str, Any]:
        """处理上传的Excel文件"""
        try:
            # 确保文件存在
            if not os.path.exists(file_path):
                return {
                    "status": "error",
                    "message": "文件不存在"
                }

            # 尝试读取Excel文件
            try:
                # 确保返回的是 DataFrame 对象
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                if not isinstance(df, pd.DataFrame):
                    if isinstance(df, dict):
                        # 如果返回的是字典（多个sheet的情况），使用第一个sheet
                        sheet_name = list(df.keys())[0]
                        df = df[sheet_name]
                    else:
                        return {
                            "status": "error",
                            "message": "无法正确读取Excel文件格式"
                        }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"无法读取Excel文件: {str(e)}"
                }

            # 检查数据是否为空
            if len(df) == 0:
                return {
                    "status": "error",
                    "message": "Excel文件没有数据"
                }

            try:
                # 处理 NaN 和 Infinity 值
                df = df.replace([np.inf, -np.inf], np.nan)
                
                # 基本统计信息
                stats = {
                    "total_rows": len(df),
                    "total_columns": len(df.columns),
                    "columns": df.columns.tolist()
                }

                # 尝试生成数值列的统计信息
                try:
                    numeric_df = df.select_dtypes(include=[np.number])
                    if not numeric_df.empty:
                        # 将统计结果转换为普通Python类型
                        summary_dict = numeric_df.describe().to_dict()
                        stats["numeric_summary"] = {
                            col: {
                                k: (float(v) if not pd.isna(v) else None)
                                for k, v in values.items()
                            }
                            for col, values in summary_dict.items()
                        }
                    else:
                        stats["numeric_summary"] = {}
                except Exception as e:
                    print(f"生成数值统计信息失败: {str(e)}")
                    stats["numeric_summary"] = {}

                # 生成预览数据
                preview_data = df.head(5)
                # 将 DataFrame 转换为字典，处理特殊值
                preview_dict = []
                for record in preview_data.to_dict('records'):
                    cleaned_record = {}
                    for key, value in record.items():
                        if pd.isna(value):
                            cleaned_record[key] = None
                        elif isinstance(value, (np.int64, np.int32)):
                            cleaned_record[key] = int(value)
                        elif isinstance(value, (np.float64, np.float32)):
                            cleaned_record[key] = None if np.isnan(value) else float(value)
                        else:
                            cleaned_record[key] = str(value)
                    preview_dict.append(cleaned_record)
                
                stats["preview"] = preview_dict

                return {
                    "status": "success",
                    "data": stats,
                    "message": "Excel文件处理成功"
                }
            except Exception as e:
                print(f"处理统计信息失败: {str(e)}")
                return {
                    "status": "error",
                    "message": f"处理统计信息失败: {str(e)}"
                }

        except Exception as e:
            print(f"处理Excel文件失败: {str(e)}")
            return {
                "status": "error",
                "message": f"处理Excel文件失败: {str(e)}"
            }
        finally:
            # 清理临时文件
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass

    async def get_department_stats(self, department: str, months: int = 3) -> Dict[str, Any]:
        """获取部门统计数据"""
        try:
            # 生成模拟数据
            def generate_mock_data(department: str, months: int) -> Dict[str, Any]:
                current_date = datetime.now()
                monthly_stats = {}
                total_approvals = 0
                approved = 0
                rejected = 0
                pending = 0
                
                # 根据不同部门生成不同范围的数据
                if department == "税务管理部门":
                    base_count = 80
                    variance = 20
                elif department == "市民服务中心":
                    base_count = 120
                    variance = 30
                elif department == "社会保障部门":
                    base_count = 100
                    variance = 25
                else:  # 公共事业部门
                    base_count = 90
                    variance = 15

                # 生成每月数据
                for i in range(months):
                    date = current_date - timedelta(days=30 * i)
                    month = date.strftime('%Y-%m')
                    
                    # 生成本月审批数据
                    month_total = base_count + np.random.randint(-variance, variance)
                    month_approved = int(month_total * np.random.uniform(0.6, 0.8))
                    month_rejected = int(month_total * np.random.uniform(0.1, 0.2))
                    month_pending = month_total - month_approved - month_rejected
                    
                    monthly_stats[month] = {
                        'total': month_total,
                        'approved': month_approved,
                        'rejected': month_rejected,
                        'pending': month_pending
                    }
                    
                    total_approvals += month_total
                    approved += month_approved
                    rejected += month_rejected
                    pending += month_pending

                # 生成平均处理时间（小时）
                avg_processing_time = np.random.uniform(12, 48)
                
                return {
                    "total_approvals": total_approvals,
                    "status_distribution": {
                        "pending": pending,
                        "approved": approved,
                        "rejected": rejected
                    },
                    "avg_processing_time": avg_processing_time,
                    "monthly_trends": monthly_stats,
                    "department": department,
                    "period": f"近{months}个月"
                }

            # 如果文件不存在或为空，使用模拟数据
            if not self.approvals_file.exists() or os.path.getsize(self.approvals_file) == 0:
                mock_data = generate_mock_data(department, months)
                # 保存模拟数据到文件
                try:
                    if not self.approvals_file.exists():
                        with open(self.approvals_file, 'w', encoding='utf-8') as f:
                            json.dump([], f, ensure_ascii=False, indent=2)
                    return mock_data
                except Exception as e:
                    print(f"保存模拟数据失败: {str(e)}")
                    return mock_data

            # 读取真实数据
            with open(self.approvals_file, 'r', encoding='utf-8') as f:
                approvals = json.load(f)

            # 如果没有该部门的数据，使用模拟数据
            department_approvals = [a for a in approvals if a['department'] == department]
            if not department_approvals:
                return generate_mock_data(department, months)

            # 过滤最近n个月的数据
            cutoff_date = datetime.now() - timedelta(days=30 * months)
            recent_approvals = [
                a for a in department_approvals
                if datetime.fromisoformat(a['submit_time']) > cutoff_date
            ]

            # 如果过滤后没有数据，使用模拟数据
            if not recent_approvals:
                return generate_mock_data(department, months)

            # 计算各种统计指标
            total_count = len(recent_approvals)
            status_counts = {
                "pending": len([a for a in recent_approvals if a['status'] == 'pending']),
                "approved": len([a for a in recent_approvals if a['status'] == 'approved']),
                "rejected": len([a for a in recent_approvals if a['status'] == 'rejected'])
            }

            # 计算平均处理时间
            processing_times = []
            for approval in recent_approvals:
                if 'updatedAt' in approval and approval['status'] != 'pending':
                    submit_time = datetime.fromisoformat(approval['submit_time'])
                    update_time = datetime.fromisoformat(approval['updatedAt'])
                    processing_time = (update_time - submit_time).total_seconds() / 3600  # 转换为小时
                    processing_times.append(processing_time)

            avg_processing_time = np.mean(processing_times) if processing_times else 0

            # 按月统计趋势
            monthly_stats = {}
            for approval in recent_approvals:
                month = datetime.fromisoformat(approval['submit_time']).strftime('%Y-%m')
                if month not in monthly_stats:
                    monthly_stats[month] = {'total': 0, 'approved': 0, 'rejected': 0}
                monthly_stats[month]['total'] += 1
                if approval['status'] == 'approved':
                    monthly_stats[month]['approved'] += 1
                elif approval['status'] == 'rejected':
                    monthly_stats[month]['rejected'] += 1

            return {
                "total_approvals": total_count,
                "status_distribution": status_counts,
                "avg_processing_time": avg_processing_time,
                "monthly_trends": monthly_stats,
                "department": department,
                "period": f"近{months}个月"
            }

        except Exception as e:
            print(f"获取部门统计数据失败: {str(e)}")
            # 发生错误时返回模拟数据
            return generate_mock_data(department, months)

    async def generate_analysis_report(self, stats: Dict[str, Any]) -> str:
        """生成AI分析报告"""
        try:
            prompt = f"""你是一个专业的数据分析专家，请根据以下政务部门数据生成一份详细的分析报告。

数据概要：
部门：{stats['department']}
时间范围：{stats['period']}
总审批数：{stats['total_approvals']}
状态分布：
- 待审批：{stats['status_distribution']['pending']}
- 已通过：{stats['status_distribution']['approved']}
- 已拒绝：{stats['status_distribution']['rejected']}
平均处理时间：{stats['avg_processing_time']:.2f}小时

月度趋势数据：
{json.dumps(stats['monthly_trends'], ensure_ascii=False, indent=2)}

请严格按照以下JSON格式返回分析结果，确保包含所有字段：

{{
    "总体评估": "这里是对部门整体工作情况的详细评估，包括工作量、效率等方面，如果没有数据则返回暂无数据",
    "效率分析": "这里是对审批效率的具体分析，包括平均处理时间、积压情况等，如果没有数据则返回暂无数据",
    "问题发现": "这里列出发现的主要问题，如处理延迟、拒绝率过高等，如果没有数据则返回暂无数据",
    "改进建议": [
        "具体的改进建议1",
        "具体的改进建议2",
        "具体的改进建议3"
    ],
    "未来预测": "基于当前数据趋势的未来预测分析",
    "风险预警": [
        {{
            "风险类型": "具体的风险类型",
            "风险等级": "高/中/低",
            "可能影响": "风险可能造成的具体影响",
            "建议措施": "针对该风险的具体防范措施"
        }}
    ],
    "效率优化建议": {{
        "流程优化": [
            "流程优化建议1",
            "流程优化建议2"
        ],
        "资源配置": [
            "资源配置建议1",
            "资源配置建议2"
        ],
        "系统改进": [
            "系统改进建议1",
            "系统改进建议2"
        ]
    }},
    "关键指标异常分析": [
        {{
            "指标名称": "具体的指标名称",
            "异常情况": "指标异常的具体描述",
            "可能原因": [
                "可能原因1",
                "可能原因2"
            ],
            "处理建议": "针对该异常的具体处理建议"
        }}
    ]
}}

请注意：
1. 必须返回完整的JSON格式数据
2. 必须包含所有指定的字段
3. 分析要基于提供的实际数据
4. 使用中文返回
5. 不要添加任何额外的解释或者markdown标记
"""
            # 获取AI响应
            response = await chat_service.get_response(prompt)
            
            # 处理响应数据
            report_data = None
            if isinstance(response, dict):
                report_data = response
            else:
                # 如果是字符串，尝试解析JSON
                try:
                    # 清理响应文本
                    json_str = response.strip()
                    if json_str.startswith('```json'):
                        json_str = json_str[7:]
                    if json_str.endswith('```'):
                        json_str = json_str[:-3]
                    json_str = json_str.strip()
                    report_data = json.loads(json_str)
                except:
                    return f"无法解析AI响应: {response}"

            # 验证必要字段
            required_fields = ['总体评估', '效率分析', '问题发现', '改进建议', '未来预测', 
                             '风险预警', '效率优化建议', '关键指标异常分析']
            
            # 添加默认值处理
            default_values = {
                '总体评估': f"{stats['department']}在{stats['period']}期间共处理了{stats['total_approvals']}件审批事项，整体运转情况良好。",
                '效率分析': f"平均处理时间为{stats['avg_processing_time']:.2f}小时，审批效率处于正常水平。",
                '问题发现': "暂未发现重大问题。",
                '改进建议': ["优化审批流程", "加强人员培训", "完善系统功能"],
                '未来预测': "基于当前数据，预计未来工作量将保持稳定。",
                '风险预警': [
                    {
                        "风险类型": "处理延迟",
                        "风险等级": "低",
                        "可能影响": "可能导致部分业务积压",
                        "建议措施": "适当增加人员配置"
                    }
                ],
                '效率优化建议': {
                    "流程优化": ["简化审批流程", "优化文件传递"],
                    "资源配置": ["合理分配人力", "优化工作时间"],
                    "系统改进": ["升级系统功能", "完善数据统计"]
                },
                '关键指标异常分析': [
                    {
                        "指标名称": "审批时效",
                        "异常情况": "暂无明显异常",
                        "可能原因": ["系统运转正常", "人员配置合理"],
                        "处理建议": "继续保持现有工作状态"
                    }
                ]
            }

            # 检查并填充缺失字段
            for field in required_fields:
                if field not in report_data:
                    print(f"使用默认值填充缺失字段: {field}")  # 添加日志
                    report_data[field] = default_values[field]
                
            # 格式化为易读的文本
            report = f"""# {stats['department']}数据分析报告
                
## 总体评估
{report_data['总体评估']}

## 效率分析
{report_data['效率分析']}

## 问题发现
{report_data['问题发现']}

## 改进建议
"""
            for i, suggestion in enumerate(report_data['改进建议'], 1):
                report += f"{i}. {suggestion}\n"
            
            report += f"""
## 未来预测
{report_data['未来预测']}

## 风险预警
"""
            for i, risk in enumerate(report_data['风险预警'], 1):
                report += f"{i}. 风险类型：{risk['风险类型']}\n   风险等级：{risk['风险等级']}\n   可能影响：{risk['可能影响']}\n   建议措施：{risk['建议措施']}\n\n"
            
            report += f"""
## 效率优化建议
"""
            for category, suggestions in report_data['效率优化建议'].items():
                report += f"\n### {category}\n"
                for i, suggestion in enumerate(suggestions, 1):
                    report += f"{i}. {suggestion}\n"
            
            report += f"""
## 关键指标异常分析
"""
            for i, analysis in enumerate(report_data['关键指标异常分析'], 1):
                report += f"""
### {analysis['指标名称']}
- 异常情况：{analysis['异常情况']}
- 可能原因：
"""
                for reason in analysis['可能原因']:
                    report += f"  - {reason}\n"
                report += f"- 处理建议：{analysis['处理建议']}\n"
            
            report += f"""
---
报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
分析范围：{stats['period']}
"""
            return report
                
        except Exception as e:
            return f"生成分析报告失败: {str(e)}"

    async def predict_workload(self, department: str, days: int = 30) -> Dict[str, Any]:
        """预测未来工作量"""
        try:
            stats = await self.get_department_stats(department)
            
            prompt = f"""作为AI预测专家，请根据以下历史数据预测未来{days}天的作量趋势：

历史数据：
{json.dumps(stats['monthly_trends'], ensure_ascii=False, indent=2)}

请分析历史数据的模式和趋势，考虑季节性因素，并返回如下格式的JSON：
{{
    "预测工作量": 预测的数值,
    "增长率": 预测的增长率,
    "置信度": 预测的置信度(0-100),
    "影响因素": [
        {{
            "因素": "因素名称",
            "影响程度": "高/中/低",
            "说明": "具体说明"
        }}
    ],
    "建议措施": [
        "建议1",
        "建议2"
    ]
}}
"""
            response = await chat_service.get_response(prompt)
            return json.loads(response)
            
        except Exception as e:
            return {"error": f"预测失败: {str(e)}"}

    async def analyze_bottlenecks(self, department: str) -> Dict[str, Any]:
        """分析业务瓶颈"""
        try:
            stats = await self.get_department_stats(department)
            
            prompt = f"""作为流程优化专家，请分析以下数据找出业务瓶颈：

部门数据：
{json.dumps(stats, ensure_ascii=False, indent=2)}

请返回如下格式的JSON：
{{
    "主要瓶颈": [
        {{
            "环节": "瓶颈环节名称",
            "问t描述": "具体问题",
            "影响程度": "高/中/低",
            "优化建议": ["建议1", "建议2"]
        }}
    ],
    "资源分配建议": {{
        "人力资源": ["建议1", "建议2"],
        "系统资源": ["建议1", "建议2"],
        "流程改进": ["建议1", "建议2"]
    }},
    "自动化机会": [
        {{
            "环节": "可自动化环节",
            "收益评估": "预期收益",
            "实施难度": "高/中/低",
            "建议方案": "具体建议"
        }}
    ]
}}
"""
            response = await chat_service.get_response(prompt)
            return json.loads(response)
            
        except Exception as e:
            return {"error": f"分析失败: {str(e)}"}

# 创建服务实例
analytics_service = AnalyticsService() 
