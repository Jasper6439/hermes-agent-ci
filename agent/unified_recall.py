# Source: AutoGPT
# Upstream: https://github.com/Significant-Gravitas/AutoGPT
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Unified Recall — 统一记忆召回系统

整合 L2 Fusion + L3/L5 Semble + L4 Session Search，提供一站式记忆召回。

Usage:
    from agent.unified_recall import UnifiedRecall
    
    recall = UnifiedRecall()
    context = recall.recall("部署前检查")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

import math
from datetime import datetime


def rrf_fusion_rank(result_lists: list, k: int = 60) -> list:
    """Reciprocal Rank Fusion - 融合多个排序列表。
    RRF_score(d) = Σ 1/(k + rank_i(d))
    """
    scores = {}
    for result_list in result_lists:
        for rank, r in enumerate(result_list):
            key = r.content[:100].strip()
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
    scored = []
    seen = set()
    for result_list in result_lists:
        for r in result_list:
            key = r.content[:100].strip()
            if key not in seen:
                seen.add(key)
                r.score = scores[key]
                scored.append(r)
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored


def three_factor_score(result, alpha=0.5, beta=0.3, gamma=0.2):
    """三因子评分: relevance + importance + recency。"""
    relevance = result.score
    importance_map = {"L2": 0.8, "L3": 0.9, "L4": 0.5, "L5": 1.0}
    importance = importance_map.get(result.layer, 0.5)
    recency = 0.8  # 默认值
    return alpha * relevance + beta * importance + gamma * recency





@dataclass
class RecallResult:
    """召回结果。"""
    layer: str              # L2, L3, L4, L5
    content: str            # 记忆内容
    source: str             # 来源
    score: float            # 相关性分数
    type: str               # semantic, fact, session, wisdom


@dataclass
class RecallContext:
    """召回上下文（注入到 LLM）。"""
    results: List[RecallResult] = field(default_factory=list)
    total_tokens: int = 0
    
    def to_prompt(self, max_results: int = 5) -> str:
        """转换为可注入的 prompt 片段。"""
        if not self.results:
            return ""
        
        lines = ["[记忆召回结果]"]
        
        for r in self.results[:max_results]:
            layer_name = {
                "L2": "语义记忆",
                "L3": "跨话题事实",
                "L4": "会话历史",
                "L5": "祖先记忆",
            }.get(r.layer, r.layer)
            
            lines.append(f"\n【{layer_name}】(来源: {r.source})")
            lines.append(r.content[:200])  # 限制长度
        
        return "\n".join(lines)



# CrossEncoder reranker (lazy load)
_reranker_model = None
def _get_reranker():
    global _reranker_model
    if _reranker_model is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device="cpu")
        except Exception:
            _reranker_model = False
    return _reranker_model if _reranker_model is not False else None


class UnifiedRecall:
    """统一记忆召回器。"""
    
    _instance: Optional[UnifiedRecall] = None
    
    def __new__(cls) -> UnifiedRecall:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        logger.info("UnifiedRecall initialized")
    
    def _recall_fusion(self, query: str, limit: int = 3) -> List[RecallResult]:
        """从 L2 Fusion 召回。"""
        try:
            from hermes_tools import fusion_recall
            result = fusion_recall(query=query, reasoning_level="minimal")
            
            if result and "answer" in result:
                return [RecallResult(
                    layer="L2",
                    content=result["answer"],
                    source="Fusion",
                    score=1.0,
                    type="semantic",
                )]
        except Exception as e:
            logger.warning(f"Fusion recall failed: {e}")
        
        return []
    
    def _recall_semble(self, query: str, layer: str, path: str, limit: int = 3) -> List[RecallResult]:
        """从 Semble 索引层召回。"""
        try:
            from agent.memory_indexer import memory_indexer
            results = memory_indexer.search_layer(query, layer, limit=limit)
            
            return [RecallResult(
                layer=layer,
                content=r.content,
                source=r.source,
                score=r.score,
                type="fact" if layer == "L3" else "wisdom",
            ) for r in results]
            
        except Exception as e:
            logger.warning(f"Semble recall failed for {layer}: {e}")
        
        return []
    
    def _recall_session(self, query: str, limit: int = 3) -> List[RecallResult]:
        """从 L4 Session DB 召回（使用 FTS5 搜索）。"""
        try:
            from tools.session_search_tool import session_search
            result = session_search(query=query, limit=limit)
            
            if result and isinstance(result, str) and "No results" not in result:
                return [RecallResult(
                    layer="L4",
                    content=result[:500],  # 限制长度
                    source="SessionDB",
                    score=0.8,
                    type="session",
                )]
        except Exception as e:
            logger.warning(f"Session search failed: {e}")
        
        return []
    
    def recall(
        self,
        query: str,
        include_fusion: bool = True,
        include_semble: bool = True,
        include_session: bool = True,
        limit: int = 5,
    ) -> RecallContext:
        """
        统一召回。
        
        Args:
            query: 搜索查询
            include_fusion: 是否包含 L2 Fusion
            include_semble: 是否包含 L3/L5 Semble
            include_session: 是否包含 L4 Session Search
            limit: 返回结果数量
        
        Returns:
            RecallContext: 召回上下文
        """
        all_results = []
        
        # L2 Fusion
        if include_fusion:
            fusion_results = self._recall_fusion(query, limit=limit)
            all_results.extend(fusion_results)
        
        # L3 Semble (MEMORY.md)
        if include_semble:
            semble_results = self._recall_semble(query, "L3", "~/.hermes/memories", limit=limit)
            all_results.extend(semble_results)
        
        # L4 Session Search (FTS5)
        if include_session:
            session_results = self._recall_session(query, limit=limit)
            all_results.extend(session_results)
        
        # L5 Semble (Ancestral Memory)
        if include_semble:
            ancestral_results = self._recall_semble(query, "L5", "~/.hermes/memories", limit=limit)
            all_results.extend(ancestral_results)
        
        # RRF融合排序 + 三因子评分
        # 按来源分组
        layer_groups = {}
        for r in all_results:
            layer_groups.setdefault(r.layer, []).append(r)
        
        # RRF融合
        if len(layer_groups) > 1:
            fused = rrf_fusion_rank(list(layer_groups.values()))
        else:
            all_results.sort(key=lambda x: x.score, reverse=True)
            fused = all_results
        
        # 三因子评分重排
        for r in fused:
            r.score = three_factor_score(r)
        fused.sort(key=lambda x: x.score, reverse=True)
        
        # 去重
        unique_results = []
        seen_contents = set()
        for r in fused:
            content_key = r.content[:100].strip()
            if content_key not in seen_contents:
                seen_contents.add(content_key)
                unique_results.append(r)
        
        context = RecallContext(results=unique_results[:limit])
        logger.info(f"Recall: {len(context.results)} results for '{query[:30]}...'")
        
        return context
    
    @staticmethod
    def rerank(query: str, results: list, top_k: int = None) -> list:
        """Rerank results using CrossEncoder."""
        if not results or len(results) <= 1:
            return results
        reranker = _get_reranker()
        if not reranker:
            return results
        try:
            pairs = [(query, r.get("content", r.get("text", ""))) for r in results]
            scores = reranker.predict(pairs)
            for r, s in zip(results, scores):
                r["rerank_score"] = float(s)
            results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        except Exception:
            pass
        if top_k:
            results = results[:top_k]
        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。"""
        from agent.memory_indexer import memory_indexer
        return memory_indexer.get_stats()


# 全局实例
unified_recall = UnifiedRecall()
