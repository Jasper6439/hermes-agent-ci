"""TokenJuice plugin for Hermes — deterministic output compaction using 267+ JSON rules.

Based on vincentkoc/tokenjuice. Loads rules from ~/.tokenjuice/rules/ and applies
command-specific compression to CLI output before sending to LLM.
Replaces the old "token-compressor" plugin with official TokenJuice naming.

Loads 96+ JSON rules from ~/.tokenjuice/rules/ and applies command-specific compression.
Uses specificity scoring to select the best matching rule.

Pipeline: L0 Guard → L1 Rule-based → L2 Per-Tool Cap
Headroom (AI compression) runs as a SEPARATE hook, not inside tokenjuice.
"""

import json
import re
import sys
from pathlib import Path

# User rules directory (OpenHuman vendor rules + custom rules)
RULES_DIR = Path.home() / ".tokenjuice" / "rules"

# Cache for loaded rules
_rules_cache = None

# ── L0 Guard Layer constants ──
MIN_COMPACT_INPUT_BYTES = 512   # Skip compression if output < 512 bytes
MIN_COMPACT_RATIO = 0.95        # Skip if compressed output > 95% of original

# Per-tool hard character caps (tool_name -> max_chars)
TOOL_CAPS = {
    "terminal": 8000,
    "read_file": 6000,
    "search_files": 5000,
    "default": 6000,
}

# Domain tools that return structured data — skip generic/fallback
DOMAIN_TOOLS = {
    "web_search", "web_fetch", "process",
    "create_memory", "search_memories", "list_memories",
    "create_calendar_event", "list_calendar_events",
    "update_calendar_event", "delete_calendar_event",
    "get_current_datetime", "ask_user",
}

# Feature flag: disable L3 headroom integration (now separate hook)
PIPELINE_V2 = True  # When True: L0→L1→L2 only, headroom is separate

import logging
logger = logging.getLogger(__name__)


def _load_rules():
    """Load all JSON rules from the rules directory tree."""
    global _rules_cache
    if _rules_cache is not None:
        return _rules_cache

    rules = []
    if not RULES_DIR.exists():
        _rules_cache = rules
        return rules

    for rule_file in sorted(RULES_DIR.rglob("*.json")):
        try:
            with open(rule_file) as f:
                content = f.read()
                # Fix common JSON escape issues
                content = content.replace('\\', '\\\\')
                rule = json.loads(content)
            rule["_source"] = rule_file.name
            rules.append(rule)
        except Exception as e:
            print(f"token-compressor: Failed to load {rule_file.name}: {e}", file=sys.stderr)

    _rules_cache = rules
    return rules


def _match_rule(rule, command):
    """Check if a rule matches the given command."""
    match_config = rule.get("match", {})

    # Empty match = fallback, don't match in strict mode
    if not match_config:
        return False

    # Check argv0 (command name)
    argv0_patterns = match_config.get("argv0", [])
    if argv0_patterns:
        cmd_name = command.strip().split()[0] if command.strip() else ""
        if cmd_name not in argv0_patterns:
            return False

    # Check argvIncludes (substrings that must appear in command)
    # Each entry can be a string or a list of alternatives (OR within, AND across entries)
    argv_includes = match_config.get("argvIncludes", [])
    for inc in argv_includes:
        if isinstance(inc, list):
            # List of alternatives: at least one must match
            if not any(alt in command for alt in inc):
                return False
        else:
            if inc not in command:
                return False

    return True


def _score_rule(rule, command):
    """Score a rule by specificity for the given command."""
    score = 0
    match_config = rule.get("match", {})

    # Exact argv0 match is high score
    argv0_patterns = match_config.get("argv0", [])
    if argv0_patterns:
        cmd_name = command.strip().split()[0] if command.strip() else ""
        if cmd_name in argv0_patterns:
            score += 10

    # argvIncludes matches
    argv_includes = match_config.get("argvIncludes", [])
    for inc in argv_includes:
        if isinstance(inc, list):
            for alt in inc:
                if alt in command:
                    score += 5
                    break
        else:
            if inc in command:
                score += 5

    return score


