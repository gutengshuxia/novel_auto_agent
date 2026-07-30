# 修改日志

本文件记录 novel_auto_agent 项目的重要功能修改、问题修复和改进。

---

## [2026-07-29] 任务执行日志前端可视化

### 问题描述

用户无法在前端看到分镜提取等任务的执行日志，只能看到进度条和当前步骤名称，无法了解任务执行的详细过程。

### 修改内容

- **新增 TaskLogEntry 模型**（`backend/app/models/task_log.py`）
  - 字段：task_id、timestamp、level（info/warn/error/success）、step、message
  - 注册到 `models/__init__.py` 和 `core/db.py` 的 `init_db()`

- **任务执行器写入日志**（`backend/app/services/worker/task_executor.py`）
  - 新增 `_write_log()` 方法，使用独立 session 写入（不影响主事务）
  - 在任务开始、步骤切换、LLM 执行完成、任务成功/失败时写入日志

- **分镜任务详细日志**（`backend/app/services/script_processing_worker.py`）
  - DivideTaskExecutor.execute() 执行后写入：镜头总数、前5个镜头名称

- **新增 API 端点**（`backend/app/api/v1/routes/film/task_status.py`）
  - `GET /tasks/{task_id}/logs?after_id=N`：增量拉取日志（最多 200 条）

- **前端日志面板**（`front/src/pages/aiStudio/project/ProjectWorkbench/components/TaskLogPanel.tsx`）
  - 暗色终端风格，按时间线展示日志
  - 每 2 秒增量轮询，自动滚动到底部
  - 不同级别用不同颜色图标区分（info=蓝●、success=绿✓、warn=黄⚠、error=红✗）

- **集成到章节列表**（`front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`）
  - 有活跃任务的章节行可展开，展开后显示 TaskLogPanel

- **数据流**：Worker 执行 → write_task_log() → task_log_entries 表 → API 轮询 → TaskLogPanel 展示

### 使用方式

1. 启动后端（`uvicorn`）和前端（`vite`）
2. 在章节列表触发分镜提取
3. 展开正在执行的章节行，即可看到实时执行日志

### 兼容性

- `task_log_entries` 表通过 `init_db.py` 创建
- 日志写入失败不影响主任务执行（静默降级）

---

## [2026-07-29] 分镜提取增强：丰富镜头语言 + 按情节智能拆分

### 问题描述

1. **分镜列表只有剧本摘录**：分镜提取后 ShotDetail 全部使用默认值（static 机位、eye_level、ms 景别），没有画面描述、运镜、氛围等信息
2. **按回车/句号拆分而非按情节**：原 system prompt 过于简短，LLM 默认按段落边界切分

### 修改内容

- **ShotDivision schema 增强**（`backend/app/schemas/skills/script_processing.py`）
  - 新增可选字段：`description`（画面描述）、`camera_shot`（景别）、`camera_angle`（机位）、`camera_movement`（运镜）、`duration`（时长）、`mood_tags`（情绪标签）、`atmosphere`（氛围）
  - 所有新字段均为可选，向后兼容旧数据

- **ScriptDividerAgent prompt 增强**（`backend/app/chains/agents/script_divider_agent.py`）
  - 明确"禁止按段落/标点拆分"规则
  - 要求每个镜头必须提供：画面描述、景别、机位、运镜、时长、情绪标签、氛围
  - 给出镜头语言推断指引（对话→CU/MCU，动作→MS/MLS，环境→LS/ELS）

- **写库逻辑升级**（`backend/app/services/studio/script_division.py`）
  - 新增 `_safe_camera_shot` / `_safe_camera_angle` / `_safe_camera_movement` 安全映射函数
  - `_append_division_rows` 现在使用 LLM 输出的丰富数据填充 ShotDetail（description、duration、mood_tags、atmosphere 等）
  - 无法识别的枚举值安全降级为默认值

---

## [2026-07-29] 更新 README 文件

### 修改内容

同步更新两份 README，反映项目最新状态：

- **根目录 README.md**
  - 核心功能新增：任务执行线程降级、步骤可视化、结果通知、模型管理
  - 项目结构更新：task_manager/、worker/、script_processing_worker.py
  - 技术栈更新：Celery → ThreadPoolExecutor(默认)/Celery(可选)，多 LLM 供应商
  - 启动流程更新：新增"配置模型"步骤，标注无需 Celery
  - Web GUI 说明扩展：分镜提取、AI Prompt、模型管理、任务通知
  - 文档列表新增 CHANGELOG.md

