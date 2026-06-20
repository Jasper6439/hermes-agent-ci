"""Dynamic tool loader — reduces token consumption by only loading relevant tools.

Instead of sending all 69 tool schemas with every API call, this module:
1. Always loads core tools (terminal, file, web, etc.)
2. Loads toolset-specific tools based on keyword detection in user message
3. Caches loaded toolsets to avoid re-loading within a session

Expected savings: ~10K-15K tokens per message (from ~27K to ~12K-17K)
"""

import re
from typing import Set, Dict, List, Optional

# Toolsets that are ALWAYS loaded (core functionality)
ALWAYS_LOADED = {"core", "file", "web", "browser"}

# Toolset triggers: keywords/patterns that indicate a toolset is needed
TOOLSET_TRIGGERS: Dict[str, List[str]] = {
    "terminal": [
        r"terminal", r"命令行", r"shell", r"bash", r"执行.*命令", r"run.*command",
        r"install", r"安装", r"pip", r"apt", r"npm", r"docker", r"systemctl",
        r"python", r"脚本", r"script", r"编译", r"compile", r"build",
    ],
    "process": [
        r"process", r"进程", r"background", r"后台", r"daemon", r"服务",
        r"long.*running", r"长时间",
    ],
    "cronjob": [
        r"cron", r"定时", r"schedule", r"定期", r"每.*小时", r"每天", r"每周",
        r"recurring", r"periodic",
    ],
    "delegate": [
        r"delegate", r"子代理", r"subagent", r"并行", r"parallel", r"batch",
        r"同时.*做", r"分发",
    ],
    "image": [
        r"image.*gen", r"生成.*图", r"画.*图", r"dall.*e", r"midjourney", r"stable.*diffusion",
        r"illustration", r"illustrate",
    ],
    "tts": [
        r"tts", r"text.*to.*speech", r"语音", r"朗读", r"voice", r"音频.*生成",
    ],
    "video": [
        r"video", r"视频", r"mp4", r"ffmpeg", r"剪辑",
    ],
    "spotify": [
        r"spotify", r"音乐", r"music", r"song", r"playlist", r"播放列表",
    ],
    "feishu": [
        r"feishu", r"飞书", r"lark",
    ],
    "discord": [
        r"discord",
    ],
    "homeassistant": [
        r"home.*assistant", r"hass", r"智能家居", r"smart.*home", r"灯光", r"light",
        r"温度", r"thermostat",
    ],
    "kanban": [
        r"kanban", r"看板", r"任务.*板", r"todo.*board", r"任务.*管理",
    ],
    "computer_use": [
        r"computer.*use", r"桌面", r"desktop", r"screenshot.*click", r"gui.*操作",
    ],
    "x_search": [
        r"x\.com", r"twitter", r"推特", r"tweet", r"x.*search",
    ],
    "yuanbao": [
        r"yuanbao", r"元宝", r"腾讯.*ai",
    ],
    "todo": [
        r"todo", r"待办", r"任务.*列表", r"task.*list",
    ],
    "session_search": [
        r"session.*search", r"搜索.*会话", r"查找.*历史", r"recall.*conversation",
    ],
}


def detect_needed_toolsets(user_message: str) -> Set[str]:
    """Detect which toolsets are needed based on user message content.
    
    Returns set of toolset names that should be loaded.
    """
    needed = set(ALWAYS_LOADED)
    message_lower = user_message.lower()
    
    for toolset, patterns in TOOLSET_TRIGGERS.items():
        for pattern in patterns:
            if re.search(pattern, message_lower):
                needed.add(toolset)
                break
    
    return needed


def get_dynamic_tool_list(
    user_message: str,
    all_available_tools: List[str],
    tool_to_toolset: Dict[str, str],
    always_include: Optional[Set[str]] = None,
) -> List[str]:
    """Get list of tool names to include based on user message.
    
    Args:
        user_message: The user's message text
        all_available_tools: List of all available tool names
        tool_to_toolset: Mapping of tool_name -> toolset_name
        always_include: Extra tool names to always include
    
    Returns:
        Filtered list of tool names to send to the model
    """
    needed_toolsets = detect_needed_toolsets(user_message)
    
    # Add any always-include tools
    always = set(always_include or [])
    
    filtered = []
    for tool_name in all_available_tools:
        # Always include if in always_include set
        if tool_name in always:
            filtered.append(tool_name)
            continue
        
        # Include if toolset is needed
        toolset = tool_to_toolset.get(tool_name, "core")
        if toolset in needed_toolsets:
            filtered.append(tool_name)
    
    return filtered


# ── Context-aware tool injection ──────────────────────────────────
# For the SOUL.md / system prompt, we can also dynamically include
# only relevant skill categories

SKILL_CATEGORY_TRIGGERS: Dict[str, List[str]] = {
    "devops": [r"deploy", r"docker", r"nginx", r"systemd", r"ci.*cd", r"devops", r"运维"],
    "mlops": [r"model", r"train", r"inference", r"gpu", r"vllm", r"llama", r"huggingface", r"模型"],
    "creative": [r"image", r"art", r"design", r"creative", r"画", r"设计", r"illustration"],
    "research": [r"research", r"paper", r"arxiv", r"研究", r"论文", r"搜索.*资料"],
    "github": [r"github", r"git", r"pr", r"issue", r"commit", r"repo", r"仓库"],
    "media": [r"youtube", r"spotify", r"music", r"video", r"音乐", r"视频"],
    "productivity": [r"calendar", r"email", r"日历", r"邮件", r"linear", r"notion"],
    "legal": [r"legal", r"law", r"contract", r"法律", r"合同", r"合规"],
    "web": [r"browse", r"web.*scrape", r"浏览器", r"网页", r"crawl"],
}


def get_relevant_skill_categories(user_message: str, all_categories: List[str]) -> List[str]:
    """Get skill categories relevant to the user's message.
    
    Returns list of category names to include in the skill index.
    """
    relevant = set()
    message_lower = user_message.lower()
    
    for category, patterns in SKILL_CATEGORY_TRIGGERS.items():
        for pattern in patterns:
            if re.search(pattern, message_lower):
                relevant.add(category)
                break
    
    # Always include a few core categories
    relevant.update({"autonomous-ai-agents", "software-development"})
    
    # Return only categories that exist
    return [c for c in all_categories if c in relevant]
