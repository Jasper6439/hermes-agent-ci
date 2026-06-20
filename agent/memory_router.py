# Source: AutoGPT
# Upstream: https://github.com/Significant-Gravitas/AutoGPT
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Memory Router — 智能记忆路由系统

根据查询特征，智能选择 L3/L4/L5 记忆层进行召回，
避免全量搜索，提高召回效率。

Usage:
    from agent.memory_router import MemoryRouter
    
    router = MemoryRouter()
    result = router.route("这个API怎么用？")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryLayer(Enum):
    """Memory layer identifiers."""
    L1 = "topic_memory"      # 当前会话上下文
    L2 = "memory_md"         # 长期记忆文件
    L3 = "fusion"            # 语义记忆 (Qdrant)
    L4 = "session_db"        # 会话历史
    L5 = "wiki"              # 实体知识库


@dataclass
class RoutingDecision:
    """Routing decision with rationale."""
    primary: MemoryLayer
    fallback: List[MemoryLayer]
    reason: str
    confidence: float


class MemoryRouter:
    """Intelligent memory routing based on query analysis."""
    
    _instance: Optional[MemoryRouter] = None
    
    def __new__(cls) -> MemoryRouter:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Query patterns for routing
        self._patterns: Dict[str, List[MemoryLayer]] = {
            # 实体查询 → Wiki
            "who is": [MemoryLayer.L5, MemoryLayer.L3],
            "what is": [MemoryLayer.L5, MemoryLayer.L3],
            "tell me about": [MemoryLayer.L5, MemoryLayer.L3],
            
            # 会话历史 → Session DB
            "之前讨论过": [MemoryLayer.L4, MemoryLayer.L3],
            "上次说过": [MemoryLayer.L4, MemoryLayer.L3],
            "当时": [MemoryLayer.L4, MemoryLayer.L3],
            "聊天记录": [MemoryLayer.L4],
            
            # 代码/技术 → Fusion
            "怎么用": [MemoryLayer.L3, MemoryLayer.L5],
            "如何实现": [MemoryLayer.L3, MemoryLayer.L5],
            "API": [MemoryLayer.L3, MemoryLayer.L5],
            "错误": [MemoryLayer.L3, MemoryLayer.L4],
            "bug": [MemoryLayer.L3, MemoryLayer.L4],
            
            # 记忆管理 → Memory MD
            "记住": [MemoryLayer.L2],
            "不要忘记": [MemoryLayer.L2],
            "重要": [MemoryLayer.L2],
        }
        
        self._initialized = True
        logger.info("MemoryRouter initialized")
    
    def route(self, query: str) -> RoutingDecision:
        """Route a query to the appropriate memory layer."""
        query_lower = query.lower()
        
        # Check pattern matches
        for pattern, layers in self._patterns.items():
            if pattern in query_lower:
                return RoutingDecision(
                    primary=layers[0],
                    fallback=layers[1:] if len(layers) > 1 else [MemoryLayer.L3],
                    reason=f"Pattern match: '{pattern}'",
                    confidence=0.8,
                )
        
        # Default: Fusion (L3) as primary, Session DB (L4) as fallback
        return RoutingDecision(
            primary=MemoryLayer.L3,
            fallback=[MemoryLayer.L4, MemoryLayer.L5],
            reason="Default routing",
            confidence=0.5,
        )
    
    def route_multi(self, queries: List[str]) -> Dict[str, RoutingDecision]:
        """Route multiple queries at once."""
        return {q: self.route(q) for q in queries}


# Global instance
memory_router = MemoryRouter()
