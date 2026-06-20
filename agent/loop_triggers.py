# Source: Loop
# Upstream: https://github.com/loop-ai/loop
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Loop Triggers — 事件驱动的自动触发系统

监听系统事件，自动触发对应的 Loop 模板执行。

Usage:
    from agent.loop_triggers import TriggerManager
    
    manager = TriggerManager()
    manager.register_trigger("code_change", "code_review")
    manager.emit("code_change", {"code": "..."})
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent.loop_templates import LoopContext, LoopTemplate, TemplateRegistry

logger = logging.getLogger(__name__)


@dataclass
class TriggerEvent:
    """An event that can trigger loops."""
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: float = 0.0


class TriggerManager:
    """Manages event-driven loop triggers."""
    
    _instance: Optional[TriggerManager] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> TriggerManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._triggers: Dict[str, List[str]] = defaultdict(list)  # event -> template names
        self._handlers: Dict[str, Callable] = {}  # event -> handler
        self._history: List[TriggerEvent] = []
        self._max_history = 100
        self._initialized = True
        
        logger.info("TriggerManager initialized")
    
    def register_trigger(self, event_name: str, template_name: str) -> None:
        """Register a template to be triggered by an event."""
        if template_name not in TemplateRegistry.list_all():
            logger.warning(f"Template {template_name} not found in registry")
            return
        
        self._triggers[event_name].append(template_name)
        logger.info(f"Registered trigger: {event_name} -> {template_name}")
    
    def register_handler(self, event_name: str, handler: Callable) -> None:
        """Register a custom handler for an event."""
        self._handlers[event_name] = handler
        logger.info(f"Registered handler for: {event_name}")
    
    def emit(self, event_name: str, data: Optional[Dict[str, Any]] = None) -> List[LoopContext]:
        """Emit an event, triggering all registered templates."""
        import time
        
        event = TriggerEvent(
            name=event_name,
            data=data or {},
            timestamp=time.time(),
        )
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        logger.info(f"Event emitted: {event_name}")
        
        # Run custom handler if registered
        if event_name in self._handlers:
            try:
                self._handlers[event_name](event)
            except Exception as e:
                logger.error(f"Handler error for {event_name}: {e}")
        
        # Run triggered templates
        results = []
        template_names = self._triggers.get(event_name, [])
        
        for template_name in template_names:
            template = TemplateRegistry.get(template_name)
            if template is None:
                logger.warning(f"Template {template_name} not found")
                continue
            
            context = LoopContext(data=data or {})
            result = template.execute(context)
            results.append(result)
        
        return results
    
    def get_history(self, limit: int = 10) -> List[TriggerEvent]:
        """Get recent trigger history."""
        return self._history[-limit:]
    
    def get_triggers(self) -> Dict[str, List[str]]:
        """Get all registered triggers."""
        return dict(self._triggers)


# Global instance
trigger_manager = TriggerManager()
