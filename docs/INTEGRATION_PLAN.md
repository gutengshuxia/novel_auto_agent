# [已归档] 集成计划已完成 — 请参考 ARCHITECTURE.md §16

# Jellyfish × novel_codex_agent 集成技术方案

> 日期: 2026-07-28 | 版本: v1.0

---

## 一、项目定位

| 项目 | 定位 | 核心能力 |
|---|---|---|
| **Jellyfish** | AI 短剧全流程管理平台 | 项目管理 → 剧本分镜 → 角色/场景资产管理 → 分帧Prompt → 视频生成 → 剪辑 |
| **novel_codex_agent** | 高质量视频 Prompt 引擎 | 剧本分析 → 分镜设计 → Prompt规划 → Prompt撰写(物理真实感/导演风格) → 一致性检查 → 多模型适配 |

**集成目标**: 将 novel_codex_agent 作为 Jellyfish 的 **Prompt 增强引擎**，通过 Jellyfish 前端一键触发。

---

## 二、架构总览

```
┌─────────────────────────────────────────────────────┐
│              Jellyfish 前端 (React + Ant Design)      │
│                                                       │
│  项目大厅 → 项目工作台 → 章节工作室 → 镜头编辑         │
│                                    ↓                  │
│                        ┌─────────────────────┐        │
│                        │ "一键生成 Prompt" 按钮 │       │
│                        └─────────┬───────────┘        │
└──────────────────────────────────┼────────────────────┘
                                   │ POST /api/v1/novel-codex/generate
                                   ▼
┌──────────────────────────────────────────────────────┐
│              Jellyfish 后端 (FastAPI)                  │
│                                                       │
│  ┌─────────────────────────────────────────────┐      │
│  │  API: /api/v1/novel-codex/                   │      │
│  │  ├── POST /generate          (异步生成)       │      │
│  │  ├── GET  /status/{task_id}  (查询进度)       │      │
│  │  └── GET  /result/{task_id}  (获取结果)       │      │
│  └────────────────────┬────────────────────────┘      │
│                       │                               │
│  ┌────────────────────▼────────────────────────┐      │
│  │  Service: novel_codex_bridge                 │      │
│  │  ├── 从 DB 读取 shots/entities/assets        │      │
│  │  ├── 调用 Pipeline Engine                    │      │
│  │  └── 将结果写回 DB (shot prompts)            │      │
│  └────────────────────┬────────────────────────┘      │
│                       │                               │
│  ┌────────────────────▼────────────────────────┐      │
│  │  Engine: novel_codex_agent (作为 Python 包)   │      │
│  │  ├── Step 1: StoryAnalysis                   │      │
│  │  ├── Step 2: Storyboard                      │      │
│  │  ├── Step 3: PromptPlan                      │      │
│  │  ├── Step 4: PromptWriter                    │      │
│  │  ├── Step 5: ConsistencyCheck                │      │
│  │  └── Step 6: ModelAdapter (kling/jimeng)     │      │
│  └─────────────────────────────────────────────┘      │
│                                                       │
│  ┌─────────────────────────────────────────────┐      │
│  │  数据库 (SQLite/MySQL)                        │      │
│  │  shots → shot_details → prompt 字段更新       │      │
│  │  novel_codex_tasks → 任务状态追踪             │      │
│  └─────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────┘
```

---

## 三、数据流映射

### 3.1 Jellyfish DB → novel_codex_agent 输入

| Jellyfish 数据 | novel_codex_agent 字段 | 说明 |
|---|---|---|
| `Chapter.script_text` (或合并所有 shots 的 script_excerpt) | `GraphState.story_text` | 剧本文本 |
| `Project.name` | `GraphState.story_title` | 故事标题 |
| `Project.visual_style` + `Project.style` | 注入 Step 4 system prompt | 全局风格 |
| `Shot.script_excerpt` | Step 2 分镜参考 | 已有分镜信息 |
| `ShotDetail.camera_shot/angle/movement` | Step 2 运镜信息 | 已有镜头参数 |
| `Character.description` + `Character.portrait` | `cast_data` 角色描述 | 角色资产 |
| `Scene.description` | 场景描述 | 场景资产 |
| `ShotCharacterLink` | 镜头-角色关联 | 谁出现在哪个镜头 |

### 3.2 novel_codex_agent 输出 → Jellyfish DB

| novel_codex_agent 产物 | Jellyfish 写入目标 | 说明 |
|---|---|---|
| `PromptVariant.prompt_text` (kling) | `ShotDetail.description` 或新字段 `video_prompt_kling` | kling 视频 prompt |
| `PromptVariant.prompt_text` (jimeng) | 新字段 `video_prompt_jimeng` | jimeng 视频 prompt |
| `PromptVariant.negative_prompt` | `ShotDetail` 新字段 `negative_prompt` | 负面提示词 |
| `StoryboardCardGenerator` 输出 | 新表 `storyboard_cards` 或 JSON 字段 | 故事板卡片 |
| `consistency_report.score` | `ShotDetail` 新字段 `prompt_quality_score` | 质量评分 |
| `cast_data` (更新后) | 回写到 `Character` / `Costume` 表 | 角色资产增强 |

