# Source: ReWOO
# Upstream: https://github.com/SeungoneKim/ReWOO
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
ReWOO Planning Module — 无观察推理策略

先规划所有步骤，再批量执行，减少中间 token 消耗。
移植自 AutoGPT 的 ReWOO 策略，适配 Hermes 架构。

Usage:
    from agent.rewoo import ReWOOPlanner
    
    planner = ReWOOPlanner()
    plan = planner.create_plan("帮我检查服务器状态，清理 /tmp，然后重启 nginx")
    results = planner.execute_plan(plan)
    summary = planner.summarize_results(plan, results)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StepStatus(str, Enum):
    """步骤执行状态"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """单个计划步骤"""
    step_id: int
    tool: str
    args: Dict[str, Any]
    dependencies: List[int] = field(default_factory=list)
    description: str = ""
    status: StepStatus = StepStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ReWOOPlan:
    """ReWOO 执行计划"""
    task: str
    steps: List[PlanStep]
    evidence: Dict[int, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ReWOOPlanner:
    """ReWOO 规划器"""
    
    def __init__(self):
        self.plan: Optional[ReWOOPlan] = None
    
    def create_plan(
        self,
        task: str,
        context: Optional[str] = None
    ) -> ReWOOPlan:
        """
        创建 ReWOO 执行计划
        
        Args:
            task: 任务描述
            context: 额外上下文
            
        Returns:
            ReWOOPlan 对象
        """
        # 这里应该调用 LLM 生成计划
        # 为了演示，使用简单的规则引擎
        steps = self._generate_steps(task, context)
        
        self.plan = ReWOOPlan(
            task=task,
            steps=steps,
            metadata={
                "created_by": "metis",
                "strategy": "rewoo",
            }
        )
        
        logger.info(f"ReWOO plan created: {len(steps)} steps for task: {task[:50]}...")
        return self.plan
    
    def _generate_steps(
        self,
        task: str,
        context: Optional[str]
    ) -> List[PlanStep]:
        """
        生成执行步骤（规则引擎版本）
        
        实际实现应该调用 LLM 生成更精确的计划
        """
        steps = []
        step_id = 1
        
        # 简单的任务分解规则
        task_lower = task.lower()
        
        # 检查类任务
        if any(kw in task_lower for kw in ['检查', '查看', '状态', 'check', 'status']):
            steps.append(PlanStep(
                step_id=step_id,
                tool="terminal",
                args={"command": "echo '检查任务开始'"},
                description="初始化检查任务",
            ))
            step_id += 1
            
            if '服务器' in task_lower or 'server' in task_lower:
                steps.append(PlanStep(
                    step_id=step_id,
                    tool="terminal",
                    args={"command": "uptime && free -h && df -h"},
                    dependencies=[step_id - 1],
                    description="检查服务器状态",
                ))
                step_id += 1
        
        # 清理类任务
        if any(kw in task_lower for kw in ['清理', '清除', 'clean', 'clear']):
            steps.append(PlanStep(
                step_id=step_id,
                tool="terminal",
                args={"command": "du -sh /tmp"},
                description="检查 /tmp 使用情况",
            ))
            step_id += 1
            
            steps.append(PlanStep(
                step_id=step_id,
                tool="terminal",
                args={"command": "rm -rf /tmp/*"},
                dependencies=[step_id - 1],
                description="清理 /tmp",
            ))
            step_id += 1
        
        # 重启类任务
        if any(kw in task_lower for kw in ['重启', 'restart']):
            steps.append(PlanStep(
                step_id=step_id,
                tool="terminal",
                args={"command": "systemctl restart nginx"},
                description="重启 nginx",
            ))
            step_id += 1
            
            steps.append(PlanStep(
                step_id=step_id,
                tool="terminal",
                args={"command": "systemctl status nginx"},
                dependencies=[step_id - 1],
                description="验证重启结果",
            ))
            step_id += 1
        
        # 如果没有匹配到规则，创建通用步骤
        if not steps:
            steps.append(PlanStep(
                step_id=step_id,
                tool="terminal",
                args={"command": f"echo '执行任务: {task}'"},
                description="执行任务",
            ))
        
        return steps
    
    def get_executable_steps(self) -> List[PlanStep]:
        """
        获取当前可执行的步骤（依赖已满足）
        
        Returns:
            可执行的步骤列表
        """
        if not self.plan:
            return []
        
        executable = []
        for step in self.plan.steps:
            if step.status != StepStatus.PENDING:
                continue
            
            # 检查依赖是否都已完成
            deps_satisfied = all(
                self.plan.steps[dep - 1].status == StepStatus.COMPLETED
                for dep in step.dependencies
            )
            
            if deps_satisfied:
                executable.append(step)
        
        return executable
    
    def mark_step_completed(
        self,
        step_id: int,
        result: str
    ) -> None:
        """标记步骤完成"""
        if not self.plan:
            return
        
        step = self.plan.steps[step_id - 1]
        step.status = StepStatus.COMPLETED
        step.result = result
        self.plan.evidence[step_id] = result
        
        logger.info(f"Step {step_id} completed: {result[:50]}...")
    
    def mark_step_failed(
        self,
        step_id: int,
        error: str
    ) -> None:
        """标记步骤失败"""
        if not self.plan:
            return
        
        step = self.plan.steps[step_id - 1]
        step.status = StepStatus.FAILED
        step.error = error
        
        # 跳过依赖此步骤的后续步骤
        for subsequent in self.plan.steps:
            if step_id in subsequent.dependencies:
                subsequent.status = StepStatus.SKIPPED
        
        logger.error(f"Step {step_id} failed: {error}")
    
    def is_plan_complete(self) -> bool:
        """检查计划是否完成"""
        if not self.plan:
            return False
        
        return all(
            step.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for step in self.plan.steps
        )
    
    def get_plan_progress(self) -> Dict[str, Any]:
        """获取计划进度"""
        if not self.plan:
            return {"total": 0, "completed": 0, "failed": 0, "pending": 0}
        
        total = len(self.plan.steps)
        completed = sum(1 for s in self.plan.steps if s.status == StepStatus.COMPLETED)
        failed = sum(1 for s in self.plan.steps if s.status == StepStatus.FAILED)
        pending = sum(1 for s in self.plan.steps if s.status == StepStatus.PENDING)
        
        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "progress": f"{completed}/{total} ({completed/total*100:.0f}%)" if total > 0 else "0/0",
        }
    
    def summarize_results(
        self,
        plan: ReWOOPlan,
        results: Dict[int, str]
    ) -> str:
        """
        汇总执行结果
        
        Args:
            plan: 执行计划
            results: 执行结果
            
        Returns:
            汇总文本
        """
        summary_parts = [f"任务: {plan.task}", ""]
        
        for step in plan.steps:
            if step.status == StepStatus.COMPLETED:
                summary_parts.append(f"✓ 步骤 {step.step_id}: {step.description}")
                if step.step_id in results:
                    summary_parts.append(f"  结果: {results[step.step_id][:100]}...")
            elif step.status == StepStatus.FAILED:
                summary_parts.append(f"✗ 步骤 {step.step_id}: {step.description}")
                summary_parts.append(f"  错误: {step.error}")
            elif step.status == StepStatus.SKIPPED:
                summary_parts.append(f"⊘ 步骤 {step.step_id}: {step.description} (已跳过)")
        
        return "\n".join(summary_parts)
    
    def to_json(self) -> str:
        """导出计划为 JSON"""
        if not self.plan:
            return "{}"
        
        return json.dumps({
            "task": self.plan.task,
            "steps": [
                {
                    "step_id": s.step_id,
                    "tool": s.tool,
                    "args": s.args,
                    "dependencies": s.dependencies,
                    "description": s.description,
                    "status": s.status.value,
                    "result": s.result,
                    "error": s.error,
                }
                for s in self.plan.steps
            ],
            "evidence": self.plan.evidence,
            "metadata": self.plan.metadata,
        }, ensure_ascii=False, indent=2)
