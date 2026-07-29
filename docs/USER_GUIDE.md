# novel_auto_agent 使用手册

> 面向内容创作者 / 产品运营 / 任何想用本工具的人。
> 配套源码位置:`/Users/guteng/Coding/AI_MOVIE/novel_auto_agent/`

---

## 1. 这个工具能做什么?

把一段小说/剧本/故事大纲,**自动拆成多镜头分镜表**,并为每个镜头生成 **2 个主流 AI 视频模型** (Kling / 即梦) 都能用的 Prompt。

**输入**: 一份 `.txt` 故事文本  
**输出**: 一份 `.xlsx` Excel 表格,含分镜概览 + 多模型 Prompt + 全局演员表 + 故事板卡片

---

## 2. 快速上手 (3 分钟)

### 2.1 准备环境

需要:
- Python 3.11 或更高
- 一个 OpenAI API Key (或兼容 OpenAI 协议的代理)

```bash
# 1. 进入项目目录
cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent

# 2. 创建后端虚拟环境
cd backend
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -e ".[dev]"

# 4. 配置 API Key
cp ../.env.example .env
# 用编辑器打开 .env, 把 OPENAI_API_KEY=sk-... 改成你自己的 key
```

### 2.2 运行示例故事

```bash
cd .. && python main.py data/sample_story.txt
```

看到类似输出:

```
[Step 1] 开始剧本分析 (输入 87 字)
[Step 1] ✅ 完成: 2 角色 / 2 场景
[Step 2] 开始导演分镜 ...
...
[Step 4] ✅ Excel 已导出: output/storyboard_女巫与龙_20260716_001936.xlsx
[Step 6]   runway: 3 镜头
[Step 6]   kling: 3 镜头
...
=== Pipeline 完成 ===
```

打开 `output/storyboard_女巫与龙_<时间戳>.xlsx`,你会看到两个工作表:

- **Storyboard**: 分镜概览
- **Prompt Variants**: 每个镜头 × 5 个模型的 Prompt

### 2.3 跑自己的故事

把 `.txt` 文件丢到任意位置,然后:

```bash
python main.py /path/to/your/story.txt --title "我的小说"
```

可选参数:

```bash
python main.py <文件> \
    --title "故事标题"              # 用作 Excel 文件名, 可选
    --max-replans 5                  # 一致性检查最多回滚 5 次, 默认 3
    --output-dir ./my_output         # Excel 输出目录, 默认 ./output
```

---

## 3. 输入故事有什么要求?

**没有硬性要求**,但建议:

| 维度 | 建议 | 例子 |
|---|---|---|
| 长度 | 200 ~ 5000 字 | 太短分不出镜头,太长 LLM token 爆 |
| 语言 | 中文 / 英文均可 | LLM 自动识别 |
| 格式 | 纯文本 / 段落分明 | "段落1\\n\\n段落2" 比一行长文本好 |
| 内容 | 有角色、有场景、有动作 | 抽象抒情文学分镜效果较差 |

### 3.1 示例故事

```text
夜色如墨, 古老的城堡矗立在悬崖之上。
年轻的女巫艾琳举起手中的水晶球, 低声吟唱失传已久的咒语。
一道蓝光划破长空, 城堡的封印轰然碎裂。
她踏入城堡, 看见了被囚禁千年的龙——那曾是她的导师。
龙睁开金瞳, 缓缓开口:「你终于来了, 继承者。」
```

(Located in `data/sample_story.txt`)

---

## 4. 输出 Excel 怎么读?

打开 `output/storyboard_<标题>_<时间戳>.xlsx`,你会看到 **4 个工作表**。

### Sheet 1: Storyboard (分镜概览, 1 镜头 = 1 行)

