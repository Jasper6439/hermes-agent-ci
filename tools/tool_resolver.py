"""Tool Resolver — maps profile names to concrete tool sets.

This module provides the canonical Profile → Tool mapping used by the
dynamic tool loading system.  It is imported by tool_profiles.py and
model_tools.py to resolve which tools to send to the model.
"""

import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Profile → Tool mapping
# ---------------------------------------------------------------------------
# Each profile maps to a list of tool names that should be loaded when
# that profile is active.  Tool names come from the function.name field
# in the tool schema (i.e. the registry name, not the Python module name).

PROFILE_TOOL_MAP: Dict[str, List[str]] = {
    "browser": [
        "browser_navigate", "browser_click", "browser_type", "browser_snapshot",
        "browser_back", "browser_scroll", "browser_press", "browser_console",
        "browser_get_images", "browser_vision",
    ],
    "cron": [
        "cronjob",
    ],
    "kanban": [
        "kanban_create", "kanban_read", "kanban_update",
    ],
    "delegate": [
        "delegate_task",
    ],
    "image": [
        "image_generate",
    ],
    "tts": [
        "text_to_speech",
    ],
    "video": [
        "video_generate", "video_analyze",
    ],
    "xurl": [
        "xurl",
    ],
    "trading": [
        "trading", "trading_analysis", "trading_execute",
    ],
    "media": [
        "media_download", "media_search",
    ],
    "spreadsheet": [
        "airtable", "skill_view",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_tools(profiles: List[str]) -> Set[str]:
    """Resolve profile names to a flat set of tool names.

    Args:
        profiles: List of profile name strings.

    Returns:
        Set of tool name strings that should be available.
    """
    # Guard: None, non-list, or empty list → empty set
    if not isinstance(profiles, list) or not profiles:
        return set()
    tools: Set[str] = set()
    for profile in profiles:
        profile_tools = PROFILE_TOOL_MAP.get(profile, [])
        if not profile_tools and profile not in PROFILE_TOOL_MAP:
            logger.debug("resolve_tools: unknown profile '%s', skipping", profile)
        tools.update(profile_tools)
    return tools


def get_all_profile_names() -> List[str]:
    """Return all supported profile names."""
    return list(PROFILE_TOOL_MAP.keys())


def get_profile_tools(profile_name: str) -> List[str]:
    """Return the tool list for a single profile, or empty list if unknown."""
    return list(PROFILE_TOOL_MAP.get(profile_name, []))