---

## 四、新增文件清单

### 4.1 Jellyfish 后端新增

```
backend/app/
├── api/v1/routes/
│   └── novel_codex.py              # API 路由 (3个端点)
├── services/
│   └── novel_codex_bridge.py       # 桥接服务 (DB读写 + Pipeline调用)
├── schemas/
│   └── novel_codex.py              # 请求/响应 Schema
└── models/
    └── novel_codex_task.py         # 任务追踪表 (可选, 也可复用 GenerationTask)
```

### 4.2 novel_codex_agent 改造

```
novel_codex_agent/
├── src/
│   ├── engine.py                   # 新增: Pipeline 引擎封装 (供外部调用)
│   └── adapters/
│       └── jellyfish_adapter.py    # 新增: Jellyfish 数据适配器
```

---

## 五、详细设计

### 5.1 novel_codex_agent: Pipeline 引擎封装

**文件**: `src/engine.py`

```python
"""Pipeline 引擎 —— 供外部系统(Jellyfish)调用。"""

from dataclasses import dataclass
from typing import Any, Callable

from src.graph import build_graph
from src.graph.state import GraphState
from src.utils import CastManager, StoryboardCardGenerator


@dataclass
class PipelineResult:
    """Pipeline 执行结果。"""
    success: bool
    storyboard: dict | None = None        # 分镜数据
    prompt_plan: dict | None = None       # Prompt 计划
    consistency_report: dict | None = None # 一致性报告
    storyboard_cards: list[dict] = None   # 故事板卡片
    cast_data: dict | None = None         # 更新后的演员表
    error: str | None = None


class PipelineEngine:
    """封装 LangGraph Pipeline 为可调用引擎。"""

    def __init__(self, *, enable_cards: bool = True):
        self.enable_cards = enable_cards
        self._graph = build_graph()

    def run(
        self,
        story_text: str,
        story_title: str,
        cast_data: dict | None = None,
        director_ids: list[str] | None = None,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> PipelineResult:
        """
        执行完整 Pipeline。

        Args:
            story_text: 剧本文本
            story_title: 标题
            cast_data: 已有演员表 (可选)
            director_ids: 导演风格列表 (可选)
            progress_callback: 进度回调 (step_name, percent)
        """
        ...
```

**核心逻辑**:
1. 构建 `GraphState` 初始状态
2. 调用 `graph.invoke()` 执行 6 步 Pipeline
3. 收集产物: storyboard / prompt_plan / consistency_report
4. 可选生成故事板卡片
5. 返回 `PipelineResult`

### 5.2 Jellyfish 数据适配器

**文件**: `novel_codex_agent/src/adapters/jellyfish_adapter.py`

```python
"""Jellyfish 数据适配器 —— DB ↔ Pipeline 数据转换。"""

class JellyfishAdapter:
    """在 Jellyfish DB 和 Pipeline 之间做数据转换。"""

    def __init__(self, db_session):
        self.db = db_session

    def load_chapter_context(self, chapter_id: str) -> dict:
        """从 DB 加载章节上下文, 转为 Pipeline 输入。"""
        # 1. 读取 chapter + project 信息
        # 2. 读取所有 shots + shot_details
        # 3. 读取关联的 characters/scenes/props/costumes
        # 4. 组装为 {story_text, story_title, cast_data, director_ids, ...}
        ...

    def write_back_results(self, chapter_id: str, result: PipelineResult):
        """将 Pipeline 结果写回 DB。"""
        # 1. 遍历 prompt_plan.shot_prompts
        # 2. 按 shot_index 匹配 DB 中的 Shot
        # 3. 更新 ShotDetail 的 prompt 相关字段
        # 4. 保存故事板卡片 (如有)
        # 5. 更新角色资产 (如有增强)
        ...
```

### 5.3 API 路由设计

**文件**: `backend/app/api/v1/routes/novel_codex.py`

```python
router = APIRouter(prefix="/novel-codex", tags=["novel-codex"])

# ---- 端点 1: 异步生成 Prompt ----
@router.post("/generate")
async def generate_prompts(
    request: NovelCodexGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[NovelCodexTaskRead]:
    """
    为指定章节一键生成高质量视频 Prompt。

    流程:
    1. 从 DB 读取章节所有 shots + entities
    2. 组装 Pipeline 输入
    3. 在后台线程执行 Pipeline
    4. 返回 task_id, 前端轮询状态
    """

# ---- 端点 2: 查询任务状态 ----
@router.get("/status/{task_id}")
async def get_task_status(task_id: str) -> ApiResponse[NovelCodexStatusRead]:
    """查询 Prompt 生成任务状态。"""

# ---- 端点 3: 获取生成结果 ----
@router.get("/result/{task_id}")
async def get_task_result(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[NovelCodexResultRead]:
    """获取生成结果摘要 (prompt 列表 + 质量评分 + 卡片)。"""
```

