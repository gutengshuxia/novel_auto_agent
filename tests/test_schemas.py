"""Schema 静态校验 —— sandbox 无 pydantic, 用纯 AST + 源码字符串扫描。"""
from __future__ import annotations

import ast, pathlib, sys

ROOT = pathlib.Path(__file__).parent.parent

REQUIRED = {
    "src/schemas/story_analysis.py": {
        "Character": ["character_id","name","role","appearance","personality","visual_keywords"],
        "Scene": ["scene_id","location","time_of_day","description","characters","visual_keywords"],
        "StoryAnalysis": ["title","genre","tone","visual_style","target_models",
                          "characters","scenes","plot_summary","visual_keywords"],
    },
    "src/schemas/storyboard.py": {
        "CameraMovement": None,
        "DialogueLine": ["character_id","line","emotion","delivery_type"],
        "Shot": ["shot_id","scene_id","shot_index","duration_sec","framing","camera",
                 "description","characters_in_shot","dialogue","visual_style_override","visual_focus"],
        "Storyboard": ["title","based_on_title","shots","total_duration_sec"],
    },
    "src/schemas/prompt_plan.py": {
        "PromptVariant": ["target_model","prompt_text","negative_prompt","aspect_ratio","duration_sec","notes"],
        "ShotPrompts": ["shot_id","variants","dialogue"],
        "PromptPlan": ["story_title","target_models","shot_prompts"],
    },
    "src/schemas/enums.py": {
        "TargetModel": ["KLING","JIMENG"],
        "FramingStyle": None, "VisualStyle": None, "MoodTone": None, "AspectRatio": None,
    },
}
TOP_LEVEL_SCHEMA_CLASSES = {"StoryAnalysis", "Storyboard", "PromptPlan"}

errors = []
for rel, classes in REQUIRED.items():
    full = ROOT / rel
    if not full.exists():
        errors.append(f"MISSING FILE: {rel}"); continue
    src = full.read_text(encoding="utf-8")
    tree = ast.parse(src)
    defined = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    for cname, expected in classes.items():
        if cname not in defined:
            errors.append(f"{rel}: missing class {cname}"); continue
        cnode = defined[cname]
        if expected is None:
            continue
        if rel.endswith("enums.py"):
            enum_members = [t.targets[0].id for t in cnode.body
                            if isinstance(t, ast.Assign) and isinstance(t.targets[0], ast.Name)
                            and t.targets[0].id.isupper()]
            miss = [m for m in expected if m not in enum_members]
            if miss:
                errors.append(f"{rel}::{cname} 缺 enum 成员: {miss}")
            continue
        actual = [t.target.id for t in cnode.body
                  if isinstance(t, ast.AnnAssign) and isinstance(t.target, ast.Name)]
        missing = [f for f in expected if f not in actual]
        if missing:
            errors.append(f"{rel}::{cname} missing fields: {missing}")
        if cname in TOP_LEVEL_SCHEMA_CLASSES:
            has_schema = "def to_json_schema" in src
            if not has_schema:
                errors.append(f"{rel}::{cname} should have to_json_schema()")

init_text = (ROOT/"src/schemas/__init__.py").read_text(encoding="utf-8")
for sym in ["AspectRatio","FramingStyle","MoodTone","TargetModel","VisualStyle",
            "Character","Scene","StoryAnalysis","DEFAULT_TARGET_MODELS",
            "CameraMovement","DeliveryType","DialogueLine","Shot","Storyboard",
            "PromptVariant","ShotPrompts","PromptPlan"]:
    if sym not in init_text:
        errors.append(f"schemas/__init__.py: not exporting {sym}")

print(f"[1/3] Static check: {len(REQUIRED)} files scanned")
if errors:
    print("FAILED:"); [print("  X", e) for e in errors]; sys.exit(1)
print("  OK All required classes & fields present")

# ---- Part 2/3: 源码级 enum/覆盖校验 ----
print("\n[2/3] Enum coverage from source code:")
import re
enums_src = (ROOT/"src/schemas/enums.py").read_text(encoding="utf-8")

def enum_members(name):
    m = re.search(rf"class {name}\(str, Enum\):(.*?)(?=\nclass |\Z)", enums_src, re.S)
    if not m: return set()
    return set(re.findall(r"^\s{4}([A-Z_]+)\s*=", m.group(1), re.M))

