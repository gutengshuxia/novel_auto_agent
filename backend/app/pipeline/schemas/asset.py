"""P3 资产锚点系统 (Asset Anchor Registry)。

灵感来自 "古风甜宠短剧" Skill 的 node_key 体系:
- 每个角色 / 场景 / 构图参考 都注册为一个 AssetNode
- 后续 Prompt 生成用 <<<node_key>>> 占位符引用
- 避免 LLM 漂移 / 形象不一致
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AssetType(str, Enum):
    """资产类型。"""

    CHARACTER = "character"           # 角色四视图 / 参考图
    SCENE = "scene"                   # 场景参考图
    COMPOSITION = "composition"       # 构图参考图
    PROP = "prop"                     # 道具参考图
    STYLE = "style"                   # 视觉风格参考


class AssetSource(str, Enum):
    """资产来源。"""

    USER_UPLOAD = "user_upload"       # 用户上传
    AI_GENERATED = "ai_generated"     # AI 生成
    LLM_INFERRED = "llm_inferred"     # LLM 推断 (无图, 仅文字描述)


class AssetNode(BaseModel):
    """单个资产锚点。"""

    node_key: str = Field(..., min_length=1, description="资产唯一 ID, 形如 char_001_face")
    asset_type: AssetType
    source: AssetSource = AssetSource.LLM_INFERRED
    reference_url: str = Field(default="", description="资产 URL (本地路径或 CDN)")
    description: str = Field(default="", description="资产文字描述 (≥30 字符)")
    bound_to: str = Field(
        default="",
        description="绑定到的业务对象 ID, 如 character_id / scene_id",
    )
    priority: int = Field(
        default=0,
        description="优先级, 数字越大越优先. 用户上传 = 100, AI 生成 = 50, LLM 推断 = 10",
    )


class AssetRegistry(BaseModel):
    """全局资产注册表。"""

    nodes: dict[str, AssetNode] = Field(default_factory=dict)

    def __init__(self, **data):
        super().__init__(**data)
        # 兜底: 兼容 mock 环境未初始化 nodes
        if self.nodes is None:
            object.__setattr__(self, "nodes", {})

    def register(self, node: AssetNode) -> None:
        """注册或覆盖一个资产节点 (priority 高的覆盖低的)。"""
        if not self.nodes:
            object.__setattr__(self, "nodes", {})
        existing = self.nodes.get(node.node_key)
        if existing and existing.priority >= node.priority:
            return  # 已存在更高优先级, 不覆盖
        self.nodes[node.node_key] = node

    def get(self, node_key: str) -> AssetNode | None:
        if not self.nodes:
            return None
        return self.nodes.get(node_key)

    def by_type(self, asset_type: AssetType) -> list[AssetNode]:
        if not self.nodes:
            return []
        return [n for n in self.nodes.values() if n.asset_type == asset_type]

    def to_json_schema(self) -> dict[str, Any]:
        return self.model_json_schema()


__all__ = ["AssetType", "AssetSource", "AssetNode", "AssetRegistry"]
