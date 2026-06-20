#!/usr/bin/env python3
"""
Memory Turbovec — L2 双写模块

当 Topic Memory 保存时，同时写入 MEMORY.md「跨话题记忆」部分。
支持文件锁防止并发写入冲突。

用法：
    from memory_turbovec import store
    store(content, topic_id="session_key", layer="L2", source="dual_write")
"""

import os
import sys
import fcntl
from datetime import datetime
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
MEMORY_FILE = HERMES_HOME / "MEMORY.md"


def store(content: str, topic_id: str = "", layer: str = "L2", source: str = "dual_write") -> bool:
    """
    存储内容到 MEMORY.md「跨话题记忆」部分。
    使用文件锁防止并发写入冲突。

    Args:
        content: 要存储的内容
        topic_id: 来源话题 ID
        layer: 目标层标识
        source: 来源标识

    Returns:
        bool: 是否成功存储
    """
    for attempt in range(3):
        try:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            topic_info = f" (from: {topic_id})" if topic_id else ""
            new_entry = f"- [{timestamp}] [{source}]{topic_info}: {content}\n"

            # 读-改-写 with flock
            with open(MEMORY_FILE, "a+", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.seek(0)
                    existing = f.read()

                    if "## 跨话题记忆" not in existing:
                        existing += "\n## 跨话题记忆\n\n"

                    # 追加到文件末尾（跨话题记忆部分总是在最后）
                    if not existing.endswith("\n"):
                        existing += "\n"
                    f.seek(0)
                    f.truncate()
                    f.write(existing + new_entry)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)

            return True

        except Exception as e:
            if attempt == 2:
                print(f"[memory_turbovec] 写入失败 (attempt {attempt+1}/3): {e}", file=sys.stderr)
                return False
    return False


if __name__ == "__main__":
    test_content = "双写机制验证 - " + datetime.now().isoformat()
    result = store(test_content, topic_id="test", source="test")
    print(f"结果: {'成功' if result else '失败'}")
