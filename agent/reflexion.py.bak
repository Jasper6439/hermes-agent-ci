# Source: Reflexion
# Upstream: https://github.com/noahshinn/reflexion
# Integrated: 2026-06-11
# See ~/.hermes/AGENT_SOURCES.md for full provenance map
"""
Reflexion Module — 自我反思机制

任务完成后自动评估结果，失败时生成反思，下次避免同样错误。
移植自 AutoGPT 的 Reflexion 策略，适配 Hermes 架构。

Usage:
    from agent.reflexion import ReflexionManager
    
    reflexion = ReflexionManager()
    
    # 任务完成后评估
    evaluation = reflexion.evaluate(task, result, success=True)
    
    # 生成反思
    if not evaluation["success"]:
        reflection = reflexion.reflect(task, result, evaluation)
        reflexion.store_reflection(reflection)
    
    # 查询反思记忆
    similar_reflections = reflexion.query_reflections("代码部署")
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 反思数据库路径
REFLEXION_DB_PATH = os.path.expanduser("~/.hermes/reflexion.db")


@dataclass
class Reflection:
    """单条反思记录"""
    id: Optional[int] = None
    task_type: str = ""
    task_description: str = ""
    error_type: str = ""
    error_detail: str = ""
    reflection: str = ""
    improvement: str = ""
    timestamp: str = ""
    frequency: int = 1
    context: Dict[str, Any] = field(default_factory=dict)


class ReflexionManager:
    """Reflexion 管理器"""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or REFLEXION_DB_PATH
        self._init_db()
    
    def _init_db(self) -> None:
        """初始化反思数据库"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reflections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT NOT NULL,
                    task_description TEXT,
                    error_type TEXT,
                    error_detail TEXT,
                    reflection TEXT,
                    improvement TEXT,
                    timestamp TEXT,
                    frequency INTEGER DEFAULT 1,
                    context TEXT,
                    UNIQUE(task_type, error_type)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_type 
                ON reflections(task_type)
            """)
            conn.commit()
    
    def evaluate(
        self,
        task: str,
        result: str,
        success: bool,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        评估任务执行结果
        
        Args:
            task: 任务描述
            result: 执行结果
            success: 是否成功
            context: 额外上下文
            
        Returns:
            评估结果
        """
        evaluation = {
            "task": task,
            "success": success,
            "timestamp": datetime.now().isoformat(),
        }
        
        if success:
            evaluation["quality"] = self._assess_quality(result)
            evaluation["improvement_suggestions"] = self._suggest_improvements(task, result)
        else:
            evaluation["error_type"] = self._classify_error(result)
            evaluation["error_detail"] = result
            evaluation["needs_reflection"] = True
        
        return evaluation
    
    def _assess_quality(self, result: str) -> str:
        """评估结果质量"""
        # 简单的质量评估规则
        if not result or len(result.strip()) == 0:
            return "empty"
        
        if "error" in result.lower() or "failed" in result.lower():
            return "poor"
        
        if "warning" in result.lower():
            return "acceptable"
        
        return "good"
    
    def _classify_error(self, result: str) -> str:
        """分类错误类型"""
        result_lower = result.lower()
        
        if "syntaxerror" in result_lower:
            return "syntax_error"
        elif "indentationerror" in result_lower:
            return "indentation_error"
        elif "nameerror" in result_lower:
            return "name_error"
        elif "typeerror" in result_lower:
            return "type_error"
        elif "permission denied" in result_lower:
            return "permission_error"
        elif "not found" in result_lower:
            return "not_found"
        elif "timeout" in result_lower:
            return "timeout"
        elif "connection" in result_lower:
            return "connection_error"
        else:
            return "unknown"
    
    def _suggest_improvements(self, task: str, result: str) -> List[str]:
        """建议改进"""
        suggestions = []
        
        # 基于结果的建议
        if len(result) > 1000:
            suggestions.append("结果过长，考虑使用 Token Compressor 压缩")
        
        if "warning" in result.lower():
            suggestions.append("存在警告，建议检查并处理")
        
        return suggestions
    
    def reflect(
        self,
        task: str,
        result: str,
        evaluation: Dict[str, Any]
    ) -> Reflection:
        """
        生成反思
        
        Args:
            task: 任务描述
            result: 执行结果
            evaluation: 评估结果
            
        Returns:
            Reflection 对象
        """
        error_type = evaluation.get("error_type", "unknown")
        
        # 生成反思内容
        reflection_text = self._generate_reflection_text(task, result, error_type)
        improvement_text = self._generate_improvement_text(error_type)
        
        reflection = Reflection(
            task_type=self._classify_task(task),
            task_description=task[:200],
            error_type=error_type,
            error_detail=result[:500],
            reflection=reflection_text,
            improvement=improvement_text,
            timestamp=datetime.now().isoformat(),
            context=evaluation,
        )
        
        return reflection
    
    def _classify_task(self, task: str) -> str:
        """分类任务类型"""
        task_lower = task.lower()
        
        if any(kw in task_lower for kw in ['部署', 'deploy', '发布']):
            return "deployment"
        elif any(kw in task_lower for kw in ['代码', 'code', 'python', 'script']):
            return "coding"
        elif any(kw in task_lower for kw in ['配置', 'config', '设置']):
            return "configuration"
        elif any(kw in task_lower for kw in ['清理', 'clean', '删除']):
            return "cleanup"
        elif any(kw in task_lower for kw in ['检查', 'check', '状态']):
            return "inspection"
        else:
            return "general"
    
    def _generate_reflection_text(
        self,
        task: str,
        result: str,
        error_type: str
    ) -> str:
        """生成反思文本"""
        templates = {
            "syntax_error": "代码语法错误。需要在执行前验证语法。",
            "indentation_error": "缩进错误。Python 代码需要一致的缩进。",
            "name_error": "变量名错误。可能拼写错误或未定义。",
            "type_error": "类型错误。参数类型不匹配。",
            "permission_error": "权限不足。可能需要 sudo 或检查文件权限。",
            "not_found": "文件或命令未找到。检查路径是否正确。",
            "timeout": "执行超时。任务可能过于复杂或系统负载过高。",
            "connection_error": "连接错误。检查网络和服务状态。",
            "unknown": "未知错误。需要进一步调查。",
        }
        
        return templates.get(error_type, "需要分析错误原因并制定改进计划。")
    
    def _generate_improvement_text(self, error_type: str) -> str:
        """生成改进建议"""
        improvements = {
            "syntax_error": "执行前使用 validate_python_code() 检查语法",
            "indentation_error": "使用 fix_python_indentation() 统一缩进",
            "name_error": "检查变量名拼写，确保已定义",
            "type_error": "使用 command_validator 验证参数类型",
            "permission_error": "使用 sudo 或检查文件权限",
            "not_found": "使用 which 或 ls 确认路径",
            "timeout": "拆分任务或增加超时时间",
            "connection_error": "检查网络连接和服务状态",
        }
        
        return improvements.get(error_type, "详细分析错误日志，找出根本原因")
    
    def store_reflection(self, reflection: Reflection) -> None:
        """存储反思到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("""
                    INSERT INTO reflections 
                    (task_type, task_description, error_type, error_detail, 
                     reflection, improvement, timestamp, frequency, context)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (
                    reflection.task_type,
                    reflection.task_description,
                    reflection.error_type,
                    reflection.error_detail,
                    reflection.reflection,
                    reflection.improvement,
                    reflection.timestamp,
                    json.dumps(reflection.context, ensure_ascii=False),
                ))
                conn.commit()
                logger.info(f"Stored reflection: {reflection.task_type}/{reflection.error_type}")
            except sqlite3.IntegrityError:
                # 已存在相同类型错误，增加频率
                conn.execute("""
                    UPDATE reflections 
                    SET frequency = frequency + 1,
                        timestamp = ?,
                        error_detail = ?
                    WHERE task_type = ? AND error_type = ?
                """, (
                    reflection.timestamp,
                    reflection.error_detail,
                    reflection.task_type,
                    reflection.error_type,
                ))
                conn.commit()
                logger.info(f"Updated reflection frequency: {reflection.task_type}/{reflection.error_type}")
    
    def query_reflections(
        self,
        task_type: Optional[str] = None,
        error_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Reflection]:
        """
        查询反思记忆
        
        Args:
            task_type: 任务类型过滤
            error_type: 错误类型过滤
            limit: 返回数量限制
            
        Returns:
            反思记录列表
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            query = "SELECT * FROM reflections WHERE 1=1"
            params = []
            
            if task_type:
                query += " AND task_type = ?"
                params.append(task_type)
            
            if error_type:
                query += " AND error_type = ?"
                params.append(error_type)
            
            query += " ORDER BY frequency DESC, timestamp DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            
            return [
                Reflection(
                    id=row["id"],
                    task_type=row["task_type"],
                    task_description=row["task_description"],
                    error_type=row["error_type"],
                    error_detail=row["error_detail"],
                    reflection=row["reflection"],
                    improvement=row["improvement"],
                    timestamp=row["timestamp"],
                    frequency=row["frequency"],
                    context=json.loads(row["context"]) if row["context"] else {},
                )
                for row in rows
            ]
    
    def get_reflection_summary(self, task_type: Optional[str] = None) -> str:
        """
        获取反思摘要
        
        Args:
            task_type: 任务类型过滤
            
        Returns:
            摘要文本
        """
        reflections = self.query_reflections(task_type=task_type, limit=5)
        
        if not reflections:
            return "暂无反思记录"
        
        summary_parts = ["历史反思摘要:", ""]
        
        for r in reflections:
            summary_parts.append(
                f"• [{r.task_type}] {r.error_type} (出现 {r.frequency} 次)"
            )
            summary_parts.append(f"  反思: {r.reflection}")
            summary_parts.append(f"  改进: {r.improvement}")
            summary_parts.append("")
        
        return "\n".join(summary_parts)
    
    def should_warn(self, task: str) -> Optional[str]:
        """
        检查是否需要警告（基于历史反思）
        
        Args:
            task: 当前任务
            
        Returns:
            警告信息，如果没有相关反思则返回 None
        """
        task_type = self._classify_task(task)
        reflections = self.query_reflections(task_type=task_type, limit=3)
        
        if not reflections:
            return None
        
        # 找到高频错误
        high_freq = [r for r in reflections if r.frequency >= 2]
        
        if high_freq:
            r = high_freq[0]
            return (
                f"⚠️ 历史反思警告: 此类任务曾多次出现 '{r.error_type}' 错误 ({r.frequency} 次)\n"
                f"反思: {r.reflection}\n"
                f"建议: {r.improvement}"
            )
        
        return None
