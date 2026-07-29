# 修改日志

本文件记录 novel_auto_agent 项目的重要功能修改、问题修复和改进。

---

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
