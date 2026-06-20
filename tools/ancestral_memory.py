# Source: AutoGPT
# Upstream: https://github.com/Significant-Gravitas/AutoGPT
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Ancestral Memory Tool — 祖先记忆工具

提供祖先记忆的添加和召回接口。

Usage:
    ancestral_memory_add(category="lesson", title="不要删除前确认", content="关闭≠删除")
    ancestral_memory_recall(query="部署", category="lesson")
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from tools.registry import registry

logger = logging.getLogger(__name__)


# ─── Tool Schemas ──────────────────────────────────────────────────────────────

ANCESTRAL_ADD_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "ancestral_memory_add",
        "description": (
            "添加祖先记忆（经验结晶）。"
            "用于存储决策框架、成功策略、失败教训、用户偏好。"
            "不是简单事实，而是提炼后的智慧。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["decision", "strategy", "lesson", "preference", "workflow", "security", "architecture"],
                    "description": "记忆分类",
                },
                "title": {
                    "type": "string",
                    "description": "简短标题",
                },
                "content": {
                    "type": "string",
                    "description": "详细内容（经验/教训/策略）",
                },
                "source": {
                    "type": "string",
                    "description": "来源（哪次事件/教训）",
                    "default": "",
                },
                "importance": {
                    "type": "integer",
                    "description": "重要性 1-10（10 最重要）",
                    "default": 5,
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "标签列表",
                    "default": [],
                },
            },
            "required": ["category", "title", "content"],
        },
    },
}

ANCESTRAL_RECALL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "ancestral_memory_recall",
        "description": (
            "召回祖先记忆。"
            "根据关键词搜索经验结晶，获取决策框架和历史教训。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "category": {
                    "type": "string",
                    "enum": ["decision", "strategy", "lesson", "preference", "workflow", "security", "architecture"],
                    "description": "限定分类（可选）",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回数量（默认 5）",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


# ─── Handlers ──────────────────────────────────────────────────────────────────

def _handle_ancestral_add(**kwargs) -> str:
    """处理添加祖先记忆。"""
    from agent.ancestral_memory import ancestral_memory
    
    category = kwargs.get("category", "")
    title = kwargs.get("title", "")
    content = kwargs.get("content", "")
    source = kwargs.get("source", "")
    importance = kwargs.get("importance", 5)
    tags = kwargs.get("tags", [])
    
    if not category or not title or not content:
        return "Error: category, title, content 都是必填项"
    
    wisdom_id = ancestral_memory.add_wisdom(
        category=category,
        title=title,
        content=content,
        source=source,
        importance=importance,
        tags=tags,
    )
    
    return f"✅ 祖先记忆已添加: {title} (ID: {wisdom_id})"


def _handle_ancestral_recall(**kwargs) -> str:
    """处理召回祖先记忆。"""
    from agent.ancestral_memory import ancestral_memory
    
    query = kwargs.get("query", "")
    category = kwargs.get("category")
    limit = kwargs.get("limit", 5)
    
    if not query:
        return "Error: query 是必填项"
    
    wisdoms = ancestral_memory.recall(query=query, category=category, limit=limit)
    
    if not wisdoms:
        return f"未找到相关祖先记忆: {query}"
    
    lines = [f"找到 {len(wisdoms)} 条祖先记忆:\n"]
    for w in wisdoms:
        lines.append(f"【{w.category}】{w.title} (重要性: {w.importance})")
        lines.append(f"  {w.content}")
        if w.source:
            lines.append(f"  来源: {w.source}")
        lines.append("")
    
    return "\n".join(lines)


# ─── Register ──────────────────────────────────────────────────────────────────

registry.register(
    name="ancestral_memory_add",
    toolset="memory",
    schema=ANCESTRAL_ADD_SCHEMA,
    handler=_handle_ancestral_add,
    emoji="📜",
    max_result_size_chars=5_000,
)

registry.register(
    name="ancestral_memory_recall",
    toolset="memory",
    schema=ANCESTRAL_RECALL_SCHEMA,
    handler=_handle_ancestral_recall,
    emoji="🔮",
    max_result_size_chars=10_000,
)
