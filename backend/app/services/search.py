import http.client
import json
import os
from typing import Dict, Any, Optional

class SearchService:
    def __init__(self):
        self.api_key = os.getenv("SERPER_API_KEY", "")
        self.host = "google.serper.dev"

        if not self.api_key:
            import logging
            logging.getLogger(__name__).warning(
                "搜索服务缺少API密钥，联网搜索功能将不可用。请在.env文件中配置SERPER_API_KEY。"
            )

    async def search(self, query: str) -> Dict[str, Any]:
        """
        使用Google搜索API搜索信息
        """
        if not self.api_key:
            return {"error": "搜索服务未配置API密钥", "results": []}
        try:
            conn = http.client.HTTPSConnection(self.host)
            payload = json.dumps({
                "q": query,
                "gl": "cn",  # 地区设置为中国
                "hl": "zh-cn"  # 语言设置为中文
            })
            
            headers = {
                'X-API-KEY': self.api_key,
                'Content-Type': 'application/json'
            }
            
            conn.request("POST", "/search", payload, headers)
            response = conn.getresponse()
            data = response.read()
            
            if response.status != 200:
                raise Exception(f"搜索API返回错误: {response.status} {response.reason}")
                
            return json.loads(data.decode("utf-8"))
            
        except Exception as e:
            raise Exception(f"搜索失败: {str(e)}")
        finally:
            conn.close()

# 创建搜索服务实例
search_service = SearchService()
