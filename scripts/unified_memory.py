"""
Unified Memory Hub — Hub/Spoke Architecture

Hub = current topic session (L1)
Spokes = L2-L6 (fallback layers)

Recall: L1 → L2 → L3 → L4 → L5 → L6 (逐层 fallback)
Overflow: L1 full → extract key facts to L2, trim L1
"""

import hashlib
from datetime import datetime, timezone
import json
import logging
import os
import re
import subprocess
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MEMORIES_DIR = Path(os.path.expanduser("~/.hermes/memories"))
L1_DIR = MEMORIES_DIR / "topics" / "sessions"
L3_FILE = MEMORIES_DIR / "MEMORY.md"
L4_DB = MEMORIES_DIR / "state.db"
L5_DIR = MEMORIES_DIR / "wiki"

SEMBLE_BIN = "/usr/local/bin/semblectl"
QDRANT_URL = os.environ.get("FUSION_QDRANT_URL", "")
QDRANT_KEY = os.environ.get("FUSION_QDRANT_API_KEY", "")
QDRANT_COLLECTION = "hermes_fusion"
EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "qwen3-embedding:0.6b"

L1_LIMIT = 3072


def get_session_hash(session_key: str) -> str:
    return hashlib.sha256(session_key.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Recall: unified search across all layers
# ---------------------------------------------------------------------------

def unified_recall(query: str, session_key: str = "", limit: int = 5) -> List[Dict[str, Any]]:
    """Search all layers in order: L1 → L2 → L3 → L4 → L5.
    Returns results with source labels. Stops when enough results found.
    """
    results = []
    seen_texts = set()

    # L1: Topic Memory (semblectl)
    for r in search_l1(query, session_key):
        txt = r["text"][:100]
        if txt not in seen_texts:
            seen_texts.add(txt)
            results.append({"layer": "L1", "score": 1.0, **r})
    if len(results) >= limit:
        return results[:limit]

    # L3: MEMORY.md (semblectl)
    for r in search_l3(query):
        txt = r["text"][:100]
        if txt not in seen_texts:
            seen_texts.add(txt)
            results.append({"layer": "L3", "score": 0.8, **r})
    if len(results) >= limit:
        return results[:limit]

    # L4: Session DB (FTS5)
    for r in search_l4(query):
        txt = r["text"][:100]
        if txt not in seen_texts:
            seen_texts.add(txt)
            results.append({"layer": "L4", "score": 0.6, **r})
    if len(results) >= limit:
        return results[:limit]

    # L5: Wiki (semblectl)
    for r in search_l5(query):
        txt = r["text"][:100]
        if txt not in seen_texts:
            seen_texts.add(txt)
            results.append({"layer": "L5", "score": 0.5, **r})

    return results[:limit]


# ---------------------------------------------------------------------------
# L1: Topic Memory — semblectl search
# ---------------------------------------------------------------------------

def search_l1(query: str, session_key: str = "", limit: int = 3) -> List[Dict[str, Any]]:
    """Search L1 topic memory using semblectl."""
    if not L1_DIR.exists():
        return []

    key_hash = get_session_hash(session_key) if session_key else ""

    # Search all L1 files, prioritize current session
    try:
        proc = subprocess.run(
            [SEMBLE_BIN, "search", str(L1_DIR), query, "--format", "json", "-k", str(limit * 2)],
            capture_output=True, text=True, timeout=10
        )
        if proc.returncode == 0 and proc.stdout.strip():
            raw = json.loads(proc.stdout)
            results = []
            for item in (raw if isinstance(raw, list) else []):
                path = item.get("path", "")
                snippet = item.get("snippet", item.get("text", ""))
                score = item.get("score", 0.5)
                fname = os.path.basename(path)
                is_current = key_hash and fname.startswith(key_hash)
                if is_current:
                    score += 0.3
                results.append({"text": snippet, "score": score, "source": f"L1/{fname}"})
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]
    except Exception as e:
        logger.debug("L1 semblectl failed: %s", e)

    # Fallback: grep
    return _grep_dir(L1_DIR, query, limit)


# ---------------------------------------------------------------------------
# L3: MEMORY.md — semblectl
# ---------------------------------------------------------------------------

