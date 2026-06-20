#!/usr/bin/env python3
"""Unified Recall — Single entry point for all memory layers.

Replaces: fusion_recall, fusion_search, session_search, semblectl_search
Layers: L1 (topic) → L2 (fusion/vector) → L2.5 (collective) → L3 (memory.md) → L4 (session DB) → L5 (wiki)
"""
import json
import os
from typing import Any, Dict, List, Optional

def unified_recall(query: str, limit: int = 5, min_confidence: float = 0.3) -> Dict[str, Any]:
    """Single entry point for all memory layers.
    
    Args:
        query: Search query
        limit: Max results per layer
        min_confidence: Minimum confidence threshold
    
    Returns:
        {
            "results": [...],
            "sources": ["L1", "L2_Fusion", ...],
            "total": int,
            "filtered": int,
        }
    """
    all_results = []
    sources_used = []
    
    # L1: Topic Memory (auto-injected via pre_llm_call, skip here)
    
    # L2: Fusion/Qdrant vector search
    try:
        from fusion import get_fusion_provider
        fusion = get_fusion_provider()
        if fusion and fusion.is_available():
            result_str = fusion.handle_tool_call("fusion_search", {
                "query": query,
                "limit": limit,
                "min_confidence": min_confidence,
            })
            fusion_data = json.loads(result_str)
            for r in fusion_data.get("results", []):
                all_results.append({
                    "source": "L2_Fusion",
                    "text": r.get("text", ""),
                    "score": r.get("confidence", 0.5),
                })
            if fusion_data.get("results"):
                sources_used.append("L2_Fusion")
    except Exception:
        pass
    
    # L3: MEMORY.md (semblectl search)
    try:
        from semblectl_search import search as semblectl_search
        memory_path = os.path.expanduser("~/.hermes/memories/MEMORY.md")
        if os.path.exists(memory_path):
            results = semblectl_search(query, paths=[memory_path], limit=limit)
            for r in results:
                all_results.append({
                    "source": "L3_MEMORY",
                    "text": r.get("snippet", r.get("text", "")),
                    "score": r.get("score", 0.4),
                })
            if results:
                sources_used.append("L3_MEMORY")
    except Exception:
        pass
    
    # L4: Session DB (FTS5 search)
    try:
        from hermes_state import SessionDB
        db = SessionDB()
        results = db.search_messages(query, limit=limit)
        for r in results:
            all_results.append({
                "source": "L4_Session",
                "text": r.get("content", "")[:300],
                "score": r.get("score", 0.3),
            })
        if results:
            sources_used.append("L4_Session")
    except Exception:
        pass
    
    # L5: Wiki/Obsidian (semblectl search)
    try:
        wiki_path = os.path.expanduser("~/.hermes/memories/wiki")
        if os.path.exists(wiki_path):
            from semblectl_search import search as semblectl_search
            results = semblectl_search(query, paths=[wiki_path], limit=limit)
            for r in results:
                all_results.append({
                    "source": "L5_Wiki",
                    "text": r.get("snippet", r.get("text", "")),
                    "score": r.get("score", 0.2),
                })
            if results:
                sources_used.append("L5_Wiki")
    except Exception:
        pass
    
    # Filter by confidence
    filtered = [r for r in all_results if r.get("score", 0) >= min_confidence]
    
    # Sort by score
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    return {
        "results": filtered[:limit],
        "sources": sources_used,
        "total": len(all_results),
        "filtered": len(filtered),
    }

# Tool schema for LLM
TOOL_SCHEMA = {
    "name": "unified_recall",
    "description": (
        "Search all memory layers (L1-L5) with a single query. "
        "Returns relevant memories from topic memory, vector search, "
        "session history, and knowledge base."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for in memory.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default: 5).",
            },
            "min_confidence": {
                "type": "number",
                "description": "Minimum confidence threshold (default: 0.3).",
            },
        },
        "required": ["query"],
    },
}

def handle_tool_call(args: Dict[str, Any]) -> str:
    """Handle tool call from LLM."""
    query = args.get("query", "")
    limit = args.get("limit", 5)
    min_confidence = args.get("min_confidence", 0.3)
    
    result = unified_recall(query, limit=limit, min_confidence=min_confidence)
    return json.dumps(result, ensure_ascii=False)
