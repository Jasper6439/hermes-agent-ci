"""Headroom Hook — content-type aware compression via transform_tool_result hook.

NOTE: With the TokenJuice pipeline redesign (L3 integration), headroom compression
is now called internally by tokenjuice. This hook remains for backward compatibility
and as a fallback when tokenjuice is disabled. It checks for _tokenjuice_stats
to avoid double-compression.
"""
import json
import os
import sys
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.expanduser("~/workspace/projects/implantation/headroom"))

import logging
logger = logging.getLogger(__name__)

try:
    import headroom
    HAS_HEADROOM = True
except ImportError:
    HAS_HEADROOM = False
    logger.warning("Headroom not available, hook disabled")


def register(ctx):
    """Register the transform_tool_result hook."""
    ctx.register_hook("transform_tool_result", _transform_tool_result)


def _detect_content_type(text: str) -> str:
    """Detect the content type of text for headroom compression.

    Returns one of: 'json', 'log', 'code', 'other'.
    """
    text_lower = text.lower().strip()
    if text_lower.startswith('{') or text_lower.startswith('['):
        try:
            json.loads(text)
            return "json"
        except:
            pass
    log_patterns = ['error:', 'warn:', 'info:', 'debug:', 'traceback', 'exception']
    if any(p in text_lower for p in log_patterns):
        return "log"
    code_patterns = ['def ', 'class ', 'import ', 'function ']
    if any(p in text for p in code_patterns):
        return "code"
    return "other"


def _transform_tool_result(tool_name=None, result=None, **kwargs):
    """Transform tool result using headroom compression.

    Skips if:
    - headroom not available
    - result already compressed by tokenjuice (has _tokenjuice_stats)
    - result too short (< 200 chars)
    - content type is 'other' (not json/log/code)
    """
    if not HAS_HEADROOM or not isinstance(result, str):
        return None
    if len(result) < 200:
        return None
    # Skip if tokenjuice already processed this (avoid double-compression)
    if "_tokenjuice_stats" in result:
        return None

    try:
        data = json.loads(result)
        output = data.get("output", result)
    except:
        output = result

    content_type = _detect_content_type(output)
    if content_type == "other":
        return None

    try:
        # Use headroom.compress with messages format
        messages = [{"role": "assistant", "content": output}]
        result_obj = headroom.compress(messages)

        # Check if compression actually happened
        if result_obj.compression_ratio > 0.2:  # At least 20% compression
            compressed_content = result_obj.messages[0]["content"] if result_obj.messages else output

            try:
                data = json.loads(result)
                data["output"] = compressed_content
                data["_headroom_stats"] = {
                    "original_tokens": result_obj.tokens_before,
                    "compressed_tokens": result_obj.tokens_after,
                    "compression_ratio": round(result_obj.compression_ratio * 100, 1),
                    "transforms": result_obj.transforms_applied,
                    "content_type": content_type,
                }
                return json.dumps(data)
            except:
                return compressed_content
    except Exception as e:
        logger.debug("Headroom compression failed: %s", e)

    return None
