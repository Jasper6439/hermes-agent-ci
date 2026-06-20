# Source: AutoGPT
# Upstream: https://github.com/Significant-Gravitas/AutoGPT
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Cross-Session Context Sharing — 跨会话上下文共享（基于现有记忆架构）

不创建新的存储层，而是作为 L2 MEMORY.md 和 L3 Fusion 的智能接口。
共享的上下文存储在 L2，通过 L3 语义召回。

Usage:
    from agent.cross_session import CrossSessionManager
    
    manager = CrossSessionManager()
    manager.share_context("project_x", {"status": "active"})
    context = manager.get_context("project_x")
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CrossSessionManager:
    """跨会话上下文共享，基于 L2 MEMORY.md 和 L3 Fusion。"""
    
    _instance: Optional[CrossSessionManager] = None
    
    def __new__(cls) -> CrossSessionManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        logger.info("CrossSessionManager initialized (using L2/L3 architecture)")
    
    def share_context(
        self,
        key: str,
        data: Dict[str, Any],
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        共享上下文到 L2 MEMORY.md。
        
        返回写入的记忆文本。
        """
        # 格式化为记忆文本
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        data_str = ", ".join(f"{k}={v}" for k, v in data.items())
        memory_text = f"[共享上下文]{tag_str} {key}: {data_str}"
        
        # 写入 L2 MEMORY.md（通过 Hermes 记忆系统）
        try:
            from hermes_tools import memory as hermes_memory
            hermes_memory(action="add", target="memory", content=memory_text)
            logger.info(f"Shared context to L2: {key}")
        except Exception as e:
            logger.warning(f"Failed to write to L2: {e}")
            # Fallback: 直接追加到 MEMORY.md
            self._append_to_memory_md(memory_text)
        
        return memory_text
    
    def get_context(self, key: str) -> Optional[Dict[str, Any]]:
        """
        从 L3 Fusion 召回共享上下文。
        
        使用语义搜索查找相关记忆。
        """
        try:
            from hermes_tools import fusion_recall
            result = fusion_recall(query=f"共享上下文 {key}", reasoning_level="minimal")
            
            if result and "answer" in result:
                # 解析召回结果
                answer = result["answer"]
                if key in answer:
                    return self._parse_context(answer, key)
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to recall from L3: {e}")
            return None
    
    def _append_to_memory_md(self, text: str) -> None:
        """直接追加到 MEMORY.md（fallback）。"""
        from pathlib import Path
        memory_file = Path.home() / ".hermes" / "memories" / "MEMORY.md"
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(memory_file, "a") as f:
            f.write(f"\n{text}")
    
    def _parse_context(self, text: str, key: str) -> Dict[str, Any]:
        """从召回文本解析上下文数据。"""
        # 简单解析：查找 key: 后面的内容
        import re
        pattern = rf"{key}:\s*(.+?)(?:\n|$)"
        match = re.search(pattern, text)
        if match:
            data_str = match.group(1)
            # 解析 key=value 对
            result = {}
            for pair in data_str.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    result[k.strip()] = v.strip()
            return result
        return {}
    
    def search_contexts(self, query: str) -> List[Dict[str, Any]]:
        """
        从 L3 Fusion 搜索相关共享上下文。
        """
        try:
            from hermes_tools import fusion_recall
            result = fusion_recall(query=f"共享上下文 {query}", reasoning_level="low")
            
            if result and "answer" in result:
                return [{"text": result["answer"], "source": "L3"}]
            
            return []
            
        except Exception as e:
            logger.warning(f"Failed to search L3: {e}")
            return []


# Global instance
cross_session_manager = CrossSessionManager()
