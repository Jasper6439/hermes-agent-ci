#!/usr/bin/env python3
"""
Topic Memory Store — Per-Session Hot Cache (Phase 0)

Per-session memory that holds facts relevant to the current conversation
topic. Each session gets its own file at ~/.hermes/memories/topics/{session_id}.md.

Same §-delimited format as MEMORY.md. When >90% full, evicts lowest-priority
entries to the collective MEMORY.md via _migrate_entry_to_fusion().

This is behind the `memory.topic_memory_enabled` feature flag (default: false).
"""

import json
import logging
import sys as _sys
from pathlib import Path
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / ".hermes" / "scripts"))

# Dual-write: route important entries to L2 (turbovec) simultaneously
try:
    from memory_turbovec import store as _l2_store
    from memory_recall import route_memory as _route_memory
    _DUAL_WRITE_ENABLED = True
except ImportError:
    _DUAL_WRITE_ENABLED = False
import os
import re as _re
import tempfile
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from tools.memory_tool import (
    ENTRY_DELIMITER,
    MemoryStore,
    _drift_error,
    _scan_memory_content,
    get_memory_dir,
)

try:
    import fcntl
except ImportError:
    fcntl = None
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

logger = logging.getLogger(__name__)

try:
    from hermes_constants import get_hermes_home
except ImportError:
    pass

try:
    from utils import atomic_replace
except ImportError:
    def atomic_replace(src: str, dst: Path) -> None:
        os.replace(src, str(dst))


def _log_eviction_failure(failure_type: str, details: str, session_key: str):
    """Log eviction failures to dedicated file for monitoring."""
    log_dir = Path.home() / ".hermes" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "eviction_failures.log"
    
    timestamp = datetime.now().isoformat()
    entry = f"[{timestamp}] [{failure_type}] session={session_key[:30]}... {details}\n"
    
    try:
        with open(log_file, "a") as f:
            f.write(entry)
    except Exception:
        pass  # Don't fail the main operation if logging fails


