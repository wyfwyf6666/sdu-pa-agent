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

### 1. 准备数据文件与模型文件

这两类文件需要分开看：**业务数据（data.zip）必需**；**模型文件（models.zip）可选**，代码支持联网自动下载，也支持用环境变量指向任意兼容模型。

#### 1.1 业务数据（必需）

- **data.zip** (275.8MB): https://pan.baidu.com/s/1_O1TrmwPxpZZu3b-KoaPDQ?pwd=an7k

包含 `city.json`、`users.json`、`approvals.json`、`urban_gov_eval/`（评估题库），以及 `public/`、`private/` 下已构建好的 FAISS 索引与 metadata。这些属于项目私有数据，没有公开下载源，只能使用随仓库分发的包。

```bash
# Windows: 将 data.zip 解压到 backend\data\
# Linux/macOS:
unzip data.zip -d backend/
```

> 缺少 `users.json` 时后端会自动创建空用户表并生成默认管理员账号，项目仍可启动；但已有知识库索引与 `urban_gov_eval/query.jsonl` 缺失会导致对应功能不可用。

#### 1.2 模型文件（可选，四种方式任选其一）

RAG 使用 `distiluse-base-multilingual-cased-v1`（512 维）做向量化与检索；语音识别使用 Whisper `base.pt`，仅在安装 `openai-whisper` 后生效（默认依赖中不含，语音功能会自动禁用）。

**方式 A：运行时自动下载（推荐，需可访问 HuggingFace）**

```bash
# .env
EMBEDDING_MODEL_NAME=sentence-transformers/distiluse-base-multilingual-cased-v1
```

首次启动时 `sentence-transformers` 会自动把模型下载到 `~/.cache/huggingface`。国内网络可先启用镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com   # 或写入 .env
```

**方式 B：通过国内镜像手动下载**

```bash
pip install -U huggingface_hub
export HF_ENDPOINT=https://hf-mirror.com
hf download sentence-transformers/distiluse-base-multilingual-cased-v1 \
  --local-dir backend/models/distiluse-base-multilingual-cased-v1
```

> `huggingface_hub < 0.34` 没有 `hf` 命令，把开头的 `hf` 换成 `huggingface-cli` 即可。

或使用魔搭 ModelScope：

```bash
pip install modelscope
modelscope download --model sentence-transformers/distiluse-base-multilingual-cased-v1 \
  --local-dir backend/models/distiluse-base-multilingual-cased-v1
```

**方式 C：使用网盘离线包**

- **models.zip** (606.4MB): https://pan.baidu.com/s/18OU-5nnoOb8aPkBtcW-pGA?pwd=36yf

适合完全离线、无法访问 HuggingFace 的环境：

```bash
# Windows: 将 models.zip 解压到 backend\models\
# Linux/macOS:
unzip models.zip -d backend/
```

**方式 D：复用已有的兼容模型**

```bash
# .env（绝对路径，或相对当前启动目录的路径）
EMBEDDING_MODEL_PATH=/path/to/your/embedding-model
```

> ⚠️ 更换向量模型后维度可能变化（默认 distiluse 为 512 维）。此时已有 FAISS 索引会因维度不一致而检索失败，需要重建：公共库可运行 `python scripts/init_kb.py --force`；私有知识组可在界面上重新上传文档，或调用 `document_service.build_merged_index(..., force_full_rebuild=True)` 重建。

若完全离线且不想用网盘，也可把任意兼容模型直接放到默认路径 `backend/models/distiluse-base-multilingual-cased-v1/`，无需修改配置。

语音识别为可选能力：安装 `openai-whisper` 后，将 `base.pt` 放到 `backend/models/base.pt`；或让它首次运行时自动下载（缓存到 `~/.cache/whisper`）。

最终目录结构：

```
backend/
├── models/                                    # 可选，见 1.2
│   ├── base.pt                                # 可选：语音识别
│   └── distiluse-base-multilingual-cased-v1/  # 向量模型
└── data/                                      # 必需，见 1.1
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