def search_l3(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    if not L3_FILE.exists():
        return []
    try:
        proc = subprocess.run(
            [SEMBLE_BIN, "search", str(L3_FILE), query, "--format", "json", "-k", str(limit)],
            capture_output=True, text=True, timeout=10
        )
        if proc.returncode == 0 and proc.stdout.strip():
            raw = json.loads(proc.stdout)
            return [{"text": i.get("snippet", ""), "score": i.get("score", 0.5), "source": "L3/MEMORY.md"}
                    for i in (raw if isinstance(raw, list) else [])[:limit]]
    except Exception as e:
        logger.debug("L3 semblectl failed: %s", e)
    return _grep_file(L3_FILE, query, limit)


# ---------------------------------------------------------------------------
# L4: Session DB — FTS5
# ---------------------------------------------------------------------------

def search_l4(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    if not L4_DB.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{L4_DB}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT content, session_id FROM messages_fts WHERE messages_fts MATCH ? LIMIT ?",
            (query, limit)
        ).fetchall()
        conn.close()
        return [{"text": r[0][:300], "score": 0.5, "source": f"L4/{r[1][:20]}"} for r in rows]
    except Exception as e:
        logger.debug("L4 FTS5 failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# L5: Wiki — semblectl
# ---------------------------------------------------------------------------

def search_l5(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    if not L5_DIR.exists():
        return []
    try:
        proc = subprocess.run(
            [SEMBLE_BIN, "search", str(L5_DIR), query, "--format", "json", "-k", str(limit)],
            capture_output=True, text=True, timeout=10
        )
        if proc.returncode == 0 and proc.stdout.strip():
            raw = json.loads(proc.stdout)
            return [{"text": i.get("snippet", ""), "score": i.get("score", 0.5), "source": f"L5/{os.path.basename(i.get('path', ''))}"}
                    for i in (raw if isinstance(raw, list) else [])[:limit]]
    except Exception as e:
        logger.debug("L5 semblectl failed: %s", e)
    return _grep_dir(L5_DIR, query, limit)


# ---------------------------------------------------------------------------
# Overflow: L1 full → extract key facts → push to L2 (Qdrant)
# ---------------------------------------------------------------------------

def check_and_overflow(session_key: str) -> Optional[str]:
    """Check if L1 is over limit. If so, extract key facts to L2, trim L1."""
    if not session_key:
        return None

    hash_name = get_session_hash(session_key)
    l1_file = L1_DIR / f"{hash_name}.md"
    if not l1_file.exists():
        return None

    content = l1_file.read_text(encoding="utf-8")
    if len(content) <= L1_LIMIT:
        return None

    # Extract key facts (lines with § separator, or ## headers)
    lines = content.split("\n")
    key_facts = []
    keep_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") or (stripped and not stripped.startswith("---") and not stripped.startswith("session_")):
            # Heuristic: lines with important keywords stay, others can be trimmed
            if any(kw in stripped for kw in ["✅", "❌", "⚠️", "关键", "重要", "修复", "配置", "密码", "token", "API", "http"]):
                key_facts.append(stripped)
            else:
                keep_lines.append(line)
        else:
            keep_lines.append(line)

    if not key_facts:
        # No key facts to extract, just trim oldest entries
        trimmed = content[len(content) - L1_LIMIT:]
        # Find next § boundary
        idx = trimmed.find("\n§\n")
        if idx > 0:
            trimmed = trimmed[idx + 3:]
        l1_file.write_text(trimmed, encoding="utf-8")
        return f"L1 trimmed from {len(content)} to {len(trimmed)} chars"

    # Push key facts to L2 (Qdrant)
    facts_text = "\n".join(key_facts)
    pushed = _push_to_qdrant(facts_text, session_key)

    # Trim L1: keep only keep_lines
    trimmed = "\n".join(keep_lines)
    if len(trimmed) > L1_LIMIT:
        trimmed = trimmed[len(trimmed) - L1_LIMIT:]
    l1_file.write_text(trimmed, encoding="utf-8")

    return f"L1 overflow: extracted {len(key_facts)} facts to L2, trimmed to {len(trimmed)} chars"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _push_to_qdrant(text: str, session_key: str) -> bool:
    """Push text to Qdrant Cloud (L2)."""
    try:
        # Get embedding
        data = json.dumps({"model": EMBED_MODEL, "input": text[:2000]}).encode()
        req = urllib.request.Request(EMBED_URL, data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=30)
        vec = json.loads(resp.read())["embeddings"][0]

        # Push to Qdrant
        import uuid
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY, timeout=30)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"L1_overflow:{session_key}:{len(text)}"))
        # Extract topic_id from session_key
        topic_id = ""
        if session_key and ":" in session_key:
            parts = session_key.split(":")
            if len(parts) >= 5:
                topic_id = parts[-1]  # Last part is thread_id
        
        client.upsert(collection_name=QDRANT_COLLECTION, points=[
            PointStruct(id=point_id, vector=vec, payload={
                "text": text,
                "source": "L1_overflow",
                "session_key": session_key,
                "topic_id": topic_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "L2",
            })
        ])
        return True
    except Exception as e:
        logger.warning("Qdrant push failed: %s", e)
        return False


def _grep_file(path: Path, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["grep", "-i", "-m", str(limit), query, str(path)],
            capture_output=True, text=True, timeout=5
        )
        if proc.returncode == 0:
            return [{"text": l.strip()[:300], "score": 0.3, "source": f"grep/{path.name}"}
                    for l in proc.stdout.strip().split("\n") if l.strip()][:limit]
    except:
        pass
    return []


def _grep_dir(dirpath: Path, query: str, limit: int) -> List[Dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["grep", "-r", "-i", "-m", str(limit), "--include=*.md", query, str(dirpath)],
            capture_output=True, text=True, timeout=5
        )
        if proc.returncode == 0:
            results = []
            for line in proc.stdout.strip().split("\n")[:limit]:
                if ":" in line:
                    parts = line.split(":", 1)
                    results.append({"text": parts[1].strip()[:300], "score": 0.3, "source": f"grep/{os.path.basename(parts[0])}"})
            return results
    except:
        pass
    return []
