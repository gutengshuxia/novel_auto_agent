"""Agent 静态校验 —— 不依赖 pydantic/langchain, 验证结构、签名、关键代码。"""
from __future__ import annotations

import ast, pathlib, sys

ROOT = pathlib.Path(__file__).parent.parent

# ---- Part 1/4: 文件齐全 ----
AGENT_FILES = [
    "src/agents/_base.py",
    "src/agents/step1_analyzer.py",
    "src/agents/step2_director.py",
    "src/agents/step3_planner.py",
    "src/agents/step4_writer.py",
    "src/agents/step5_consistency.py",
    "src/agents/step6_adapter.py",
]
print("[1/4] File completeness:")
missing = [f for f in AGENT_FILES if not (ROOT/f).exists()]
if missing:
    print("  X missing:", missing); sys.exit(1)
print(f"  OK {len(AGENT_FILES)} agent files present")

# ---- Part 2/4: 每个 Step Agent 必须继承 BaseAgent ----
print("\n[2/4] Class inheritance:")
for f in AGENT_FILES[1:]:
    src = (ROOT/f).read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "BaseAgent":
                    found = True
                    break
    name = pathlib.Path(f).stem
    if not found:
        print(f"  X {name}: no class inherits BaseAgent"); sys.exit(1)
    print(f"  OK {name}")

# ---- Part 3/4: 关键方法存在 ----
print("\n[3/4] Required methods per agent:")
must_have = {
    "src/agents/step1_analyzer.py": ["Step1Analyzer", "__call__", "system_prompt", "output_schema"],
    "src/agents/step2_director.py": ["Step2Director", "__call__", "system_prompt"],
    "src/agents/step3_planner.py": ["Step3Planner", "__call__", "system_prompt"],
    "src/agents/step4_writer.py": ["Step4Writer", "__call__", "export_prompts_to_excel"],
    "src/agents/step5_consistency.py": ["Step5ConsistencyChecker", "__call__", "_JudgeOutput", "passed", "issues", "suggestions"],
    "src/agents/step6_adapter.py": ["Step6ModelAdapter", "__call__", "_OPTIMIZERS",
                                    "TargetModel.KLING",
                                    "TargetModel.JIMENG"],
}
for rel, tokens in must_have.items():
    src = (ROOT/rel).read_text(encoding="utf-8")
    miss = [t for t in tokens if t not in src]
    if miss:
        print(f"  X {rel}: missing tokens {miss}"); sys.exit(1)
    print(f"  OK {rel}: all {len(tokens)} tokens present")

# ---- Part 4/4: 模块实例 (singleton) 暴露 ----
print("\n[4/4] Singleton instances in agents/__init__.py:")
init = (ROOT/"src/agents/__init__.py").read_text(encoding="utf-8")
for inst in ["step1_analyze", "step2_storyboard", "step3_plan_prompts",
             "step4_write_prompts", "step5_consistency_check", "step6_model_adapter"]:
    if inst not in init:
        print(f"  X not exported: {inst}"); sys.exit(1)
print(f"  OK all 6 singletons exported")

# ---- Bonus: Step 4 必须包含 Excel 导出调用 ----
print("\n[Bonus] Step 4 invokes Excel export:")
src = (ROOT/"src/agents/step4_writer.py").read_text(encoding="utf-8")
if "export_prompts_to_excel(" not in src:
    print("  X step4 does not call export_prompts_to_excel"); sys.exit(1)
print("  OK step4 calls export_prompts_to_excel")

# ---- Bonus: Step 5 必须 LLM-as-judge + 回滚计数 ----
src = (ROOT/"src/agents/step5_consistency.py").read_text(encoding="utf-8")
checks = {
    "LLM 裁判调用": "_JudgeOutput" in src,
    "passed 字段": "passed=" in src or '"passed"' in src,
    "issues 字段": "issues=" in src,
    "suggestions 字段": "suggestions=" in src,
    "回滚计数自增": 'replan_count"] = replan_count + 1' in src or "replan_count'] = replan_count + 1" in src,
    "回滚时清空 prompt_text": 'v.prompt_text = ""' in src,
}
for label, ok in checks.items():
    print(f"  {'OK' if ok else 'X'} {label}")
    if not ok: sys.exit(1)

# ---- Bonus: Step 6 必须 5 模型专属优化器 ----
print("\n[Bonus] Step 6 2-model optimizers:")
src = (ROOT/"src/agents/step6_adapter.py").read_text(encoding="utf-8")
optimizers = ["_optimize_kling", "_optimize_jimeng"]
miss = [o for o in optimizers if o not in src]
if miss:
    print(f"  X missing optimizers: {miss}"); sys.exit(1)
print(f"  OK all 2 model optimizers defined + dispatch table")

# ---- Bonus: Step 4 5 模型风格指南 ----
src = (ROOT/"src/agents/step4_writer.py").read_text(encoding="utf-8")
must_styles = [
    "TargetModel.KLING", "TargetModel.JIMENG",
]
miss = [m for m in must_styles if m not in src]
if miss:
    print(f"  X MODEL_STYLE_GUIDE missing: {miss}"); sys.exit(1)
print(f"  OK MODEL_STYLE_GUIDE covers all 2 models")

print("\nGREEN Agent static check all passed.")
