# novel_auto_agent 开发指南

> 给想贡献代码、扩展功能、二次开发的工程师。
> 阅读本文前建议先看 [ARCHITECTURE.md](./ARCHITECTURE.md)。

---

## 1. 开发环境搭建

```bash
# 合并后的项目
cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent

# 后端环境
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../.env.example .env

# 前端环境 (如需前端开发)
cd ../front
npm install
```

---

## 2. 代码组织原则

本项目遵循 **高内聚、低耦合** 的模块化设计:

```
backend/app/pipeline/
├── schemas/   <- 数据契约, 唯一真理之源
├── agents/    <- 业务逻辑, 单一职责
├── graph/     <- 编排, 不含业务
└── utils/     <- 基础设施, 可独立测试
```

### 2.1 依赖方向 (严禁反向)

```
graph -> agents -> schemas
              -> utils
```

- `schemas/` 不依赖任何项目模块
- `utils/` 不依赖 schemas/agents/graph
- `agents/` 可依赖 schemas 和 utils
- `graph/` 可依赖 agents(注入),但不直接定义业务

---

## 3. 添加新模型 (如 Pika / Sora / Luma)

需要改 2 处:

### 3.1 `backend/app/pipeline/schemas/enums.py`

```python
class TargetModel(str, Enum):
    KLING = "kling"
    JIMENG = "jimeng"
    PIKA = "pika"           # 新增
    SORA = "sora"           # 新增
```

### 3.2 `backend/app/pipeline/agents/step6_adapter.py`

加基线优化器:

```python
# 基线优化器
def _optimize_pika(text: str) -> str:
    return text.replace("cinematic", "pika-style cinematic")

def _optimize_sora(text: str) -> str:
    return f"{text}. The scene feels alive with subtle micro-movements."

_OPTIMIZERS = {
    TargetModel.PIKA.value: _optimize_pika,
    TargetModel.SORA.value: _optimize_sora,
}
```

**注意**: 当前只保留 kling 和 jimeng 两个目标模型,如需添加新模型,还需更新 `DEFAULT_TARGET_MODELS`。

### 3.5 加新 Prompt 版本 (D 版)

若需要第 4 个版本(如 D = "创意自由版"), 改动 2 处:

**1. `backend/app/pipeline/schemas/prompt_plan.py`**:
```python
class PromptStrategy(BaseModel):
    length: str = "medium"
    freedom: str = "medium"
    style: str = "A"   # 也支持 "D"

class PromptVariant(BaseModel):
    ...
    version_a: str
    version_b: str
    version_c: str
    version_d: str = Field(default="", description="创意自由版")  # 新增
    prompt_text: str = ""
```

**2. `backend/app/pipeline/agents/step6_adapter.py`**:
```python
_VERSION_STRATEGIES[_model] = {
    "A": _for_A, "B": _for_B, "C": _for_C, "D": _for_D,
}
```

**3. `utils/excel_export.py` Sheet 3**:
```python
versions = [
    ("A", variant.version_a or ...),
    ("B", variant.version_b or ...),
    ("C", variant.version_c or ...),
    ("D", variant.version_d or ...),  # 新增
]
```

**4. `step4_writer.py`** system prompt 加 Version D 说明。

### 3.4 跑测试

```bash
cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent
python tests/test_schemas.py    # 校验枚举
python tests/test_e2e.py        # 端到端 (记得在测试 JSON 里加新模型)
```

---

## 4. 添加新 Agent 节点

例如想在 Step 3 和 Step 4 之间加一个"分镜质量预审"节点:

### 4.1 在 `backend/app/pipeline/agents/` 加 `step35_pre_review.py`

```python
from ._base import BaseAgent
from ..schemas import Storyboard
from ..graph.state import GraphState
from ..utils import get_logger

logger = get_logger(__name__)

class Step35PreReview(BaseAgent):
    name = "step35_pre_review"
    temperature = 0.3

    def __call__(self, state: GraphState) -> dict:
        storyboard = state["storyboard"]
        logger.info("[Step 3.5] 预审 %d 镜头", len(storyboard.shots))

        # 你的业务逻辑
        if len(storyboard.shots) < 3:
            logger.warning("镜头数过少, 建议补充")

        return {"pre_review_passed": True}


step35_pre_review = Step35PreReview()
```

