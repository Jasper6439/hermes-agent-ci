"""AnySearch web search provider — plugin form.

Connects to the AnySearch MCP server at https://api.anysearch.com/mcp
using Streamable HTTP transport. Supports web search across 23 vertical domains.

Config keys::
    web:
      search_backend: "anysearch"

No API key required for anonymous access (lower rate limits).
Optional: ANYSEARCH_API_KEY for higher rate limits.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict

import httpx

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)

_MCP_URL = "https://api.anysearch.com/mcp"
_MCP_CLIENT_NAME = "hermes-mcp-client"
_MCP_CLIENT_VERSION = "1.0.0"
_MCP_TIMEOUT = 30.0


def _headers() -> dict:
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    api_key = os.environ.get("ANYSEARCH_API_KEY", "")
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _mcp_call(method: str, params: dict = None, timeout: float = _MCP_TIMEOUT) -> dict:
    """Make a JSON-RPC call to the AnySearch MCP server."""
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params or {},
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(_MCP_URL, json=payload, headers=_headers())
        resp.raise_for_status()
        # Handle SSE or JSON response
        ct = resp.headers.get("content-type", "")
        if "text/event-stream" in ct:
            for line in resp.text.split("\n"):
                if line.startswith("data: "):
                    return json.loads(line[6:])
            return {"error": "No data in SSE stream"}
        return resp.json()


class AnySearchProvider(WebSearchProvider):
    """AnySearch MCP-based web search provider."""

    @property
    def name(self) -> str:
        return "anysearch"

    @property
    def display_name(self) -> str:
        return "AnySearch (MCP)"

    def is_available(self) -> bool:
        """Always available (anonymous access)."""
        return True

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute search via AnySearch MCP."""
        try:
            result = _mcp_call("tools/call", {
                "name": "search",
                "arguments": {
                    "query": query,
                    "max_results": min(limit, 20),
                },
            })

            # Parse MCP response
            content = result.get("result", {}).get("content", [])
            if not content:
                error = result.get("error", {})
                if error:
                    return {"success": False, "error": str(error.get("message", error))}
                return {"success": True, "data": {"web": []}}

            # Extract text content from MCP response
            text = ""
            for item in content:
                if item.get("type") == "text":
                    text += item.get("text", "")

            if not text:
                return {"success": True, "data": {"web": []}}

            # Try to parse as JSON (structured results)
            try:
                data = json.loads(text)
                if isinstance(data, dict) and "web" in data:
                    return {"success": True, "data": data}
                if isinstance(data, list):
                    web_results = []
                    for i, hit in enumerate(data[:limit]):
                        web_results.append({
                            "title": hit.get("title", ""),
                            "url": hit.get("url", ""),
                            "description": hit.get("snippet", hit.get("description", "")),
                            "position": i + 1,
                        })
                    return {"success": True, "data": {"web": web_results}}
            except json.JSONDecodeError:
                pass

            # Fallback: return raw text as single result
            return {
                "success": True,
                "data": {"web": [{"title": "Search Result", "url": "", "description": text[:2000], "position": 1}]},
            }

        except Exception as exc:
            logger.warning("AnySearch error: %s", exc)
            return {"success": False, "error": f"AnySearch failed: {exc}"}

    async def extract(self, url: str, timeout: float = 30.0) -> Dict[str, Any]:
        """Extract page content via AnySearch MCP."""
        try:
            result = _mcp_call("tools/call", {
                "name": "extract",
                "arguments": {"url": url},
            }, timeout=timeout)

            content = result.get("result", {}).get("content", [])
            text = ""
            for item in content:
                if item.get("type") == "text":
                    text += item.get("text", "")

            if text:
                return {"success": True, "data": {"markdown": text}}
            return {"success": False, "error": "No content extracted"}

        except Exception as exc:
            logger.warning("AnySearch extract error: %s", exc)
            return {"success": False, "error": f"AnySearch extract failed: {exc}"}

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "AnySearch (MCP)",
            "badge": "free · no key · search + extract · 23 domains",
            "tag": "Unified search via AnySearch MCP — supports web, finance, academic, and 20+ vertical domains",
            "env_vars": [
                {"name": "ANYSEARCH_API_KEY", "description": "Optional API key for higher rate limits", "required": False},
            ],
        }
