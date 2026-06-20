"""
ACT (Adaptive Computation Time) Controller v3 — 真正的自主循环

核心理念：
- 模型自己决定什么时候完成，而不是由启发式规则决定
- 连续无工具调用 ≠ 任务完成（模型可能在思考、规划、写总结）
- 只有明确的完成信号或预算耗尽才停止循环

停止条件（保守）：
1. 模型明确说"done"/"完成"/"任务完成"（通过 response 检测）
2. 预算完全耗尽
3. 连续无工具调用达到高阈值（默认 8，可配置）
4. 明确的错误/死循环检测
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import re

@dataclass
class ACTState:
    """ACT 控制器状态"""
    initial_max: int = 30
    current_max: int = 30
    iteration_history: List[Dict] = field(default_factory=list)
    halting_score: float = 0.0
    p_continue: float = 1.0
    steps_survived: float = 0.0
    consecutive_no_tools: int = 0
    task_completion_score: float = 0.0
    max_extensions: int = 5          # 允许更多扩展
    extension_count: int = 0
    total_tool_calls: int = 0
    total_errors: int = 0
    consecutive_errors: int = 0
    
    def reset(self, initial_max: int = 30):
        self.initial_max = initial_max
        self.current_max = initial_max
        self.iteration_history.clear()
        self.halting_score = 0.0
        self.p_continue = 1.0
        self.steps_survived = 0.0
        self.consecutive_no_tools = 0
        self.task_completion_score = 0.0
        self.extension_count = 0
        self.total_tool_calls = 0
        self.total_errors = 0
        self.consecutive_errors = 0


class ACTController:
    """ACT 控制器 v3 — 真正的自主循环"""
    
    # 模型完成信号的模式
    DONE_PATTERNS = [
        r"(?i)\bt(?:as|sk)\s*(?:is\s+)?(?:done|complete(?:d|finished)?|finished)\b",
        r"(?i)\b(?:all|everything)\s+(?:is\s+)?(?:done|complete|finished)\b",
        r"(?i)\b任务[已完]*(?:成|毕|结|了)\b",
        r"(?i)\b(?:全部|所有|一切)[已完]*(?:成|毕|结)\b",
        r"(?i)\bdeliver(?:y|ed)?\s+(?:complete|done)\b",
    ]
    
    def __init__(self, initial_max: int = 30, max_no_tools: int = 8):
        self.state = ACTState(initial_max=initial_max, current_max=initial_max)
        self.max_no_tools = max_no_tools
    
    def should_continue(
        self,
        api_call_count: int,
        had_tool_calls: bool,
        iteration_budget_remaining: int,
        response_quality: float = 0.5,
        response_text: Optional[str] = None,
    ) -> Tuple[bool, Dict]:
        self._update_state(had_tool_calls, response_quality)
        self._compute_halting_score()
        self._compute_p_continue(api_call_count, iteration_budget_remaining)
        should_stop, stop_reason = self._check_stop_conditions(
            api_call_count, iteration_budget_remaining, response_text
        )
        
        metadata = {
            "api_call_count": api_call_count,
            "max_iterations": self.state.current_max,
            "halting_score": self.state.halting_score,
            "p_continue": self.state.p_continue,
            "steps_survived": self.state.steps_survived,
            "consecutive_no_tools": self.state.consecutive_no_tools,
            "total_tool_calls": self.state.total_tool_calls,
            "task_completion": self.state.task_completion_score,
            "should_stop": should_stop,
            "stop_reason": stop_reason,
            "extension_count": self.state.extension_count,
        }
        
        if should_stop:
            return False, metadata
        
        if self._should_extend(api_call_count, iteration_budget_remaining):
            self._extend_max()
            metadata["extended"] = True
            metadata["new_max"] = self.state.current_max
        
        return api_call_count < self.state.current_max, metadata
    
    def _update_state(self, had_tool_calls: bool, response_quality: float):
        self.state.iteration_history.append({"had_tools": had_tool_calls, "quality": response_quality})
        if not had_tool_calls:
            self.state.consecutive_no_tools += 1
        else:
            self.state.consecutive_no_tools = 0
            self.state.total_tool_calls += 1
            self.state.consecutive_errors = 0  # 成功工具调用重置错误计数
        self.state.steps_survived += self.state.p_continue
    
    def _compute_halting_score(self):
        """halting_score 只用于 p_continue 计算，不再作为 task_completion_score"""
        if not self.state.iteration_history:
            self.state.halting_score = 0.0
            return
        recent = self.state.iteration_history[-5:]
        tool_calls_per_iter = sum(1 for h in recent if h.get("had_tools")) / len(recent)
        if tool_calls_per_iter < 0.1:
            self.state.halting_score = 0.6  # 降低，不再直接触发停止
        elif tool_calls_per_iter < 0.3:
            self.state.halting_score = 0.4
        elif tool_calls_per_iter < 0.5:
            self.state.halting_score = 0.2
        else:
            self.state.halting_score = 0.1
    
    def _compute_p_continue(self, api_call_count: int, budget_remaining: int):
        base_continue = 1.0 - self.state.halting_score
        budget_ratio = budget_remaining / max(self.state.initial_max, 1)
        budget_factor = min(1.0, budget_ratio * 2)
        self.state.p_continue = base_continue * budget_factor
    
    def _check_stop_conditions(
        self,
        api_call_count: int,
        budget_remaining: int,
        response_text: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        # 1. 预算完全耗尽
        if budget_remaining <= 0 and api_call_count >= self.state.current_max:
            return True, "budget_exhausted"
        
        # 2. 连续错误过多（真正的死循环检测）
        if self.state.consecutive_errors >= 5:
            return True, "consecutive_errors"
        
        # 3. 连续无工具调用（高阈值，允许长时间思考/写作）
        if self.state.consecutive_no_tools >= self.max_no_tools:
            return True, "consecutive_no_tools"
        
        # 4. 模型明确说完成
        if response_text and self._detect_completion_signal(response_text):
            # 只有在至少调用过一次工具后才接受完成信号
            # 防止模型一开始就"完成"
            if self.state.total_tool_calls > 0:
                return True, "task_completed"
        
        return False, None
    
    def _detect_completion_signal(self, text: str) -> bool:
        """检测模型是否明确表示任务完成"""
        if not text:
            return False
        for pattern in self.DONE_PATTERNS:
            if re.search(pattern, text):
                return True
        return False
    
    def record_error(self):
        """记录一次错误（由调用方报告）"""
        self.state.total_errors += 1
        self.state.consecutive_errors += 1
    
    def reset_error_streak(self):
        """重置连续错误计数"""
        self.state.consecutive_errors = 0
    
    def mark_task_complete(self, reason: str = "explicit"):
        """外部标记任务完成（例如模型在响应中明确说完成）"""
        self.state.task_completion_score = 1.0
    
    def _should_extend(self, api_call_count: int, budget_remaining: int) -> bool:
        if self.state.extension_count >= self.state.max_extensions:
            return False
        if (api_call_count > self.state.current_max * 0.8
            and self.state.task_completion_score < 0.5
            and budget_remaining > self.state.current_max * 0.3):
            return True
        return False
    
    def _extend_max(self):
        self.state.current_max = min(int(self.state.current_max * 1.5), 120)
        self.state.extension_count += 1
    
    def get_status_line(self, api_call_count: int) -> str:
        return (
            f"🔄 Loop: {api_call_count}/{self.state.current_max} "
            f"| 🔧 Tools: {self.state.total_tool_calls} "
            f"| ⏸ NoTool: {self.state.consecutive_no_tools}/{self.max_no_tools}"
        )


_controllers: Dict[str, ACTController] = {}

def get_act_controller(session_id: str, initial_max: int = 30, max_no_tools: int = 8) -> ACTController:
    if session_id not in _controllers:
        _controllers[session_id] = ACTController(initial_max, max_no_tools)
    return _controllers[session_id]

def reset_act_controller(session_id: str):
    if session_id in _controllers:
        _controllers[session_id].state.reset()
