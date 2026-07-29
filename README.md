# novel_auto_agent

> AI 视频分镜 Prompt 生成系统 — 6 步 Pipeline + FastAPI 后端 + React 前端

---

## 项目简介

将一段小说/剧本/故事大纲，**自动拆解为多镜头分镜表**，并为每个镜头生成 **Kling / 即梦** 两大主流 AI 视频模型的高质量 Prompt。

本项目由 **novel_codex_agent** (6 步 Prompt Pipeline) 和 **Jellyfish** (FastAPI + React 前后端) 合并而成，提供 **CLI / REST API / Web GUI** 三种使用方式。

---

## 核心功能

- **6 步 LangGraph Pipeline**: 剧本分析 → 导演分镜 → Prompt 规划 → Prompt 撰写 → 一致性检查 → 模型适配
- **12 维度一致性审计**: LLM-as-judge 自动检查角色/场景/道具/动作/镜头等一致性
- **2 模型专属优化**: Kling (中英混合) + 即梦 (中文) 各有针对性 Prompt 优化
- **全局演员表**: cast.json 跨章节持久化，`@角色名` 引用保证视觉一致性
- **故事板卡片**: 自动生成角色/场景/镜头参考卡，支持 DALL-E 3 出图
- **25+ 导演风格注入**: 王家卫、徐克、张艺谋等导演风格参考
- **物理真实感增强**: 重力/惯性/发力感等专业动作描述
- **Web GUI**: 分镜工作台一键生成 Prompt，实时进度展示
- **任务执行线程降级**: 默认线程池模式，无需 Celery，启动 uvicorn 即可执行异步任务
- **步骤可视化**: 任务执行过程中实时显示当前步骤（如"正在拆分镜头…"）
- **结果通知**: 任务完成后自动弹出通知，显示产出摘要（如"成功拆分为 N 个镜头"）
- **模型管理**: 前端添加/测试/设为默认，支持 DashScope 等多供应商

---

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/gutengshuxia/novel_auto_agent.git
cd novel_auto_agent
```

### 2. 安装后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
pip install -e ".[dev]"
cp ../.env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 3. 配置模型

启动后在前端「模型管理」页面添加 LLM 模型（如 qwen-max），并设为默认。

### 4. 启动服务

```bash
# 后端 (FastAPI) — 线程模式默认，无需启动 Celery
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 前端 (React)
cd front
npm install
npm run dev
```

访问 http://localhost:5173 进入 Web 界面。

### 5. CLI 模式 (可选)

```bash
cd novel_auto_agent
python main.py data/sample_story.txt --no-hitl
```

---

## 项目结构

```
novel_auto_agent/
├── backend/
│   ├── app/
│   │   ├── pipeline/          # 6 步 Prompt Pipeline
│   │   │   ├── engine.py      # PipelineEngine 引擎
│   │   │   ├── agents/        # 6 步 Agent (分析/分镜/规划/撰写/检查/适配)
│   │   │   ├── graph/         # LangGraph 工作流
│   │   │   ├── schemas/       # Pydantic v2 数据契约
│   │   │   ├── utils/         # LLM工厂 / Excel导出 / CastManager
│   │   │   └── adapters/      # JellyfishAdapter 数据转换
│   │   ├── api/v1/routes/     # REST API 路由 (film/llm/studio/novel_codex)
│   │   ├── core/task_manager/ # 任务管理器 (状态/存储/类型)
│   │   ├── services/          # Bridge + 任务执行器
│   │   │   ├── worker/task_executor.py      # 任务执行基类
│   │   │   └── script_processing_worker.py  # 9 个具体执行器
│   │   ├── schemas/           # API Schema
│   │   └── models/            # DB 模型 (task/llm/studio)
│   └── pyproject.toml         # 合并依赖
├── front/                     # React 18 + Ant Design 前端
│   └── src/pages/aiStudio/   # 分镜工作台 (章节/分镜/模型/任务)
├── main.py                    # CLI 入口
├── data/sample_story.txt      # 示例故事
├── docs/                      # 文档
│   ├── ARCHITECTURE.md        # 架构文档
│   ├── USER_GUIDE.md          # 使用手册
│   ├── DEVELOPER_GUIDE.md     # 开发指南
│   └── CHANGELOG.md           # 修改日志
└── tests/                     # Pipeline 测试
```

---

## 使用方式

### CLI

```bash
python main.py <故事文件.txt> [--title "标题"] [--max-replans 3] [--output-dir ./output]
```

### REST API

```bash
# 启动生成任务
curl -X POST http://localhost:8000/api/v1/novel-codex/generate \
  -H "Content-Type: application/json" \
  -d '{"chapter_id": "your-chapter-id"}'

# 查询进度
curl http://localhost:8000/api/v1/novel-codex/status/{task_id}

# 获取结果
curl http://localhost:8000/api/v1/novel-codex/result/{task_id}
```

### Web GUI

- **分镜提取**: 章节页面点击「提取分镜」，系统自动调用 LLM 拆分镜头
- **AI Prompt 生成**: 分镜工作台点击 **「AI Prompt」** 按钮，一键生成 Prompt
- **模型管理**: 添加/测试/设为默认模型，支持 DashScope 等多供应商
- **任务通知**: 任务完成后自动弹出结果摘要（如"成功拆分为 12 个镜头"）

---

## 输出示例

Excel 输出包含 4 个 Sheet:

| Sheet | 内容 |
|-------|------|
| Storyboard | 分镜概览 (镜头编号/时长/景别/运镜/描述) |
| Prompt Variants | 2 模型 × N 镜头的 Prompt 文本 |
| 演员表 | 全局角色注册 (外貌/视觉描述/服装变化) |
| 故事板卡片 | 角色/场景/镜头参考卡提示词 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| Pipeline | Python 3.11+, LangGraph, LangChain, Pydantic v2 |
| 后端 | FastAPI, SQLAlchemy, ThreadPoolExecutor (默认) / Celery (可选) |
| 前端 | React 18, Ant Design, Zustand, Vite |
| LLM | 多供应商支持: OpenAI / DashScope (qwen-max) / 自定义 |
| 数据库 | SQLite (默认) / MySQL / PostgreSQL |

---

## 文档

- [架构文档](./docs/ARCHITECTURE.md) — 系统拓扑、状态机、数据契约、ADR、任务执行系统
- [使用手册](./docs/USER_GUIDE.md) — 快速上手、进阶用法、分镜提取操作指引、FAQ
- [开发指南](./docs/DEVELOPER_GUIDE.md) — 环境搭建、扩展点、任务执行器开发、隐私安全
- [修改日志](./docs/CHANGELOG.md) — 功能演进与问题修复记录

---

## License

MIT