### 5.4 请求/响应 Schema

**文件**: `backend/app/schemas/novel_codex.py`

```python
class NovelCodexGenerateRequest(BaseModel):
    chapter_id: str                    # 章节 ID
    director_ids: list[str] | None     # 导演风格 (可选)
    target_models: list[str] = ["kling", "jimeng"]  # 目标模型
    enable_storyboard_cards: bool = True  # 是否生成故事板卡片

class NovelCodexTaskRead(BaseModel):
    task_id: str
    status: str           # pending / running / succeeded / failed
    progress: int         # 0-100
    current_step: str     # 当前步骤名

class NovelCodexShotPromptRead(BaseModel):
    shot_id: str
    shot_index: int
    prompt_text: str           # 视频 prompt
    negative_prompt: str       # 负面提示词
    model: str                 # kling / jimeng
    quality_score: float       # 一致性评分

class NovelCodexResultRead(BaseModel):
    task_id: str
    status: str
    shot_prompts: list[NovelCodexShotPromptRead]
    storyboard_cards: list[dict]
    overall_score: float
    cast_updated: bool
```

### 5.5 桥接服务

**文件**: `backend/app/services/novel_codex_bridge.py`

```python
class NovelCodexBridge:
    """桥接 Jellyfish DB 和 novel_codex_agent Pipeline。"""

    async def generate_for_chapter(
        self,
        db: AsyncSession,
        chapter_id: str,
        director_ids: list[str] | None = None,
        target_models: list[str] = None,
        enable_cards: bool = True,
    ) -> dict:
        """
        核心方法: 为章节生成 Prompt。

        1. 从 DB 加载数据
        2. 调用 PipelineEngine.run()
        3. 将结果写回 DB
        4. 返回结果摘要
        """

    def _build_story_text(self, shots: list[Shot]) -> str:
        """合并所有 shots 的 script_excerpt 为完整剧本文本。"""

    def _build_cast_data(
        self,
        characters: list[Character],
        costumes: list[Costume],
    ) -> dict:
        """从 DB entities 构建 Pipeline 的 cast_data 格式。"""

    def _write_back(
        self,
        db: AsyncSession,
        chapter_id: str,
        result: PipelineResult,
        target_models: list[str],
    ):
        """将 Pipeline 结果写回 Jellyfish DB。"""
```

---

## 六、集成步骤 (实施顺序)

### Phase 1: Pipeline 引擎封装 (novel_codex_agent 侧)

| # | 任务 | 文件 | 预计行数 |
|---|---|---|---|
| 1.1 | 创建 `PipelineEngine` 类 | `src/engine.py` | ~150 行 |
| 1.2 | 创建 `JellyfishAdapter` | `src/adapters/jellyfish_adapter.py` | ~200 行 |
| 1.3 | 单元测试 | `tests/test_engine.py` | ~100 行 |

### Phase 2: Jellyfish 后端集成

| # | 任务 | 文件 | 预计行数 |
|---|---|---|---|
| 2.1 | 新增 Schema | `backend/app/schemas/novel_codex.py` | ~80 行 |
| 2.2 | 新增桥接服务 | `backend/app/services/novel_codex_bridge.py` | ~250 行 |
| 2.3 | 新增 API 路由 | `backend/app/api/v1/routes/novel_codex.py` | ~150 行 |
| 2.4 | 注册路由 | `backend/app/api/v1/__init__.py` | +3 行 |
| 2.5 | 添加 novel_codex_agent 为依赖 | `backend/requirements.txt` 或 pyproject.toml | +1 行 |

### Phase 3: Jellyfish 前端集成

| # | 任务 | 文件 | 预计行数 |
|---|---|---|---|
| 3.1 | API Service 层 | `front/src/services/novelCodexService.ts` | ~60 行 |
| 3.2 | "生成 Prompt" 按钮组件 | `front/src/pages/aiStudio/chapter/components/NovelCodexButton.tsx` | ~120 行 |
| 3.3 | 进度弹窗组件 | `front/src/pages/aiStudio/chapter/components/NovelCodexProgressModal.tsx` | ~180 行 |
| 3.4 | 结果展示组件 | `front/src/pages/aiStudio/chapter/components/NovelCodexResultPanel.tsx` | ~200 行 |
| 3.5 | 集成到 ChapterStudio | `front/src/pages/aiStudio/chapter/ChapterStudio.tsx` | +20 行 |