- **backend/README.md**
  - 目录结构更新：core/task_manager/、services/worker/、pipeline/
  - 新增「任务执行系统」章节：双模式执行、9 个执行器一览、步骤可视化
  - 新增「隐私安全」说明：.env / *.db / *.log / cast.json 不可提交
  - 扩展说明新增任务执行器开发指引


## [2026-07-29] 更新架构文档：任务执行系统 + 分镜提取结果展示

### 修改内容

同步更新三份文档，反映近期新增的任务执行线程降级、步骤可视化、结果通知等功能：

- **ARCHITECTURE.md** 新增 §17「任务执行系统与前端可视化」
  - 双模式执行架构（线程/Celery）
  - current_step 数据流全链路
  - 任务结果通知机制
  - 9 个任务执行器一览

- **DEVELOPER_GUIDE.md** 新增 §20「任务执行系统开发指南」
  - 环境变量配置说明
  - 添加新执行器的步骤
  - current_step 各层字段对照
  - 隐私安全文件清单（.env / *.db / *.log / cast.json）

- **USER_GUIDE.md** 新增 §16「分镜提取与结果查看」
  - 提取分镜操作步骤
  - 执行进度查看说明
  - 结果通知与查看方式
  - 设置默认模型指引
  - 常见问题速查表


## [2026-07-29] 分镜提取完成后显示结果通知

### 问题描述

分镜提取任务完成后，前端只显示进度条和"已完成"状态，用户无法直观看到提取的产出结果（如拆分了多少个镜头）。

### 解决思路

在任务完成（settled）时，通过已建立的 task ID 追踪链路，从后端 `/tasks/{task_id}/result` API 获取任务结果数据（`ScriptDivisionResult`），提取 `total_shots` 字段，通过 antd `notification.success` 弹窗展示给用户。

### 修改文件

- `front/src/pages/aiStudio/project/ProjectWorkbench/chapterDivisionTasks.ts`
  - 新增 `TaskResultInfo` 类型
  - `useChapterDivisionTaskMapPolling` 新增 `chapterTaskIdsRef` 追踪每个章节的任务 ID
  - 任务完成时自动调用 `getTaskResultApiV1FilmTasksTaskIdResultGet` 获取结果
  - `onTasksSettled` 回调签名扩展为 `(chapterIds, taskResults) => void`

- `front/src/pages/aiStudio/project/ProjectWorkbench/tabs/ChaptersTab.tsx`
  - 导入 `notification` 组件
  - `onTasksSettled` 回调中遍历 taskResults，显示通知：
    - 成功：`分镜提取完成 - 章节名：成功拆分为 N 个镜头`
    - 失败：`分镜提取失败 - 章节名：提取失败，请查看日志`

### 数据流

任务完成 → polling 检测到 finished → 通过 chapterTaskIdsRef 获取 taskId → 调用 /tasks/{taskId}/result API → 解析 ScriptDivisionResult.total_shots → notification.success 展示

### 测试结果

- ✅ TypeScript 编译通过（0 errors）


## [2024-07-21] 前端模型管理与 Pipeline 打通 + LLM 测试功能实现

### 问题描述

1. **模型管理与 Pipeline 断开**：前端「模型管理」页面可以添加供应商和模型，但 Pipeline（6步分析）只读 `.env` 文件配置，两者完全独立。用户在前端配置的模型无法用于小说分镜分析。

2. **测试功能为 Mock**：
   - 供应商管理的「测试连接」按钮：只 setTimeout 800ms 后直接显示成功，没有真正调用 API
   - 模型管理的「测试生成」按钮：onClick 是空函数，点击无任何反应
   - 模型管理的「快速测试」按钮：没有 onClick 事件，纯占位

### 解决思路

**问题 1 打通方案**：
- 在 Pipeline 的 `llm.py` 添加「DB 配置覆盖」机制
- Bridge 从 DB 读取选择的模型配置后，调用 `set_llm_override()` 设置覆盖
- `get_llm()` 优先检查覆盖配置，忽略 `.env`
- Pipeline 执行完毕后调用 `clear_llm_override()` 清理
- 前端 NovelCodexPanel 添加模型选择下拉框，传递 `text_model_id` 到后端

**问题 2 解决思路**：
- 后端新增真实测试接口，实际调用 LLM API 验证
- 前端按钮绑定到这些接口，显示 loading 和结果

### 修改内容

