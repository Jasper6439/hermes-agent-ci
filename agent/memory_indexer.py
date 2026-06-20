# Source: AutoGPT
# Upstream: https://github.com/Significant-Gravitas/AutoGPT
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Memory Indexer — 统一记忆索引

使用 Semble 索引 L3/L5 记忆层，L4 使用 FTS5 搜索。

Usage:
    from agent.memory_indexer import MemoryIndexer
    
    indexer = MemoryIndexer()
    results = indexer.search("部署前检查", limit=5)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    """记忆召回结果。"""
    layer: str              # L3, L5
    content: str            # 精确片段
    source: str             # 来源文件/ID
    score: float            # 相关性分数
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryIndexer:
    """统一记忆索引器（L3/L5 使用 Semble）。"""
    
    _instance: Optional[MemoryIndexer] = None
    
    def __new__(cls) -> MemoryIndexer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._semble_cli = self._find_semble_cli()
        self._index_paths = {
            "L3": Path.home() / ".hermes" / "memories",  # 包含 MEMORY.md
            "L5": Path.home() / ".hermes" / "memories",  # 包含 ancestral_memory.md
        }
        self._initialized = True
        
        logger.info("MemoryIndexer initialized")
    
    def _find_semble_cli(self) -> Optional[str]:
        """找到 Semble CLI。"""
        # 使用包装脚本避免 shebang 问题
        wrapper = Path.home() / "hermes" / ".venv" / "bin" / "semble-wrapper"
        if wrapper.exists():
            return str(wrapper)
        
        import shutil
        for candidate in [
            shutil.which("semble"),
            os.path.expanduser("~/hermes/.venv/bin/semble"),
        ]:
            if candidate and os.path.isfile(candidate):
                return candidate
        return None
    
    def _run_semble_search(self, query: str, path: str, top_k: int = 5) -> List[Dict]:
        """运行 Semble 搜索。"""
        if not self._semble_cli:
            logger.warning("Semble CLI not found")
            return []
        
        # 确保路径是目录
        if not os.path.isdir(path):
            logger.warning(f"Path is not a directory: {path}")
            return []
        
        cmd = [self._semble_cli, "search", query, path, "--top-k", str(top_k), "--include-text-files"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                logger.warning(f"Semble search failed: {result.stderr[:100]}")
                return []
            
            data = json.loads(result.stdout.strip())
            return data.get("results", [])
            
        except Exception as e:
            logger.warning(f"Semble search error: {e}")
            return []
    
    def search_layer(self, query: str, layer: str, limit: int = 3) -> List[MemoryResult]:
        """搜索单个记忆层。"""
        path = self._index_paths.get(layer)
        if not path or not path.exists():
            return []
        
        results = self._run_semble_search(query, str(path), top_k=limit)
        
        memories = []
        for r in results:
            chunk = r.get("chunk", {})
            memories.append(MemoryResult(
                layer=layer,
                content=chunk.get("content", ""),
                source=chunk.get("file_path", chunk.get("path", "")),
                score=r.get("score", 0),
                metadata={
                    "start_line": chunk.get("start_line", 0),
                    "end_line": chunk.get("end_line", 0),
                },
            ))
        
        return memories
    
    def search_all(self, query: str, limit: int = 5) -> List[MemoryResult]:
        """跨层搜索所有记忆。"""
        all_results = []
        
        # 搜索 L3/L5
        for layer in ["L3", "L5"]:
            results = self.search_layer(query, layer, limit=limit)
            all_results.extend(results)
        
        # 按分数排序
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        # 去重（基于内容相似度）
        unique_results = []
        seen_contents = set()
        
        for r in all_results:
            # 简单去重：内容前100字符
            content_key = r.content[:100].strip()
            if content_key not in seen_contents:
                seen_contents.add(content_key)
                unique_results.append(r)
        
        return unique_results[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息。"""
        stats = {}
        for layer, path in self._index_paths.items():
            if path.exists():
                if path.is_file():
                    stats[layer] = f"File: {path.stat().st_size} bytes"
                elif path.is_dir():
                    file_count = len(list(path.glob("*")))
                    stats[layer] = f"Dir: {file_count} files"
            else:
                stats[layer] = "Not found"
        return stats


# 全局实例
memory_indexer = MemoryIndexer()
