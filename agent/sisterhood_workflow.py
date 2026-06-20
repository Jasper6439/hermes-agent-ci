# Source: Langflow
# Upstream: https://github.com/langflow-ai/langflow
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Sisterhood Workflow — 姐妹会工作流封装

基于 Graph 引擎的姐妹会标准工作流。

Usage:
    from agent.sisterhood_workflow import SisterhoodWorkflow
    
    workflow = SisterhoodWorkflow()
    result = workflow.execute("优化记忆系统")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent.graph_engine import (
    AgentNode,
    Edge,
    GraphContext,
    Node,
    NodeResult,
    NodeStatus,
    ParallelGroup,
    ToolNode,
    WorkflowGraph,
)

logger = logging.getLogger(__name__)


class SisterhoodWorkflow:
    """姐妹会标准工作流。"""
    
    def __init__(self):
        self._graph = self._build_standard_workflow()
        logger.info("SisterhoodWorkflow initialized")
    
    def _build_standard_workflow(self) -> WorkflowGraph:
        """构建标准工作流图。"""
        return WorkflowGraph(
            name="sisterhood_standard",
            nodes=[
                # Phase 1: Metis 设计
                AgentNode(
                    name="metis",
                    role="metis",
                    input_keys=["task"],
                    output_key="design",
                    timeout=600,
                ),
                
                # Phase 2: Enki 实施
                AgentNode(
                    name="enki",
                    role="enki",
                    input_keys=["task", "design"],
                    output_key="implementation",
                    timeout=600,
                ),
                
                # Phase 3: Persephone 双向验证（正向+负面）
                AgentNode(
                    name="persephone",
                    role="persephone",
                    input_keys=["task", "implementation"],
                    output_key="test_report",
                    timeout=600,
                ),
                
                # Phase 4: Socrates 审计
                AgentNode(
                    name="socrates",
                    role="socrates",
                    input_keys=["task", "implementation", "test_report"],
                    output_key="audit_report",
                    timeout=300,
                ),
            ],
            edges=[
                Edge(from_node="metis", to_node="enki"),
                Edge(from_node="enki", to_node="persephone"),
                Edge(from_node="persephone", to_node="socrates"),
            ],
        )
    
    def execute(
        self,
        task: str,
        context: Optional[GraphContext] = None,
    ) -> GraphContext:
        """
        执行工作流。
        
        Args:
            task: 任务描述
            context: 初始上下文（可选）
        
        Returns:
            GraphContext: 执行结果
        """
        if context is None:
            context = GraphContext()
        
        # 设置任务
        context.set("task", task)
        
        # 执行工作流
        logger.info(f"Executing sisterhood workflow: {task[:50]}...")
        result = self._graph.execute(context)
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """获取工作流统计信息。"""
        return self._graph.get_stats()


class SimplifiedWorkflow:
    """简化工作流（跳过某些阶段）。"""
    
    def __init__(self, skip_phases: Optional[List[str]] = None):
        self._skip_phases = skip_phases or []
        self._graph = self._build_workflow()
        logger.info(f"SimplifiedWorkflow initialized, skipping: {self._skip_phases}")
    
    def _build_workflow(self) -> WorkflowGraph:
        """构建简化工作流。"""
        nodes = []
        edges = []
        
        # Metis
        if "metis" not in self._skip_phases:
            nodes.append(AgentNode(
                name="metis",
                role="metis",
                input_keys=["task"],
                output_key="design",
            ))
        
        # Enki
        if "enki" not in self._skip_phases:
            nodes.append(AgentNode(
                name="enki",
                role="enki",
                input_keys=["task", "design"],
                output_key="implementation",
            ))
            if "metis" not in self._skip_phases:
                edges.append(Edge(from_node="metis", to_node="enki"))
        
        # Testing
        if "persephone" not in self._skip_phases:
            nodes.append(AgentNode(
                name="persephone",
                role="persephone",
                input_keys=["task", "implementation"],
                output_key="test_report",
            ))
            if "enki" not in self._skip_phases:
                edges.append(Edge(from_node="enki", to_node="persephone"))
        
        # Socrates
        if "socrates" not in self._skip_phases:
            nodes.append(AgentNode(
                name="socrates",
                role="socrates",
                input_keys=["task", "implementation", "test_report"],
                output_key="audit_report",
            ))
            if "persephone" not in self._skip_phases:
                edges.append(Edge(from_node="persephone", to_node="socrates"))
        
        return WorkflowGraph(
            name="sisterhood_simplified",
            nodes=nodes,
            edges=edges,
        )
    
    def execute(
        self,
        task: str,
        context: Optional[GraphContext] = None,
    ) -> GraphContext:
        """执行简化工作流。"""
        if context is None:
            context = GraphContext()
        
        context.set("task", task)
        return self._graph.execute(context)


class QuickWorkflow:
    """快速工作流（仅 Enki）。"""
    
    def __init__(self):
        self._graph = WorkflowGraph(
            name="sisterhood_quick",
            nodes=[
                AgentNode(
                    name="enki",
                    role="enki",
                    input_keys=["task"],
                    output_key="result",
                ),
            ],
            edges=[],
        )
    
    def execute(self, task: str) -> GraphContext:
        """执行快速工作流。"""
        context = GraphContext(data={"task": task})
        return self._graph.execute(context)
