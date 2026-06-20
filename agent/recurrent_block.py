"""
RecurrentBlock — 来自 OpenMythos 的双层循环架构

核心思想：
- H-level (高层): 每 N 步更新一次，全局规划 (类似 Metis)
- L-level (低层): 每步更新，局部执行 (类似 Enki)
- z_state: 跨步共享的 latent memory (上下文)

在 agent 层面实现：
- carry_h: 高层规划状态 (Metis 的任务拆解结果)
- carry_y: 低层执行状态 (Enki 的当前执行进度)
- carry_z: 共享 latent memory (跨步上下文)
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class CarryState:
    """循环状态 — 类似 OpenMythos 的 carry"""
    
    # H-level: 高层规划状态 (Metis)
    carry_h: Dict = field(default_factory=lambda: {
        "plan": None,           # 当前任务计划
        "subtasks": [],         # 子任务列表
        "current_subtask": 0,   # 当前子任务索引
        "plan_version": 0,      # 计划版本号
        "last_update_iter": 0,  # 上次更新的迭代号
    })
    
    # L-level: 低层执行状态 (Enki)
    carry_y: Dict = field(default_factory=lambda: {
        "current_tool": None,   # 当前使用的工具
        "tool_args": None,      # 当前工具参数
        "tool_result": None,    # 上次工具结果
        "execution_step": 0,    # 执行步骤
        "last_update_iter": 0,  # 上次更新的迭代号
    })
    
    # Z-state: 共享 latent memory (上下文)
    carry_z: Dict = field(default_factory=lambda: {
        "context_summary": None,    # 上下文摘要
        "important_facts": [],      # 重要事实
        "tool_history": [],         # 工具调用历史
        "error_history": [],        # 错误历史
        "last_update_iter": 0,      # 上次更新的迭代号
    })
    
    # 元数据
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    total_iterations: int = 0
    h_level_updates: int = 0
    l_level_updates: int = 0
    
    def reset(self):
        """重置状态"""
        self.carry_h = {
            "plan": None,
            "subtasks": [],
            "current_subtask": 0,
            "plan_version": 0,
            "last_update_iter": 0,
        }
        self.carry_y = {
            "current_tool": None,
            "tool_args": None,
            "tool_result": None,
            "execution_step": 0,
            "last_update_iter": 0,
        }
        self.carry_z = {
            "context_summary": None,
            "important_facts": [],
            "tool_history": [],
            "error_history": [],
            "last_update_iter": 0,
        }
        self.total_iterations = 0
        self.h_level_updates = 0
        self.l_level_updates = 0


class RecurrentBlock:
    """
    循环块 — 双层循环架构
    
    类似 OpenMythos 的 RecurrentBlock:
    - H-level: 每 N 步更新一次 (全局规划)
    - L-level: 每步更新 (局部执行)
    - z_state: 跨步共享的 latent memory
    """
    
    def __init__(self, h_level_interval: int = 5):
        """
        Args:
            h_level_interval: H-level 更新间隔 (每 N 步更新一次)
        """
        self.state = CarryState()
        self.h_level_interval = h_level_interval
    
    def step(
        self,
        iteration: int,
        had_tool_calls: bool,
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict] = None,
        tool_result: Optional[str] = None,
        error: Optional[str] = None,
        context_summary: Optional[str] = None,
    ) -> Dict:
        """
        执行一步循环
        
        返回: 更新后的状态摘要
        """
        self.state.total_iterations = iteration
        
        # L-level: 每步更新
        self._update_l_level(iteration, had_tool_calls, tool_name, tool_args, tool_result, error)
        
        # H-level: 每 N 步更新
        if iteration % self.h_level_interval == 0:
            self._update_h_level(iteration, context_summary)
        
        # Z-state: 每步更新
        self._update_z_state(iteration, had_tool_calls, tool_name, tool_result, error, context_summary)
        
        return self.get_status()
    
    def _update_l_level(
        self,
        iteration: int,
        had_tool_calls: bool,
        tool_name: Optional[str],
        tool_args: Optional[Dict],
        tool_result: Optional[str],
        error: Optional[str],
    ):
        """更新 L-level (低层执行状态)"""
        self.state.carry_y["execution_step"] = iteration
        self.state.carry_y["last_update_iter"] = iteration
        
        if had_tool_calls:
            self.state.carry_y["current_tool"] = tool_name
            self.state.carry_y["tool_args"] = tool_args
            self.state.carry_y["tool_result"] = tool_result
        
        self.state.l_level_updates += 1
    
    def _update_h_level(self, iteration: int, context_summary: Optional[str]):
        """更新 H-level (高层规划状态)"""
        # 在 agent 层面，H-level 更新意味着重新评估任务计划
        # 这里只记录状态，实际的计划更新由 Metis 角色负责
        self.state.carry_h["last_update_iter"] = iteration
        self.state.carry_h["plan_version"] += 1
        self.state.h_level_updates += 1
    
    def _update_z_state(
        self,
        iteration: int,
        had_tool_calls: bool,
        tool_name: Optional[str],
        tool_result: Optional[str],
        error: Optional[str],
        context_summary: Optional[str],
    ):
        """更新 Z-state (共享 latent memory)"""
        # 记录工具调用历史
        if had_tool_calls and tool_name:
            self.state.carry_z["tool_history"].append({
                "iteration": iteration,
                "tool": tool_name,
                "result_preview": str(tool_result)[:100] if tool_result else None,
            })
        
        # 记录错误历史
        if error:
            self.state.carry_z["error_history"].append({
                "iteration": iteration,
                "error": str(error)[:200],
            })
        
        # 更新上下文摘要
        if context_summary:
            self.state.carry_z["context_summary"] = context_summary
        
        self.state.carry_z["last_update_iter"] = iteration
    
    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            "total_iterations": self.state.total_iterations,
            "h_level_updates": self.state.h_level_updates,
            "l_level_updates": self.state.l_level_updates,
            "carry_h": self.state.carry_h.copy(),
            "carry_y": self.state.carry_y.copy(),
            "carry_z": {
                "context_summary": self.state.carry_z["context_summary"],
                "tool_history_count": len(self.state.carry_z["tool_history"]),
                "error_history_count": len(self.state.carry_z["error_history"]),
                "important_facts_count": len(self.state.carry_z["important_facts"]),
            },
        }
    
    def get_status_line(self) -> str:
        """获取状态行"""
        return (
            f"🔁 H:{self.state.h_level_updates} L:{self.state.l_level_updates} "
            f"| 🔧 Tools:{len(self.state.carry_z['tool_history'])} "
            f"| ❌ Errors:{len(self.state.carry_z['error_history'])}"
        )


# ── 全局实例 ────────────────────────────────────────────────────
_blocks: Dict[str, RecurrentBlock] = {}

def get_recurrent_block(session_id: str, h_level_interval: int = 5) -> RecurrentBlock:
    if session_id not in _blocks:
        _blocks[session_id] = RecurrentBlock(h_level_interval)
    return _blocks[session_id]

def reset_recurrent_block(session_id: str):
    if session_id in _blocks:
        _blocks[session_id].state.reset()
