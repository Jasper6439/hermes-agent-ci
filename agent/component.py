# Source: Langflow
# Upstream: https://github.com/langflow-ai/langflow
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Component System — 基于 Langflow 的组件化工具系统

提供类型化输入/输出、自动验证、自动文档生成。

Usage:
    from agent.component import Component, StrInput, IntInput, Output
    
    class MyComponent(Component):
        inputs = [
            StrInput(name="query", display_name="查询", required=True),
            IntInput(name="limit", display_name="数量", default=5),
        ]
        outputs = [
            Output(display_name="结果", name="result", method="process"),
        ]
        
        def process(self) -> str:
            return f"Query: {self.query}, Limit: {self.limit}"
"""

from __future__ import annotations
import json

import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


# ─── Input Types ───────────────────────────────────────────────────────────────

class InputType(Enum):
    """输入类型。"""
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    LIST = "list"
    DICT = "dict"
    FILE = "file"
    CODE = "code"
    SELECT = "select"


@dataclass
class Input:
    """输入定义。"""
    name: str
    display_name: str
    input_type: InputType = InputType.STR
    required: bool = True
    default: Any = None
    description: str = ""
    options: Optional[List[str]] = None  # 用于 SELECT 类型
    min_value: Optional[float] = None    # 用于数值类型
    max_value: Optional[float] = None    # 用于数值类型
    
    def validate(self, value: Any) -> tuple[bool, Any, str]:
        """
        验证输入值。
        
        Returns:
            (is_valid, cleaned_value, error_message)
        """
        # 检查必填
        if value is None:
            if self.required:
                return False, None, f"{self.display_name} 是必填项"
            return True, self.default, ""
        
        # 类型检查和转换
        try:
            if self.input_type == InputType.STR:
                cleaned = str(value)
            elif self.input_type == InputType.INT:
                cleaned = int(value)
                if self.min_value is not None and cleaned < self.min_value:
                    return False, None, f"{self.display_name} 不能小于 {self.min_value}"
                if self.max_value is not None and cleaned > self.max_value:
                    return False, None, f"{self.display_name} 不能大于 {self.max_value}"
            elif self.input_type == InputType.FLOAT:
                cleaned = float(value)
                if self.min_value is not None and cleaned < self.min_value:
                    return False, None, f"{self.display_name} 不能小于 {self.min_value}"
                if self.max_value is not None and cleaned > self.max_value:
                    return False, None, f"{self.display_name} 不能大于 {self.max_value}"
            elif self.input_type == InputType.BOOL:
                if isinstance(value, str):
                    cleaned = value.lower() in ("true", "1", "yes", "是")
                else:
                    cleaned = bool(value)
            elif self.input_type == InputType.LIST:
                if isinstance(value, str):
                    # 尝试解析逗号分隔
                    cleaned = [v.strip() for v in value.split(",")]
                else:
                    cleaned = list(value)
            elif self.input_type == InputType.DICT:
                if isinstance(value, str):
                    cleaned = json.loads(value)
                else:
                    cleaned = dict(value)
            elif self.input_type == InputType.SELECT:
                if self.options and value not in self.options:
                    return False, None, f"{self.display_name} 必须是 {self.options} 之一"
                cleaned = value
            else:
                cleaned = value
            
            return True, cleaned, ""
            
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return False, None, f"{self.display_name} 类型错误: {e}"


@dataclass
class StrInput(Input):
    """字符串输入。"""
    input_type: InputType = InputType.STR


@dataclass
class IntInput(Input):
    """整数输入。"""
    input_type: InputType = InputType.INT


@dataclass
class FloatInput(Input):
    """浮点数输入。"""
    input_type: InputType = InputType.FLOAT


@dataclass
class BoolInput(Input):
    """布尔输入。"""
    input_type: InputType = InputType.BOOL


@dataclass
class ListInput(Input):
    """列表输入。"""
    input_type: InputType = InputType.LIST


@dataclass
class DictInput(Input):
    """字典输入。"""
    input_type: InputType = InputType.DICT


@dataclass
class SelectInput(Input):
    """选择输入。"""
    input_type: InputType = InputType.SELECT


@dataclass
class CodeInput(Input):
    """代码输入。"""
    input_type: InputType = InputType.CODE


# ─── Output Types ──────────────────────────────────────────────────────────────

@dataclass
class Output:
    """输出定义。"""
    display_name: str
    name: str
    method: str  # 处理方法名
    description: str = ""


# ─── Component Base Class ─────────────────────────────────────────────────────

class Component(ABC):
    """组件基类。"""
    
    # 子类定义
    display_name: str = "Component"
    description: str = ""
    inputs: List[Input] = []
    outputs: List[Output] = []
    tags: List[str] = []
    
    def __init__(self, **kwargs):
        """
        初始化组件。
        
        Args:
            **kwargs: 输入参数
        """
        self._inputs: Dict[str, Any] = {}
        self._outputs: Dict[str, Any] = {}
        self._errors: List[str] = []
        self._validated = False
        
        # 设置输入值
        for inp in self.inputs:
            if inp.name in kwargs:
                self._inputs[inp.name] = kwargs[inp.name]
            elif inp.default is not None:
                self._inputs[inp.name] = inp.default
    
    def __getattr__(self, name: str) -> Any:
        """允许通过属性访问输入值。"""
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._inputs:
            return self._inputs[name]
        raise AttributeError(f"Component has no input '{name}'")
    
    def validate(self) -> bool:
        """
        验证所有输入。
        
        Returns:
            bool: 是否有效
        """
        self._errors = []
        
        for inp in self.inputs:
            value = self._inputs.get(inp.name)
            is_valid, cleaned, error = inp.validate(value)
            
            if is_valid:
                self._inputs[inp.name] = cleaned
            else:
                self._errors.append(error)
        
        self._validated = len(self._errors) == 0
        return self._validated
    
    def run(self) -> Dict[str, Any]:
        """
        执行组件。
        
        Returns:
            Dict[str, Any]: 输出结果
        """
        # 先验证
        if not self.validate():
            raise ValueError(f"Validation failed: {self._errors}")
        
        # 执行所有输出方法
        results = {}
        for output in self.outputs:
            method = getattr(self, output.method, None)
            if method is None:
                raise ValueError(f"Method '{output.method}' not found")
            
            try:
                result = method()
                results[output.name] = result
                self._outputs[output.name] = result
            except Exception as e:
                logger.error(f"Output '{output.name}' failed: {e}")
                raise
        
        return results
    
    def get_schema(self) -> Dict[str, Any]:
        """获取组件 Schema（用于文档生成）。"""
        return {
            "display_name": self.display_name,
            "description": self.description,
            "tags": self.tags,
            "inputs": [
                {
                    "name": inp.name,
                    "display_name": inp.display_name,
                    "type": inp.input_type.value,
                    "required": inp.required,
                    "default": inp.default,
                    "description": inp.description,
                    "options": inp.options,
                    "min_value": inp.min_value,
                    "max_value": inp.max_value,
                }
                for inp in self.inputs
            ],
            "outputs": [
                {
                    "name": out.name,
                    "display_name": out.display_name,
                    "method": out.method,
                    "description": out.description,
                }
                for out in self.outputs
            ],
        }
    
    def get_errors(self) -> List[str]:
        """获取验证错误。"""
        return self._errors


# ─── Component Registry ───────────────────────────────────────────────────────

class ComponentRegistry:
    """组件注册表。"""
    
    _components: Dict[str, Type[Component]] = {}
    
    @classmethod
    def register(cls, component_class: Type[Component]) -> Type[Component]:
        """注册组件。"""
        name = component_class.__name__
        cls._components[name] = component_class
        logger.info(f"Registered component: {name}")
        return component_class
    
    @classmethod
    def get(cls, name: str) -> Optional[Type[Component]]:
        """获取组件。"""
        return cls._components.get(name)
    
    @classmethod
    def list_all(cls) -> List[str]:
        """列出所有组件。"""
        return list(cls._components.keys())
    
    @classmethod
    def list_by_tag(cls, tag: str) -> List[str]:
        """按标签列出组件。"""
        return [
            name for name, comp in cls._components.items()
            if tag in comp.tags
        ]


# ─── Decorator ─────────────────────────────────────────────────────────────────

def component(cls: Type[Component]) -> Type[Component]:
    """组件注册装饰器。"""
    return ComponentRegistry.register(cls)
