from typing import List, Dict, Any
import json
from pathlib import Path
from datetime import datetime
from backend.app.services.chat import chat_service

class ApprovalAIService:
    def __init__(self):
        root_dir = Path(__file__).resolve().parents[3]
        self.history_file = root_dir / "backend" / "data" / "approvals.json"

    async def analyze_approval(self, approval_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析审批内容并生成建议"""

        # 构建提示词
        prompt = f"""作为智能政务审批助手，请分析以下审批申请并提供专业建议。请严格按照指定的JSON格式返回结果：

审批标题：{approval_data['title']}
审批类型：{approval_data['type']}
申请内容：{approval_data['content']}
紧急程度：{approval_data['urgency']}
申请部门：{approval_data['department']}

请返回如下格式的JSON（注意：必须是合法的JSON格式）：

{{
    "compliance_check": "合规性检查结果",
    "process_check": "流程检查结果",
    "risk_assessment": "风险评估结果",
    "suggestion": "建议意见",
    "key_points": ["关键点1", "关键点2", "关键点3"]
}}

请确保返回的是一个合法的JSON字符串，每个字段都要用双引号包围。"""

        try:
            # 调用AI获取分析结果
            response = await chat_service.get_response(prompt)

            # 获取实际的响应文本
            response_text = response.get('response', '')
            if not response_text:
                return {
                    "compliance_check": "分析失败：AI响应为空",
                    "process_check": "分析失败",
                    "risk_assessment": "分析失败",
                    "suggestion": "无法生成建议",
                    "key_points": ["系统错误，请稍后重试"]
                }

            # 尝试清理响应文本，移除可能的前缀和后缀
            json_str = response_text.strip()
            if json_str.startswith('```json'):
                json_str = json_str[7:]
            if json_str.endswith('```'):
                json_str = json_str[:-3]
            json_str = json_str.strip()

            try:
                analysis = json.loads(json_str)

                # 确保所有必需的字段都存在
                required_fields = ['compliance_check', 'process_check', 'risk_assessment', 'suggestion', 'key_points']
                for field in required_fields:
                    if field not in analysis:
                        analysis[field] = "未提供"
                if not isinstance(analysis['key_points'], list):
                    analysis['key_points'] = []

                return analysis

            except json.JSONDecodeError:
                # 如果返回的不是有效的JSON，进行格式化处理
                return {
                    "compliance_check": "合规性检查：" + response_text[:100] + "...",
                    "process_check": "流程检查：正常",
                    "risk_assessment": "风险评估：需要进一步评估",
                    "suggestion": "建议：请人工审核",
                    "key_points": ["AI返回格式不规范，请人工审核"]
                }

        except Exception as e:
            return {
                "compliance_check": f"分析出错: {str(e)}",
                "process_check": "分析失败",
                "risk_assessment": "分析失败",
                "suggestion": "无法生成建议",
                "key_points": ["系统错误，请稍后重试"]
            }

    async def get_similar_cases(self, approval_data: Dict[str, Any], limit: int = 3) -> List[Dict[str, Any]]:
        """查找相似的历史审批案例"""
        try:
            if not self.history_file.exists():
                return []

            with open(self.history_file, 'r', encoding='utf-8') as f:
                historical_approvals = json.load(f)

            # 构建相似度查询提示词
            current_case = f"""
            标题：{approval_data['title']}
            类型：{approval_data['type']}
            内容：{approval_data['content']}
            部门：{approval_data['department']}
            """

            similar_cases = []
            for historical in historical_approvals:
                if historical['id'] == approval_data['id']:
                    continue

                historical_case = f"""
                标题：{historical['title']}
                类型：{historical['type']}
                内容：{historical['content']}
                部门：{historical['department']}
                """

                # 计算相似度（可以后续优化为向量相似度）
                prompt = f"""请分析以下两个审批案例的相似度（0-100）：

案例1：
{current_case}

案例2：
{historical_case}

请只返回一个数字，表示相似度。
"""
                try:
                    similarity_score = float(await chat_service.get_response(prompt))
                    if similarity_score > 60:  # 相似度阈值
                        historical['similarity'] = similarity_score
                        similar_cases.append(historical)
                except:
                    continue

            # 按相似度排序并返回前N个
            similar_cases.sort(key=lambda x: x['similarity'], reverse=True)
            return similar_cases[:limit]

        except Exception as e:
            print(f"获取相似案例失败: {str(e)}")
            return []

    async def generate_approval_comment(self, approval_data: Dict[str, Any], analysis_result: Dict[str, Any]) -> str:
        """生成审批意见建议"""
        prompt = f"""作为智能政务审批助手，请根据以下信息生成一份专业的审批意见。请返回JSON格式：

审批信息：
- 标题：{approval_data['title']}
- 类型：{approval_data['type']}
- 内容：{approval_data['content']}
- 部门：{approval_data['department']}

分析结果：
- 合规性检查：{analysis_result['compliance_check']}
- 流程检查：{analysis_result['process_check']}
- 风险评估：{analysis_result['risk_assessment']}
- 关键要点：{', '.join(analysis_result['key_points'])}

请返回如下格式的JSON：

{{
    "总体评价": "对申请内容的总体评价",
    "合规性": "合规性和风险的具体说明",
    "风险评估": "风险评估结果",
    "审批建议": "同意/拒绝",
    "补充建议或注意事项": [
        "建议1",
        "建议2",
        "建议3"
    ]
}}

请确保返回的是一个合法的JSON字符串，所有字段都要用双引号包围。"""

        try:
            # 修改这里：response 现在是一个字典而不是字符串
            response = await chat_service.get_response(prompt)

            # 获取实际的响应文本
            response_text = response.get('response', '')  # 从响应字典中获取文本
            if not response_text:
                return "生成审批意见失败：AI 响应为空"

            # 清理并解析JSON
            json_str = response_text.strip()
            if json_str.startswith('```json'):
                json_str = json_str[7:]
            if json_str.endswith('```'):
                json_str = json_str[:-3]
            json_str = json_str.strip()

            try:
                comment_data = json.loads(json_str)
                # 格式化为易读的文本
                comment = f"""总体评价：{comment_data['总体评价']}\n\n"""
                comment += f"""合规性说明：{comment_data['合规性']}\n\n"""
                comment += f"""风险评估：{comment_data['风险评估']}\n\n"""
                comment += f"""审批建议：{comment_data['审批建议']}\n\n"""
                comment += "补充建议或注意事项：\n"
                for i, suggestion in enumerate(comment_data['补充建议或注意事项'], 1):
                    comment += f"{i}. {suggestion}\n"
                return comment
            except json.JSONDecodeError:
                return response_text  # 如果解析失败，直接返回原始响应文本

        except Exception as e:
            return f"生成审批意见失败: {str(e)}"

# 创建服务实例
approval_ai_service = ApprovalAIService()