def _find_best_rule(command):
    """Find the best matching rule for a command."""
    rules = _load_rules()

    matches = []
    for rule in rules:
        if _match_rule(rule, command):
            score = _score_rule(rule, command)
            matches.append((rule, score))

    if not matches:
        # Fall back to generic/fallback rule
        for rule in rules:
            if rule.get("id") == "generic/fallback":
                return rule
        return None

    # Sort by score descending, return best
    matches.sort(key=lambda x: -x[1])
    return matches[0][0]


def _apply_transforms(output, transforms):
    """Apply text transforms to the output."""
    if not transforms:
        return output

    # stripAnsi: Remove ANSI escape codes
    if transforms.get("stripAnsi"):
        ansi_pattern = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
        output = ansi_pattern.sub('', output)

    # dedupeAdjacent: Remove adjacent duplicate lines
    if transforms.get("dedupeAdjacent"):
        lines = output.split('\n')
        deduped = []
        prev = None
        for line in lines:
            if line != prev:
                deduped.append(line)
                prev = line
        output = '\n'.join(deduped)

    # trimEmptyEdges: Remove leading/trailing empty lines
    if transforms.get("trimEmptyEdges"):
        output = output.strip('\n')

    return output


def _summarize_output(output, summarize_config):
    """Apply summarization (head/tail) to the output."""
    if not summarize_config:
        return output

    lines = output.split('\n')
    total = len(lines)

    head = summarize_config.get("head", 0)
    tail = summarize_config.get("tail", 0)

    if head == 0 and tail == 0:
        return output

    if head + tail >= total:
        return output

    result = []
    if head > 0:
        result.extend(lines[:head])
    if tail > 0:
        if head > 0:
            omitted = total - head - tail
            result.append(f"... ({omitted} lines omitted) ...")
        result.extend(lines[-tail:])

    return '\n'.join(result)


def _count_items(output, counters):
    """Count items using regex patterns from counters."""
    counts = {}
    for counter in counters:
        name = counter.get("name", "unknown")
        pattern = counter.get("pattern", "")
        flags = counter.get("flags", "")

        re_flags = 0
        if "i" in flags:
            re_flags |= re.IGNORECASE
        if "m" in flags:
            re_flags |= re.MULTILINE

        try:
            matches = re.findall(pattern, output, re_flags)
            counts[name] = len(matches)
        except re.error:
            counts[name] = 0

    return counts


def _compress_output(output, command):
    """Compress output using the best matching rule."""
    rule = _find_best_rule(command)

    if not rule:
        return output, {}, "none"

    transforms = rule.get("transforms", {})
    summarize = rule.get("summarize", {})
    counters = rule.get("counters", [])

    # Apply transforms
    output = _apply_transforms(output, transforms)

    # Apply summarization
    output = _summarize_output(output, summarize)

    # Count items
    counts = _count_items(output, counters)

    return output, counts, rule.get("id", "unknown")


# ── L0 Guard Layer ──

def _extract_command_argv(args):
    """Extract the real command string from tool args.

    Tries multiple arg key names: command, cmd, argv, args.
    Returns (command_str, argv_list) or (None, None) if no command found.

    FIXED: handles 'args' list correctly (was referencing undefined 'argv').
    """
    if not isinstance(args, dict):
        return None, None

    # Try 'command' first (most common)
    cmd = args.get("command")
    if cmd and isinstance(cmd, str):
        argv = cmd.split()
        return cmd, argv

    # Try 'cmd'
    cmd = args.get("cmd")
    if cmd and isinstance(cmd, str):
        argv = cmd.split()
        return cmd, argv

    # Try 'argv' (list form)
    argv = args.get("argv")
    if argv and isinstance(argv, list) and len(argv) > 0:
        cmd = " ".join(str(a) for a in argv)
        return cmd, argv

    # Try 'args' (could be string or list)
    raw_args = args.get("args")
    if raw_args:
        if isinstance(raw_args, str):
            argv = raw_args.split()
            return raw_args, argv
        elif isinstance(raw_args, list) and len(raw_args) > 0:
            # FIXED: was 'argv' (undefined), now 'raw_args'
            cmd = " ".join(str(a) for a in raw_args)
            return cmd, raw_args

    return None, None


def _is_domain_tool(tool_name, args):
    """Check if this is a domain/structured tool (no shell command).

    Domain tools return structured data and should NOT get generic/fallback
    truncation. They are handled downstream by AI compression or left as-is.
    """
    if tool_name in DOMAIN_TOOLS:
        return True
    command, argv = _extract_command_argv(args)
    return command is None and argv is None


