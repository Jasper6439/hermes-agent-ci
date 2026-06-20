"""Skills Search Tool — keyword-based skill discovery for dynamic loading.

When skills index is in condensed mode, this tool lets the model search
for relevant skills by keyword instead of reading the full index.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry

_HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))

from agent.skill_utils import _VALID_TYPES


def _search_skills(query: str, category: Optional[str] = None, skill_type: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
    """Search skills by keyword in name, description, and content."""
    query_lower = query.lower().strip()
    if not query_lower:
        return {"error": "Empty query", "skills": []}

    # Normalize type filter
    type_filter = None
    if skill_type:
        type_filter = skill_type.lower().strip()
        if type_filter not in _VALID_TYPES:
            type_filter = None

    # Collect skill directories
    skill_dirs: List[Path] = []
    home = _HERMES_HOME

    # User skills
    user_skills = home / "skills"
    if user_skills.exists():
        skill_dirs.append(user_skills)

    # Built-in skills
    builtin = Path(__file__).parent.parent / "skills"
    if builtin.exists():
        skill_dirs.append(builtin)

    # Optional skills
    optional = Path(__file__).parent.parent / "optional-skills"
    if optional.exists():
        skill_dirs.append(optional)

    # Plugin skills
    plugins_dir = home / "plugins"
    if plugins_dir.exists():
        for plugin in plugins_dir.iterdir():
            if plugin.is_dir():
                skills_sub = plugin / "skills"
                if skills_sub.exists():
                    skill_dirs.append(skills_sub)

    results = []
    query_terms = query_lower.split()

    for skill_dir in skill_dirs:
        for skill_file in skill_dir.rglob("SKILL.md"):
            try:
                content = skill_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            # Parse frontmatter (single pass)
            name = skill_file.parent.name
            description = ""
            categories = []
            extracted_type = "skill"

            fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if fm_match:
                fm = fm_match.group(1)
                for line in fm.split("\n"):
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip().strip('"\'')
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip('"\'')
                    elif line.startswith("type:"):
                        raw_type = line.split(":", 1)[1].strip().strip('"\'').lower()
                        if raw_type in _VALID_TYPES:
                            extracted_type = raw_type
                    elif line.startswith("categories:"):
                        cats = line.split(":", 1)[1].strip()
                        if cats.startswith("["):
                            categories = [c.strip().strip('"\'') for c in cats.strip("[]").split(",")]
                        else:
                            categories = [cats]

            # Path-based type inference for references/ directories
            if extracted_type == "skill" and "references" in skill_file.parts:
                extracted_type = "reference"

            # Filter by type
            if type_filter and extracted_type != type_filter:
                continue

            # Filter by category
            if category:
                cat_lower = category.lower()
                if not any(cat_lower in c.lower() for c in categories):
                    # Also check directory path
                    if cat_lower not in str(skill_file.parent).lower():
                        continue

            # Score: check if query terms match name, description, or content
            searchable = f"{name} {description} {content[:2000]}".lower()
            matched_terms = sum(1 for term in query_terms if term in searchable)

            if matched_terms == 0:
                continue

            score = matched_terms / len(query_terms)

            # Boost for name matches
            if any(term in name.lower() for term in query_terms):
                score += 0.5

            # Boost for description matches
            if any(term in description.lower() for term in query_terms):
                score += 0.3

            results.append({
                "name": name,
                "description": description[:120] if description else "",
                "categories": categories,
                "type": extracted_type,
                "score": round(score, 2),
                "path": str(skill_file.parent.relative_to(skill_dir)) if skill_dir in skill_file.parents else name,
            })

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"skills": results[:limit], "total_matches": len(results)}


def _handle_skills_search(args: Dict[str, Any]) -> Dict[str, Any]:
    query = args.get("query", "")
    category = args.get("category")
    skill_type = args.get("type")
    limit = args.get("limit", 10)

    if not query:
        return {"error": "query parameter is required"}

    result = _search_skills(query, category=category, skill_type=skill_type, limit=min(limit, 20))

    if not result.get("skills"):
        return {
            "content": f"No skills found matching '{query}'" + (f" in category '{category}'" if category else ""),
            "skills": [],
        }

    lines = [f"Found {result['total_matches']} skill(s) matching '{query}':\n"]
    for s in result["skills"]:
        cat_str = f" [{', '.join(s['categories'])}]" if s["categories"] else ""
        type_str = f" [{s.get('type', 'skill')}]" if s.get('type') and s.get('type') != 'skill' else ""
        lines.append(f"- **{s['name']}**{type_str}{cat_str}: {s['description']}")

    return {"content": "\n".join(lines), "skills": result["skills"]}


registry.register(
    name="skills_search",
    handler=_handle_skills_search,
    schema={
        "type": "function",
        "function": {
            "name": "skills_search",
            "description": "Search available skills by keyword. Use this when you need to find a relevant skill before loading it with skill_view. Returns matching skill names, descriptions, categories, and types.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords (e.g., 'docker deploy', 'trading', 'memory', 'browser automation')",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category filter (e.g., 'devops', 'mlops', 'creative')",
                    },
                    "type": {
                        "type": "string",
                        "description": "Optional skill type filter: 'skill' (actionable instructions), 'playbook' (operational runbooks), 'config' (configuration templates), 'memory' (durable knowledge), 'reference' (API docs, architecture notes)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default: 10, max: 20)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    toolset="skills",
)
