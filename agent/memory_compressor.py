# Source: AutoGPT
# Upstream: https://github.com/Significant-Gravitas/AutoGPT
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Memory Compressor — 记忆压缩优化

压缩和优化记忆存储，减少 token 消耗。

Usage:
    from agent.memory_compressor import MemoryCompressor
    
    compressor = MemoryCompressor()
    compressed = compressor.compress("很长的记忆文本...")
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryCompressor:
    """Compress and optimize memory storage."""
    
    _instance: Optional[MemoryCompressor] = None
    
    def __new__(cls) -> MemoryCompressor:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Common abbreviations
        self._abbreviations: Dict[str, str] = {
            "Hermes Agent": "HA",
            "Hermes Gateway": "HG",
            "Qdrant Cloud": "QC",
            "Oracle Cloud Infrastructure": "OCI",
            "Vaultwarden": "VW",
            "Obsidian": "Obs",
            "Remotely Save": "RS",
        }
        
        # Patterns to remove (noise)
        self._noise_patterns = [
            r"^\s*[-*]\s*$",  # Empty list items
            r"^\s*\n",  # Empty lines
            r"\s{2,}",  # Multiple spaces
        ]
        
        self._initialized = True
        logger.info("MemoryCompressor initialized")
    
    def compress(self, text: str, level: str = "medium") -> str:
        """Compress text based on level."""
        if not text:
            return text
        
        if level == "light":
            return self._light_compress(text)
        elif level == "medium":
            return self._medium_compress(text)
        elif level == "heavy":
            return self._heavy_compress(text)
        else:
            return text
    
    def _light_compress(self, text: str) -> str:
        """Light compression: remove noise only."""
        result = text
        for pattern in self._noise_patterns:
            result = re.sub(pattern, "", result, flags=re.MULTILINE)
        return result.strip()
    
    def _medium_compress(self, text: str) -> str:
        """Medium compression: abbreviations + noise removal."""
        result = self._light_compress(text)
        
        # Apply abbreviations (case-insensitive)
        for full, abbr in self._abbreviations.items():
            result = re.sub(re.escape(full), abbr, result, flags=re.IGNORECASE)
        
        return result
    
    def _heavy_compress(self, text: str) -> str:
        """Heavy compression: aggressive optimization."""
        result = self._medium_compress(text)
        
        # Remove redundant phrases
        redundant = [
            "I think",
            "I believe",
            "In my opinion",
            "It seems",
            "Maybe",
            "Perhaps",
            "Actually",
            "Basically",
            "Just",
            "Really",
            "Very",
            "Quite",
        ]
        for phrase in redundant:
            result = re.sub(rf"\b{phrase}\b", "", result, flags=re.IGNORECASE)
        
        # Compress dates
        result = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", result)
        
        return result.strip()
    
    def deduplicate(self, memories: List[str]) -> List[str]:
        """Remove duplicate memories."""
        seen_hashes = set()
        unique = []
        
        for mem in memories:
            # Normalize for comparison
            normalized = re.sub(r"\s+", " ", mem.strip().lower())
            mem_hash = hashlib.md5(normalized.encode()).hexdigest()
            
            if mem_hash not in seen_hashes:
                seen_hashes.add(mem_hash)
                unique.append(mem)
        
        removed = len(memories) - len(unique)
        if removed > 0:
            logger.info(f"Deduplicated: removed {removed} memories")
        
        return unique
    
    def summarize(self, text: str, max_length: int = 200) -> str:
        """Create a summary of the text."""
        if len(text) <= max_length:
            return text
        
        # Simple truncation with ellipsis
        return text[:max_length - 3] + "..."


# Global instance
memory_compressor = MemoryCompressor()


# === 实体消歧 (Entity Disambiguation) ===
# 来源: GBrain零LLM方法
# 用于: SVO记忆去重，合并别名实体

ALIAS_MAP = {
    "ulysses": ["jasper", "user", "用户"],
    "hecate": ["主意识", "herself", "赫卡忒"],
    "chicago": ["chicago server", "arm server", "芝加哥"],
    "metis": ["计划专家", "梅蒂斯"],
    "persephone": ["双向验证", "珀尔塞福涅", "forseti", "pandora"],
    "socrates": ["审计专家", "苏格拉底"],
    "ploutos": ["投资专家", "普洛托斯"],
    "enki": ["执行专家", "恩基"],
}

def disambiguate_entity(entity: str) -> str:
    """将别名实体规范化为标准名。"""
    lower = entity.lower().strip()
    for canonical, aliases in ALIAS_MAP.items():
        if lower == canonical or lower in aliases:
            return canonical
    return entity

def deduplicate_svo_entries(entries: list) -> list:
    """去重SVO条目: 规范化实体 + 合并重复。"""
    seen = {}
    for entry in entries:
        subj = disambiguate_entity(entry.get("subject", ""))
        obj = disambiguate_entity(entry.get("object", ""))
        key = f"{subj}|{entry.get('verb', '')}|{obj}"
        if key not in seen:
            seen[key] = entry
        else:
            # 合并: 保留更长的描述
            if len(entry.get("context", "")) > len(seen[key].get("context", "")):
                seen[key] = entry
    return list(seen.values())
