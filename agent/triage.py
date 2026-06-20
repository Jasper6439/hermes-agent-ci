"""
Proactive Agent Triage Module

Zero-LLM keyword-based message routing. Intercepts messages before Hecate
and routes to appropriate specialist agents based on keyword matching.

Usage:
    from agent.triage import triage_message
    result = triage_message(message_text, config)
    if result:
        agent, priority, reason = result
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger("agent.triage")


@dataclass
class TriageRule:
    """Rule for proactive agent activation."""
    agent: str
    keywords: List[str]
    priority: str  # "high" (direct takeover) or "low" (suggest to Hecate)
    min_matches: int = 1  # Minimum keyword matches required
    exclude_keywords: List[str] = None  # Keywords that disqualify this agent


@dataclass
class TriageResult:
    """Result of triage decision."""
    agent: str
    priority: str
    matched_keywords: List[str]
    reason: str
    confidence: float  # 0.0 - 1.0


# Default triage rules based on Metis's design
DEFAULT_TRIAGE_RULES = [
    TriageRule(
        agent="athena",
        keywords=["磁盘", "disk", "空间", "space", "清理", "cleanup", "满了", "full", 
                  "存储", "storage", "容量", "capacity", "删除文件", "delete files"],
        priority="high",
        min_matches=1,
        exclude_keywords=["代码", "code", "审计", "audit", "安全", "security"]
    ),
    TriageRule(
        agent="socrates",
        keywords=["审计", "audit", "安全", "security", "漏洞", "vulnerability", 
                  "渗透", "penetration", "合规", "compliance", "防护", "protection"],
        priority="low",
        min_matches=1,
        exclude_keywords=[]
    ),
    TriageRule(
        agent="enki",
        keywords=["架构", "architecture", "部署", "deploy", "系统", "system", 
                  "基础设施", "infrastructure", "配置", "config", "优化", "optimize"],
        priority="low",
        min_matches=1,
        exclude_keywords=[]
    ),
    TriageRule(
        agent="metis",
        keywords=["设计", "design", "方案", "plan", "分析", "analyze", 
                  "需求", "requirement", "流程", "workflow", "重构", "refactor"],
        priority="low",
        min_matches=1,
        exclude_keywords=[]
    ),
    TriageRule(
        agent="persephone",
        keywords=["测试", "test", "验证", "verify", "检查", "check", 
                  "质量", "quality", "边界", "boundary", "异常", "exception"],
        priority="low",
        min_matches=1,
        exclude_keywords=[]
    ),
    TriageRule(
        agent="ploutos",
        keywords=["部署", "deploy", "发布", "release", "上线", "go live", 
                  "运维", "ops", "监控", "monitor", "告警", "alert"],
        priority="low",
        min_matches=1,
        exclude_keywords=[]
    ),
]


def triage_message(
    message: str,
    rules: List[TriageRule] = None,
    threshold: float = 0.3
) -> Optional[TriageResult]:
    """
    Analyze message and determine if proactive agent should be activated.
    
    Args:
        message: User message text
        rules: Triage rules to apply (defaults to DEFAULT_TRIAGE_RULES)
        threshold: Minimum confidence threshold for activation
        
    Returns:
        TriageResult if agent should be activated, None otherwise
    """
    if rules is None:
        rules = DEFAULT_TRIAGE_RULES
    
    if not message or not message.strip():
        return None
    
    message_lower = message.lower()
    best_result = None
    best_score = 0.0
    
    for rule in rules:
        # Check for exclude keywords first
        if rule.exclude_keywords:
            excluded = any(kw.lower() in message_lower for kw in rule.exclude_keywords)
            if excluded:
                continue
        
        # Count keyword matches
        matched = []
        for keyword in rule.keywords:
            if keyword.lower() in message_lower:
                matched.append(keyword)
        
        # Check minimum matches
        if len(matched) < rule.min_matches:
            continue
        
        # Calculate confidence score
        # More matches = higher confidence, but with diminishing returns
        if len(matched) == 0:
            confidence = 0.0
        elif len(matched) == 1:
            confidence = 0.5
        elif len(matched) == 2:
            confidence = 0.65
        elif len(matched) == 3:
            confidence = 0.8
        else:
            confidence = min(1.0, 0.8 + (len(matched) - 3) * 0.05)
        
        # Boost confidence for high priority rules
        if rule.priority == "high":
            confidence = min(1.0, confidence + 0.2)
        
        # Check threshold
        if confidence < threshold:
            continue
        
        # Update best result
        if confidence > best_score:
            best_score = confidence
            best_result = TriageResult(
                agent=rule.agent,
                priority=rule.priority,
                matched_keywords=matched,
                reason=f"Matched {len(matched)} keywords for {rule.agent}",
                confidence=confidence
            )
    
    if best_result:
        logger.info(
            f"Triage: {best_result.agent} ({best_result.priority}) "
            f"confidence={best_result.confidence:.2f} "
            f"keywords={best_result.matched_keywords}"
        )
    
    return best_result


def get_triage_stats() -> Dict[str, int]:
    """Get triage statistics (for monitoring)."""
    # TODO: Implement actual stats tracking
    return {
        "total_messages": 0,
        "triaged": 0,
        "by_agent": {},
        "by_priority": {"high": 0, "low": 0}
    }