#### 后端修改

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `backend/app/pipeline/utils/llm.py` | 新增功能 | 添加 `set_llm_override()` / `clear_llm_override()` / `get_llm_override()` 函数；`get_llm()` 新增检查覆盖配置逻辑 |
| `backend/app/pipeline/utils/__init__.py` | 导出更新 | 导出新增的 override 函数 |
| `backend/app/services/novel_codex_bridge.py` | 新增功能 | `generate_for_chapter()` 新增 `text_model_id` 参数；新增 `_resolve_model_config()` 方法从 DB 加载模型配置 |
| `backend/app/schemas/novel_codex.py` | 字段新增 | `NovelCodexGenerateRequest` 新增 `text_model_id` 字段 |
| `backend/app/api/v1/routes/novel_codex.py` | 透传参数 | 将 `text_model_id` 传递给 bridge |
| `backend/app/api/v1/routes/llm.py` | 新增接口 | 新增 `POST /providers/{id}/test` 和 `POST /models/{id}/test` 测试端点 |
| `backend/app/services/llm/test_connection.py` | 新建文件 | 实现真实的 LLM 连接测试逻辑，支持 OpenAI 兼容和 Anthropic 协议 |

#### 前端修改

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `front/src/services/novelCodexService.ts` | 参数新增 | `NovelCodexGenerateParams` 新增 `text_model_id` 字段 |
| `front/src/pages/.../NovelCodexPanel.tsx` | UI 新增 | 添加模型选择下拉框，自动加载 text 类型模型列表，传递选中模型 ID |
| `front/src/pages/.../ProvidersTab.tsx` | 功能修复 | 「测试连接」按钮从 mock 改为调用真实 API |
| `front/src/pages/.../ModelsTab.tsx` | 功能修复 | 「测试生成」「快速测试」按钮添加 onClick 事件，调用模型测试接口 |

### 数据流

**Pipeline 打通后的数据流**：

```
前端模型管理 UI → 添加供应商/模型 → 存入 DB
                                         ↓
前端 NovelCodexPanel → 选择模型 → POST /generate (text_model_id)
                                         ↓
Bridge._resolve_model_config() → 从 DB 读取 provider.api_key + base_url + model.name
                                         ↓
set_llm_override() → Pipeline 所有 agents 的 get_llm() 使用 DB 配置
                                         ↓
Pipeline 执行完毕 → clear_llm_override() 清理
```

**测试功能数据流**：

```
前端点击「测试生成」→ POST /api/v1/llm/models/{id}/test
                              ↓
                  test_connection.py 读取 provider 配置
                              ↓
                  向 LLM API 发送测试消息 "请用一句话回复：你好"
                              ↓
                  返回 {success, message, response, latency_ms}
                              ↓
                  前端显示成功/失败提示
```

### 测试步骤

1. **后端导入测试**：
   ```bash
   cd backend && source .venv/bin/activate
   python -c "from app.pipeline.utils.llm import set_llm_override, clear_llm_override; print('✅')"
   python -c "from app.services.novel_codex_bridge import bridge; print('✅')"
   python -c "from app.services.llm.test_connection import test_model_connection_service; print('✅')"
   ```

2. **前端编译测试**：
   ```bash
   cd front
   npx tsc --noEmit    # TypeScript 类型检查
   npx vite build      # 生产构建
   ```

3. **功能测试**：
   - 启动后端：`uvicorn app.main:app --reload --port 8000`
   - 启动前端：`npm run dev`
   - 在「模型管理」添加供应商（如阿里百炼）和模型
   - 点击「测试生成」按钮，验证是否显示成功/失败提示
   - 在章节页面点击「AI Prompt」，验证模型选择下拉框是否显示
   - 选择模型后生成，验证 Pipeline 是否使用了选中的模型

### 测试结果

- ✅ 后端所有模块导入正常
- ✅ TypeScript 编译通过（0 errors）
- ✅ Vite 生产构建成功（3.08s）
- ✅ API 端点注册正确（`/providers/{id}/test`、`/models/{id}/test`）

### 使用方式

**打通后的使用流程**：

1. 在「模型管理」页面添加供应商（如阿里百炼、OpenAI 等）
2. 在该供应商下添加模型（类别选「文本」）
3. 进入章节页面，点击「AI Prompt」按钮
4. 弹窗顶部会出现「选择分析模型」下拉框
5. 选择要使用的模型，点击生成
6. Pipeline 会使用选中的模型进行 6 步分析

**测试功能**：