| 列 | 含义 | 例子 |
|---|---|---|
| 镜头编号 | shot_001, shot_002 ... | |
| 时长(s) | 建议视频时长 | 4.0 |
| 景别 | 取景范围 | medium / close_up |
| 运镜 | 镜头运动 | dolly_in / pan_left / static |
| 镜头描述 | 画面内容 | "艾琳举起水晶球, 蓝光从球体溢出" |
| 出场角色 | 角色 ID | char_001 |
| 关联台词 | 该镜头所有对白 | "封印, 在我的咒语下碎裂吧" |

### Sheet 2: Prompt Variants (2 模型 × Version B + 导演风格, N 镜头 × 2 = N×2 行)

| 列 | 含义 | 例子 |
|---|---|---|
| 镜头编号 | shot_001 | |
| 目标模型 | kling / jimeng | |
| 导演风格 | 该镜头应用的导演风格 | 王家卫风格 |
| Prompt 文本 | Version B (时间戳节奏版), 直接复制到对应模型的输入框 | "[0-2s] 艾琳举起水晶球..." |
| 镜头描述(参考) | 来自 Sheet 1, 方便对照 | |
| 备注 | 导演备注 | |

### Sheet 3: 演员表 (全局演员表, 1 角色 = 1 行)

| 列 | 含义 | 例子 |
|---|---|---|
| 角色名 | 角色显示名 | 艾琳 |
| 角色ID | char_001 | |
| 角色定位 | 主角 / 配角 / 反派 | 主角 |
| 基础外貌 | 基础外观描述 | "年龄约20岁, 身高约165cm..." |
| 角色资产描述 | 完整视觉描述 (≥80字) | "正面半身像, 黑色长发..." |
| 首次出现 | 首次出现的章节 | 第001章 |
| 服装变化 | 各章节服装变化 | "第001章: 黑色斗篷; 第002章: 白色长裙" |

**数据来源**: 优先使用全局演员表 (cast.json),否则使用本章分析结果

### Sheet 4: 故事板卡片 (Storyboard Cards, 2-3 卡片/镜头)

| 列 | 含义 | 例子 |
|---|---|---|
| 镜头编号 | shot_001 | |
| 卡片类型 | character / scene / shot | character |
| 卡片标题 | 角色参考 - 艾琳 | |
| 卡片提示词 | 完整的参考图生成提示词 | "正面半身像, 黑色长发..." |
| 图片 URL | DALL-E 3 生成的图片 URL (可选) | https://... |

**卡片类型说明**:
- `character`: 角色参考卡 (每个角色一张)
- `scene`: 场景风格参考卡
- `shot`: 镜头构图参考卡

**用途**: 将卡片提示词复制到 Midjourney / DALL-E 生成参考图,用于控制视频生成的视觉一致性

### 4.1 A/B/C 三版叙述风格差异

| 版本 | 风格 | 适用场景 | Runway 示例 |
|---|---|---|---|
| **A (导演脚本版)** | 电影语言, 自然表达, 留 AI 发挥空间 | 节奏型镜头, 信任模型 | `cinematic艾琳举起水晶球, dramatic composition, character-driven` |
| **B (时间戳节奏版)** | 全要素锁定 + 时间轴 `[0-2s]...` | 动作密集, 需精确控制 | `[0-2s] 起始: 艾琳站在古堡前\n[2-4s] 动作: 抬手, 蓝光溢出\n[4-6s] 环境: 封印碎裂` |
| **C (Beat 调度版)** | Beat 驱动的结构化清单 | 复杂调度, 多 Beat | `[摄影] 景别=medium 焦段=50mm\n[演员] 动作=举手 微表情=坚定\n[Beat1] 开始施法` |

**哪个版本最好用?** 经验法则:
- Runway → **A 版**(摄影术语友好)
- Kling → **B 版**(时间轴明确)
- Jimeng → **B 版的中文变体**(`[0-2秒]`)
- Veo → **C 版**(bullet 风格)
- PixVerse → **C 版**(逗号关键词)

### 4.2 5 个模型的 Prompt 风格差异

