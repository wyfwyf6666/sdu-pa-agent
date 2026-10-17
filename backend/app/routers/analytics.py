from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional
import os
from backend.app.services.analytics import analytics_service
from pathlib import Path
import shutil

router = APIRouter()

# 部门ID映射
DEPARTMENT_MAP = {
    "1": "市民服务中心",
    "2": "税务管理部门",
    "3": "社会保障部门",
    "4": "公共事业部门",
}

@router.post("/analytics/upload-excel")
async def upload_excel(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = None
):
    """上传并处理Excel文件"""
    print(f"接收到文件上传请求: {file.filename}")
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="未提供文件")
        
    temp_file = None
    try:
        # 检查文件类型
        if not file.filename.endswith(('.xls', '.xlsx')):
            raise HTTPException(status_code=400, detail="只支持Excel文件(.xls, .xlsx)")
        
        # 检查文件大小
        file_size = 0
        try:
            file_size = len(await file.read())
            await file.seek(0)  # 重置文件指针
            if file_size > 10 * 1024 * 1024:  # 10MB
                raise HTTPException(status_code=400, detail="文件大小不能超过10MB")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"读取文件失败: {str(e)}")
        
        print(f"文件大小: {file_size} bytes")
        
        # 创建临时文件
        temp_file = Path(analytics_service.excel_dir) / f"temp_{file.filename}"
        os.makedirs(analytics_service.excel_dir, exist_ok=True)
        
        print(f"临时文件路径: {temp_file}")
        
        # 保存上传的文件
        try:
            with open(temp_file, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            print(f"文件保存成功: {temp_file}")
        except Exception as e:
            print(f"文件保存失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")
        
        # 处理Excel文件
        try:
            result = await analytics_service.process_excel(str(temp_file), sheet_name)
            print(f"Excel处理结果: {result}")
        except Exception as e:
            print(f"Excel处理失败: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Excel处理失败: {str(e)}")
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result["message"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"处理失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")
    finally:
        # 清理临时文件
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
                print(f"临时文件已清理: {temp_file}")
            except Exception as e:
                print(f"清理临时文件失败: {str(e)}")
                pass

@router.get("/analytics/department/{department_id}")
async def get_department_analytics(
    department_id: str,
    months: Optional[int] = 3
):
    """获取部门统计数据"""
    try:
        if department_id not in DEPARTMENT_MAP:
            raise HTTPException(status_code=404, detail="部门不存在")
            
        department_name = DEPARTMENT_MAP[department_id]
        stats = await analytics_service.get_department_stats(department_name, months)
        
        if "error" in stats:
            raise HTTPException(status_code=400, detail=stats["error"])
            
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取数据失败: {str(e)}")

@router.get("/analytics/department/{department_id}/report")
async def get_department_report(
    department_id: str,
    months: Optional[int] = 3
):
    """获取部门AI分析报告"""
    try:
        if department_id not in DEPARTMENT_MAP:
            raise HTTPException(status_code=404, detail="部门不存在")
            
        department_name = DEPARTMENT_MAP[department_id]
        stats = await analytics_service.get_department_stats(department_name, months)
        
        if "error" in stats:
            raise HTTPException(status_code=400, detail=stats["error"])
        
        # 生成分析报告
        report = await analytics_service.generate_analysis_report(stats)
        
        if not report:
            raise HTTPException(status_code=500, detail="生成报告失败")
            
        return {"report": report}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成报告失败: {str(e)}") 