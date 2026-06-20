# Source: AutoGPT
# Upstream: https://github.com/Significant-Gravitas/AutoGPT
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Ancestral Memory — 祖先记忆层 (L5)

经验的结晶：决策框架、成功策略、失败教训、用户偏好。
不是简单的事实存储，而是经过提炼的智慧。

Usage:
    from agent.ancestral_memory import AncestralMemory
    
    am = AncestralMemory()
    am.add_wisdom(
        category="deployment",
        title="部署前检查现有基础设施",
        content="用户对重复/冗余零容忍，部署前必须先检查现有服务",
        source="多次部署冲突教训",
    )
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WisdomCategory(Enum):
    """祖先记忆分类。"""
    DECISION = "decision"          # 决策框架
    STRATEGY = "strategy"          # 成功策略
    LESSON = "lesson"              # 失败教训
    PREFERENCE = "preference"      # 用户偏好
    WORKFLOW = "workflow"          # 工作流规范
    SECURITY = "security"          # 安全准则
    ARCHITECTURE = "architecture"  # 架构原则


@dataclass
class Wisdom:
    """一条祖先记忆（经验结晶）。"""
    id: str
    category: str
    title: str
    content: str
    source: str = ""               # 来源（哪次教训/成功）
    importance: int = 5            # 1-10，10 最重要
    created_at: float = 0.0
    accessed_count: int = 0
    last_accessed: float = 0.0
    tags: List[str] = field(default_factory=list)


class AncestralMemory:
    """祖先记忆管理器。"""
    
    _instance: Optional[AncestralMemory] = None
    
    def __new__(cls) -> AncestralMemory:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._wisdoms: Dict[str, Wisdom] = {}
        self._storage_file = Path.home() / ".hermes" / "memories" / "ancestral_memory.json"
        self._load()
        self._initialized = True
        
        logger.info(f"AncestralMemory initialized: {len(self._wisdoms)} wisdoms")
    
    def _load(self) -> None:
        """从磁盘加载祖先记忆。"""
        try:
            if self._storage_file.exists():
                with open(self._storage_file, 'r') as f:
                    data = json.load(f)
                    for w in data:
                        wisdom = Wisdom(**w)
                        self._wisdoms[wisdom.id] = wisdom
                logger.info(f"Loaded {len(self._wisdoms)} ancestral memories")
        except Exception as e:
            logger.warning(f"Failed to load ancestral memory: {e}")
    
    def _save(self) -> None:
        """持久化到磁盘。"""
        try:
            self._storage_file.parent.mkdir(parents=True, exist_ok=True)
            data = [asdict(w) for w in self._wisdoms.values()]
            with open(self._storage_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save ancestral memory: {e}")
    
    def add_wisdom(
        self,
        category: str,
        title: str,
        content: str,
        source: str = "",
        importance: int = 5,
        tags: Optional[List[str]] = None,
    ) -> str:
        """添加一条祖先记忆。"""
        import hashlib
        
        # 生成唯一 ID
        wisdom_id = hashlib.md5(f"{category}:{title}".encode()).hexdigest()[:12]
        
        # 检查是否已存在
        if wisdom_id in self._wisdoms:
            existing = self._wisdoms[wisdom_id]
            existing.content = content  # 更新内容
            existing.importance = max(existing.importance, importance)
            existing.accessed_count += 1
            existing.last_accessed = time.time()
            self._save()
            logger.info(f"Updated ancestral memory: {title}")
            return wisdom_id
        
        wisdom = Wisdom(
            id=wisdom_id,
            category=category,
            title=title,
            content=content,
            source=source,
            importance=importance,
            created_at=time.time(),
            last_accessed=time.time(),
            tags=tags or [],
        )
        
        self._wisdoms[wisdom_id] = wisdom
        self._save()
        
        logger.info(f"Added ancestral memory: {title}")
        return wisdom_id
    
    def recall(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
    ) -> List[Wisdom]:
        """召回相关祖先记忆。"""
        query_lower = query.lower()
        results = []
        
        for wisdom in self._wisdoms.values():
            # 分类过滤
            if category and wisdom.category != category:
                continue
            
            # 简单关键词匹配（后续可接入 L3 语义搜索）
            score = 0
            if query_lower in wisdom.title.lower():
                score += 3
            if query_lower in wisdom.content.lower():
                score += 2
            if any(query_lower in tag.lower() for tag in wisdom.tags):
                score += 1
            
            if score > 0:
                wisdom.accessed_count += 1
                wisdom.last_accessed = time.time()
                results.append((score, wisdom))
        
        # 按分数和重要性排序
        results.sort(key=lambda x: (x[0], x[1].importance), reverse=True)
        
        self._save()
        return [w for _, w in results[:limit]]
    
    def list_by_category(self, category: str) -> List[Wisdom]:
        """按分类列出祖先记忆。"""
        return [w for w in self._wisdoms.values() if w.category == category]
    
    def list_all(self) -> List[Wisdom]:
        """列出所有祖先记忆。"""
        return sorted(
            self._wisdoms.values(),
            key=lambda w: w.importance,
            reverse=True,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。"""
        categories = {}
        for w in self._wisdoms.values():
            categories[w.category] = categories.get(w.category, 0) + 1
        
        return {
            "total": len(self._wisdoms),
            "categories": categories,
            "avg_importance": sum(w.importance for w in self._wisdoms.values()) / max(len(self._wisdoms), 1),
        }


# 全局实例
ancestral_memory = AncestralMemory()
