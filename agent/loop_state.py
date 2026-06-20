# Source: Loop
# Upstream: https://github.com/loop-ai/loop
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Loop State Management — 管理 Loop 执行状态和进度

跟踪 Loop 执行历史、持久化状态、支持断点续传。

Usage:
    from agent.loop_state import LoopStateManager
    
    manager = LoopStateManager()
    manager.start_loop("code_review", {"code": "..."})
    manager.update_step("code_review", "validate", "success")
    manager.complete_loop("code_review", "success")
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LoopPhase(Enum):
    """Loop execution phase."""
    INIT = "init"
    RUNNING = "running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class StepState:
    """State of a single step."""
    name: str
    status: str = "pending"
    started_at: float = 0.0
    completed_at: float = 0.0
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class LoopState:
    """Complete state of a loop execution."""
    loop_id: str
    template_name: str
    phase: LoopPhase = LoopPhase.INIT
    started_at: float = 0.0
    completed_at: float = 0.0
    steps: Dict[str, StepState] = field(default_factory=dict)
    context_data: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class LoopStateManager:
    """Manages loop execution state with persistence."""
    
    _instance: Optional[LoopStateManager] = None
    
    def __new__(cls) -> LoopStateManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._states: Dict[str, LoopState] = {}
        self._history: List[LoopState] = []
        self._max_history = 50
        self._state_file = Path.home() / ".hermes" / "loop_states.json"
        self._initialized = True
        
        # Load persisted states
        self._load_states()
        
        logger.info("LoopStateManager initialized")
    
    def _load_states(self) -> None:
        """Load persisted states from disk."""
        try:
            if self._state_file.exists():
                with open(self._state_file, 'r') as f:
                    data = json.load(f)
                    for loop_id, state_data in data.items():
                        state = LoopState(
                            loop_id=state_data["loop_id"],
                            template_name=state_data["template_name"],
                            phase=LoopPhase(state_data["phase"]),
                            started_at=state_data["started_at"],
                            completed_at=state_data["completed_at"],
                            context_data=state_data.get("context_data", {}),
                            results=state_data.get("results", {}),
                            errors=state_data.get("errors", []),
                        )
                        self._states[loop_id] = state
                logger.info(f"Loaded {len(self._states)} loop states")
        except Exception as e:
            logger.warning(f"Failed to load loop states: {e}")
    
    def _save_states(self) -> None:
        """Persist states to disk."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            for loop_id, state in self._states.items():
                data[loop_id] = {
                    "loop_id": state.loop_id,
                    "template_name": state.template_name,
                    "phase": state.phase.value,
                    "started_at": state.started_at,
                    "completed_at": state.completed_at,
                    "context_data": state.context_data,
                    "results": state.results,
                    "errors": state.errors,
                }
            with open(self._state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save loop states: {e}")
    
    def start_loop(
        self,
        template_name: str,
        context_data: Optional[Dict[str, Any]] = None,
        loop_id: Optional[str] = None,
    ) -> str:
        """Start a new loop execution."""
        if loop_id is None:
            loop_id = f"{template_name}_{int(time.time())}"
        
        state = LoopState(
            loop_id=loop_id,
            template_name=template_name,
            phase=LoopPhase.RUNNING,
            started_at=time.time(),
            context_data=context_data or {},
        )
        
        self._states[loop_id] = state
        self._save_states()
        
        logger.info(f"Started loop: {loop_id}")
        return loop_id
    
    def update_step(
        self,
        loop_id: str,
        step_name: str,
        status: str,
        result: Any = None,
        error: Optional[str] = None,
    ) -> None:
        """Update the state of a specific step."""
        state = self._states.get(loop_id)
        if state is None:
            logger.warning(f"Loop {loop_id} not found")
            return
        
        step = state.steps.get(step_name)
        if step is None:
            step = StepState(name=step_name)
            state.steps[step_name] = step
        
        step.status = status
        if status == "running":
            step.started_at = time.time()
        elif status in ("success", "failed"):
            step.completed_at = time.time()
        
        if result is not None:
            step.result = result
            state.results[step_name] = result
        
        if error is not None:
            step.error = error
            state.errors.append(f"[{step_name}] {error}")
        
        self._save_states()
    
    def complete_loop(
        self,
        loop_id: str,
        status: str = "success",
        final_results: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark a loop as completed."""
        state = self._states.get(loop_id)
        if state is None:
            logger.warning(f"Loop {loop_id} not found")
            return
        
        state.phase = LoopPhase.COMPLETED if status == "success" else LoopPhase.FAILED
        state.completed_at = time.time()
        
        if final_results:
            state.results.update(final_results)
        
        # Move to history
        self._history.append(state)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        # Remove from active states
        del self._states[loop_id]
        self._save_states()
        
        logger.info(f"Completed loop: {loop_id} ({status})")
    
    def get_state(self, loop_id: str) -> Optional[LoopState]:
        """Get the current state of a loop."""
        return self._states.get(loop_id)
    
    def get_active_loops(self) -> List[LoopState]:
        """Get all active (running) loops."""
        return [s for s in self._states.values() if s.phase == LoopPhase.RUNNING]
    
    def get_history(self, limit: int = 10) -> List[LoopState]:
        """Get recent loop history."""
        return self._history[-limit:]


# Global instance
loop_state_manager = LoopStateManager()