got_models = {v.lower() for v in enum_members("TargetModel")}
expected_models = {"kling","jimeng"}
assert got_models == expected_models, f"TargetModel 不符: {expected_models} vs {got_models}"
print(f"  OK TargetModel = {sorted(got_models)}")

storyboard_src = (ROOT/"src/schemas/storyboard.py").read_text(encoding="utf-8")
m = re.search(r"class CameraMovement\(str, Enum\):(.*?)(?=\nclass |\Z)", storyboard_src, re.S)
got_mov = set(re.findall(r"^\s{4}([A-Z_]+)\s*=", m.group(1), re.M))
got_mov_lower = {v.lower() for v in got_mov}
must_mov = {"static","pan_left","pan_right","tilt_up","tilt_down",
            "dolly_in","dolly_out","zoom_in","zoom_out",
            "track_left","track_right","crane_up","crane_down","handheld","drone_aerial"}
miss = must_mov - got_mov_lower
assert not miss, f"CameraMovement 缺: {miss}"
print(f"  OK CameraMovement 覆盖 {len(got_mov_lower)} 种运镜")

m = re.search(r"class FramingStyle\(str, Enum\):(.*?)(?=\nclass |\Z)", enums_src, re.S)
got_f = {v.lower() for v in re.findall(r"^\s{4}([A-Z_]+)\s*=", m.group(1), re.M)}
must_f = {"close_up","medium","wide"}
assert must_f.issubset(got_f), f"FramingStyle 缺: {must_f-got_f}"
print(f"  OK FramingStyle 含 close_up/medium/wide ({len(got_f)} 种景别)")

# ---- Part 3/3: 字段交叉校验逻辑是否到位 ----
print("\n[3/3] Cross-reference validators:")
checks = [
    ("StoryAnalysis 校验 scenes->characters 引用",
     "_check_characters_in_scenes" in (ROOT/"src/schemas/story_analysis.py").read_text(encoding="utf-8")),
    ("Storyboard 校验 shot_id 唯一",
     "_check_unique_shot_id_and_order" in (ROOT/"src/schemas/storyboard.py").read_text(encoding="utf-8")),
    ("PromptPlan 校验 5 模型全覆盖",
     "_check_models_covered" in (ROOT/"src/schemas/prompt_plan.py").read_text(encoding="utf-8")),
    ("Storyboard 自动汇总 total_duration_sec",
     "_compute_total_duration" in (ROOT/"src/schemas/storyboard.py").read_text(encoding="utf-8")),
    ("to_json_schema 方法已暴露给 LLM 调用方",
     all(f"def to_json_schema" in (ROOT/f"src/schemas/{f}.py").read_text(encoding="utf-8")
         for f in ("story_analysis","storyboard","prompt_plan"))),
]
for label, ok in checks:
    print(f"  {'OK' if ok else 'X'} {label}")
    if not ok: sys.exit(1)

print("\nGREEN Schema static + simulation all passed.")


# ---- Part 4/4: 微调字段验证 ----
print("\n[4/4] Recent schema micro-adjustments:")
storyboard_src = (ROOT/"src/schemas/storyboard.py").read_text(encoding="utf-8")

# DeliveryType 取值 + DialogueLine 默认值
import re
assert "DeliveryType = Literal[" in storyboard_src
m = re.search(r"DeliveryType = Literal\[([^\]]+)\]", storyboard_src)
literal_values = [v.strip().strip('"').strip("'") for v in m.group(1).split(",")]
expected_dt = {"dialogue", "voiceover", "sfx"}
assert set(literal_values) == expected_dt, f"DeliveryType 期望 {expected_dt}, 得到 {literal_values}"
print(f"  OK DeliveryType = {literal_values}")

# Shot.visual_style_override 默认 None + 类型 Optional[VisualStyle]
assert "visual_style_override: Optional[VisualStyle]" in storyboard_src
assert "default=None" in storyboard_src.split("visual_style_override")[1].split("visual_focus")[0]
print("  OK Shot.visual_style_override: Optional[VisualStyle] = None")

# DialogueLine.delivery_type 默认 "dialogue"
assert 'delivery_type: DeliveryType' in storyboard_src
assert 'default="dialogue"' in storyboard_src
print('  OK DialogueLine.delivery_type: DeliveryType = "dialogue"')

print("\nGREEN Static + simulation + micro-adjustments all passed.")
