"""
LTI (Learnable Token Injection) — 来自 OpenMythos 的可学习 prompt 注入

核心思想：
- 将可学习的 token 向量注入到 system message 中
- Gate 机制根据任务类型动态调整注入量
- 路由 tokens 帮助模型判断任务类型
- 上下文 tokens 携带 L1-L5 记忆摘要

在 agent 层面实现（非模型层）：
- 用规则分类器替代可学习向量（0 token 消耗）
- 用模板注入替代向量注入（兼容任何 LLM）
- Gate 逻辑用任务复杂度控制
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Tuple

class LTITokenType(Enum):
    """LTI token 类型"""
    ROUTING = "routing"          # 路由 tokens: 帮助模型判断任务类型
    CONTEXT = "context"          # 上下文 tokens: 携带记忆摘要
    COMPLEXITY = "complexity"    # 复杂度 tokens: 控制推理深度
    TOOL_HINT = "tool_hint"     # 工具提示 tokens: 建议使用的工具

# ── 路由 token 模板 ──────────────────────────────────────────────
ROUTING_TEMPLATES = {
    "simple": {
        "prefix": "[TASK:SIMPLE]",
        "instructions": [
            "直接回答，不需要复杂推理",
            "跳过思考链，直接输出结果",
            "如果需要工具，最多使用 1-2 个",
        ],
        "reasoning_effort": "low",
    },
    "medium": {
        "prefix": "[TASK:MEDIUM]",
        "instructions": [
            "需要适度推理，可以使用工具",
            "如果涉及代码，先分析再实现",
            "如果涉及数据，先检查再处理",
        ],
        "reasoning_effort": "medium",
    },
    "complex": {
        "prefix": "[TASK:COMPLEX]",
        "instructions": [
            "需要深度推理，可以使用多个工具",
            "先规划再执行，分步完成",
            "如果涉及架构设计，先 Metis 分析再 Enki 实施",
        ],
        "reasoning_effort": "high",
    },
}

# ── 工具提示模板 ────────────────────────────────────────────────
TOOL_HINTS = {
    "coding": ["execute_code", "terminal"],
    "analysis": ["execute_code", "terminal", "browser_snapshot"],
    "creative": ["image_generate", "browser_snapshot"],
    "research": ["browser_navigate", "browser_snapshot", "terminal"],
    "file_ops": ["terminal", "execute_code"],
}

# ── 任务类型检测规则 ────────────────────────────────────────────
TASK_TYPE_RULES = {
    "simple": [
        r"^(几点|什么时间|天气|翻译|计算|\d+[\+\-\*\/]\d+)",
        r"^(你好|hi|hello|thanks|谢谢)",
        r"^(什么是|谁是|定义|解释).{0,20}$",
    ],
    "medium": [
        r"(写|生成|创建|实现|编写).*(函数|脚本|代码|程序)",
        r"(分析|统计|计算|处理).*(数据|文件|日志)",
        r"(查找|搜索|查询|获取).*(信息|资料|文档)",
    ],
    "complex": [
        r"(设计|架构|重构|迁移|部署|集成)",
        r"(多步|分步|逐步|工作流|pipeline)",
        r"(优化|改进|升级|改造).*(系统|架构|流程)",
    ],
}

TASK_CATEGORY_RULES = {
    "coding": [
        r"(代码|函数|脚本|程序|python|javascript|bash|shell)",
        r"(bug|debug|error|exception|traceback)",
        r"(git|commit|push|pull|merge|branch)",
    ],
    "analysis": [
        r"(分析|统计|计算|处理).*(数据|文件|日志|csv|json)",
        r"(图表|可视化|plot|chart|graph)",
        r"(sql|database|sqlite|查询)",
    ],
    "creative": [
        r"(画|生成|设计|创作).*(图|图片|海报|logo)",
        r"(写|创作).*(文章|故事|诗|歌)",
        r"(视频|动画|音频|音乐)",
    ],
    "research": [
        r"(搜索|查找|调研|研究).*(论文|资料|信息)",
        r"(网页|网站|浏览器|url|http)",
        r"(新闻|资讯|报道|消息)",
    ],
    "file_ops": [
        r"(文件|目录|文件夹|路径)",
        r"(读取|写入|创建|删除|移动|复制).*(文件|目录)",
        r"(ls|cat|cp|mv|rm|mkdir|chmod)",
    ],
}


class LTIInjector:
    """
    LTI 注入器 — 将路由/上下文/复杂度 tokens 注入到 system message
    """
    
    def __init__(self):
        self.enabled = True
    
    def inject(
        self,
        system_message: str,
        user_message: str,
        complexity: str = "medium",
        context_summary: Optional[str] = None,
        topic_memory: Optional[str] = None,
    ) -> Tuple[str, Dict]:
        """
        注入 LTI tokens 到 system message
        
        返回: (增强后的 system_message, 注入元数据)
        """
        if not self.enabled:
            return system_message, {"injected": False}
        
        # 1. 检测任务类型
        task_type = self._detect_task_type(user_message)
        task_category = self._detect_task_category(user_message)
        
        # 2. 构建注入内容
        injections = []
        metadata = {
            "injected": True,
            "complexity": complexity,
            "task_type": task_type,
            "task_category": task_category,
        }
        
        # 3. 注入路由 tokens
        routing = ROUTING_TEMPLATES.get(complexity, ROUTING_TEMPLATES["medium"])
        injections.append(f"\n{routing['prefix']}")
        for instruction in routing["instructions"]:
            injections.append(f"  • {instruction}")
        
        # 4. 注入工具提示
        if task_category in TOOL_HINTS:
            tools = TOOL_HINTS[task_category]
            injections.append(f"\n[PREFERRED_TOOLS:{','.join(tools)}]")
            metadata["preferred_tools"] = tools
        
        # 5. 注入上下文摘要
        if context_summary:
            injections.append(f"\n[CONTEXT_SUMMARY]")
            injections.append(f"  {context_summary[:500]}")  # 限制长度
            metadata["has_context"] = True
        
        # 6. 注入 topic memory
        if topic_memory:
            injections.append(f"\n[TOPIC_MEMORY]")
            injections.append(f"  {topic_memory[:500]}")  # 限制长度
            metadata["has_topic_memory"] = True
        
        # 7. 注入推理努力度
        injections.append(f"\n[REASONING_EFFORT:{routing['reasoning_effort']}]")
        metadata["reasoning_effort"] = routing["reasoning_effort"]
        
        # 8. 拼接到 system message
        injection_text = "\n".join(injections)
        enhanced_system = f"{system_message}\n{injection_text}"
        
        return enhanced_system, metadata
    
    def _detect_task_type(self, message: str) -> str:
        """检测任务复杂度类型"""
        for level, patterns in TASK_TYPE_RULES.items():
            for pattern in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    return level
        return "medium"
    
    def _detect_task_category(self, message: str) -> str:
        """检测任务类别"""
        for category, patterns in TASK_CATEGORY_RULES.items():
            for pattern in patterns:
                if re.search(pattern, message, re.IGNORECASE):
                    return category
        return "general"


# ── 全局实例 ────────────────────────────────────────────────────
_lti_injector: Optional[LTIInjector] = None

def get_lti_injector() -> LTIInjector:
    global _lti_injector
    if _lti_injector is None:
        _lti_injector = LTIInjector()
    return _lti_injector


# ── 测试 ────────────────────────────────────────────────────────
if __name__ == "__main__":
    injector = LTIInjector()
    
    test_cases = [
        "几点了？",
        "写一个 Python 函数计算斐波那契数列",
        "分析这个 CSV 文件的数据趋势",
        "设计一个微服务架构",
        "帮我搜索最新的 AI 论文",
        "生成一张海报",
    ]
    
    for msg in test_cases:
        enhanced, meta = injector.inject(
            system_message="You are a helpful assistant.",
            user_message=msg,
            complexity="medium",
        )
        print(f"\n{'='*60}")
        print(f"Input: {msg}")
        print(f"Type: {meta['task_type']} | Category: {meta['task_category']}")
        print(f"Tools: {meta.get('preferred_tools', 'none')}")
        print(f"Effort: {meta['reasoning_effort']}")
