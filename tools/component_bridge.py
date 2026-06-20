# Source: Langflow
# Upstream: https://github.com/langflow-ai/langflow
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Component Bridge — 组件系统与工具注册表的桥接

将 Component 自动注册为 Hermes 工具。

Usage:
    from tools.component_bridge import auto_register_components
    
    auto_register_components()
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from tools.registry import registry

logger = logging.getLogger(__name__)


def component_to_tool_schema(comp_class) -> Dict[str, Any]:
    """将 Component 转换为工具 Schema。"""
    inputs = comp_class.inputs
    outputs = comp_class.outputs
    
    properties = {}
    required = []
    
    for inp in inputs:
        prop = {
            "type": _map_type(inp.input_type.value),
            "description": inp.description or inp.display_name,
        }
        
        if inp.default is not None:
            prop["default"] = inp.default
        
        if inp.options:
            prop["enum"] = inp.options
        
        if inp.min_value is not None:
            prop["minimum"] = inp.min_value
        
        if inp.max_value is not None:
            prop["maximum"] = inp.max_value
        
        properties[inp.name] = prop
        
        if inp.required:
            required.append(inp.name)
    
    return {
        "type": "function",
        "function": {
            "name": comp_class.__name__,
            "description": comp_class.description or comp_class.display_name,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def _map_type(input_type: str) -> str:
    """映射输入类型到 JSON Schema 类型。"""
    mapping = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "boolean": "boolean",
        "list": "array",
        "dict": "object",
        "select": "string",
        "code": "string",
        "file": "string",
    }
    return mapping.get(input_type, "string")


def component_handler(comp_class):
    """创建组件的工具处理器。"""
    def handler(**kwargs) -> str:
        try:
            comp = comp_class(**kwargs)
            results = comp.run()
            
            # 格式化输出
            lines = [f"✅ {comp_class.display_name} 执行成功"]
            for name, value in results.items():
                lines.append(f"\n【{name}】")
                lines.append(str(value)[:500])
            
            return "\n".join(lines)
            
        except ValueError as e:
            return f"❌ 验证失败: {e}"
        except Exception as e:
            return f"❌ 执行失败: {e}"
    
    return handler


def auto_register_components():
    """自动注册所有组件为工具。"""
    from agent.component import ComponentRegistry
    
    for name, comp_class in ComponentRegistry._components.items():
        # 转换 Schema
        schema = component_to_tool_schema(comp_class)
        
        # 创建处理器
        handler = component_handler(comp_class)
        
        # 注册到工具注册表
        registry.register(
            name=name,
            toolset="component",
            schema=schema,
            handler=handler,
            emoji="🧩",
            max_result_size_chars=10_000,
        )
        
        logger.info(f"Registered component as tool: {name}")
