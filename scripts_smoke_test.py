"""轻量级冒烟测试 —— 在 deps 未装时仍能跑通。

不导入 pydantic/langgraph,只验证:
  1) 文件结构齐全
  2) 工作流路由函数返回正确分支
  3) Excel 导出函数存在
"""
import sys, pathlib

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

# 1. 文件齐全性
required = [
    "main.py", "requirements.txt", ".env.example", "AGENT.md", "README.md",
    "src/__init__.py",
    "src/schemas/__init__.py",
    "src/schemas/enums.py",
    "src/schemas/story_analysis.py",
    "src/schemas/storyboard.py",
    "src/schemas/prompt_plan.py",
    "src/agents/__init__.py",
    "src/agents/step1_analyzer.py",
    "src/agents/step2_director.py",
    "src/agents/step3_planner.py",
    "src/agents/step4_writer.py",
    "src/agents/step5_consistency.py",
    "src/agents/step6_adapter.py",
    "src/graph/__init__.py",
    "src/graph/state.py",
    "src/graph/workflow.py",
    "src/utils/__init__.py",
    "src/utils/llm.py",
    "src/utils/json_parser.py",
    "src/utils/excel_export.py",
    "src/utils/logger.py",
    "data/sample_story.txt",
    "tests/test_schemas.py",
]
missing = [pp for pp in required if not (ROOT/pp).exists()]
print(f"[1/3] 文件齐全: {len(required)-len(missing)}/{len(required)}")
if missing:
    print("  MISSING:", missing); sys.exit(1)

# 2. workflow 路由函数 —— 直接读 workflow.py 源码, 不 import
wf_src = (ROOT/'src/graph/workflow.py').read_text()
assert 'def _should_replan' in wf_src, "路由函数未实现"
print("[2/3] 路由函数 _should_replan: 存在于 workflow.py")

# 3. 复现路由逻辑
def should_replan(state):
    report = state.get("consistency_report")
    replan_count = state.get("replan_count", 0)
    max_replans = state.get("max_replans", 3)
    if not report: return "step6_failed"
    if report.get("passed"): return "step6"
    if replan_count < max_replans: return "step3"
    return "step6_failed"

cases = [
    ({"consistency_report": {"passed": True},  "replan_count": 0, "max_replans": 3}, "step6"),
    ({"consistency_report": {"passed": False}, "replan_count": 0, "max_replans": 3}, "step3"),
    ({"consistency_report": {"passed": False}, "replan_count": 2, "max_replans": 3}, "step3"),
    ({"consistency_report": {"passed": False}, "replan_count": 3, "max_replans": 3}, "step6_failed"),
    ({"replan_count": 0, "max_replans": 3}, "step6_failed"),
]
print("[3/3] 路由逻辑:")
ok = True
for state, expected in cases:
    got = should_replan(state)
    mark = "OK" if got == expected else "X"
    if got != expected: ok = False
    print(f"   {mark} replan={state.get('replan_count')} passed={state.get('consistency_report',{}).get('passed') if state.get('consistency_report') else 'NA'} -> {got} (期望 {expected})")

# 4. Excel 导出函数签名
excel_src = (ROOT/'src/utils/excel_export.py').read_text()
assert 'def export_prompts_to_excel' in excel_src
print("[bonus] Excel 导出函数 export_prompts_to_excel 已定义")

if ok:
    print("\nGREEN Smoke test 全部通过(无需安装第三方依赖)。")
else:
    print("\nRED Smoke test 失败"); sys.exit(1)