### 4.2 在 `backend/app/pipeline/agents/__init__.py` 暴露

```python
from .step35_pre_review import Step35PreReview, step35_pre_review
```

### 4.3 在 `backend/app/pipeline/graph/workflow.py` 注册

```python
from ..agents import step35_pre_review, ...

workflow.add_node("step35_pre_review", step35_pre_review)
workflow.add_edge("step3_plan_prompts", "step35_pre_review")
workflow.add_edge("step35_pre_review", "step4_write_prompts")
```

### 4.4 在 `backend/app/pipeline/graph/state.py` 加字段(可选)

如果新节点要写 state:
```python
class GraphState(TypedDict, total=False):
    ...
    pre_review_passed: bool
```

---

## 5. 修改 Step 5 一致性规则

修改 `backend/app/pipeline/agents/step5_consistency.py:_JUDGE_SYSTEM` 的 system prompt 即可。

### 5.1 加新维度

现有 12 维度: `story / character / scene / prop / action / camera / lighting / environment / audio / prompt_quality / negative_prompt / completeness`

加新维度需改 3 处:

**1. system prompt 加规则**:
```python
_JUDGE_SYSTEM = """...
## Step 13 — 主角戏份 (新)
- 主角 (role=主角 的 character) 必须出现在 ≥50% 的镜头
- 主演对白总字数 ≥ 反派
"""
```

**2. `_JudgeOutput` Pydantic 模型加字段**:
```python
class _JudgeOutput(BaseModel):
    ...
    main_character_coverage: _DimensionStatus = Field(default_factory=_DimensionStatus)
```

**3. `_sync_passed_from_dimensions` 加进 dim_names 列表**:
```python
dim_names = [..., "main_character_coverage"]
```

### 5.2 自动修正 (auto-fix)

`_JudgeOutput.optimized_prompt` 由 LLM 填充,Step 5 通过时**自动写回**到 `prompt_plan`:

```python
if judge.passed and (judge.optimized_prompt.version_a ...):
    for sp in plan.shot_prompts:
        for variant in sp.variants:
            variant.version_a = judge.optimized_prompt.version_a
            variant.prompt_text = judge.optimized_prompt.version_a
            # version_b/c 同样
```

若不想自动写回, 把这段代码注释掉即可。

### 5.3 验证

```bash
python tests/test_e2e.py
```

E2E 测试在 `tests/test_e2e.py:_build_judge_pass_json` / `_build_judge_fail_json` 中维护 mock JSON, 新增维度时记得同步加字段。

---

## 6. 更换 LLM Provider

`backend/app/pipeline/utils/llm.py:get_llm` 是工厂函数,改实现即可:

### 6.1 换 Claude

```python
from langchain_anthropic import ChatAnthropic

@lru_cache(maxsize=1)
def get_llm(model=None, temperature=0.7, max_tokens=None):
    return ChatAnthropic(
        model=model or "claude-sonnet-4-5",
        temperature=temperature,
        max_tokens=max_tokens,
    )
```

`requirements.txt` 加 `langchain-anthropic`。

### 6.2 换国内大模型 (如 DeepSeek)

```python
from langchain_openai import ChatOpenAI

@lru_cache(maxsize=1)
def get_llm(model=None, temperature=0.7, max_tokens=None):
    return ChatOpenAI(
        model=model or "deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )
```

---

## 7. 测试

### 7.1 测试金字塔

```
        E2E (test_e2e.py)
            /\n   - 跑整图, 验证拓扑
           /  \n  - Mock LLM, 无 API 消耗
          /----\
         /      \
        / Agent  \n  - 静态校验 Agent 结构
       / (test_   \
      /  agents)   \
     /--------------\
    /   Schema 静态  \n
   / (test_schemas)  \
  /--------------------\
```

### 7.2 写新测试

