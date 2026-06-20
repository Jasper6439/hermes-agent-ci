"""
Post-Response Hook v2 — 集成到 Loop 控制器

整合:
1. 上下文快照保存 (L1)
2. 重要信息检测 → 写入 L1
3. Topic memory 更新
4. 上下文使用率监控
"""

import os
import sys
from pathlib import Path
from typing import Dict, Optional

# Add scripts directory to path
SCRIPT_DIR = Path(__file__).parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def post_response_hook_v2(
    session_id: str,
    topic_id: Optional[str] = None,
    session_key: Optional[str] = None,
    user_message: str = "",
    agent_response: str = "",
    iteration: int = 0,
    had_tool_calls: bool = False,
    tool_name: Optional[str] = None,
    tool_result: Optional[str] = None,
) -> Dict:
    """
    Post-Response Hook v2 — 集成到 Loop 控制器
    
    在每次响应后自动执行:
    1. 保存上下文快照到 L1
    2. 检测重要信息 → 写入 L1
    3. 更新 topic memory
    4. 检查上下文使用率
    """
    result = {
        "session_id": session_id,
        "topic_id": topic_id,
        "iteration": iteration,
        "actions": [],
    }
    
    # 1. 保存上下文快照
    try:
        from scripts.context_manager import save_context_snapshot
        summary = _extract_summary(user_message, agent_response)
        if summary:
            success = save_context_snapshot(session_id, topic_id, summary)
            if success:
                result["actions"].append("context_snapshot_saved")
    except Exception as e:
        result["actions"].append(f"context_snapshot_error: {e}")
    
    # 2. 检测重要信息 → 写入 L1 (Topic Memory)
    try:
        important_info = _detect_important_info(user_message, agent_response)
        if important_info:
            # 写入 topic memory
            from tools.topic_memory import TopicMemoryStore
            if session_key:
                tm = TopicMemoryStore(session_key)
                tm.add(important_info)
            elif session_id:
                tm = TopicMemoryStore(session_id)
                tm.add(important_info)
                result["actions"].append("topic_memory_updated")
            

    except Exception as e:
        result["actions"].append(f"important_info_error: {e}")
    

    
    # 4. 检查上下文使用率
    try:
        context_usage = _check_context_usage(session_id)
        result["context_usage"] = context_usage
        
        if context_usage > 0.8:
            result["actions"].append("context_warning_high")
        elif context_usage > 0.6:
            result["actions"].append("context_warning_medium")
    except Exception as e:
        result["actions"].append(f"context_check_error: {e}")
    
    return result


def _extract_summary(user_message: str, agent_response: str) -> Optional[str]:
    """提取对话摘要"""
    if not user_message or not agent_response:
        return None
    
    # 简单摘要: 用户消息 + 响应前 200 字符
    summary = f"User: {user_message[:100]}\nAgent: {agent_response[:200]}"
    return summary


def _detect_important_info(user_message: str, agent_response: str) -> Optional[str]:
    """检测重要信息"""
    # 检测包含重要标记的内容
    important_markers = [
        "重要",
        "记住",
        "注意",
        "警告",
        "密码",
        "密钥",
        "API",
        "配置",
        "设置",
        "remember",
        "important",
        "warning",
        "password",
        "key",
        "config",
    ]
    
    combined = f"{user_message} {agent_response}".lower()
    
    for marker in important_markers:
        if marker.lower() in combined:
            # 提取包含标记的句子
            sentences = f"{user_message} {agent_response}".split("。")
            for sentence in sentences:
                if marker.lower() in sentence.lower():
                    return sentence.strip()
    
    return None


def _check_context_usage(session_id: str) -> float:
    """检查上下文使用率"""
    try:
        # 这里可以集成实际的 token 计数
        # 目前返回估计值
        return 0.5
    except Exception:
        return 0.0


# ── 测试 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = post_response_hook_v2(
        session_id="test_session",
        topic_id="test_topic",
        session_key="agent:main:cli:dm:test_session",
        user_message="请记住这个重要的 API 密钥: abc123",
        agent_response="好的，我已经记住了这个 API 密钥。",
        iteration=1,
        had_tool_calls=False,
    )
    print(f"Result: {result}")
