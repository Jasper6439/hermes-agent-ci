# Source: AutoGPT
# Upstream: https://github.com/Significant-Gravitas/AutoGPT
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Unified Recall Tool — 统一记忆召回工具

整合 L2 Fusion + Semble (L3/L4/L5)，提供一站式记忆召回。

Usage:
    unified_recall(query="部署前检查", limit=5)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from tools.registry import registry

logger = logging.getLogger(__name__)


# ─── Tool Schema ──────────────────────────────────────────────────────────────

UNIFIED_RECALL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "unified_recall",
        "description": (
            "统一记忆召回：一次搜索跨 L2/L3/L4/L5 记忆层。"
            "L2=语义记忆(Fusion)，L3=跨话题事实，L4=会话历史，L5=祖先记忆。"
            "返回相关记忆片段，自动去重排序。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询",
                },
                "limit": {
                    "type": "integer",
                    "description": "返回结果数量（默认 5）",
                    "default": 5,
                },
                "include_fusion": {
                    "type": "boolean",
                    "description": "是否包含 L2 Fusion（默认 true）",
                    "default": True,
                },
                "include_semble": {
                    "type": "boolean",
                    "description": "是否包含 L3-L5 Semble（默认 true）",
                    "default": True,
                },
            },
            "required": ["query"],
        },
    },
}


# ─── Handler ──────────────────────────────────────────────────────────────────

def _handle_unified_recall(**kwargs) -> str:
    """处理统一召回。"""
    from agent.unified_recall import unified_recall
    
    query = kwargs.get("query", "")
    limit = kwargs.get("limit", 5)
    include_fusion = kwargs.get("include_fusion", True)
    include_semble = kwargs.get("include_semble", True)
    
    if not query:
        return "Error: query 是必填项"
    
    context = unified_recall.recall(
        query=query,
        include_fusion=include_fusion,
        include_semble=include_semble,
        limit=limit,
    )
    
    if not context.results:
        return f"未找到相关记忆: {query}"
    
    return context.to_prompt(max_results=limit)


# ─── Register ──────────────────────────────────────────────────────────────────

registry.register(
    name="unified_recall",
    toolset="memory",
    schema=UNIFIED_RECALL_SCHEMA,
    handler=_handle_unified_recall,
    emoji="🧠",
    max_result_size_chars=10_000,
)
