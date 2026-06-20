"""
Sisterhood Enhancements Plugin — 姐妹会增强功能

集成 ReWOO、Reflexion 和 Command Validator 到 Hermes 系统。
通过插件 hooks 而非直接修改核心文件。

Usage:
    插件自动加载，无需手动调用。
    
    功能：
    1. ReWOO 规划 - Metis 使用
    2. Reflexion 反思 - Hecate 使用
    3. 命令验证 - 所有工具调用前验证
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 插件元数据
PLUGIN_NAME = "sisterhood-enhancements"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "姐妹会增强功能 — ReWOO 规划、Reflexion 反思、命令验证"


class SisterhoodEnhancementsPlugin:
    """姐妹会增强功能插件"""
    
    def __init__(self):
        self._rewoo = None
        self._reflexion = None
        self._validator = None
        self._initialized = False
    
    def _ensure_initialized(self) -> None:
        """延迟初始化"""
        if self._initialized:
            return
        
        try:
            from agent.rewoo import ReWOOPlanner
            from agent.reflexion import ReflexionManager
            from agent.command_validator import validate_and_fix_tool_call
            
            self._rewoo = ReWOOPlanner()
            self._reflexion = ReflexionManager()
            self._validator = validate_and_fix_tool_call
            self._initialized = True
            
            logger.info("Sisterhood enhancements plugin initialized")
        except Exception as e:
            logger.error(f"Failed to initialize sisterhood enhancements: {e}")
    
    def on_before_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> tuple[bool, Dict[str, Any], List[str]]:
        """
        工具调用前的验证 hook
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            context: 额外上下文
            
        Returns:
            (is_valid, fixed_args, errors)
        """
        self._ensure_initialized()
        
        if not self._initialized or not self._validator:
            return True, args, []
        
        try:
            is_valid, fixed_args, errors = self._validator(tool_name, args)
            
            if errors:
                logger.warning(f"Tool call validation errors for {tool_name}: {errors}")
            
            return is_valid, fixed_args, errors
        except Exception as e:
            logger.error(f"Tool call validation failed: {e}")
            return True, args, []
    
    def on_after_tool_call(
        self,
        tool_name: str,
        args: Dict[str, Any],
        result: str,
        success: bool,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        工具调用后的反思 hook
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            result: 执行结果
            success: 是否成功
            context: 额外上下文
            
        Returns:
            可选的反思警告信息
        """
        self._ensure_initialized()
        
        if not self._initialized or not self._reflexion:
            return None
        
        try:
            # 评估结果
            evaluation = self._reflexion.evaluate(
                task=f"{tool_name}({args})",
                result=result,
                success=success,
                context=context,
            )
            
            # 如果失败，生成反思
            if not success and evaluation.get("needs_reflection"):
                reflection = self._reflexion.reflect(
                    task=f"{tool_name}({args})",
                    result=result,
                    evaluation=evaluation,
                )
                self._reflexion.store_reflection(reflection)
                
                return (
                    f"⚠️ Reflexion: 此操作失败，已记录反思\n"
                    f"错误类型: {reflection.error_type}\n"
                    f"反思: {reflection.reflection}\n"
                    f"建议: {reflection.improvement}"
                )
            
            return None
        except Exception as e:
            logger.error(f"Reflexion failed: {e}")
            return None
    
    def on_before_task(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        任务开始前的反思查询 hook
        
        Args:
            task: 任务描述
            context: 额外上下文
            
        Returns:
            可选的反思警告信息
        """
        self._ensure_initialized()
        
        if not self._initialized or not self._reflexion:
            return None
        
        try:
            return self._reflexion.should_warn(task)
        except Exception as e:
            logger.error(f"Reflexion query failed: {e}")
            return None
    
    def create_rewoo_plan(
        self,
        task: str,
        context: Optional[str] = None
    ) -> Optional[Any]:
        """
        创建 ReWOO 执行计划
        
        Args:
            task: 任务描述
            context: 额外上下文
            
        Returns:
            ReWOOPlan 对象，如果初始化失败返回 None
        """
        self._ensure_initialized()
        
        if not self._initialized or not self._rewoo:
            return None
        
        try:
            return self._rewoo.create_plan(task, context)
        except Exception as e:
            logger.error(f"ReWOO planning failed: {e}")
            return None
    
    def get_reflection_summary(
        self,
        task_type: Optional[str] = None
    ) -> str:
        """
        获取反思摘要
        
        Args:
            task_type: 任务类型过滤
            
        Returns:
            摘要文本
        """
        self._ensure_initialized()
        
        if not self._initialized or not self._reflexion:
            return "Reflexion 未初始化"
        
        try:
            return self._reflexion.get_reflection_summary(task_type)
        except Exception as e:
            logger.error(f"Failed to get reflection summary: {e}")
            return "获取反思摘要失败"


# 全局插件实例
_plugin_instance: Optional[SisterhoodEnhancementsPlugin] = None


def get_plugin() -> SisterhoodEnhancementsPlugin:
    """获取插件实例"""
    global _plugin_instance
    if _plugin_instance is None:
        _plugin_instance = SisterhoodEnhancementsPlugin()
    return _plugin_instance


# Hook 函数（供插件系统调用）
def on_before_tool_call(
    tool_name: str,
    args: Dict[str, Any],
    context: Optional[Dict[str, Any]] = None
) -> tuple[bool, Dict[str, Any], List[str]]:
    """工具调用前验证"""
    return get_plugin().on_before_tool_call(tool_name, args, context)


def on_after_tool_call(
    tool_name: str,
    args: Dict[str, Any],
    result: str,
    success: bool,
    context: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """工具调用后反思"""
    return get_plugin().on_after_tool_call(tool_name, args, result, success, context)


def on_before_task(
    task: str,
    context: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """任务开始前查询"""
    return get_plugin().on_before_task(task, context)


def create_rewoo_plan(
    task: str,
    context: Optional[str] = None
) -> Optional[Any]:
    """创建 ReWOO 计划"""
    return get_plugin().create_rewoo_plan(task, context)


def get_reflection_summary(
    task_type: Optional[str] = None
) -> str:
    """获取反思摘要"""
    return get_plugin().get_reflection_summary(task_type)
