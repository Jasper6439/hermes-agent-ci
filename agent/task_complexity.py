"""
Task Complexity Assessment — 来自 HRM 的任务复杂度评估

核心思想：
- 用规则分类器（0 token）预判任务复杂度
- 动态调整 max_iterations 和 reasoning_effort
- 简单任务 3-5 轮，中等 10-15 轮，复杂 20-30 轮
- 支持 LLM 兜底（可选，默认关闭）
"""

import re
from enum import Enum
from typing import Tuple, Optional

class ComplexityLevel(Enum):
    SIMPLE = "simple"      # "几点了", "翻译这个"
    MEDIUM = "medium"      # "写个函数", "分析数据"
    COMPLEX = "complex"    # "设计架构", "多步推理"

# ── 复杂度配置 ──────────────────────────────────────────────────
COMPLEXITY_CONFIG = {
    ComplexityLevel.SIMPLE: {
        "max_iterations": 10,
        "reasoning_effort": "low",
        "token_budget": 2000,
        "description": "简单任务：直接回答，不需要复杂推理",
    },
    ComplexityLevel.MEDIUM: {
        "max_iterations": 30,
        "reasoning_effort": "medium",
        "token_budget": 8000,
        "description": "中等任务：需要适度推理和工具调用",
    },
    ComplexityLevel.COMPLEX: {
        "max_iterations": 60,
        "reasoning_effort": "high",
        "token_budget": 20000,
        "description": "复杂任务：需要深度推理和多步执行",
    },
}

# ── 检测规则 ────────────────────────────────────────────────────
SIMPLE_PATTERNS = [
    r"^(几点|什么时间|天气|翻译|计算|\d+[\+\-\*\/]\d+)",
    r"^(你好|hi|hello|thanks|谢谢|ok|好的|明白)",
    r"^(什么是|谁是|定义|解释).{0,20}$",
    r"^(列出|显示|查看|检查).{0,15}$",
]

MEDIUM_PATTERNS = [
    r"(写|生成|创建|实现|编写).*(函数|脚本|代码|程序)",
    r"(分析|统计|计算|处理).*(数据|文件|日志)",
    r"(查找|搜索|查询|获取).*(信息|资料|文档)",
    r"(安装|配置|设置|部署).*(软件|服务|工具)",
    r"(读取|写入|创建|删除|移动|复制).*(文件|目录)",
]

COMPLEX_PATTERNS = [
    r"(设计|架构|重构|迁移|部署|集成)",
    r"(多步|分步|逐步|工作流|pipeline)",
    r"(优化|改进|升级|改造).*(系统|架构|流程)",
    r"(调试|排查|修复).*(问题|bug|错误|故障)",
    r"(研究|调研|分析).*(方案|策略|技术)",
]

# ── 长度启发式 ──────────────────────────────────────────────────
LENGTH_THRESHOLDS = {
    "simple": 50,    # < 50 字符 → 可能简单
    "medium": 200,   # 50-200 字符 → 可能中等
    # > 200 字符 → 可能复杂
}


class TaskComplexityAssessor:
    """
    任务复杂度评估器
    """
    
    def __init__(self, enable_llm_fallback: bool = False):
        self.enable_llm_fallback = enable_llm_fallback
    
    def assess(self, message: str) -> Tuple[ComplexityLevel, dict]:
        """
        评估任务复杂度
        
        返回: (复杂度级别, 评估元数据)
        """
        metadata = {
            "method": "rules",
            "message_length": len(message),
        }
        
        # 1. 规则分类器
        for level, patterns in [
            (ComplexityLevel.SIMPLE, SIMPLE_PATTERNS),
            (ComplexityLevel.MEDIUM, MEDIUM_PATTERNS),
            (ComplexityLevel.COMPLEX, COMPLEX_PATTERNS),
        ]:
            for pattern in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    metadata["matched_pattern"] = pattern
                    metadata["level"] = level.value
                    config = COMPLEXITY_CONFIG[level]
                    metadata.update(config)
                    return level, metadata
        
        # 2. 长度启发式
        length = len(message)
        if length < LENGTH_THRESHOLDS["simple"]:
            level = ComplexityLevel.SIMPLE
        elif length < LENGTH_THRESHOLDS["medium"]:
            level = ComplexityLevel.MEDIUM
        else:
            level = ComplexityLevel.COMPLEX
        
        metadata["method"] = "length_heuristic"
        metadata["level"] = level.value
        config = COMPLEXITY_CONFIG[level]
        metadata.update(config)
        
        return level, metadata
    
    def get_config(self, level: ComplexityLevel) -> dict:
        """获取复杂度配置"""
        return COMPLEXITY_CONFIG[level]
    
    def get_max_iterations(self, level: ComplexityLevel) -> int:
        """获取最大迭代数"""
        return COMPLEXITY_CONFIG[level]["max_iterations"]
    
    def get_reasoning_effort(self, level: ComplexityLevel) -> str:
        """获取推理努力度"""
        return COMPLEXITY_CONFIG[level]["reasoning_effort"]


# ── 全局实例 ────────────────────────────────────────────────────
_assessor: Optional[TaskComplexityAssessor] = None

def get_complexity_assessor() -> TaskComplexityAssessor:
    global _assessor
    if _assessor is None:
        _assessor = TaskComplexityAssessor()
    return _assessor


# ── 测试 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    assessor = TaskComplexityAssessor()
    
    test_cases = [
        "几点了？",
        "你好",
        "写一个 Python 函数计算斐波那契数列",
        "分析这个 CSV 文件的数据趋势",
        "设计一个微服务架构，需要支持高并发和分布式部署",
        "帮我搜索最新的 AI 论文",
        "修复这个 bug：TypeError: cannot read property 'map' of undefined",
        "创建一个自动化工作流，每天早上 6 点拉取数据并生成报告",
    ]
    
    for msg in test_cases:
        level, meta = assessor.assess(msg)
        config = COMPLEXITY_CONFIG[level]
        print(f"\n{'='*60}")
        print(f"Input: {msg}")
        print(f"Level: {level.value} | Method: {meta['method']}")
        print(f"Max Iter: {config['max_iterations']} | Effort: {config['reasoning_effort']}")
        print(f"Budget: {config['token_budget']} tokens")
