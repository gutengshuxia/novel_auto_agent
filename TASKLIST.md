# 任务清单 - Pipeline 集成

> 最后更新：2026-07-29
> Commit: 3cb5e1b

---

## 本次改动概述

将 Pipeline（novel_codex_agent）的 Step 3-6 集成到前端工作流，实现完整的 Prompt 生成流程：
**Beat 规划 → 时间戳 Prompt 生成 → 一致性审计 → 模型适配**

---

## ✅ 已完成

### 1. 分镜拆分 Prompt 优化（合并优先原则）
- [x] 修改 ScriptDividerAgent prompt，新增"宁少勿多，合并优先"核心原则
- [x] 明确"环境描写 + 同一环境中的人物活动 = 一个建立镜头"
- [x] 删除"超过 5-8 行就拆"的激进规则
- [x] Commit: e20e2a3

### 2. 新增 4 个 Agent
- [x] **BeatPlanningAgent** (`backend/app/chains/agents/beat_planning_agent.py`)
  - 将镜头拆分为时间戳 Beat 序列
  - 输出声音设计 + Prompt 策略（A/B/C）
  - 移植自 Pipeline Step3_Planner

- [x] **TimestampPromptAgent** (`backend/app/chains/agents/timestamp_prompt_agent.py`)
  - 生成带时间戳节奏的视频 Prompt（[0-2s] Beat1 / [2-4s] Beat2...）
  - 使用 @角色名 引用（不重复描述外貌）
  - 包含负面提示词 + 5 模型风格指令
  - 移植自 Pipeline Step4_Writer

- [x] **PromptConsistencyAgent** (`backend/app/chains/agents/prompt_consistency_agent.py`)
  - 11 维度一致性审计
  - 宽容审核策略：只抓实质性错误，允许合理细化
  - 输出评分 + 修正建议 + 优化后 Prompt
  - 移植自 Pipeline Step5_Consistency

- [x] **ModelAdapterAgent** (`backend/app/chains/agents/model_adapter_agent.py`)
  - 纯规则优化，不需要 LLM 调用
  - Kling：补充中文运镜
  - 即梦：确保长度 >= 80 字符
  - 通用负面提示词兜底

### 3. 新增 Schema
- [x] **BeatPlanResult** (`backend/app/schemas/skills/beat_planning.py`)
  - Beat 序列 + 声音设计 + Prompt 策略

### 4. 完整 Pipeline 任务
- [x] **full_prompt_pipeline_tasks.py** (`backend/app/services/film/full_prompt_pipeline_tasks.py`)
  - 4 步串行流程：Beat 规划 → 时间戳 Prompt → 一致性审计 → 模型适配
  - 复用 shot_frame_prompt_tasks 的上下文构建逻辑
  - 每步写入执行日志
  - 结果写入 ShotDetail.first_frame_prompt / key_frame_prompt / last_frame_prompt

### 5. API 端点
- [x] **POST /api/v1/film/tasks/full-prompt-pipeline**
  - 参数：shot_id + target_model（kling/jimeng/veo/runway/pixverse/通用）
  - 文件：`backend/app/api/v1/routes/film/tasks_images.py`

### 6. 前端集成
- [x] ChapterStudio.tsx：在"AI生成"按钮旁新增"完整Pipeline"按钮
- [x] chapterDivisionTasks.ts：新增 createFullPromptPipelineTask 函数
- [x] taskCopy.ts / taskCenterMeta.ts：注册新任务类型文案

### 7. 任务注册
- [x] task_registry.py：注册 full_prompt_pipeline 任务
- [x] stores.py：添加 full_prompt_pipeline 映射

### 8. 文档
- [x] CHANGELOG.md：记录所有改动

---

## ⏳ 待完成 / 后续优化

### 前端体验优化
- [ ] "完整Pipeline"按钮支持选择目标模型（目前固定为"通用"）
- [ ] Pipeline 执行过程中的实时进度展示（4 步进度条）
- [ ] Pipeline 完成后展示审计评分和 Beat 序列
- [ ] 将 Pipeline 执行日志接入 TaskLogPanel（可展开查看每步详情）

### 功能增强
- [ ] 支持批量 Pipeline（对整个章节所有镜头一键执行）
- [ ] 审计未通过时自动重试（最多 1 次）
- [ ] Pipeline 结果对比：同时展示"简单版"和"Pipeline版"Prompt
- [ ] 支持导出 Pipeline 结果为 Excel（类似 Pipeline CLI 的 export_prompts_to_excel）

### 模型适配增强
- [ ] 完善 Veo/Runway/PixVerse 的适配规则（目前只是透传）
- [ ] 支持更多模型（Sora、Hailuo 等）