---

## 七、关键设计决策

### 7.1 为什么是"插件"而非"合并"?

| 方案 | 优点 | 缺点 |
|---|---|---|
| **A: 插件 (选定)** | 两个项目独立演进, 松耦合; novel_codex_agent 可独立使用(CLI) | 需要数据转换层 |
| B: 代码合并 | 无转换开销 | 代码耦合, 难以独立维护, git 冲突风险 |
| C: 微服务 | 完全解耦 | 部署复杂, 需要额外服务发现/通信 |

### 7.2 数据转换策略

novel_codex_agent 内部使用自己的 Schema (Storyboard/PromptPlan/StoryAnalysis)，
Jellyfish 使用 SQLAlchemy ORM 模型。

**桥接层职责**:
- **读取**: Jellyfish DB → 组装 Pipeline 输入 (story_text + cast_data + 已有分镜)
- **写回**: Pipeline 输出 → 匹配 Jellyfish Shot → 更新 prompt 字段

### 7.3 任务执行模型

复用 Jellyfish 的异步任务框架 (`AbstractAsyncDelegatingExecutor`)：
- Pipeline 运行在后台线程/进程
- 前端通过 task_id 轮询进度
- 支持取消操作

### 7.4 Prompt 存储方案

**方案 A (推荐)**: 在 `ShotDetail` 新增字段
```sql
ALTER TABLE shot_details ADD COLUMN video_prompt_kling TEXT DEFAULT '';
ALTER TABLE shot_details ADD COLUMN video_prompt_jimeng TEXT DEFAULT '';
ALTER TABLE shot_details ADD COLUMN negative_prompt TEXT DEFAULT '';
ALTER TABLE shot_details ADD COLUMN prompt_quality_score REAL DEFAULT 0;
```

**方案 B**: 新建 `shot_video_prompts` 表 (更灵活, 支持多模型扩展)
```sql
CREATE TABLE shot_video_prompts (
    id INTEGER PRIMARY KEY,
    shot_id VARCHAR(64) NOT NULL,
    target_model VARCHAR(32) NOT NULL,
    prompt_text TEXT NOT NULL,
    negative_prompt TEXT DEFAULT '',
    quality_score REAL DEFAULT 0,
    source VARCHAR(32) DEFAULT 'novel_codex',
    UNIQUE(shot_id, target_model)
);
```

---

## 八、前端交互流程

```
用户在 ChapterStudio 页面
    │
    ▼
点击 "AI Prompt 生成" 按钮
    │
    ▼
弹出配置面板:
┌─────────────────────────────┐
│  导演风格: [下拉选择]         │
│  目标模型: ☑ kling  ☑ jimeng │
│  故事板卡片: ☑ 生成          │
│                             │
│       [开始生成]             │
└─────────────────────────────┘
    │
    ▼
POST /api/v1/novel-codex/generate
    │
    ▼
进度弹窗 (轮询 /status):
┌─────────────────────────────┐
│  ████████░░░░ 65%           │
│  当前步骤: Step 4/6          │
│  Prompt 撰写中...            │
│                             │
│       [取消]                │
└─────────────────────────────┘
    │
    ▼
完成 → 结果面板:
┌─────────────────────────────┐
│  ✅ 生成完成! 评分: 92/100   │
│                             │
│  Shot 1: 陆沉抬头  [查看]    │
│  Shot 2: 苏瑶推门  [查看]    │
│  ...                        │
│                             │
│  故事板卡片: 12 张 [查看全部] │
│                             │
│  [应用到镜头]  [导出 Excel]   │
└─────────────────────────────┘
    │
    ▼
点击 "应用到镜头" → 写入 DB → 镜头列表刷新
```

---

## 九、风险与注意事项

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| Pipeline 执行时间长 (30s-3min) | 前端等待体验差 | 异步任务 + 进度轮询 |
| LLM API 调用失败 | 部分镜头无 prompt | 支持单镜头重试 |
| 数据格式不匹配 | 角色/场景信息丢失 | 适配器层充分测试 |
| novel_codex_agent 依赖冲突 | Jellyfish 环境被破坏 | 使用独立 venv 或 pip install -e |
| DB Schema 变更 | Jellyfish 现有数据不兼容 | 提供 migration 脚本 |

---

## 十、后续扩展

1. **增量更新**: 只重新生成被修改镜头的 Prompt, 而非全章节
2. **Prompt 对比**: 并排展示 Jellyfish 原始 prompt vs novel_codex 增强 prompt
3. **模板市场**: 将 novel_codex 的 Prompt 策略作为可配置模板
4. **批量处理**: 支持一次处理多个章节
5. **质量追踪**: 记录每次生成的质量评分趋势