**Schema 改动** → 在 `tests/test_schemas.py` 加 REQUIRED 字段  
**Agent 改动** → 在 `tests/test_agents.py` 加 must_have token  
**E2E 新场景** → 在 `tests/test_e2e.py` 加 scenario 函数

### 7.3 跑全部测试

```bash
cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent
python tests/test_schemas.py
python tests/test_agents.py
python scripts_smoke_test.py
python tests/test_e2e.py
```

全部应输出 `GREEN` 字样。

### 7.4 E2E 测试的 Mock 机制

`tests/test_e2e.py` 通过 `sys.modules` 注入 mock Pydantic / LangChain / LangGraph:

```python
import sys, types
pyd_mod = types.ModuleType("pydantic")
pyd_mod.BaseModel = MyBaseModel  # 简化版
sys.modules["pydantic"] = pyd_mod

# 然后才 import 项目代码
from backend.app.pipeline.graph.workflow import build_graph
```

需要新增 mock 字段时,修改 `tests/test_e2e.py` 顶部的 mock 注入区。

---

## 8. 调试技巧

### 8.1 看 LangGraph 状态

每个 Agent 都会写 `state["messages"]`,最后 inspect:

```python
from backend.app.pipeline.graph import build_graph
graph = build_graph()
state = graph.invoke({...})
for msg in state["messages"]:
    print(f"[{msg['agent']}] {msg['content']}")
```

### 8.2 单独跑某个 Agent

```python
from backend.app.pipeline.agents.step1_analyzer import step1_analyze

state = {"story_text": "...", "story_title": "...", "messages": []}
update = step1_analyze(state)
print(update["story_analysis"])
```

### 8.3 让某步 LLM 输出更详细

修改对应 Agent 的 `system_prompt`, 加 "请详细解释你的选择"。

### 8.4 关掉某个 Step (快速试验)

在 `backend/app/pipeline/graph/workflow.py` 注释掉 `workflow.add_edge("stepX", "stepY")` 并重接。

---

## 9. 性能优化

### 9.1 Step 4 并行化

当前逐变体串行,可改为 `asyncio.gather` 并发:

```python
import asyncio

async def write_variant(variant, ctx):
    # async LLM call
    ...

# in __call__:
tasks = [write_variant(v, ctx) for sp in plan.shot_prompts for v in sp.variants]
await asyncio.gather(*tasks)
```

注意 API 限流,建议加 `asyncio.Semaphore(5)`。

### 9.2 Step 4 缓存

相同 (shot_id, model) 对的 Prompt 可以缓存到磁盘:

```python
import hashlib, json
cache_key = hashlib.md5(json.dumps([shot.model_dump(), variant.target_model]).encode()).hexdigest()
cache_path = f".cache/{cache_key}.json"
if Path(cache_path).exists():
    variant.prompt_text = json.loads(Path(cache_path).read_text())["prompt_text"]
    continue
```

### 9.3 减少 LLM Token

- Step 1 的 story_text > 3000 字时,先做摘要
- Step 3 传给 Step 4 的 storyboard 可以只保留 shot_id / description 字段

---

## 10. 发布流程 (可选)

### 10.1 版本号

遵循 SemVer: `MAJOR.MINOR.PATCH`

### 10.2 CHANGELOG

每次发版前更新 `CHANGELOG.md`:
```markdown
## [0.2.0] - 2026-07-20
### Added
- 5 模型专属 Prompt 优化 (runway/kling/jimeng/veo/pixverse)
- 一致性检查 LLM-as-judge
### Fixed
- Excel 导出枚举序列化 bug
```

### 10.3 CI

可加 `.github/workflows/test.yml`:
```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: python tests/test_schemas.py
      - run: python tests/test_agents.py
      - run: python scripts_smoke_test.py
      - run: python tests/test_e2e.py
```

---

## 11. 常见开发问题

### Q: 改完代码, E2E 还是显示 mock 的旧行为?
**A**: `tests/test_e2e.py` 通过 mock 让 LLM 返回固定响应。E2E 测的是**代码逻辑**,不是 LLM 真实输出。要测真实链路,得 `python main.py data/sample_story.txt`。

