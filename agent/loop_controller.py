"""
Loop Controller v2 — 四路融合控制器

整合:
1. LTI Injection (OpenMythos) — 可学习 prompt 注入
2. Task Complexity (HRM) — 任务复杂度评估
3. ACT Controller (OpenMythos) — 动态迭代控制
4. RecurrentBlock (OpenMythos) — 双层循环架构
5. Post-Response Hook (Loop 设计) — 上下文保存
6. 可视化监控 — 状态行

这是集成入口，供 conversation_loop.py 调用。
"""

from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass

from agent.lti_injection import LTIInjector, get_lti_injector
from agent.task_complexity import (
    TaskComplexityAssessor,
    ComplexityLevel,
    get_complexity_assessor,
)
from agent.act_controller import ACTController, get_act_controller, reset_act_controller
from agent.recurrent_block import RecurrentBlock, get_recurrent_block, reset_recurrent_block
from agent.lora_adapter import LoRAAdapter, get_lora_adapter


@dataclass
class LoopState:
    """Loop 控制器状态"""
    session_id: str
    complexity: ComplexityLevel = ComplexityLevel.MEDIUM
    complexity_metadata: Dict = None
    lti_metadata: Dict = None
    lora_metadata: Dict = None
    act_metadata: Dict = None
    recurrent_status: Dict = None
    initialized: bool = False


class LoopController:
    """
    Loop v2 控制器 — 四路融合
    
    职责:
    1. 预处理: 评估任务复杂度 + 注入 LTI tokens
    2. 迭代控制: ACT 动态停止 + RecurrentBlock 状态维护
    3. 后处理: Post-Response Hook + 可视化
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.lti = get_lti_injector()
        self.assessor = get_complexity_assessor()
        self.lora = get_lora_adapter()
        self.act: Optional[ACTController] = None
        self.recurrent: Optional[RecurrentBlock] = None
        self.state = LoopState(session_id=session_id)
    
    def initialize(
        self,
        user_message: str,
        system_message: str,
        context_summary: Optional[str] = None,
        topic_memory: Optional[str] = None,
    ) -> Tuple[str, int, Dict]:
        """
        初始化 Loop — 在对话开始时调用
        
        返回: (增强后的 system_message, 初始 max_iterations, 初始化元数据)
        """
        # 1. 评估任务复杂度
        complexity, comp_meta = self.assessor.assess(user_message)
        self.state.complexity = complexity
        self.state.complexity_metadata = comp_meta
        
        # 2. 获取初始 max_iterations
        initial_max = self.assessor.get_max_iterations(complexity)
        
        # 3. 初始化 ACT 控制器
        reset_act_controller(self.session_id)
        self.act = get_act_controller(self.session_id, initial_max)
        
        # 4. 初始化 RecurrentBlock
        reset_recurrent_block(self.session_id)
        self.recurrent = get_recurrent_block(self.session_id)
        
        # 5. 注入 LTI tokens
        enhanced_system, lti_meta = self.lti.inject(
            system_message=system_message,
            user_message=user_message,
            complexity=complexity.value,
            context_summary=context_summary,
            topic_memory=topic_memory,
        )
        self.state.lti_metadata = lti_meta
        
        # 6. 应用 LoRA Adapter
        task_category = lti_meta.get("task_category", "general")
        enhanced_system, lora_meta = self.lora.get_enhanced_system_prompt(
            base_system=enhanced_system,
            task_category=task_category,
            complexity=complexity.value,
        )
        self.state.lora_metadata = lora_meta
        
        # 6. 标记初始化完成
        self.state.initialized = True
        
        init_meta = {
            "complexity": complexity.value,
            "initial_max": initial_max,
            "reasoning_effort": comp_meta.get("reasoning_effort", "medium"),
            "lti_injected": lti_meta.get("injected", False),
            "task_type": lti_meta.get("task_type", "unknown"),
            "task_category": lti_meta.get("task_category", "general"),
            "preferred_tools": lti_meta.get("preferred_tools", []),
        }
        
        return enhanced_system, initial_max, init_meta
    
    def step(
        self,
        iteration: int,
        had_tool_calls: bool,
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict] = None,
        tool_result: Optional[str] = None,
        error: Optional[str] = None,
        iteration_budget_remaining: int = 0,
        response_text: Optional[str] = None,
    ) -> Tuple[bool, Dict]:
        """
        执行一步迭代控制
        
        返回: (是否继续, 步骤元数据)
        """
        if not self.state.initialized:
            return True, {"error": "not_initialized"}
        
        # 1. ACT 控制（传递 response_text 用于完成检测）
        should_continue, act_meta = self.act.should_continue(
            api_call_count=iteration,
            had_tool_calls=had_tool_calls,
            iteration_budget_remaining=iteration_budget_remaining,
            response_text=response_text,
        )
        self.state.act_metadata = act_meta
        
        # 2. RecurrentBlock 状态更新
        rec_status = self.recurrent.step(
            iteration=iteration,
            had_tool_calls=had_tool_calls,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            error=error,
        )
        self.state.recurrent_status = rec_status
        
        # 3. 构建步骤元数据
        step_meta = {
            "iteration": iteration,
            "should_continue": should_continue,
            "act": act_meta,
            "recurrent": rec_status,
            "status_line": self.get_status_line(iteration),
        }
        
        return should_continue, step_meta
    
    def get_status_line(self, iteration: int) -> str:
        """获取状态行"""
        if not self.state.initialized:
            return "🔄 Loop: not initialized"
        
        act_line = self.act.get_status_line(iteration) if self.act else ""
        rec_line = self.recurrent.get_status_line() if self.recurrent else ""
        
        return f"{act_line} | {rec_line}"
    
    def get_initialization_summary(self) -> str:
        """获取初始化摘要"""
        if not self.state.initialized:
            return "❌ Loop not initialized"
        
        meta = self.state.complexity_metadata or {}
        lti = self.state.lti_metadata or {}
        lora = self.state.lora_metadata or {}
        
        lines = [
            f"🎯 Task: {self.state.complexity.value}",
            f"🔄 Max Iterations: {meta.get('max_iterations', '?')}",
            f"⚡ Reasoning: {meta.get('reasoning_effort', '?')}",
            f"🔧 LTI: {'ON' if lti.get('injected') else 'OFF'}",
            f"🧬 Adapter: {lora.get('adapter_name', 'default')}",
        ]
        
        if lti.get("preferred_tools"):
            lines.append(f"🛠️ Tools: {', '.join(lti['preferred_tools'])}")
        
        return " | ".join(lines)
    
    def cleanup(self):
        """清理资源"""
        self.state.initialized = False


# ── 便捷函数 ────────────────────────────────────────────────────
def create_loop_controller(session_id: str) -> LoopController:
    """创建 Loop 控制器"""
    return LoopController(session_id)