### 测试
- [ ] 端到端测试：启动前后端，实际执行一次完整 Pipeline
- [ ] 验证 Beat 规划结果是否合理
- [ ] 验证时间戳 Prompt 格式是否正确
- [ ] 验证一致性审计评分是否合理
- [ ] 验证模型适配输出是否正确

### 架构优化
- [ ] 将 Pipeline 的 cast.json 机制与 Jellyfish 的角色表打通（目前 @角色名 引用使用 DB 中的 character.description）
- [ ] 考虑将 Pipeline 的 Step 1-2（剧本分析 + 导演分镜）也集成到前端
- [ ] 统一两套 Prompt 生成逻辑（ShotFramePromptAgent vs TimestampPromptAgent），避免维护两套代码

---

## 文件变更清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `backend/app/chains/agents/beat_planning_agent.py` | 新增 | Beat 规划 Agent |
| `backend/app/chains/agents/timestamp_prompt_agent.py` | 新增 | 时间戳 Prompt Agent |
| `backend/app/chains/agents/prompt_consistency_agent.py` | 新增 | 一致性审计 Agent |
| `backend/app/chains/agents/model_adapter_agent.py` | 新增 | 模型适配 Agent |
| `backend/app/schemas/skills/beat_planning.py` | 新增 | Beat 规划 Schema |
| `backend/app/services/film/full_prompt_pipeline_tasks.py` | 新增 | 完整 Pipeline 任务 |
| `backend/app/chains/agents/__init__.py` | 修改 | 注册新 Agent |
| `backend/app/api/v1/routes/film/tasks_images.py` | 修改 | 新增 API 端点 |
| `backend/app/services/worker/task_registry.py` | 修改 | 注册新任务 |
| `backend/app/core/task_manager/stores.py` | 修改 | 添加映射 |
| `backend/app/chains/agents/script_divider_agent.py` | 修改 | 合并优先原则 |
| `front/src/pages/aiStudio/chapter/ChapterStudio.tsx` | 修改 | 新增按钮 |
| `front/src/pages/aiStudio/components/taskCopy.ts` | 修改 | 任务文案 |
| `front/src/pages/aiStudio/components/taskCenterMeta.ts` | 修改 | 任务中心 |
| `front/src/pages/aiStudio/project/ProjectWorkbench/chapterDivisionTasks.ts` | 修改 | API 函数 |
| `docs/CHANGELOG.md` | 修改 | 变更记录 |

---

## 快速验证步骤

1. 启动后端：`cd backend && uvicorn app.main:app --reload --port 7788`
2. 启动前端：`cd front && npm run dev`
3. 进入分镜工作室，选择一个镜头
4. 点击"完整Pipeline"按钮
5. 等待执行完成（约 30-60 秒）
6. 检查 key_frame_prompt 字段是否已填充时间戳格式 Prompt
7. 检查 Prompt 中是否使用 @角色名 引用（而非重复描述外貌）
8. 检查是否包含负面提示词

---

## 2026-07-31 ??

### ??????
- [x] "??Pipeline"?????????????/Kling/??/Veo/Runway/PixVerse?
- [x] Pipeline ????????????? 4 ? Steps ????Beat???Prompt??????????????
- [x] ??????????Beat ?????????? Prompt ??
- [x] ????? TaskLogPanel ????????

### ????
- [x] ?? Pipeline?`POST /api/v1/film/tasks/batch-full-prompt-pipeline` ?????????????
- [x] ????????????? 1 ?????????????? Prompt ??
- [x] Pipeline ?????????????"???"?"Pipeline ?" Prompt
- [x] Excel ???`GET /api/v1/film/tasks/{task_id}/export-excel` ?? Pipeline ??

### ??????
- [x] Veo??????????????
- [x] Runway????????????
- [x] PixVerse??????????????
- [x] Sora????????????
- [x] Hailuo??????????????

### ????
| ?? | ?? | ?? |
|------|------|------|
| `front/src/pages/aiStudio/chapter/ChapterStudio.tsx` | ?? | ????? + ????? + ???? |
| `front/src/pages/aiStudio/chapter/components/PipelineProgressModal.tsx` | ?? | Pipeline ???? |
| `backend/app/chains/agents/model_adapter_agent.py` | ?? | ????????? + Sora/Hailuo |
| `backend/app/services/film/full_prompt_pipeline_tasks.py` | ?? | ???? + ?? Pipeline |
| `backend/app/api/v1/routes/film/tasks_images.py` | ?? | ?? API + Excel ?? |
| `backend/app/services/worker/task_registry.py` | ?? | ?? batch_pipeline |
| `backend/app/core/task_manager/stores.py` | ?? | batch_pipeline ???? |