### Q: Pydantic v2 校验失败的报错信息很长, 怎么定位?
**A**: 直接看 `ValidationError` 的 `errors()` 列表,每条含 `loc` / `msg` / `type`。或用 `model_validate(data, strict=True)` 更严格。

### Q: 想在 Step 之间插入"人工审核"怎么办?
**A**: 用 LangGraph 的 `interrupt_before` / `interrupt_after`:
```python
return workflow.compile(interrupt_before=["step4_write_prompts"])
```
适合需要人在回路的场景。

### Q: 怎么把日志输出到文件?
**A**: 修改 `backend/app/pipeline/utils/logger.py:get_logger`,加 `FileHandler`:
```python
logger.addHandler(logging.FileHandler("pipeline.log"))
```

### Q: 想用 Pydantic v1 怎么办?
**A**: 不建议。v2 性能更好,语法差异不大。本项目 `@model_validator(mode="after")` 在 v1 是 `@validator`。

---

## 12. 风格规范

- Python: 遵循 PEP 8, 用 `ruff` 或 `black` 格式化
- 注释: 中文 (项目面向中文用户)
- 字符串: 双引号优先, 单引号用于嵌套
- Type hints: 强制, `from __future__ import annotations`
- 文件长度: < 200 行, 超过考虑拆分

---

## 13. 路线图

- [x] Web UI (已集成到 Jellyfish 前后端系统)
- [ ] 支持多语言故事 (英/日/韩)
- [ ] Step 4 异步并发
- [ ] Prompt 缓存层
- [ ] LangSmith 集成做 trace
- [ ] 视频模型 API 直连 (不只是 Prompt 生成)

---

## 14. 添加新的人审节点 (HITL Review)

如果你想在某个 Step 后插入一个人工审核节点,流程如下:

### 14.1 创建 Review Agent

在 `backend/app/pipeline/agents/` 新建 `step35_pre_review.py`:

```python
from .human_review import HumanReviewAgent


class Step35PreReview(HumanReviewAgent):
    """审核 Step 3 产出的 PromptPlan (回滚 Step 2 重做)。"""

    name = "step3_5_review"
    review_target = "prompt_plan"

    def _extract_review_payload(self, state):
        plan = state.get("prompt_plan")
        if not plan:
            return {}
        return {
            "shot_count": len(plan.shot_prompts),
            "first_shot": plan.shot_prompts[0].model_dump() if plan.shot_prompts else None,
        }


step3_5_review = Step35PreReview()
```

### 14.2 在 `__init__.py` 暴露

`backend/app/pipeline/agents/__init__.py`:
```python
from .step35_pre_review import step3_5_review  # noqa: F401
```

### 14.3 在 workflow 注册 + 加条件边

`backend/app/pipeline/graph/workflow.py`:

```python
from ..agents import step3_5_review

# 节点
workflow.add_node("step3_5_review", step3_5_review)

# 边: Step 3 → 审核 → Step 4 (或回滚 Step 2)
workflow.add_edge("step3_plan_prompts", "step3_5_review")
workflow.add_conditional_edges(
    "step3_5_review",
    lambda s: "step2" if s.get("step3_5_review_decision") == "rejected" else "step4",
    {"step4": "step4_write_prompts", "step2": "step2_storyboard"},
)
```

### 14.4 在 state 加决策字段 (可选)

`backend/app/pipeline/graph/state.py`:
```python
class GraphState(TypedDict, total=False):
    ...
    step3_5_review_decision: Optional[str]   # 新审核节点的归一化决策
```

### 14.5 加 E2E 测试

`tests/test_e2e.py` 加 Scenario E, 验证审核 → reject → 回滚 → 通过。

### 14.6 设计要点

| 要点 | 说明 |
|---|---|
| per-node 决策字段 | 每个 Review 节点用独立字段 (e.g., `step3_5_review_decision`) 避免状态污染 |
| 归一化字符串 | HumanReviewAgent 自动把 `reject:xxx` 归一化为 `"rejected"` |
| FIFO 队列 | `human_feedback` 是 list,每节点 `pop(0)` 消费一条 |
| 默认 accept | 队列空时默认 accept (CI 模式无需注入) |

