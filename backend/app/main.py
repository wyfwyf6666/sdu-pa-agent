import os
import importlib
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 加载.env文件
try:
    from dotenv import load_dotenv
    root_dir = Path(__file__).resolve().parents[2]
    env_path = root_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[OK] 已加载环境变量配置文件: {env_path}")
    else:
        print(f"[WARN] 未找到.env文件: {env_path}")
except ImportError:
    print("[WARN] 未安装python-dotenv，将使用系统环境变量")
    print("  建议安装: pip install python-dotenv")

app = FastAPI(title="山大公管智能体")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def include_router_safely(module_path: str, tag: str):
    try:
        module = importlib.import_module(module_path)
        app.include_router(module.router, prefix="/api/v1", tags=[tag])
        print(f"[OK] 已加载路由: {module_path}")
    except Exception as exc:
        print(f"[SKIP] 跳过路由 {module_path}: {exc}")

# 注册路由（按功能模块）
include_router_safely("backend.app.routers.auth", "auth")
include_router_safely("backend.app.routers.pre_review", "pre_review")
include_router_safely("backend.app.routers.academic_integrity", "academic_integrity")
include_router_safely("backend.app.routers.chat", "chat")
include_router_safely("backend.app.routers.files", "files")
include_router_safely("backend.app.routers.documents", "documents")
include_router_safely("backend.app.routers.knowledge_groups", "knowledge_groups")
include_router_safely("backend.app.routers.knowledge_graph", "knowledge_graph")
include_router_safely("backend.app.routers.teaching", "teaching")
include_router_safely("backend.app.routers.approval", "approval")
include_router_safely("backend.app.routers.analytics", "analytics")
include_router_safely("backend.app.routers.history", "history")
include_router_safely("backend.app.routers.urban_gov_eval", "urban_gov_eval")
include_router_safely("backend.app.routers.local_bibliography", "bibliography")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8890, reload=False)
