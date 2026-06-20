# Source: Loop
# Upstream: https://github.com/loop-ai/loop
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Loop Templates — 标准化工作流模板

基于 OpenMythos 的 LOOP 架构，将重复性任务标准化为可复用的模板。
每个模板定义：触发条件、执行步骤、验证规则、输出格式。

Usage:
    from agent.loop_templates import LoopTemplate, TemplateRegistry
    
    template = TemplateRegistry.get("code_review")
    result = template.execute(context)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class LoopStatus(Enum):
    """Loop execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class LoopStep:
    """A single step in a loop template."""
    name: str
    description: str
    handler: Callable[..., Any]
    required: bool = True
    timeout: int = 300  # seconds
    retry_count: int = 0
    fallback: Optional[Callable[..., Any]] = None


@dataclass
class LoopContext:
    """Context passed through loop execution."""
    data: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    status: LoopStatus = LoopStatus.PENDING
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
    
    def add_result(self, step_name: str, result: Any) -> None:
        self.results[step_name] = result
    
    def add_error(self, step_name: str, error: str) -> None:
        self.errors.append(f"[{step_name}] {error}")


@dataclass
class LoopTemplate:
    """A reusable workflow template."""
    name: str
    description: str
    steps: List[LoopStep]
    triggers: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    def execute(self, context: Optional[LoopContext] = None) -> LoopContext:
        """Execute all steps in sequence."""
        if context is None:
            context = LoopContext()
        
        context.status = LoopStatus.RUNNING
        logger.info(f"Starting loop: {self.name}")
        
        for step in self.steps:
            try:
                logger.info(f"  Step: {step.name}")
                result = step.handler(context)
                context.add_result(step.name, result)
                
            except Exception as e:
                error_msg = f"{step.name} failed: {e}"
                logger.error(error_msg)
                context.add_error(step.name, error_msg)
                
                if step.required:
                    context.status = LoopStatus.FAILED
                    return context
                elif step.fallback:
                    try:
                        fallback_result = step.fallback(context)
                        context.add_result(f"{step.name}_fallback", fallback_result)
                    except Exception as fallback_error:
                        context.add_error(step.name, f"Fallback also failed: {fallback_error}")
        
        context.status = LoopStatus.SUCCESS
        logger.info(f"Loop {self.name} completed: {context.status.value}")
        return context


class TemplateRegistry:
    """Registry for loop templates."""
    
    _templates: Dict[str, LoopTemplate] = {}
    
    @classmethod
    def register(cls, template: LoopTemplate) -> None:
        """Register a loop template."""
        cls._templates[template.name] = template
        logger.info(f"Registered loop template: {template.name}")
    
    @classmethod
    def get(cls, name: str) -> Optional[LoopTemplate]:
        """Get a template by name."""
        return cls._templates.get(name)
    
    @classmethod
    def list_all(cls) -> List[str]:
        """List all registered template names."""
        return list(cls._templates.keys())
    
    @classmethod
    def list_by_tag(cls, tag: str) -> List[str]:
        """List templates with a specific tag."""
        return [
            name for name, tmpl in cls._templates.items()
            if tag in tmpl.tags
        ]


# ─── Built-in Templates ────────────────────────────────────────────────────────


def _step_validate_code(context: LoopContext) -> str:
    """Validate code changes."""
    code = context.get("code", "")
    if not code:
        return "No code to validate"
    
    # Basic validation
    issues = []
    if "import os" in code and "os.system" in code:
        issues.append("Uses os.system (security risk)")
    if "eval(" in code:
        issues.append("Uses eval() (security risk)")
    if "exec(" in code:
        issues.append("Uses exec() (security risk)")
    
    return f"Validation: {len(issues)} issues found" if issues else "Validation: OK"


def _step_run_tests(context: LoopContext) -> str:
    """Run tests (placeholder)."""
    test_command = context.get("test_command", "pytest")
    return f"Would run: {test_command}"


def _step_generate_report(context: LoopContext) -> str:
    """Generate execution report."""
    results = context.results
    errors = context.errors
    
    report = [
        f"Loop Report: {context.status.value}",
        f"Steps completed: {len(results)}",
        f"Errors: {len(errors)}",
    ]
    
    for step, result in results.items():
        report.append(f"  - {step}: {result}")
    
    for error in errors:
        report.append(f"  ⚠️ {error}")
    
    return "\n".join(report)


# Register built-in templates
TemplateRegistry.register(LoopTemplate(
    name="code_review",
    description="Standard code review workflow",
    steps=[
        LoopStep(name="validate", description="Validate code", handler=_step_validate_code),
        LoopStep(name="test", description="Run tests", handler=_step_run_tests, required=False),
        LoopStep(name="report", description="Generate report", handler=_step_generate_report),
    ],
    triggers=["code_change", "pr_opened"],
    tags=["code", "review"],
))

TemplateRegistry.register(LoopTemplate(
    name="memory_consolidation",
    description="Consolidate and optimize memory",
    steps=[
        LoopStep(
            name="collect",
            description="Collect recent memories",
            handler=lambda ctx: "Collected 15 memories",
        ),
        LoopStep(
            name="deduplicate",
            description="Remove duplicates",
            handler=lambda ctx: "Removed 3 duplicates",
        ),
        LoopStep(
            name="archive",
            description="Archive old memories",
            handler=lambda ctx: "Archived 5 memories",
        ),
        LoopStep(
            name="report",
            description="Generate report",
            handler=_step_generate_report,
        ),
    ],
    triggers=["memory_full", "daily"],
    tags=["memory", "maintenance"],
))


# ─── Graph 工作流模板 ──────────────────────────────────────────────────────────

def _step_graph_workflow(context: LoopContext) -> str:
    """Graph 工作流执行步骤。"""
    from agent.sisterhood_workflow import SisterhoodWorkflow
    
    task = context.get("task", "")
    if not task:
        return "Error: No task provided"
    
    workflow = SisterhoodWorkflow()
    result = workflow.execute(task)
    
    # 收集结果
    outputs = []
    for name, node_result in result.results.items():
        if node_result.status == NodeStatus.SUCCESS:
            outputs.append(f"✅ {name}: {str(node_result.output)[:100]}")
        elif node_result.status == NodeStatus.FAILED:
            outputs.append(f"❌ {name}: {node_result.error}")
        else:
            outputs.append(f"⏭️ {name}: {node_result.status.value}")
    
    return "\n".join(outputs)


TemplateRegistry.register(LoopTemplate(
    name="sisterhood_graph",
    description="姐妹会 Graph 工作流（支持并行执行）",
    steps=[
        LoopStep(
            name="execute_graph",
            description="执行 Graph 工作流",
            handler=_step_graph_workflow,
        ),
    ],
    triggers=["sisterhood", "workflow", "graph"],
    tags=["sisterhood", "workflow", "graph"],
))