---

## 15. 使用全局演员表 (CastManager)

### 15.1 基本用法

```python
from backend.app.pipeline.utils import CastManager

# 加载全局演员表
cast_manager = CastManager()
cast_manager.load()  # 从 output/cast.json 加载

# 合并新角色 (通常在 Step 1 后)
new_characters = [
    {"name": "陆沉", "character_sheet": "...", "base_appearance": "..."},
    {"name": "赵无极", "character_sheet": "...", "base_appearance": "..."},
]
result = cast_manager.merge_characters(new_characters, chapter_title="第001章")
# result: {"new": 2, "updated": 0, "total": 2}

# 保存到 cast.json
cast_manager.save()

# 导出供 Excel 使用
excel_data = cast_manager.to_excel_data()
# [{"name": "陆沉", "character_id": "char_001", "costumes": "第001章: 卫衣+夹克"}, ...]
```

### 15.2 在 Pipeline 中使用

`main.py` 已集成 CastManager:

```python
# 启动时加载
cast_manager = CastManager()
cast_manager.load()
initial_state = {
    "cast_data": cast_manager.cast_data,
    ...
}

# Pipeline 运行后保存
cast_manager.cast_data = final_state.get("cast_data", {})
cast_manager.save()
```

### 15.3 @角色名 引用

在 Step 4 生成的 Prompt 中,使用 `@角色名` 引用角色资产:

```python
# 正确 ✅
prompt = "@陆沉 坐在昏暗出租屋中央的旧木椅上, 低头看左手捏着的揉皱诊断证明"

# 错误 ❌ (重复描述外貌)
prompt = "@陆沉, 20岁, 178cm, 窄脸, 苍白肤色... 坐在昏暗出租屋中央..."
```

**原因**: @角色名 是角色资产图片的引用,视频工具会自动查找演员表中的形象描述。

---

## 16. 使用故事板卡片生成器

### 16.1 基本用法

```python
from backend.app.pipeline.utils import StoryboardCardGenerator

# 初始化 (可选: 启用 DALL-E 3 图片生成)
generator = StoryboardCardGenerator(enable_image_generation=False)

# 从视频 Prompt 生成卡片
cards = generator.generate_cards_from_prompt(
    shot_id="shot_001",
    video_prompt="[0-2.5s] @陆沉 弓背坐在旧木椅上...",
    character_sheets={"陆沉": "年龄约20岁, 身高约178cm..."},
    scene_description="昏暗出租屋, 白炽灯, 冷蓝色调",
    director_style="王家卫风格",
)
# cards: [{"type": "character", "title": "角色参考 - 陆沉", "prompt": "..."}, ...]

# 可选: 生成图片 (需要 OPENAI_API_KEY)
if generator.enable_image_generation:
    cards = generator.generate_images(cards, output_dir="output/cards/")
```

### 16.2 在 Pipeline 中使用

`main.py` 已集成故事板卡片生成:

```python
# Pipeline 完成后生成卡片
card_generator = StoryboardCardGenerator(enable_image_generation=False)

for shot_prompt in prompt_plan.shot_prompts:
    cards = card_generator.generate_cards_from_prompt(
        shot_id=shot_prompt.shot_id,
        video_prompt=shot_prompt.variants[0].prompt_text,
        character_sheets=character_sheets,
        scene_description=scene_desc,
        director_style=director_style,
    )
    storyboard_cards.extend(cards)

# 导出到 Excel
export_prompts_to_excel(
    storyboard=storyboard,
    prompt_plan=prompt_plan,
    storyboard_cards=storyboard_cards,  # 新增参数
    ...
)
```

### 16.3 卡片类型

| 类型 | 用途 | 内容 |
|---|---|---|
| `character` | 角色参考卡 | 正面半身像 + 姿态 + 光线 + 色调 |
| `scene` | 场景风格参考卡 | 环境 + 光线 + 色调 + 氛围 + 质感 |
| `shot` | 镜头构图参考卡 | 景别 + 机位 + 构图 + 运动 + 风格 |