- 供应商页面：点击「测试连接」验证 API Key 和 Base URL 是否正确
- 模型页面：点击「测试生成」验证模型是否能正常返回结果
- 测试中显示 loading，完成后显示成功/失败消息和延迟

### 兼容性

- 未选择模型时，Pipeline 回退到 `.env` 默认配置（向后兼容）
- 测试接口失败时返回详细错误信息，不会导致系统崩溃

## [2026-07-21] 任务执行线程降级 + 前端步骤可视化

### 问题描述

1. **任务无法执行**：分镜提取等异步任务依赖 Celery worker，但开发环境下用户通常只启动 FastAPI + 前端，不会单独启动 Celery。导致任务创建后一直卡在 `pending` 状态，前端显示"任务执行中"但实际什么都没做。

2. **看不到执行步骤**：任务执行过程中只有 3 个进度节点（5% → 70% → 100%），没有中间步骤信息。用户无法知道当前执行到了哪一步（如"正在拆分镜头"还是"正在写入结果"）。

3. **日志信息不足**：`task_logging.py` 只记录基础事件（started/succeeded/failed），缺少中间步骤日志。

### 解决思路

**问题 1 — 线程降级模式**：
- `execute_task.py` 新增 `TASK_EXECUTOR_MODE` 环境变量（默认 `"thread"`）
- 线程模式下，任务在后台线程池中直接执行，无需 Celery worker
- 保留 Celery 模式（设置 `TASK_EXECUTOR_MODE=celery` 即可切换）

**问题 2 — 步骤可视化**：
- 给 `GenerationTask` 模型添加 `current_step` 字段（VARCHAR 255）
- 贯穿全链路：DB → TaskRecord → TaskStatusView → API 响应 → 前端类型 → 通知组件
- 每个执行器配置 `step_names` 列表（如 `["准备分镜任务", "正在拆分镜头…", "写入分镜结果"]`）
- 执行器在不同阶段自动更新 `current_step`
- 前端通知弹窗显示当前步骤名称

### 修改内容

#### 后端修改

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `backend/app/models/task.py` | 字段新增 | `GenerationTask` 新增 `current_step` 列 |
| `backend/app/core/task_manager/types.py` | 字段新增 | `TaskRecord`、`TaskStatusView`、`TaskListItemView` 新增 `current_step` 字段 |
| `backend/app/core/task_manager/stores.py` | 方法新增 | `SqlAlchemyTaskStore` 和 `SyncSqlAlchemyTaskStore` 新增 `set_current_step()` 方法；`get_status_view()` 和 `list_task_views()` 返回 `current_step` |
| `backend/app/api/v1/routes/film/common.py` | 字段新增 | `TaskStatusRead`、`TaskListItemRead` 新增 `current_step` 字段 |
| `backend/app/api/v1/routes/film/task_status.py` | 透传字段 | `get_task_status` 和 `list_tasks` 端点返回 `current_step` |
| `backend/app/services/worker/task_executor.py` | 功能增强 | 新增 `step_names` 类属性和 `_set_step()` 方法；执行阶段自动更新步骤名称 |
| `backend/app/services/script_processing_worker.py` | 步骤配置 | 9 个执行器均配置 `step_names`（分镜/提取/一致性/人物/道具/场景/服装/优化/精简） |
| `backend/app/tasks/execute_task.py` | 重写 | 支持线程降级模式（默认）和 Celery 模式 |

#### 前端修改

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `front/src/services/generated/models/TaskStatusRead.ts` | 字段新增 | 新增 `current_step` 可选字段 |
| `front/src/services/generated/models/TaskListItemRead.ts` | 字段新增 | 新增 `current_step` 可选字段 |
| `front/src/pages/.../chapterDivisionTasks.ts` | 类型扩展 | `RelationTaskState` 新增 `currentStep`；`toRelationTaskStateFromStatusRead` 映射该字段 |
| `front/src/pages/.../components/taskUiStore.ts` | 类型扩展 | `TaskUiItem` 新增 `currentStep`；合并逻辑包含该字段 |
| `front/src/pages/.../components/taskNotificationHelpers.tsx` | 显示增强 | 通知描述中优先显示 `currentStep`（如"正在拆分镜头… 进度 35%"） |

#### 数据库变更

| 操作 | SQL |
|------|-----|
| 新增列 | `ALTER TABLE generation_tasks ADD COLUMN current_step VARCHAR(255) DEFAULT NULL;` |

### 数据流

**任务执行 + 步骤可视化**：