class TopicMemoryStore:
    """Per-session memory store. Each session has its own file.

    Storage: ~/.hermes/memories/topics/{hash}.md
    Uses SHA256 of session_key for stable filenames across session resets.
    Same §-delimited format as MEMORY.md.
    When >90% full, evicts lowest-priority entries to collective MEMORY.md.
    """

    def __init__(self, session_key: str, char_limit: int = 3072):
        if not session_key or not session_key.strip():
            raise ValueError("session_key must be a non-empty string")
        self.session_key = session_key
        self._filename = self._key_to_filename(session_key)
        self.char_limit = char_limit
        self.entries: List[str] = []
        self._system_prompt_snapshot: str = ""

    @staticmethod
    def _key_to_filename(session_key: str) -> str:
        """Convert session_key to stable filename using SHA256.

        session_key = "agent:main:telegram:group:-1003951319454:6"
        filename    = "a3f7b2c91e4d"  (SHA256[:12])
        """
        import hashlib
        return hashlib.sha256(session_key.encode()).hexdigest()[:12]

    @property
    def _path(self) -> Path:
        """Path: ~/.hermes/memories/topics/sessions/{hash}.md"""
        return get_memory_dir() / "topics" / "sessions" / f"{self._filename}.md"

    def load_from_disk(self):
        """Load entries from topic-specific file, capture system prompt snapshot.

        Same frozen-snapshot pattern as MemoryStore — mid-session writes
        do NOT change the system prompt (prefix cache preservation).
        """
        topics_dir = self._path.parent
        topics_dir.mkdir(parents=True, exist_ok=True)

        self.entries = self._read_file(self._path)
        self.entries = list(dict.fromkeys(self.entries))  # deduplicate

        # Sanitize for system prompt snapshot (threat scanning)
        from tools.threat_patterns import scan_for_threats
        sanitized: List[str] = []
        for entry in self.entries:
            if not entry or entry.startswith("[BLOCKED:"):
                sanitized.append(entry)
                continue
            findings = scan_for_threats(entry, scope="strict")
            if findings:
                logger.warning(
                    "Topic memory entry blocked at load time: %s",
                    ", ".join(findings),
                )
                sanitized.append(
                    f"[BLOCKED: Topic entry contained threat pattern(s): "
                    f"{', '.join(findings)}. Removed from system prompt; "
                    f"use memory(action=read) to inspect and memory(action=remove) "
                    f"to delete the original.]"
                )
            else:
                sanitized.append(entry)

        self._system_prompt_snapshot = self._render_block(sanitized)

    def save_to_disk(self):
        """Persist entries to topic-specific file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._write_file(self._path, self.entries)
        self._system_prompt_snapshot = self._render_block(self.entries)

    def add(self, content: str) -> Dict[str, Any]:
        """Add a new entry. If at capacity, evict to collective MEMORY.md."""
        content = content.strip()
        if not content:
            return {"success": False, "error": "Content cannot be empty."}

        # Fix #1.2: Reject § character (used as entry delimiter)
        if "§" in content:
            return {"success": False, "error": "Content cannot contain § character (entry delimiter)."}

        # Fix: Front-end length guard — reject absurdly large content before
        # building any intermediate strings (prevents O(n²) join on 1MB+ input)
        if len(content) > self.char_limit:
            return {
                "success": False,
                "error": (
                    f"Content exceeds topic memory capacity ({self.char_limit:,} chars). "
                    f"Current size: {len(content):,} chars."
                ),
            }

        scan_error = _scan_memory_content(content)
        if scan_error:
            return {"success": False, "error": scan_error}

        with self._file_lock(self._path):
            # Reload under lock to stay consistent
            fresh = self._read_file(self._path)
            fresh = list(dict.fromkeys(fresh))
            self.entries = fresh

            # Reject exact duplicates
            if content in self.entries:
                return self._success_response("Entry already exists (no duplicate added).")

            new_entries = self.entries + [content]
            new_total = len(ENTRY_DELIMITER.join(new_entries))

            if new_total > self.char_limit:
                evicted = self._evict_to_collective(self.entries, len(content))
                if evicted:
                    self.entries = self._read_file(self._path)
                    self.entries = list(dict.fromkeys(self.entries))
                    new_entries = self.entries + [content]
                    new_total = len(ENTRY_DELIMITER.join(new_entries))
                    if new_total <= self.char_limit:
                        self.entries.append(content)
                        self.save_to_disk()
                        return self._success_response(
                            f"Entry added. ({evicted} entries evicted to collective MEMORY.md.)"
                        )

                # Soft eviction: if all external tiers unavailable, remove
                # lowest-priority non-iron-law entry from topic to make room
                soft_evicted = self._soft_evict(len(content))
                if soft_evicted:
                    self.entries = self._read_file(self._path)
                    self.entries = list(dict.fromkeys(self.entries))
                    new_entries = self.entries + [content]
                    new_total = len(ENTRY_DELIMITER.join(new_entries))
                    if new_total <= self.char_limit:
                        self.entries.append(content)
                        self.save_to_disk()
                        return self._success_response(
                            f"Entry added. ({soft_evicted} low-priority entries soft-evicted to make room.)"
                        )

                current = self._char_count()
                return {
                    "success": False,
                    "error": (
                        f"Topic memory at {current:,}/{self.char_limit:,} chars. "
                        f"Adding this entry ({len(content)} chars) would exceed the limit. "
                        f"Replace or remove existing entries first."
                    ),
                    "current_entries": self.entries,
                    "usage": f"{current:,}/{self.char_limit:,}",
                }

            self.entries.append(content)
            self.save_to_disk()

        # Dual-write: route important entries to L2 (turbovec) simultaneously
        if _DUAL_WRITE_ENABLED:
            try:
                layer = _route_memory(content)
                if layer in ["L2", "L3", "L4", "L5"]:
                    _l2_store(content, topic_id=self.session_key, layer=layer, source="dual_write")
            except Exception:
                pass

        return self._success_response("Entry added.")

    def replace(self, old_text: str, new_content: str) -> Dict[str, Any]:
        """Find entry containing old_text substring, replace with new_content."""
        old_text = old_text.strip()
        new_content = new_content.strip()
        if not old_text:
            return {"success": False, "error": "old_text cannot be empty."}
        if not new_content:
            return {"success": False, "error": "new_content cannot be empty. Use 'remove' to delete entries."}

        # Fix: Front-end length guard for replace too
        if len(new_content) > self.char_limit:
            return {
                "success": False,
                "error": (
                    f"Replacement content exceeds topic memory capacity ({self.char_limit:,} chars). "
                    f"Current size: {len(new_content):,} chars."
                ),
            }

        scan_error = _scan_memory_content(new_content)
        if scan_error:
            return {"success": False, "error": scan_error}

        with self._file_lock(self._path):
            fresh = self._read_file(self._path)
            fresh = list(dict.fromkeys(fresh))
            self.entries = fresh

            matches = [(i, e) for i, e in enumerate(self.entries) if old_text in e]
            if not matches:
                return {"success": False, "error": f"No entry matched '{old_text}'."}

            if len(matches) > 1:
                unique_texts = {e for _, e in matches}
                if len(unique_texts) > 1:
                    previews = [e[:80] + ("..." if len(e) > 80 else "") for _, e in matches]
                    return {
                        "success": False,
                        "error": f"Multiple entries matched '{old_text}'. Be more specific.",
                        "matches": previews,
                    }

            idx = matches[0][0]
            test_entries = self.entries.copy()
            test_entries[idx] = new_content
            new_total = len(ENTRY_DELIMITER.join(test_entries))

            if new_total > self.char_limit:
                return {
                    "success": False,
                    "error": (
                        f"Replacement would put topic memory at {new_total:,}/{self.char_limit:,} chars. "
                        f"Shorten the new content or remove other entries first."
                    ),
                }

            self.entries[idx] = new_content
            self.save_to_disk()

        return self._success_response("Entry replaced.")

    def remove(self, old_text: str) -> Dict[str, Any]:
        """Remove the entry containing old_text substring."""
        old_text = old_text.strip()
        if not old_text:
            return {"success": False, "error": "old_text cannot be empty."}

        with self._file_lock(self._path):
            fresh = self._read_file(self._path)
            fresh = list(dict.fromkeys(fresh))
            self.entries = fresh

            matches = [(i, e) for i, e in enumerate(self.entries) if old_text in e]
            if not matches:
                return {"success": False, "error": f"No entry matched '{old_text}'."}

            if len(matches) > 1:
                unique_texts = {e for _, e in matches}
                if len(unique_texts) > 1:
                    previews = [e[:80] + ("..." if len(e) > 80 else "") for _, e in matches]
                    return {
                        "success": False,
                        "error": f"Multiple entries matched '{old_text}'. Be more specific.",
                        "matches": previews,
                    }

            idx = matches[0][0]
            self.entries.pop(idx)
            self.save_to_disk()

        return self._success_response("Entry removed.")

    def format_for_system_prompt(self) -> Optional[str]:
        """Return frozen snapshot for system prompt injection.

        Returns None if the snapshot is empty.
        """
        return self._system_prompt_snapshot if self._system_prompt_snapshot else None

    def archive(self):
        """Archive topic memory at session end (keep for /resume)."""
        if not self._path.exists():
            return
        archive_dir = self._path.parent.parent / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{self._filename}.md"
        try:
            # Copy to archive (atomic)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(archive_dir), suffix=".tmp", prefix=".mem_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(self._path.read_text(encoding="utf-8"))
                    f.flush()
                    os.fsync(f.fileno())
                atomic_replace(tmp_path, archive_path)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            logger.info("Topic memory archived for session %s", self.session_key)
        except (OSError, IOError) as e:
            logger.warning("Failed to archive topic memory for session %s: %s", self.session_key, e)
    # -- Internal helpers --

    def _char_count(self) -> int:
        if not self.entries:
            return 0
        return len(ENTRY_DELIMITER.join(self.entries))

    def _evict_to_collective(self, entries: List[str], need_chars: int) -> int:
        """Move lowest-priority entries to collective MEMORY.md when overflowing.

        Returns the number of entries evicted.
        """
        # Score each entry
        scored: list[tuple[float, int, str]] = []
        for i, entry in enumerate(entries):
            score = 0.0
            # ⚠️ entries are iron laws — never evict
            if "⚠️" in entry:
                score += 100
            # Short dense entries are high-value
            if len(entry) < 80:
                score += 15
            elif len(entry) > 300:
                score -= 10
            # Earlier entries placed first = more important
            score += (len(entries) - i) / len(entries) * 5
            # Date-heavy entries may be stale
            if len(_re.findall(r"\d{4}-\d{2}", entry)) >= 3:
                score -= 5
            scored.append((score, i, entry))

        scored.sort(key=lambda x: x[0])

        remaining = list(scored)
        evicted = 0
        target_bytes = int(self.char_limit * 0.75)

        # Track failed entries to prevent infinite loop
        failed_indices: set[int] = set()

        while remaining:
            current_size = len(ENTRY_DELIMITER.join(e for _, _, e in remaining))
            if current_size <= target_bytes and current_size + need_chars + 10 <= self.char_limit:
                break

            # Peek at next entry WITHOUT removing it
            score, idx, entry = remaining[0]
            if score >= 100:
                # Iron-law entries are never evicted; if we've reached them,
                # all evictable entries have been tried. Break to avoid
                # either infinite loop or data loss.
                break

            # Now safe to remove
            remaining.pop(0)

            # Evict to collective MEMORY.md
            try:
                from tools.memory_tool import MemoryStore
                collective = MemoryStore()
                collective.load_from_disk()
                result = collective.add("memory", entry)
                if result.get("success"):
                    evicted += 1
                    logger.info("Evicted topic entry to collective MEMORY.md: %s...", entry[:60])
                else:
                    # Collective full — keep entry in topic (don't lose data)
                    remaining.append((score, idx, entry))
                    failed_indices.add(idx)
                    logger.warning("Collective full, keeping in topic: %s", entry[:60])
                    _log_eviction_failure("collective_full", entry[:60], self.session_key)
            except Exception as e:
                # Service unavailable — keep entry in topic (don't lose data)
                remaining.append((score, idx, entry))
                failed_indices.add(idx)
                logger.warning("Failed to evict (keeping in topic): %s", e)
                _log_eviction_failure("service_unavailable", str(e), self.session_key)

            # Safety valve: if all remaining evictable entries have failed, stop
            evictable_left = [(s, i, e) for s, i, e in remaining if s < 100]
            if evictable_left and all(i in failed_indices for _, i, _ in evictable_left):
                logger.warning("All evictable entries failed, stopping eviction loop")
                break

        if not evicted:
            return 0

        # Rebuild entries in original order (sort once, not in loop)
        remaining.sort(key=lambda x: x[1])
        self.entries = [e for _, _, e in remaining]
        self.save_to_disk()
        return evicted

    def _soft_evict(self, need_chars: int) -> int:
        """Archive lowest-priority entries when all external tiers are unavailable.

        Philosophy: Every memory is ancestral memory. Never delete — archive to
        local disk + 139 cloud. Entries can be restored later or become knowledge.

        Returns number of entries archived and removed from active memory.
        """
        if not self.entries:
            return 0

        # Score entries same as _evict_to_collective
        import re as _re
        scored: list[tuple[float, int, str]] = []
        for i, entry in enumerate(self.entries):
            score = 0.0
            if "⚠️" in entry:
                score += 100  # iron law — never evict
            if len(entry) < 80:
                score += 15
            elif len(entry) > 300:
                score -= 10
            score += (len(self.entries) - i) / len(self.entries) * 5
            if len(_re.findall(r"\d{4}-\d{2}", entry)) >= 3:
                score -= 5
            scored.append((score, i, entry))

        scored.sort(key=lambda x: x[0])  # lowest score = least valuable

        archived = 0
        for score, idx, entry in scored:
            if score >= 100:
                break  # Don't touch iron-law entries
            # Archive before removing
            try:
                import sys
                _scripts_dir = os.path.expanduser("~/.hermes/scripts")
                if _scripts_dir not in sys.path:
                    sys.path.insert(0, _scripts_dir)
                from memory_archiver import archive_entry
                archive_entry(
                    content=entry,
                    source="topic",
                    reason="soft_evict",
                    session_key=getattr(self, 'session_key', ''),
                    score=score,
                )
            except Exception as e:
                logger.error("Archive failed, keeping entry: %s", e)
                continue  # Don't remove if archive fails

            # Remove from active memory
            remaining_entries = [e for j, e in enumerate(self.entries) if j != idx]
            current_size = len(ENTRY_DELIMITER.join(remaining_entries))
            self.entries = remaining_entries
            archived += 1
            logger.info("Archived+removed topic entry (%d chars, score=%.1f): %s...",
                       len(entry), score, entry[:60])
            if current_size + need_chars + 10 <= self.char_limit:
                break

        if archived:
            self.save_to_disk()
        return archived

    def _success_response(self, message: str = None) -> Dict[str, Any]:
        current = self._char_count()
        pct = min(100, int((current / self.char_limit) * 100)) if self.char_limit > 0 else 0

        # Proactive eviction: if >90% full
        if pct > 90:
            need_chars = current - int(self.char_limit * 0.75)
            if need_chars > 0:
                evicted = self._evict_to_collective(self.entries, need_chars)
                if evicted:
                    current = self._char_count()
                    pct = min(100, int((current / self.char_limit) * 100)) if self.char_limit > 0 else 0

        resp = {
            "success": True,
            "target": "topic",
            "entries": self.entries,
            "usage": f"{pct}% — {current:,}/{self.char_limit:,} chars",
            "entry_count": len(self.entries),
        }
        if message:
            resp["message"] = message
        return resp

    def _render_block(self, entries: List[str]) -> str:
        """Render a system prompt block with header and usage indicator."""
        if not entries:
            return ""
        content = ENTRY_DELIMITER.join(entries)
        current = len(content)
        pct = min(100, int((current / self.char_limit) * 100)) if self.char_limit > 0 else 0
        header = f"TOPIC MEMORY (this session) [{pct}% — {current:,}/{self.char_limit:,} chars]"
        separator = "═" * 46
        return f"{separator}\n{header}\n{separator}\n{content}"

    @staticmethod
    def _file_lock(path: Path):
        """Acquire an exclusive file lock for read-modify-write safety."""
        from contextlib import contextmanager
        lock_path = path.with_suffix(path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        if fcntl is None and msvcrt is None:
            # Fallback: use threading.Lock instead of no-op
            # This at least protects against concurrent threads in the same process
            import threading
            _tl_lock = threading.Lock()
            @contextmanager
            def _thread_lock():
                with _tl_lock:
                    yield
            return _thread_lock()

        @contextmanager
        def _lock():
            fd = open(lock_path, "a+", encoding="utf-8")
            try:
                if fcntl:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                else:
                    fd.seek(0)
                    msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
                yield
            finally:
                if fcntl:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    except (OSError, IOError):
                        pass
                elif msvcrt:
                    try:
                        fd.seek(0)
                        msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                    except (OSError, IOError):
                        pass
                fd.close()

        return _lock()

    @staticmethod
    def _read_file(path: Path) -> List[str]:
        """Read a memory file and split into entries."""
        if not path.exists():
            return []
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, IOError):
            return []
        except UnicodeDecodeError:
            # Fix #4.2: Handle non-UTF-8 files gracefully
            logger.warning("Non-UTF-8 file detected: %s, attempting latin-1 fallback", path)
            try:
                raw = path.read_text(encoding="latin-1")
            except Exception:
                return []
        if not raw.strip():
            return []
        entries = [e.strip() for e in raw.split(ENTRY_DELIMITER)]
        return [e for e in entries if e]

    @staticmethod
    def _write_file(path: Path, entries: List[str]):
        """Write entries using atomic temp-file + rename."""
        content = ENTRY_DELIMITER.join(entries) if entries else ""
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(path.parent), suffix=".tmp", prefix=".mem_topic_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                    f.flush()
                    os.fsync(f.fileno())
                atomic_replace(tmp_path, path)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except (OSError, IOError) as e:
            raise RuntimeError(f"Failed to write topic memory file {path}: {e}")