### 16.4 启用图片生成

如需自动生成参考图 (需要 OPENAI_API_KEY):

```python
# main.py
card_generator = StoryboardCardGenerator(enable_image_generation=True)
```

图片会通过 DALL-E 3 API 生成,URL 保存在 `card["image_url"]` 中。

---

## 17. 添加导演风格

### 17.1 创建导演风格文件

在 `backend/app/pipeline/agents/director_styles/` 创建 SKILL.md:

```markdown
# 王家卫风格指南

## 视觉特征
- 色调: 冷蓝/暖黄, 低饱和度
- 光线: 单源光, 高对比度, 强烈阴影
- 构图: 三分法, 人物偏置, 留白

## 镜头语言
- 运镜: 固定镜头为主, 偶尔手持跟拍
- 景别: 中近景, 特写
- 节奏: 慢速, 留白, 停顿

## 参考电影
- 《重庆森林》: 都市孤独, 冷色调
- 《花样年华》: 暧昧氛围, 暖色调
- 《堕落天使》: 夜景, 霓虹灯
```

### 17.2 在 Pipeline 中使用

导演风格会通过 `director_ids` 参数传递:

```python
# main.py
initial_state = {
    "director_ids": ["王家卫", "徐克"],
    ...
}
```

Step 4 和 Step 6 会自动注入对应的风格参考到 Prompt 中。

---

## 18. 物理真实感增强

### 18.1 System Prompt 要求

Step 4 的 system prompt 已包含物理真实感要求:

```markdown
# 物理真实感要求 (必须遵守)

人物动作必须有**真实物理感**:
- ✅ 真实重力感: 脚步有踩地反馈, 不能漂浮
- ✅ 真实惯性感: 快速动作后有惯性延续, 衣物随动作摆动
- ✅ 真实重量感: 物体拿取/放下有重量反馈
- ✅ 真实速度感: 快速动作有运动模糊和速度拖影
- ✅ 真实发力感: 肌肉紧张、身体重心变化、呼吸配合
- ❌ 禁止: 反物理动作、漂浮感、失重感、机械感、僵硬感
```

### 18.2 动作编排词汇

在生成动作类 Prompt 时,优先使用专业术语:

```python
# 近战动作
actions = ["拆招", "格挡", "闪避", "踢腿", "错身", "拧腰", "沉肩", "翻腕"]

# 轻功动作
actions = ["飞掠", "腾空", "落地", "借力", "旋身", "点地"]

# 表情细节
expressions = ["眼神收紧", "眉头微蹙", "嘴角含笑", "瞳孔收缩"]
```

### 18.3 负面提示词

Step 4 生成的 negative_prompt 已扩展到 25+ 项:

```python
negative_prompt = "人物变形, 多指, 少指, 穿模, 肢体扭曲, 面部崩坏, 失重感, 漂浮感, 反物理动作, 机械感, 僵硬感, AI感, CG感, 游戏感, 过度锐化, 过度美颜, 塑料皮肤, 蜡像感, 文字字幕, 水印, LOGO, 镜头漂移, 背景跳变, 廉价特效, 光污染"
```

---

## 19. Jellyfish 集成开发指南

### 19.1 架构概览

Pipeline 代码已合并为 `backend/app/pipeline/` 子包,与 Jellyfish 后端同进程运行:

```
novel_auto_agent/
├── src/engine.py               ├── backend/
├── src/adapters/               │   ├── app/schemas/novel_codex.py
│   └── jellyfish_adapter.py    │   ├── app/services/novel_codex_bridge.py
└── pyproject.toml              │   ├── app/api/v1/routes/novel_codex.py
                                │   └── pyproject.toml (dependency)
                                └── front/src/
                                    ├── services/novelCodexService.ts
                                    └── pages/.../NovelCodexPanel.tsx
```

### 19.2 安装开发环境