```
前端点击「提取分镜」→ POST /divide-async → 创建任务 → enqueue_task_execution()
                                                    ↓
                                    线程模式：ThreadPoolExecutor 提交任务
                                                    ↓
                                    DivideTaskExecutor.run(task_id)
                                        → set_current_step("准备分镜任务")     [progress=5%]
                                        → set_current_step("正在拆分镜头…")    [progress=5-70%]
                                        → LLM 调用 ScriptDividerAgent
                                        → set_current_step("写入分镜结果")     [progress=70-100%]
                                        → apply_result() 写入 DB
                                        → set_status(succeeded)              [progress=100%]
                                                    ↓
前端每 2s 轮询 GET /tasks/{id}/status → 返回 {progress, current_step, status}
                                                    ↓
前端通知弹窗显示："正在拆分镜头… 进度 35% · 已运行 12 秒"
```

### 测试步骤

1. **后端导入测试**：
   ```bash
   cd backend && source .venv/bin/activate
   python -c "from app.tasks.execute_task import enqueue_task_execution; print('✅')"
   python -c "from app.services.script_processing_worker import DivideTaskExecutor; print(DivideTaskExecutor.step_names)"
   ```

2. **前端编译测试**：
   ```bash
   cd front
   npx tsc --noEmit
   npx vite build
   ```

3. **功能测试**：
   - 启动后端：`uvicorn app.main:app --reload --port 8000`
   - 启动前端：`npm run dev`
   - 在章节页面添加内容，点击「提取分镜」
   - 观察右上角通知弹窗是否显示步骤名称和进度

### 测试结果

- ✅ 后端所有模块导入正常
- ✅ `DivideTaskExecutor.step_names = ['准备分镜任务', '正在拆分镜头…', '写入分镜结果']`
- ✅ TypeScript 编译通过（0 errors）
- ✅ Vite 生产构建成功（3.06s）

### 使用方式

**无需额外配置**：默认就是线程模式，只要启动了 `uvicorn` 就能执行任务。

如需切换回 Celery 模式：
```bash
TASK_EXECUTOR_MODE=celery uvicorn app.main:app --reload --port 8000
# 同时需要启动 Celery worker
celery -A app.core.celery_app worker --loglevel=info
```

### 兼容性

- 线程模式为默认模式，向后兼容所有现有功能
- `current_step` 为可选字段，不影响已有任务查询
- Celery 模式仍可通过环境变量切换

---

## [2026-07-29] 修复分镜提取失败 + 添加"设为默认模型"功能

### 问题描述

1. **分镜提取失败**：点击提取分镜后，任务立即失败，显示"准备分镜任务 · 进度 5%"。错误信息：`No default model configured for category=text`。

2. **无默认模型设置入口**：前端模型管理页面没有"设为默认"按钮，用户添加模型后不知道需要设置默认，也没有便捷入口。

### 解决思路

**问题 1**：`ModelSettings` 表的 `default_text_model_id` 为 NULL。分镜提取任务通过 `build_default_text_llm_sync()` 查找默认模型，找不到就报错。解决：手动设置已添加的 `qwen-max` 模型为默认。

**问题 2**：在模型管理页面的"更多"下拉菜单中添加"设为默认"选项，调用已有的 `PATCH /api/v1/llm/model-settings` 接口。

### 修改内容

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `front/src/pages/.../ModelsTab.tsx` | 功能新增 | 添加"设为默认"菜单项、`handleSetDefault` 函数、加载当前默认模型状态 |
| 数据库 | 数据修复 | 设置 `ModelSettings.default_text_model_id` 为已添加的 qwen-max 模型 ID |

### 测试结果

- ✅ TypeScript 编译通过（0 errors）
- ✅ 默认文本模型已设置为 qwen-max
- ✅ 分镜提取任务现在可以正常执行

### 使用方式

在「模型管理」页面：
1. 找到要设为默认的模型
2. 点击操作栏的"更多"（三个点图标）
3. 选择"设为默认"
4. 系统会提示"已将「xxx」设为文本/图片/视频默认模型"

---

---

## 格式说明

每条修改日志包含以下部分：

- **问题描述**：说明要解决的问题或要添加的功能
- **解决思路**：技术方案和设计决策
- **修改内容**：具体修改了哪些文件，每个文件的改动类型
- **数据流**：（如适用）展示数据在系统中的流转路径
- **测试步骤**：如何验证修改是否正确
- **测试结果**：实际测试的输出
- **使用方式**：（如适用）说明用户如何使用新功能
- **兼容性**：（如适用）说明对现有功能的影响
