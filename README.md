# 城市治理综合研究平台（部署说明）



## 📦 环境要求

- **Node.js**: >= 18.0.0
- **Python**: >= 3.9 (推荐 3.11+)
- **npm**: >= 9.0.0
- **操作系统**: Windows / macOS / Linux



## 🚀 安装步骤

### 1. 下载数据和模型文件

由于文件较大（约 1GB），数据和模型文件需要单独下载：

#### 下载链接：
- **models.zip** (606.4MB): https://pan.baidu.com/s/18OU-5nnoOb8aPkBtcW-pGA?pwd=36yf
- **data.zip** (275.8MB): https://pan.baidu.com/s/1_O1TrmwPxpZZu3b-KoaPDQ?pwd=an7k

#### 解压并放置文件：

```bash
# 下载完成后，解压到对应目录
# Windows:
# 将 models.zip 解压到 backend\models\
# 将 data.zip 解压到 backend\data\

# Linux/macOS:
unzip models.zip -d backend/
unzip data.zip -d backend/
```

#### 最终目录结构应该是：
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

### 2. 安装前端依赖

```bash
npm install
```

### 3. 安装后端依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 安装所有依赖
pip install -r backend/requirements.txt
```



## ⚙️ 配置说明

### 1. 创建环境变量文件

复制 `.env.example` 文件为 `.env`

```bash
# 复制环境变量模板
cp .env.example .env
```

### 2. 编辑 .env 文件

打开新创建的 `.env` 文件，填入实际的 API 密钥等

### 3. API 密钥获取方式

- **阿里云 DashScope**: https://dashscope.aliyun.com/
- **OpenAI API**: https://platform.openai.com/
- **Google Serper**: https://serper.dev/



## 🎯 运行项目

### 1. 启动后端服务

```bash
# 启动 FastAPI 后端（端口 8890）
python -m backend.app.main
```

后端服务将在 `http://localhost:8890` 启动

### 2. 启动前端服务

打开新的终端窗口：

```bash
# 启动 Next.js 前端（端口 3000）
npm run dev
```

前端服务将在 `http://localhost:3000` 启动

打开浏览器访问 `http://localhost:3000` 即可进入平台



## 💡 Tips

1.  路径中存在中文可能会导致文档上传失败（文件名可以是中文）
2.  在智能AI助手中，所选模型能力越强，通常能得到越出色的结果；其中，我们发现 qwen-plus 在数据分析任务中表现较好

---