```bash
# 1. 安装开发环境
cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent/backend
pip install -e .

# 2. 在 Jellyfish 后端添加依赖
cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent/backend
pip install -e ".[dev]"

# 3. 验证导入
python -c "from backend.app.pipeline.engine import PipelineEngine; print('OK')"
```

### 19.3 扩展 PipelineEngine

PipelineEngine 支持自定义:

```python
class PipelineEngine:
    def __init__(
        self,
        *,
        enable_cards: bool = True,    # 是否生成故事板卡片
        max_replans: int = 3,          # 一致性检查最大回滚次数
    ):
        self.graph = build_graph()
        self.enable_cards = enable_cards
        self.max_replans = max_replans
```

**添加自定义后处理**:

```python
engine = PipelineEngine(enable_cards=True)
result = engine.run(story_text, story_title)

# 自定义后处理
if result.success:
    for card in result.storyboard_cards:
        card["custom_field"] = "my_value"
    
    # 导出自定义格式
    import json
    with open("custom_output.json", "w") as f:
        json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
```

### 19.4 扩展 JellyfishAdapter

Adapter 支持自定义字段映射:

```python
class JellyfishAdapter:
    def build_pipeline_input(
        self,
        *,
        chapter_id: str,
        project_name: str,
        shots: list[dict],          # 镜头数据
        characters: list[dict],     # 角色数据
        scenes: list[dict] = None,  # 场景数据 (可选)
        costumes: list[dict] = None, # 服装数据 (可选)
        visual_style: str = "",     # 视觉风格
        style: str = "",            # 故事风格
        director_ids: list[str] = None, # 导演 ID 列表
    ) -> dict:
        ...
```

**字段兼容性**:
- shots: 支持 `shot_id`/`id` 和 `shot_index`/`index`
- characters: 支持 `description`/`visual_description`
- variants: 支持 `target_model`/`model`

### 19.5 添加新的 API 端点

在 Jellyfish 后端添加新端点:

```python
# backend/app/api/v1/routes/novel_codex.py

@router.post("/generate-with-custom-config")
async def generate_with_custom_config(
    body: CustomRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    # 自定义逻辑
    ...
```

### 19.6 前端组件扩展

NovelCodexPanel 支持自定义:

```tsx
<NovelCodexPanel
  chapterId={chapterId}
  onComplete={() => {
    // 生成完成后的回调
    loadShots()  // 刷新镜头列表
    message.success("Prompt 生成完成!")
  }}
/>
```

**自定义步骤名称映射**:

在 `NovelCodexPanel.tsx` 中修改 `STEP_LABELS`:

```tsx
const STEP_LABELS: Record<string, string> = {
  start: '启动中',
  step1_analyze: 'Step 1/6 · 剧本分析',
  // ... 添加自定义步骤名
}
```

### 19.7 测试集成

```bash
# 1. 测试 PipelineEngine
python3 -c "
from dotenv import load_dotenv
load_dotenv()
from backend.app.pipeline.engine import PipelineEngine
engine = PipelineEngine()
result = engine.run('测试故事', '测试')
print(f'成功: {result.success}')
"

# 2. 测试 JellyfishAdapter
python3 -c "
from backend.app.pipeline.adapters.jellyfish_adapter import JellyfishAdapter
adapter = JellyfishAdapter()
input_data = adapter.build_pipeline_input(
    chapter_id='test', project_name='Test',
    shots=[{'shot_id': 's1', 'shot_index': 1, 'script_excerpt': '测试'}],
    characters=[{'name': '主角', 'description': '测试角色'}],
)
print(f'OK: {list(input_data[\"cast_data\"].keys())}')
"

# 3. 测试 Jellyfish 后端导入
cd /Users/guteng/Coding/AI_MOVIE/Jellyfish
backend/.venv/bin/python -c "
from app.schemas.novel_codex import NovelCodexGenerateRequest
from app.api.v1.routes.novel_codex import router
print(f'Routes: {[r.path for r in router.routes]}')
"

# 4. 测试前端构建
cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent/front
npx tsc --noEmit
npx vite build
```
