"""Dynamic tool profiles — lightweight keyword classifier for per-turn tool loading.

When enabled, only core tools + matched profile tools are sent to the model
each turn, saving ~15K tokens per API call.

Scoring system (v2):
  - exact match  → 1.0
  - substring    → 0.5
  - per-match bonus → +0.2 (capped at 3.0 total)

Conversation history inheritance:
  - If the previous turn matched a profile, that profile gets a +0.3 bonus
  - Avoids flickering between profiles on short follow-up messages

Usage in model_tools.py:
    from tools.tool_profiles import classify_message, resolve_profiles_to_tools
    profiles = classify_message(user_message, history)
    allowed_tools = resolve_profiles_to_tools(profiles)
    defs = get_tool_definitions(profile_names=allowed_tools)
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Profile definitions  (tool lists are resolved via tool_resolver at import)
# ---------------------------------------------------------------------------

TOOL_PROFILES: Dict[str, Dict] = {
    "browser": {
        "keywords": ["browse", "search", "website", "url", "http", "scrape",
                      "page", "open", "navigate", "google", "link", "网页",
                      "浏览", "网站", "打开"],
        "tools": ["web_search", "web_extract", "skill_view", "skills_list"],
        "hint": "Use web_search to find information, web_extract to read pages.",
    },
    "cron": {
        "keywords": ["schedule", "cron", "timer", "remind", "daily", "weekly",
                      "定时", "提醒", "计划", "日程"],
        "tools": ["cron_add", "cron_list", "cron_remove", "cron_update"],
        "hint": "Use cron_add to schedule recurring tasks.",
    },
    "kanban": {
        "keywords": ["task", "kanban", "board", "todo", "backlog", "sprint",
                      "任务", "看板", "待办", "工单"],
        "tools": ["kanban"],
        "hint": "Use kanban to manage task boards.",
    },
    "delegate": {
        "keywords": ["delegate", "subagent", "agent", "spawn", "worker",
                      "委托", "子代理", "分发"],
        "tools": ["delegate", "plan_dispatch"],
        "hint": "Use delegate to spawn subagents for parallel work.",
    },
    "image": {
        "keywords": ["image", "picture", "photo", "generate", "draw", "art",
                      "图片", "照片", "生成图", "画", "图像"],
        "tools": ["skill_view", "skills_list"],
        "hint": "Use AI image generation skills for visual tasks.",
    },
    "tts": {
        "keywords": ["voice", "speak", "tts", "audio", "say", "narrate",
                      "语音", "说话", "朗读", "音频"],
        "tools": ["skill_view", "skills_list"],
        "hint": "Use voice/speech skills for TTS tasks.",
    },
    "video": {
        "keywords": ["video", "mp4", "youtube", "clip", "record",
                      "视频", "录像"],
        "tools": ["skill_view", "skills_list"],
        "hint": "Use video skills for video tasks.",
    },
    "xurl": {
        "keywords": ["xurl", "tweet", "twitter", "x post", "xurl",
                      "推文", "发推"],
        "tools": ["xurl"],
        "hint": "Use xurl for X/Twitter operations.",
    },
    "trading": {
        "keywords": ["trade", "trading", "crypto", "bitcoin", "eth", "price",
                      "market", "交易", "加密货币", "比特币", "行情"],
        "tools": ["skill_view", "skills_list"],
        "hint": "Use trading skills for market operations.",
    },
    "media": {
        "keywords": ["music", "song", "spotify", "playlist", "download",
                      "音乐", "歌曲", "下载"],
        "tools": ["skill_view", "skills_list"],
        "hint": "Use media skills for audio/video downloads.",
    },
    "spreadsheet": {
        "keywords": ["spreadsheet", "excel", "csv", "table", "airtable",
                      "表格", "电子表格"],
        "tools": ["airtable", "skill_view"],
        "hint": "Use airtable or spreadsheet tools for tabular data.",
    },
}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _load_config() -> Dict:
    """Load dynamic_tool_loading config from config.yaml or env vars.

    Priority: env vars > config.yaml > defaults.
    """
    config = {
        "enabled": False,           # disabled by default (backward compat)
        "threshold": 0.5,           # minimum score to activate a profile
        "max_profiles": 3,          # max profiles activated per turn
        "history_bonus": 0.3,       # bonus for previous-turn profile
        "inherit_from_history": True,
        "debug": {
            "log_loaded_tools": False,
            "log_classification": False,
            "force_all_tools": False,
        },
    }

    # Env overrides
    env_enabled = os.environ.get("HERMES_TOOL_LOADING_ENABLED")
    if env_enabled is not None:
        config["enabled"] = env_enabled.lower() in ("true", "1", "yes")

    env_debug = os.environ.get("HERMES_TOOL_LOADING_DEBUG")
    if env_debug is not None:
        config["debug"]["log_classification"] = env_debug.lower() in ("true", "1", "yes")

    env_force = os.environ.get("HERMES_TOOL_LOADING_FORCE_ALL")
    if env_force is not None:
        config["debug"]["force_all_tools"] = env_force.lower() in ("true", "1", "yes")

    # Try loading from config.yaml
    try:
        import yaml
        config_paths = [
            os.path.expanduser("~/.hermes/config.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml"),
        ]
        for cpath in config_paths:
            if os.path.exists(cpath):
                with open(cpath, "r") as f:
                    full = yaml.safe_load(f) or {}
                dtl = full.get("dynamic_tool_loading", {})
                if dtl:
                    for k, v in dtl.items():
                        if k == "debug" and isinstance(v, dict):
                            config["debug"].update(v)
                        else:
                            config[k] = v
                break
    except ImportError:
        pass  # yaml not available, use defaults
    except Exception as exc:
        logger.debug("Failed to load dynamic_tool_loading config: %s", exc)

    return config


# Cached config (loaded once)
_config: Optional[Dict] = None


def get_config() -> Dict:
    global _config
    if _config is None:
        _config = _load_config()
    return _config


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

def _score_keyword(keyword: str, message_lower: str) -> float:
    """Score a single keyword against a message.

    Returns:
        1.0  for exact word-boundary match
        0.5  for substring containment
        0.0  for no match
    """
    if not keyword:
        return 0.0

    kw_lower = keyword.lower()

    # Exact word-boundary match
    import re
    if re.search(r'\b' + re.escape(kw_lower) + r'\b', message_lower):
        return 1.0

    # Substring containment
    if kw_lower in message_lower:
        return 0.5

    return 0.0


def classify_message(
    message: str,
    history: Optional[List[Dict]] = None,
    config: Optional[Dict] = None,
) -> List[str]:
    """Classify a user message into matching tool profiles.

    Scoring:
      - Per-keyword: exact=1.0, substring=0.5, bonus=+0.2/match (max 3.0)
      - History inheritance: +0.3 for profiles active in previous turn
      - Profiles above threshold (default 0.5) are activated
      - Max profiles per turn capped at max_profiles (default 3)

    Args:
        message: Current user message text.
        history: Previous conversation messages (list of dicts with 'role'/'content').
        config: Override config dict; uses global config if None.

    Returns:
        List of profile names that match, ordered by score descending.
    """
    if not message:
        return []

    cfg = config or get_config()

    if not cfg.get("enabled", False):
        return []

    if cfg.get("debug", {}).get("force_all_tools", False):
        return list(TOOL_PROFILES.keys())

    message_lower = message.lower()
    threshold = cfg.get("threshold", 0.5)
    max_profiles = cfg.get("max_profiles", 3)

    scores: Dict[str, float] = {}

    for profile_name, profile_def in TOOL_PROFILES.items():
        keywords = profile_def.get("keywords", [])
        profile_score = 0.0
        match_count = 0

        for kw in keywords:
            kw_score = _score_keyword(kw, message_lower)
            if kw_score > 0:
                profile_score += kw_score
                match_count += 1

        # Bonus per match (capped at 3.0 total)
        profile_score = min(profile_score + match_count * 0.2, 3.0)

        scores[profile_name] = profile_score

    # History inheritance: bonus for profiles from previous turn
    if cfg.get("inherit_from_history", True) and history:
        history_bonus = cfg.get("history_bonus", 0.3)
        prev_profiles = _extract_profiles_from_history(history)
        for pname in prev_profiles:
            if pname in scores:
                scores[pname] += history_bonus

    # Filter and sort
    matched = [
        (name, score) for name, score in scores.items()
        if score >= threshold
    ]
    matched.sort(key=lambda x: x[1], reverse=True)

    result = [name for name, _ in matched[:max_profiles]]

    if cfg.get("debug", {}).get("log_classification", False):
        logger.info("classify_message: message=%r → profiles=%s (scores=%s)",
                     message[:80], result, {n: round(s, 2) for n, s in matched})

    return result


def _extract_profiles_from_history(history: List[Dict]) -> Set[str]:
    """Extract profile names from conversation history by scanning for
    tool call patterns that indicate which profiles were active."""
    profiles = set()
    if not history:
        return profiles

    # Look at the last few messages for tool usage hints
    for msg in history[-6:]:  # last 6 messages
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "assistant" and content:
            content_lower = content.lower()
            for profile_name, profile_def in TOOL_PROFILES.items():
                tools = profile_def.get("tools", [])
                for tool in tools:
                    if tool.lower() in content_lower:
                        profiles.add(profile_name)

    return profiles


# ---------------------------------------------------------------------------
# Profile → Tool resolution
# ---------------------------------------------------------------------------

def resolve_profiles_to_tools(profiles: List[str]) -> Set[str]:
    """Resolve a list of profile names to their tool sets.

    Args:
        profiles: List of profile names (e.g., ["browser", "cron"]).

    Returns:
        Set of tool name strings to load alongside core tools.
    """
    # Guard: None, non-list, or empty list → empty set
    if not isinstance(profiles, list) or not profiles:
        return set()
    tools: Set[str] = set()
    for pname in profiles:
        if pname in TOOL_PROFILES:
            tools.update(TOOL_PROFILES[pname].get("tools", []))
    return tools


def get_profile_hints(profile_names: List[str]) -> str:
    """Return newline-joined hint strings for the matched profiles."""
    hints = []
    for name in profile_names:
        if name in TOOL_PROFILES:
            hint = TOOL_PROFILES[name].get("hint", "")
            if hint:
                hints.append(hint)
    return "\n".join(hints) if hints else ""
