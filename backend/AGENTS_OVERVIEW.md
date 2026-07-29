# Codex Agent 运行时参考

> 供 Coding Agent (Codex CLI / Claude Code 等) 了解本项目的核心模块和注意事项。

---

## 1. Pipeline 引擎

位置: pp/pipeline/engine.py

封装了 LangGraph 6 步 Pipeline 为可调用引擎 PipelineEngine。推进时通过 NovelCodexBridge 桥接调度。

### 线程安全 ⚠️

NovelCodexBridge 内部使用模块级全局字典 _tasks 存储异步任务状态,
并通过 _tasks_lock = threading.Lock() 保护所有读写操作。

**关键约束:**
- 所有任务创建/状态更新/读取必须走 _create_task() / _update_task_fields() / _safe_read_task()
- **不要**直接 _tasks[key] = value 或 _tasks.get(key) 绕过锁

---

## 2. CastManager 演员表

| 文件 | ackend/app/pipeline/utils/cast_manager.py |
|------|-------------|

跨章节的角色持久化管理器, 维护 output/cast.json。(新增 CastManager)

### 并发保护 ⚠️

- 每个实例自带 self._lock (实例锁) 保护内存中的 cast_data
- 全局 _file_locks 按文件路径缓存文件锁, 保证多实例读写同一 cast.json 不冲突
- save() 使用**原子写入**: 先写 .tmp 临时文件, 再 os.replace() 到目标路径

**关键约束:**
- 修改 cast_data 前必须持有 self._lock
- 读写文件前必须持有对应的 _file_lock
- 需要在无锁情况下合并角色？用 	emp_cm = CastManager(), 然后用 	emp_cm._merge_characters_unlocked() + 持有 	emp_cm._lock
- **不要**再用 CastManager.__new__(CastManager) hack —— 它绕过了 __init__ 且不创建锁

---

## 3. PipelineAgent 的 state 修改

在 LangGraph agent 节点中修改 state 时:
- state 是 TypedDict, **尽量返回新值而非原地修改**
- Step1Analyzer 中合并 CastManager 时使用 	emp_cm._merge_characters_unlocked(), 不要绕过锁

---

## 4. Task 执行器

| 核心文件 | ackend/app/services/worker/task_executor.py |
|----------|-----------------------------|

AbstractWorkerTaskExecutor.run() 统一了 Celery worker 内的任务生命周期:
读取任务 → 执行 → 写 result/status/error → apply。

AsyncDelegateExecutor 桥接 async 业务任务 (图片/视频生 成/分镜帧提示词)。

### 回滚计数

pipeline/graph/workflow.py:  中的 _should_replan 和 _should_continue_after_review 都会递增 eplan_count。

注意: **同一个回滚不要被两处同时计数**, 否则 eplan_count 会翻倍。

---

## 5. Schema 一致性

storyboard schema 中 Shot.progers_in_shot 是 Step 5 一致性审计的道具依据。
 characters > scenes > shots 之间的 ID 引用必须保持一致性。

- Character.character_sheet >= 100 字符, 不足时 Step1 会用 isual_anchor + appearance 兜底
-  cast_manager._merge_characters_unlocked 做服装提取等副作用