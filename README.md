# 山大公管智能体（SDU-PA Agent）

> An AI agent for public administration teaching & research — RAG-powered concept Q&A, paper assistance, policy case analysis, and multi-agent deep research.

**面向公共管理教学与研究的 AI 学科智能体**，为师生提供概念解析、论文辅助、政策案例分析、文献检索与深度研究等能力。项目采用 **FastAPI + Next.js** 全栈架构，融合 **RAG 检索增强、Function Calling 工具调用、多智能体任务规划（Plan-and-Execute）**，支持 **DeepSeek / 通义千问 / GPT** 等多模型接入。

---

## ✨ 核心能力

- **概念解析**：公共管理 / 政治学概念的即时讲解与辨析，回答带出处引用
- **论文辅助**：选题、文献检索、参考文献格式校验、学术诚信核查
- **政策案例分析**：政策文件检索、案例梳理与政策扩散等理论应用
- **知识库问答**：上传课件 / 文献（PDF、Word 等），自动切块、向量化入库，基于 RAG 的专属知识库问答，答案可溯源
- **深度研究**：基于 Plan-and-Execute 的多智能体任务规划——自动拆解任务、检索取证、迭代复核，最终生成结构化研究报告（支持人工确认 Human-in-the-loop）
- **智能体工具调用**：通过 Function Calling 自主决定是否检索知识库 / 联网搜索及调用策略（支持多轮、多工具、引用编号）

## 🛠 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | Next.js 14、React 18、TypeScript、Tailwind CSS、Ant Design、ECharts |
| 后端 | FastAPI、Pydantic、asyncio 异步 |
| RAG | FAISS、m3e-base 向量模型、RecursiveCharacterTextSplitter |
| Agent | Function Calling 工具路由、Plan-and-Execute 多智能体、网页搜索（Serper）、人工确认 |
| 模型 | DeepSeek、通义千问（DashScope）、GPT |

---

## 🚀 部署说明

### 📦 环境要求

- **Node.js**: >= 18.0.0
- **Python**: >= 3.9 (推荐 3.11+)
- **npm**: >= 9.0.0
- **操作系统**: Windows / macOS / Linux

### 1. 下载数据和模型文件

由于文件较大（约 1GB），数据和模型文件需要单独下载：

- **models.zip** (606.4MB): https://pan.baidu.com/s/18OU-5nnoOb8aPkBtcW-pGA?pwd=36yf
- **data.zip** (275.8MB): https://pan.baidu.com/s/1_O1TrmwPxpZZu3b-KoaPDQ?pwd=an7k

解压并放置文件：

```bash
# Windows: 将 models.zip 解压到 backend\models\，data.zip 解压到 backend\data\
# Linux/macOS:
unzip models.zip -d backend/
unzip data.zip -d backend/
```

最终目录结构：

```
backend/
├── models/
│   ├── base.pt
│   └── distiluse-base-multilingual-cased-v1/
└── data/
    ├── city.json
    ├── metadata.json
    ├── users.json
    ├── approvals.json
    ├── excel/
    ├── private/
    ├── public/
    ├── temp/
    └── urban_gov_eval/
```

### 2. 安装依赖

```bash
# 前端依赖
npm install

# 后端依赖（推荐虚拟环境）
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 为 `.env` 并填入 API 密钥：

```bash
cp .env.example .env
```

- **阿里云 DashScope**: https://dashscope.aliyun.com/
- **OpenAI API**: https://platform.openai.com/
- **Google Serper**: https://serper.dev/

> ⚠️ `.env` 已被 `.gitignore` 忽略，请勿提交真实密钥到仓库。

### 4. 运行项目

```bash
# 启动后端（端口 8890）
python -m backend.app.main

# 启动前端（端口 3000，另开终端）
npm run dev
```

浏览器访问 `http://localhost:3000` 即可进入平台。

---

## 💡 Tips

1. 路径中存在中文可能会导致文档上传失败（文件名可以是中文）
2. 智能 AI 助手中，所选模型能力越强，通常结果越出色；其中 `qwen-plus` 在数据分析任务中表现较好

---

## 📁 项目结构

```
city_research/
├── backend/
│   ├── app/
│   │   ├── routers/        # API 路由层（chat / documents / files / approval ...）
│   │   ├── services/       # 业务层（chat / deep_research / document / search ...）
│   │   ├── models/         # 数据模型
│   │   └── main.py         # FastAPI 入口
│   └── requirements.txt
├── src/                    # Next.js 前端
│   ├── app/                # 页面路由
│   └── components/         # 组件
├── scripts/                # 数据初始化脚本
├── verify_fc_*.py          # Function Calling 改造验证脚本
└── package.json
```
