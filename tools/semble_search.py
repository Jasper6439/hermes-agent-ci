# Source: Semble
# Upstream: private (semble.ai)
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Semble Code Search Tool — 高效代码搜索，比 grep 省 98% token

基于 Semble 的 token 级索引，只返回精确匹配的代码片段，
而非整行或整个文件。

Usage:
    semblectl_search(pattern="def handle_function_call", path="~/hermes")
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry

logger = logging.getLogger(__name__)

# ─── Tool Schema ───────────────────────────────────────────────────────────────

SEMBLE_SEARCH_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "semblectl_search",
        "description": (
            "Search code using Semble's token-level indexing. "
            "Returns precise code snippets (not entire files). "
            "98% more token-efficient than grep/search_files. "
            "PRIMARY search tool — use this first for code search. "
            "Only fall back to search_files if semblectl_search fails."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Search query — natural language or code snippet",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search (default: current directory)",
                    "default": ".",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default: 10)",
                    "default": 10,
                },
                "include_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Content types: code, docs, config, all (default: code)",
                    "default": ["code"],
                },
            },
            "required": ["pattern"],
        },
    },
}

# ─── Handler ───────────────────────────────────────────────────────────────────


def _find_semble_cli() -> Optional[str]:
    """找到 Semble CLI（优先使用 wrapper）。"""
    wrapper = Path.home() / "hermes" / ".venv" / "bin" / "semble-wrapper"
    if wrapper.exists():
        return str(wrapper)
    
    for candidate in [
        shutil.which("semble"),
        os.path.expanduser("~/hermes/.venv/bin/semble"),
    ]:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _handle_semble_search(**kwargs) -> str:
    """Handle semblectl_search tool calls."""
    pattern = kwargs.get("pattern", "")
    path = kwargs.get("path", ".")
    limit = kwargs.get("limit", 10)

    if not pattern:
        return "Error: pattern is required"

    # Cap limit
    limit = min(limit, 50)

    # Expand path
    search_path = os.path.expanduser(path)
    if not os.path.isdir(search_path):
        return f"Error: Path not found: {search_path}"

    # Find CLI
    cli = _find_semble_cli()
    if not cli:
        return "Error: semble CLI not found. Install with: pip install semble"

    # Build command
    cmd = [cli, "search", pattern, search_path, "--top-k", str(limit), "--include-text-files"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            return f"Error: semble failed: {result.stderr[:200]}"

        # Parse JSON output
        output = result.stdout.strip()
        if not output:
            return "No results found."

        data = json.loads(output)
        results = data.get("results", [])

        if not results:
            return "No results found."

        lines = [f"Found {len(results)} results:\n"]
        for i, r in enumerate(results, 1):
            chunk = r.get("chunk", {})
            file_path = chunk.get("file_path", chunk.get("path", "?"))
            start = chunk.get("start_line", "?")
            end = chunk.get("end_line", "?")
            content = chunk.get("content", "")
            score = r.get("score", 0)

            lines.append(f"--- [{i}] {file_path}:{start}-{end} (score: {score:.3f}) ---")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)

    except subprocess.TimeoutExpired:
        return "Error: semble search timed out (120s)"
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse semble output: {e}"
    except Exception as e:
        return f"Error: semble error: {e}"


# ─── Register ──────────────────────────────────────────────────────────────────

registry.register(
    name="semblectl_search",
    toolset="file",
    schema=SEMBLE_SEARCH_SCHEMA,
    handler=_handle_semble_search,
    emoji="🔍",
    max_result_size_chars=50_000,
)