def _guard_checks(output, tool_name, args, exit_code=None):
    """L0 Guard Layer — pre-flight checks before any compression.

    Returns (should_skip, reason):
      - (True, reason) → skip compression entirely, return None
      - (False, "ok") → proceed with compression pipeline
    """
    # Size guard: skip tiny outputs
    if len(output) < MIN_COMPACT_INPUT_BYTES:
        return True, "too-small"

    # Domain tool guard: don't touch structured output
    if _is_domain_tool(tool_name, args):
        return True, "domain-tool"

    # Exit code guard: skip generic fallback for errors
    # (but still allow specific rule matches — checked later)
    if exit_code is not None and exit_code != 0:
        return False, "error-allow-specific-rules"

    return False, "ok"


def _apply_per_tool_cap(output, tool_name):
    """L2 Per-Tool Cap — hard character limit with head/tail truncation.

    Returns (capped_output, was_capped).
    """
    cap = TOOL_CAPS.get(tool_name, TOOL_CAPS["default"])
    if len(output) <= cap:
        return output, False

    # Head/tail truncation: keep first 70% and last 30%
    head_size = int(cap * 0.7)
    tail_size = cap - head_size - 50  # 50 chars for marker

    head = output[:head_size]
    tail = output[-tail_size:]
    omitted = len(output) - head_size - tail_size
    marker = f"\n... ({omitted} chars omitted) ...\n"

    return head + marker + tail, True


# ── Orchestrator (Pipeline V2: L0→L1→L2 only, no L3) ──

def _transform_tool_result(tool_name=None, result=None, command=None, args=None, **kwargs):
    """Orchestrate the L0→L1→L2 compression pipeline.

    Pipeline stages:
      L0: Guard checks (size, domain tool, exit code)
      L1: TokenJuice rule-based compression
      L2: Per-tool character cap

    Headroom (AI compression) runs as a SEPARATE hook, not here.
    Returns compressed result as JSON string, or None to keep original.
    """
    if tool_name != "terminal" or not isinstance(result, str):
        return None
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    output = data.get("output", "")
    if not output:
        return None

    # Extract exit code if present
    exit_code = data.get("exit_code")

    # Extract command from args
    cmd_str = command or ""
    if not cmd_str and isinstance(args, dict):
        extracted = _extract_command_argv(args)
        if extracted:
            cmd_str = extracted[0] or ""

    # ── L0: Guard checks ──
    should_skip, reason = _guard_checks(output, tool_name, args, exit_code)
    if should_skip:
        return None

    # ── L1: TokenJuice rule-based compression ──
    compressed, counts, rule_id = _compress_output(output, cmd_str)

    l1_applied = compressed is not None and len(compressed) < len(output)
    l1_ratio = len(compressed) / len(output) if l1_applied else 1.0

    # Guard: if L1 ratio is too high (didn't compress enough), skip L1 result
    if l1_applied and l1_ratio > MIN_COMPACT_RATIO:
        l1_applied = False

    # Error guard: if exit_code != 0 and we only got generic/fallback, skip it
    if exit_code is not None and exit_code != 0 and rule_id in ("generic/fallback", "none"):
        l1_applied = False

    current = compressed if l1_applied else output

    # ── L2: Per-tool cap ──
    capped, was_capped = _apply_per_tool_cap(current, tool_name)

    final_output = capped if was_capped else current

    # ── Build result ──
    if final_output == output:
        # No compression applied
        return None

    # Construct output with stats
    if data is not None:
        data["output"] = final_output
    else:
        data = {"output": final_output}

    data["_tokenjuice_stats"] = {
        "original_chars": len(output),
        "compressed_chars": len(final_output),
        "reduction_pct": round((1 - len(final_output) / len(output)) * 100, 1),
        "rule_used": rule_id,
        "counters": counts,
        "l1_applied": l1_applied,
        "l2_capped": was_capped,
        "l3_headroom": False,  # Always False in Pipeline V2
        "domain_tool": _is_domain_tool(tool_name, args),
        "exit_status": exit_code,
        "pipeline_version": "v2",
    }
    return json.dumps(data, ensure_ascii=False)


def register(ctx):
    """Register the transform_tool_result hook."""
    ctx.register_hook("transform_tool_result", _transform_tool_result)