**Runway** (英文, 摄影语言, A 版示例):
> `locked-off static shot, A young witch with red hair and silver robes stands before a crystal ball, cinematic lighting, 4K`

**Kling** (中英混合, B 版示例):
> `[0-2s] 起始: 古堡前, 夜色\n[2-4s] 动作: 艾琳举水晶球, 蓝光溢出\n镜头节奏: 慢→快 (电影质感 cinematic)`

**即梦 / Jimeng** (中文, B 版示例):
> `[0-2秒] 起始: 古堡前夜色\n[2-4秒] 动作: 艾琳举水晶球, 蓝光溢出\n镜头节奏: 慢→快`

**Veo** (英文, C 版示例):
> `• cinematic • young witch raises crystal ball • blue light radiates • slow→fast rhythm`

**PixVerse** (英文逗号串, C 版示例):
> `cinematic, young witch, red hair, silver robes, raises crystal ball, blue light, slow→fast`

---

## 5. 常见问题

### Q1: 运行报 `ModuleNotFoundError: No module named langchain_openai`

说明依赖没装好。重跑:
```bash
pip install -r requirements.txt
```

如果 pip 网络不通,试试国内镜像:
```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q2: 运行报 `OPENAI_API_KEY 未配置`

`.env` 没建或没填 key:
```bash
cp .env.example .env
# 编辑 .env, 把 OPENAI_API_KEY=sk-... 改成你的 key
```

### Q3: 输出 Excel 镜头数很少 (只有 2-3 个)

可能故事太短或太抽象。LLM 会保守拆镜。可以:
1. 把故事写得更详细(动作、场景描写)
2. 在故事末尾加一句 "请拆为 8 个镜头"
3. 提高 max_tokens (修改 `utils/llm.py:get_llm(max_tokens=8000)`)

### Q4: 一致性检查反复回滚, 一直达不到通过

检查日志看具体 issues。最常见:
- **角色引用错误**: prompt 里出现了 `characters[]` 中没有的角色名 → 在 `.env` 里加大 temperature 让 LLM 更发散,或修改 Step 1 的角色列表
- **Prompt 太短**: 调高 `step4_writer.py` 的 max_tokens, 或在 system prompt 里强调长度

可以提高 `MAX_REPLAN_ROUNDS` 给系统更多机会:
```bash
python main.py data/story.txt --max-replans 5
```

### Q5: 生成的 Prompt 在 Runway 效果不好

Prompt 风格是按官方文档最佳实践优化的, 但模型版本迭代很快。如果效果不佳:
1. 看 `output/storyboard_*.xlsx` 的 Sheet 2 选你认为最好的版本
2. 在 Runway 网页上手动微调后输入
3. 或修改 `backend/app/pipeline/agents/step6_adapter.py:_optimize_runway` 调整策略

### Q6: 想换成 Claude / Gemini / 国内大模型

修改 `backend/app/pipeline/utils/llm.py`,把 `ChatOpenAI` 换成对应 SDK 即可。多数 LangChain ChatModel 接口兼容。

### Q7: 想自定义 5 个模型清单

修改 `backend/app/pipeline/schemas/enums.py:TargetModel`:
```python
class TargetModel(str, Enum):
    RUNWAY = "runway"
    KLING = "kling"
    # 加新的:
    PIKA = "pika"
    SORA = "sora"
