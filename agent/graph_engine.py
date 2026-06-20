# Source: Langflow
# Upstream: https://github.com/langflow-ai/langflow
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Graph Engine — 基于 Langflow 的 DAG 执行引擎

支持并行执行、条件分支、错误隔离。

Usage:
    from agent.graph_engine import WorkflowGraph, AgentNode, ParallelGroup
    
    graph = WorkflowGraph(name="my_workflow", nodes=[...], edges=[...])
    result = graph.execute(context)
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class NodeStatus(Enum):
    """节点执行状态。"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class NodeType(Enum):
    """节点类型。"""
    AGENT = "agent"
    TOOL = "tool"
    CONDITION = "condition"
    PARALLEL = "parallel"
    MERGE = "merge"


@dataclass
class NodeResult:
    """节点执行结果。"""
    node_name: str
    status: NodeStatus
    output: Any = None
    error: Optional[str] = None
    started_at: float = 0.0
    completed_at: float = 0.0
    duration: float = 0.0


@dataclass
class GraphContext:
    """Graph 执行上下文。"""
    data: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, NodeResult] = field(default_factory=dict)
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
    
    def get_result(self, node_name: str) -> Optional[NodeResult]:
        return self.results.get(node_name)
    
    def get_output(self, node_name: str) -> Any:
        result = self.results.get(node_name)
        return result.output if result else None


@dataclass
class Node:
    """Graph 节点基类。"""
    name: str
    node_type: NodeType = NodeType.AGENT
    handler: Optional[Callable] = None
    timeout: int = 300
    required: bool = True
    
    def execute(self, context: GraphContext) -> Any:
        if self.handler is None:
            raise ValueError(f"Node {self.name} has no handler")
        return self.handler(context)


@dataclass
class AgentNode(Node):
    """姐妹会角色节点。"""
    role: str = ""
    input_keys: List[str] = field(default_factory=list)
    output_key: str = ""
    
    def __post_init__(self):
        self.node_type = NodeType.AGENT
    
    def execute(self, context: GraphContext) -> Any:
        inputs = {key: context.get(key) for key in self.input_keys}
        
        try:
            # 简化实现：直接调用 handler
            if self.handler:
                result = self.handler(context)
            else:
                # 模拟角色执行
                result = f"[{self.role}] executed with {len(inputs)} inputs"
            
            if self.output_key:
                context.set(self.output_key, result)
            
            return result
        except Exception as e:
            logger.error(f"AgentNode {self.name} failed: {e}")
            raise


@dataclass
class ToolNode(Node):
    """工具节点。"""
    tool_name: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    output_key: str = ""
    
    def __post_init__(self):
        self.node_type = NodeType.TOOL
    
    def execute(self, context: GraphContext) -> Any:
        try:
            from tools.registry import registry
            tool_info = registry.get_tool(self.tool_name)
            if tool_info is None:
                raise ValueError(f"Tool {self.tool_name} not found")
            
            args = {}
            for k, v in self.tool_args.items():
                if isinstance(v, str) and v.startswith("$"):
                    args[k] = context.get(v[1:], v)
                else:
                    args[k] = v
            
            result = tool_info["handler"](**args)
            
            if self.output_key:
                context.set(self.output_key, result)
            
            return result
        except Exception as e:
            logger.error(f"ToolNode {self.name} failed: {e}")
            raise


@dataclass
class ParallelGroup(Node):
    """并行执行组。"""
    nodes: List[Node] = field(default_factory=list)
    
    def __post_init__(self):
        self.node_type = NodeType.PARALLEL
    
    def execute(self, context: GraphContext) -> Dict[str, NodeResult]:
        results = {}
        
        def run_node(node: Node) -> tuple:
            started_at = time.time()
            try:
                output = node.execute(context)
                return (node.name, NodeResult(
                    node_name=node.name,
                    status=NodeStatus.SUCCESS,
                    output=output,
                    started_at=started_at,
                    completed_at=time.time(),
                    duration=time.time() - started_at,
                ))
            except Exception as e:
                return (node.name, NodeResult(
                    node_name=node.name,
                    status=NodeStatus.FAILED,
                    error=str(e),
                    started_at=started_at,
                    completed_at=time.time(),
                    duration=time.time() - started_at,
                ))
        
        with ThreadPoolExecutor(max_workers=len(self.nodes)) as executor:
            futures = [executor.submit(run_node, node) for node in self.nodes]
            for future in futures:
                name, result = future.result()
                results[name] = result
                context.results[name] = result
        
        return results


@dataclass
class Edge:
    """节点之间的边。"""
    from_node: str
    to_node: str
    condition: Optional[Callable[[GraphContext], bool]] = None


@dataclass
class WorkflowGraph:
    """工作流图。"""
    name: str
    nodes: List[Node]
    edges: List[Edge]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def _build_adjacency(self) -> Dict[str, List[str]]:
        adj = {node.name: [] for node in self.nodes}
        for edge in self.edges:
            if edge.from_node in adj:
                adj[edge.from_node].append(edge.to_node)
        return adj
    
    def _build_in_degree(self) -> Dict[str, int]:
        in_degree = {node.name: 0 for node in self.nodes}
        for edge in self.edges:
            if edge.to_node in in_degree:
                in_degree[edge.to_node] += 1
        return in_degree
    
    def topological_sort(self) -> List[List[str]]:
        in_degree = self._build_in_degree()
        adj = self._build_adjacency()
        
        queue = [name for name, degree in in_degree.items() if degree == 0]
        batches = []
        
        while queue:
            batches.append(queue)
            next_queue = []
            for node_name in queue:
                for neighbor in adj.get(node_name, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            queue = next_queue
        
        return batches
    
    def execute(self, context: Optional[GraphContext] = None) -> GraphContext:
        if context is None:
            context = GraphContext()
        
        batches = self.topological_sort()
        node_map = {node.name: node for node in self.nodes}
        
        logger.info(f"Executing workflow '{self.name}': {len(batches)} batches")
        
        for batch_idx, batch in enumerate(batches):
            logger.info(f"Batch {batch_idx + 1}: {batch}")
            
            executable_nodes = []
            for node_name in batch:
                node = node_map[node_name]
                
                can_execute = True
                for edge in self.edges:
                    if edge.to_node == node_name and edge.condition:
                        if not edge.condition(context):
                            can_execute = False
                            break
                
                if can_execute:
                    executable_nodes.append(node)
                else:
                    context.results[node_name] = NodeResult(
                        node_name=node_name,
                        status=NodeStatus.SKIPPED,
                    )
            
            if len(executable_nodes) == 1:
                node = executable_nodes[0]
                started_at = time.time()
                try:
                    output = node.execute(context)
                    context.results[node.name] = NodeResult(
                        node_name=node.name,
                        status=NodeStatus.SUCCESS,
                        output=output,
                        started_at=started_at,
                        completed_at=time.time(),
                        duration=time.time() - started_at,
                    )
                except Exception as e:
                    context.results[node.name] = NodeResult(
                        node_name=node.name,
                        status=NodeStatus.FAILED,
                        error=str(e),
                        started_at=started_at,
                        completed_at=time.time(),
                        duration=time.time() - started_at,
                    )
                    if node.required:
                        logger.error(f"Required node {node.name} failed: {e}")
                        break
            elif len(executable_nodes) > 1:
                parallel_group = ParallelGroup(
                    name=f"batch_{batch_idx}",
                    nodes=executable_nodes,
                )
                parallel_group.execute(context)
        
        return context
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "batches": len(self.topological_sort()),
        }