```

并在 `backend/app/pipeline/agents/step6_adapter.py` 加对应的优化器。

### Q8: 输出 Excel 中文乱码

确保用 Excel 2016+ 或 WPS / Numbers 打开。低版本 Excel 对 UTF-8 中文支持差。

### Q9: 如何批量处理多个故事?

写个 shell 循环:
```bash
for f in stories/*.txt; do
    python main.py "$f" --title "$(basename "$f" .txt)"
done
```

或用 Python 多进程并行(注意 API 限流):
```python
import concurrent.futures
import subprocess

def run(story_path):
    return subprocess.run(["python", "main.py", story_path], check=True)

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
    ex.map(run, ["s1.txt", "s2.txt", "s3.txt"])
```

### Q10: 怎么验证安装是否成功?

```bash
python tests/test_schemas.py   # Schema 静态校验
python tests/test_agents.py    # Agent 静态校验
python scripts_smoke_test.py   # 路由逻辑
python tests/test_e2e.py       # 端到端 (用 mock LLM, 不消耗 API)
```

应该全部打印 `GREEN` 字样。

---

## 6. 进阶用法

### 6.1 用 Mock LLM 做集成测试

`tests/test_e2e.py` 演示了如何 mock LLM 跑通整图。可用于:
- CI/CD 不消耗 API
- 单元测试特定 scenario
- 性能压测

### 6.2 切换 LLM Provider

```python
# src/utils/llm.py
from langchain_anthropic import ChatAnthropic

def get_llm(model=None, temperature=0.7, max_tokens=None):
    return ChatAnthropic(
        model=model or "claude-sonnet-4-5",
        temperature=temperature,
        max_tokens=max_tokens,
    )
```

### 6.3 自定义 Step 5 一致性规则

修改 `backend/app/pipeline/agents/step5_consistency.py:_JUDGE_SYSTEM` 的 system prompt,加你的业务规则,例如:
- "主角必须出现在至少 3 个镜头"
- "反派的对白总字数不超过主角的 50%"
- "总时长不得超过 60 秒"

### 6.4 跳过 Step 5 (快速模式)

如果不想做一致性检查,直接注释掉 `workflow.py` 中 Step 5 的节点,让 Step 4 直接到 Step 6。

### 6.5 输出 JSON 而不是 Excel

`final_outputs` 已经是 JSON 结构 (见 `state["final_outputs"]`),可以从 Python 代码里取:

```python
from backend.app.pipeline.graph import build_graph
graph = build_graph()
state = graph.invoke({"story_text": "...", ...})
import json
print(json.dumps(state["final_outputs"], ensure_ascii=False, indent=2))
```

---

## 7. 项目目录速查

```
novel_auto_agent/
├── main.py                  CLI 入口 (Pipeline 独立运行)
├── pyproject.toml           根配置
├── requirements.txt         Pipeline 依赖
├── .env.example             配置模板
├── data/sample_story.txt    示例故事
├── docs/                    文档 (你正在看)
│   ├── ARCHITECTURE.md      架构文档
│   ├── USER_GUIDE.md        使用手册 (本文件)
│   └── DEVELOPER_GUIDE.md   开发指南
├── backend/                 后端 (FastAPI + Pipeline)
│   ├── app/
│   │   ├── main.py          FastAPI 入口
│   │   ├── pipeline/        <<< 6步 Prompt Pipeline >>>
│   │   │   ├── engine.py    PipelineEngine
│   │   │   ├── agents/      6 步 Agent
│   │   │   ├── graph/       LangGraph 工作流
│   │   │   ├── schemas/     数据契约
│   │   │   ├── utils/       工具 (LLM/Excel/CastManager)
│   │   │   └── adapters/    JellyfishAdapter
│   │   ├── api/             REST API 路由
│   │   ├── schemas/         API Schema
│   │   ├── services/        Bridge 服务
│   │   ├── models/          DB 模型
│   │   └── ...              其他 Jellyfish 模块
│   ├── tests/               后端测试
│   ├── pyproject.toml       合并依赖
│   └── .venv/               虚拟环境
├── front/                   前端 (React 18 + Ant Design)
│   └── src/
│       ├── services/novelCodexService.ts   API 封装
│       └── pages/.../NovelCodexPanel.tsx   按钮+进度+结果
└── tests/                   Pipeline 测试套件
```

---

## 8. 反馈与贡献

发现 Bug / 想加新功能 / 文档不清楚? 直接:
- 修改对应文件后跑 `python tests/test_e2e.py` 验证
- 看 `DEVELOPER_GUIDE.md` 了解扩展点

---

## 9. 人在回路 (HITL) 审核 — 暂停并修改中间产物

系统支持在 **3 个关键节点**暂停,让你审核并修改中间产物。

### 9.1 何时触发审核

- **Step 1.5 审核** — 审核角色清单 / 场景描述 / 整体基调
- **Step 2.5 审核** — 审核镜头列表 / 运镜 / 时长
- **Step 4.5 审核** — 审核 Prompt 规划 + 多版本 Prompt

### 9.2 运行模式

```bash
# 默认: 交互式 (每阶段暂停, 等待用户输入)
python3 main.py data/sample_story.txt

# 自动接受所有审核 (CI / 批处理)
python3 main.py data/sample_story.txt --auto-approve

# 完全跳过 HITL 节点 (极速模式)
python3 main.py data/sample_story.txt --no-hitl
```

### 9.3 交互指令

暂停时,系统会打印当前产物摘要,你可以输入以下指令:

| 指令 | 效果 |
|---|---|
| `accept` | 接受当前产物,继续下一步 |
| `modify:shot_001.description=新描述文字` | 修改指定字段后继续 |
| `reject:不满意, 重新规划` | 回滚到上一步重做 (Step 4.5 reject 触发回滚 Step 3) |
| `quit` | 立即终止流水线 |

**示例 — 修改镜头描述**:
```
Step 2.5 review 👤 审核指令 (accept/modify/reject/quit): modify:storyboard.shots[0].description=夜色更深, 城堡笼罩在迷雾中
```

**示例 — 拒绝并回滚**:
```
Step 4.5 review 👤 审核指令 (accept/modify/reject/quit): reject:Prompt 太长, 重新规划
```

### 9.4 自动化注入 (用于测试 / 程序化调用)

```python
from backend.app.pipeline.graph.workflow import build_graph
from backend.app.pipeline.graph.state import GraphState

graph = build_graph()
state = GraphState(
    story_text="...",
    story_title="...",
    max_replans=3,
    replan_count=0,
    # FIFO 队列, 每节点消费一条:
    human_feedback=[
        "accept",                                    # Step 1.5
        "modify:storyboard.shots[0].description=...", # Step 2.5
        "reject:不满意",                              # Step 4.5 → 回滚 Step 3
    ],
)
final = graph.invoke(state)
```

### 9.5 决策字段语义

每个 Review 节点都会在 state 里写入归一化决策字段:

| 字段 | 取值 | 触发效果 |
|---|---|---|
| `step1_5_review_decision` | accept / rejected / modified / quit | Step 1.5 → Step 2 (无 conditional edge) |
| `step2_5_review_decision` | 同上 | Step 2.5 → Step 3 (无 conditional edge) |
| `step4_5_review_decision` | 同上 | Step 4.5 → Step 5 或回滚 Step 3 (conditional edge) |

**为什么每个 Review 节点用独立的字段?**
避免 Step 1.5 的 reject 误传到 Step 4.5 的 conditional edge。

---

## 10. 全局演员表 (跨章节角色一致性)

### 10.1 什么是全局演员表?

当你处理多章节小说时,系统会自动维护一个**全局演员表** (`output/cast.json`),记录所有角色的信息:

```json
{
  "陆沉": {
    "character_id": "char_001",
    "role": "主角",
    "base_appearance": "年龄约20岁, 身高约178cm...",
    "character_sheet": "完整视觉描述...",
    "costumes": {
      "第001章": "洗得发白的深蓝色连帽卫衣+黑色薄款夹克",
      "第002章": "黑色西装+白色衬衫"
    },
    "first_chapter": "第001章",
    "reference_image_url": ""
  }
}
```

### 10.2 工作流程

1. **第 1 章处理**: 系统分析角色,注册到 `cast.json`
2. **第 2 章处理**: 系统加载 `cast.json`,自动继承已有角色
3. **新角色出现**: 自动注册;同角色新服装: 自动更新服装变化
4. **Excel 输出**: 演员表 Sheet 显示所有角色及各章节服装

### 10.3 @角色名 引用

在生成的 Prompt 中,使用 `@角色名` 引用角色资产:

```prompt
✅ 正确: "@陆沉 坐在昏暗出租屋中央的旧木椅上, 低头看左手捏着的揉皱诊断证明"
❌ 错误: "@陆沉, 20岁, 178cm, 窄脸, 苍白肤色..."  (重复描述外貌)
```

**原因**: @角色名 是角色资产图片的引用,视频工具会自动查找演员表中的形象描述,Prompt 中不需要重复外貌。

### 10.4 查看演员表

打开 Excel 的 **演员表** Sheet,可以看到:
- 所有已注册角色
- 每个角色的基础外貌和完整视觉描述
- 各章节的服装变化
- 首次出现的章节

---

## 11. 故事板分镜卡片

### 11.1 什么是故事板卡片?

系统会自动为每个镜头生成 **2-3 张故事板卡片**,用于控制视频生成的视觉一致性:

| 卡片类型 | 用途 | 内容 |
|---|---|---|
| **角色参考卡** | 确保角色外观一致 | 正面半身像 + 姿态 + 光线 + 色调 |
| **场景风格参考卡** | 确保场景风格一致 | 环境 + 光线 + 色调 + 氛围 + 质感 |
| **镜头构图参考卡** | 确保镜头风格一致 | 景别 + 机位 + 构图 + 运动 + 风格 |

### 11.2 如何使用卡片?

1. 打开 Excel 的 **故事板卡片** Sheet
2. 复制卡片提示词
3. 粘贴到 Midjourney / DALL-E 生成参考图
4. 将生成的参考图上传到视频生成平台 (如 libtv)

### 11.3 示例

**角色参考卡 - 陆沉 (shot_001)**:
```
正面半身像,年龄约20岁,身高约178cm,身形清瘦...
姿态: 弓背坐在旧木椅上
光线: 冷白色顶光 (白炽灯)
色调: 冷蓝偏暗
风格: cinematic portrait, film grain, 真实皮肤质感
```

**镜头构图参考卡 - shot_001**:
```
景别: wide shot (24mm)
机位: 平视
构图: 三分法构图
运动: 固定镜头 (static)
风格: 王家卫电影的光影与孤独感
```

### 11.4 启用图片生成 (可选)

如需自动生成参考图 (需要 OPENAI_API_KEY),修改 `main.py`:

```python
card_generator = StoryboardCardGenerator(enable_image_generation=True)
```

图片会通过 DALL-E 3 API 生成,URL 保存在 Excel 的 **图片 URL** 列中。

---

## 12. 物理真实感增强

### 12.1 自动增强

系统会自动在生成的 Prompt 中强调物理真实感:

- ✅ 真实重力感: 脚步有踩地反馈
- ✅ 真实惯性感: 快速动作后有惯性延续
- ✅ 真实重量感: 物体拿取/放下有重量反馈
- ✅ 真实速度感: 快速动作有运动模糊
- ✅ 真实发力感: 肌肉紧张、身体重心变化

### 12.2 动作编排

对于动作类场景,系统会使用专业术语:

- **近战**: 拆招、格挡、闪避、踢腿、错身、拧腰
- **轻功**: 飞掠、腾空、落地、借力、旋身
- **表情**: 眼神收紧、眉头微蹙、瞳孔收缩

### 12.3 负面提示词

系统会自动生成 25+ 项负面提示词,避免常见问题:

```
人物变形, 多指, 少指, 穿模, 肢体扭曲, 面部崩坏, 失重感, 漂浮感, 
反物理动作, 机械感, 僵硬感, AI感, CG感, 游戏感, 过度锐化, 过度美颜, 
塑料皮肤, 蜡像感, 文字字幕, 水印, LOGO, 镜头漂移, 背景跳变, 廉价特效
```

---

## 13. 导演风格

### 13.1 支持的导演风格

系统内置 25+ 位著名导演的风格指南:

- **王家卫**: 冷蓝/暖黄色调, 单源光, 高对比度, 都市孤独
- **徐克**: 武侠电影镜头调度, 动作节奏, 威亚飞掠感
- **张艺谋**: 大红大绿, 对称构图, 仪式感
- **李安**: 细腻情感, 自然光, 东方美学
- **诺兰**: 非线性叙事, IMAX 质感, 冷色调
- ... 等等

### 13.2 如何应用导演风格?

在 `main.py` 中指定:

```python
initial_state = {
    "director_ids": ["王家卫", "徐克"],
    ...
}
```

系统会自动:
1. 在 Prompt 中注入风格参考 (如 "风格参考: 王家卫电影的光影与孤独感")
2. 在 Excel 的 **导演风格** 列显示应用的风格
3. 在 Step 6 模型适配时强化对应风格

### 13.3 查看导演风格

打开 Excel 的 **Prompt Variants** Sheet,可以看到 **导演风格** 列显示每个镜头应用的风格参考。

---

## 14. 常见问题

### 14.1 为什么只有 kling 和 jimeng 两个模型?

当前版本只保留 kling 和 jimeng 两个目标模型,因为:
- 这两个模型在国内使用最广泛
- 中文 Prompt 支持更好
- 如需添加其他模型,参考 [DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md) 第 3 节

### 14.2 如何处理多章节小说?

1. 依次处理每个章节
2. 系统会自动维护全局演员表 (`output/cast.json`)
3. 后续章节自动继承前几章的角色
4. 演员表 Sheet 会显示所有角色及各章节服装变化

### 14.3 故事板卡片有什么用?

故事板卡片用于:
- 控制视频生成的视觉一致性
- 生成角色/场景/镜头的参考图
- 上传到视频生成平台 (如 libtv) 作为参考

### 14.4 如何启用图片生成?

修改 `main.py`:

```python
card_generator = StoryboardCardGenerator(enable_image_generation=True)
```

需要配置 `OPENAI_API_KEY`,图片会通过 DALL-E 3 生成。

---

## 15. Jellyfish 前后端集成 — 一键生成 Prompt

### 15.1 什么是 Jellyfish 集成?

novel_auto_agent 是由 novel_codex_agent 和 Jellyfish **合并而成的统一项目**。Pipeline 代码在 `backend/app/pipeline/` 子包中,与 Jellyfish 后端共享进程空间。你可以在分镜工作台里,点击「AI Prompt」按钮,一键为当前章节生成高质量视频 Prompt。

### 15.2 使用方法

#### 前置条件

1. 确保后端虚拟环境已安装:
   ```bash
   cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent/backend
   python -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. 确保 `.env` 已配置 `OPENAI_API_KEY`

#### 启动服务

```bash
# 启动后端
cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent/backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 启动前端
cd /Users/guteng/Coding/AI_MOVIE/novel_auto_agent/front
npm run dev
```

#### 在分镜工作台使用

1. 打开 Jellyfish 前端,进入任意项目的章节分镜工作台
2. 确保章节已有分镜数据 (镜头列表)
3. 点击顶部工具栏的 **「AI Prompt」** 按钮
4. 系统会自动:
   - 读取当前章节的镜头、角色、服装信息
   - 调用 novel_codex_agent 6 步 Pipeline 生成 Prompt
   - 显示进度弹窗 (实时显示当前步骤和进度百分比)
   - 完成后显示结果摘要 (质量评分、镜头数、卡片数、耗时)
5. 点击「查看结果」可展开每个镜头的 Prompt 详情和故事板卡片
6. 结果会自动写回 Jellyfish DB,可直接在分镜工作台查看

### 15.3 API 接口

如果你想在其他系统中调用,可以直接使用 REST API:

```bash
# 1. 启动生成任务
curl -X POST http://localhost:8000/api/v1/novel-codex/generate \
  -H "Content-Type: application/json" \
  -d '{"chapter_id": "your-chapter-id"}'

# 返回: {"code": 0, "data": {"task_id": "nc_xxx", "status": "pending"}}

# 2. 查询进度
curl http://localhost:8000/api/v1/novel-codex/status/{task_id}

# 3. 获取结果 (并写回 DB)
curl http://localhost:8000/api/v1/novel-codex/result/{task_id}
```

### 15.4 作为 Python 库调用

也可以直接在 Python 代码中使用 PipelineEngine:

```python
from dotenv import load_dotenv
load_dotenv()

from app.pipeline.engine import PipelineEngine

engine = PipelineEngine(enable_cards=True)

# 进度回调
def on_progress(step, pct):
    print(f"[{pct}%] {step}")

result = engine.run(
    story_text="你的故事文本...",
    story_title="故事标题",
    cast_data=None,          # 可选: 全局演员表
    director_ids=["王家卫"], # 可选: 导演风格
    progress_callback=on_progress,
)

if result.success:
    print(f"评分: {result.consistency_report.get('overall_score')}")
    print(f"卡片: {len(result.storyboard_cards)} 张")
    print(f"耗时: {result.elapsed_seconds:.1f}s")
```

### 15.5 配合 JellyfishAdapter 使用

如果你已有 Jellyfish 的 DB 数据,可以用 Adapter 转换:

```python
from app.pipeline.adapters.jellyfish_adapter import JellyfishAdapter

adapter = JellyfishAdapter()

# 从 Jellyfish DB 数据构建 Pipeline 输入
input_data = adapter.build_pipeline_input(
    chapter_id="ch_001",
    project_name="浮生当铺",
    shots=[{"shot_id": "shot_001", "shot_index": 1, "script_excerpt": "..."}],
    characters=[{"name": "陆沉", "description": "..."}],
    costumes=[{"id": "c1", "name": "日常装", "description": "..."}],
)

# 运行 Pipeline...
# result = engine.run(...)

# 构建写回命令
cmds = adapter.build_write_back_commands(result.to_dict(), "ch_001", shots)
card_cmds = adapter.build_storyboard_cards_commands(result.to_dict(), "ch_001")
```


---

## 16. 分镜提取与结果查看

### 16.1 提取分镜

在章节页面（ChaptersTab），点击章节操作按钮即可启动分镜提取：

1. 进入项目 → 章节列表
2. 确保章节已有原文内容
3. 点击「提取分镜」按钮
4. 系统会自动调用 LLM 分析剧本并拆分为多个镜头

### 16.2 查看执行进度

提取过程中，右上角会弹出通知弹窗，显示：

- **当前步骤**：如"正在拆分镜头…"、"写入分镜结果"
- **进度百分比**：如"进度 35%"
- **累计耗时**和**开始时间**

### 16.3 查看提取结果

任务完成后：

- 右上角弹出绿色通知：`分镜提取完成 — 章节名：成功拆分为 N 个镜头`
- 章节列表的「分镜数」列自动更新
- 点击「查看分镜」可进入分镜编辑页查看每个镜头的详细信息

### 16.4 设置默认模型

分镜提取需要使用默认文本模型：

1. 进入「模型管理」页面
2. 添加模型（如 qwen-max）
3. 点击模型右侧的「更多」→「设为默认」
4. 设为默认后，分镜提取即可正常使用

### 16.5 常见问题

| 问题 | 原因 | 解决 |
|---|---|---|
| 分镜提取立即失败 | 未设置默认文本模型 | 在模型管理页设为默认 |
| 任务一直显示 pending | 后端未启动或线程池满 | 重启后端，检查 TASK_EXECUTOR_MODE |
| 看不到执行步骤 | 前端版本过旧 | 刷新页面（HMR 自动更新） |
| 404 错误 | 模型名称不匹配 | 使用 API 标识符（如 qwen-max）而非显示名 |
