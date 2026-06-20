"""
姐妹会增强工作流 v2 — 并行舰队 + 多视角审议
=============================================

模式1: Composio Agent Orchestrator — 并行执行
模式2: Agent Tower — 多视角审议（Council + Deliberate）
"""

from __future__ import annotations
import uuid
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    HECATE = "hecate"
    METIS = "metis"
    ENKI = "enki"
    PERSEPHONE = "persephone"
    SOCRATES = "socrates"
    PLOUTOS = "ploutos"


class TaskPhase(str, Enum):
    DESIGN = "design"
    IMPLEMENT = "implement"
    TEST = "test"
    AUDIT = "audit"
    MERGE = "merge"


@dataclass
class AgentWorkUnit:
    unit_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: AgentRole = AgentRole.ENKI
    phase: TaskPhase = TaskPhase.IMPLEMENT
    task_description: str = ""
    dependencies: List[str] = field(default_factory=list)
    kanban_ticket_id: Optional[str] = None
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None


@dataclass
class ParallelPipeline:
    name: str
    stages: List[List[TaskPhase]]

    @classmethod
    def default(cls) -> "ParallelPipeline":
        return cls(
            name="sisterhood_parallel",
            stages=[
                [TaskPhase.DESIGN],
                [TaskPhase.IMPLEMENT, TaskPhase.TEST],
                [TaskPhase.AUDIT],
                [TaskPhase.MERGE],
            ]
        )


class SisterhoodOrchestrator:
    MAX_PARALLEL_AGENTS = 2

    def __init__(self, pipeline: ParallelPipeline = None):
        self.pipeline = pipeline or ParallelPipeline.default()
        self.work_units: Dict[str, AgentWorkUnit] = {}
        self.completed_units: Dict[str, AgentWorkUnit] = {}

    def decompose_task(self, goal: str) -> List[AgentWorkUnit]:
        design_unit = AgentWorkUnit(
            role=AgentRole.METIS, phase=TaskPhase.DESIGN,
            task_description=f"设计: {goal}",
        )
        implement_unit = AgentWorkUnit(
            role=AgentRole.ENKI, phase=TaskPhase.IMPLEMENT,
            task_description=f"实现: {goal}",
            dependencies=[design_unit.unit_id],
        )
        test_unit = AgentWorkUnit(
            role=AgentRole.PERSEPHONE, phase=TaskPhase.TEST,
            task_description=f"测试: {goal}",
            dependencies=[design_unit.unit_id],
        )
        audit_unit = AgentWorkUnit(
            role=AgentRole.SOCRATES, phase=TaskPhase.AUDIT,
            task_description=f"审计: {goal}",
            dependencies=[implement_unit.unit_id, test_unit.unit_id],
        )
        units = [design_unit, implement_unit, test_unit, audit_unit]
        self.work_units = {u.unit_id: u for u in units}
        return units

    def get_ready_units(self) -> List[AgentWorkUnit]:
        ready = []
        for unit in self.work_units.values():
            if unit.status != "pending":
                continue
            deps_met = all(
                dep_id in self.completed_units
                for dep_id in unit.dependencies
            )
            if deps_met:
                ready.append(unit)
        return ready

    def schedule_batch(self) -> List[AgentWorkUnit]:
        running = [u for u in self.work_units.values() if u.status == "running"]
        available_slots = self.MAX_PARALLEL_AGENTS - len(running)
        if available_slots <= 0:
            return []
        return self.get_ready_units()[:available_slots]

    def mark_completed(self, unit_id: str, result: Dict[str, Any] = None):
        if unit_id in self.work_units:
            unit = self.work_units[unit_id]
            unit.status = "completed"
            unit.result = result
            self.completed_units[unit_id] = unit

    def mark_failed(self, unit_id: str, error: str = ""):
        if unit_id in self.work_units:
            self.work_units[unit_id].status = "failed"
            self.work_units[unit_id].result = {"error": error}

    def get_progress(self) -> Dict[str, Any]:
        total = len(self.work_units)
        completed = len(self.completed_units)
        running = sum(1 for u in self.work_units.values() if u.status == "running")
        failed = sum(1 for u in self.work_units.values() if u.status == "failed")
        return {
            "total": total, "completed": completed, "running": running,
            "failed": failed, "pending": total - completed - running - failed,
            "progress_pct": round(completed / total * 100) if total else 0,
        }

    def build_delegate_calls(self, units: List[AgentWorkUnit]) -> List[Dict]:
        calls = []
        for unit in units:
            calls.append({
                "goal": unit.task_description,
                "role": "leaf",
                "toolsets": ["terminal", "file"],
                "context": {
                    "unit_id": unit.unit_id,
                    "phase": unit.phase.value,
                    "parallel_partner": self._get_parallel_partner(unit),
                },
            })
        return calls

    def _get_parallel_partner(self, unit: AgentWorkUnit) -> Optional[str]:
        if unit.phase == TaskPhase.IMPLEMENT:
            return "persephone (正在并行编写测试)"
        elif unit.phase == TaskPhase.TEST:
            return "enki (正在并行实现代码)"
        return None


@dataclass
class CouncilVote:
    voter: AgentRole
    position: str
    confidence: float
    reasoning: str
    selected_option: Optional[str] = None


@dataclass
class CouncilAgenda:
    topic: str
    options: List[str]
    context: str
    voters: List[AgentRole] = field(default_factory=lambda: [
        AgentRole.METIS, AgentRole.ENKI, AgentRole.PERSEPHONE,
    ])
    weights: Dict[AgentRole, float] = field(default_factory=lambda: {
        AgentRole.METIS: 1.0, AgentRole.ENKI: 0.8,
        AgentRole.PERSEPHONE: 0.7, AgentRole.SOCRATES: 0.9,
    })


class CouncilMode:
    def build_voter_prompts(self, agenda: CouncilAgenda) -> Dict[AgentRole, str]:
        perspective_map = {
            AgentRole.METIS: "从架构设计可行性角度分析",
            AgentRole.ENKI: "从代码实现复杂度和风险角度分析",
            AgentRole.PERSEPHONE: "从测试覆盖和质量保证角度分析",
            AgentRole.SOCRATES: "从长期维护和审计合规角度分析",
            AgentRole.PLOUTOS: "从投资回报和资源消耗角度分析",
        }
        prompts = {}
        for role in agenda.voters:
            perspective = perspective_map.get(role, "从综合角度分析")
            options_text = "\n".join(f"{i+1}. {opt}" for i, opt in enumerate(agenda.options))
            prompts[role] = f"""你是{role.value}，正在参与姐妹会议会审议。

议题: {agenda.topic}
背景: {agenda.context}

候选方案:
{options_text}

你的视角: {perspective}

请分析每个方案，给出你的投票。
格式:
- 选择: [方案编号]
- 立场: [approve/reject/abstain]
- 置信度: [0.0-1.0]
- 理由: [详细分析]"""
        return prompts

    def tally_votes(self, votes: List[CouncilVote], agenda: CouncilAgenda) -> Dict:
        scores = {opt: 0.0 for opt in agenda.options}
        for vote in votes:
            if vote.position == "abstain" or not vote.selected_option:
                continue
            weight = agenda.weights.get(vote.voter, 1.0)
            multiplier = 1.0 if vote.position == "approve" else -0.5
            if vote.selected_option in scores:
                scores[vote.selected_option] += weight * vote.confidence * multiplier
        winner = max(scores, key=scores.get) if scores else None
        max_score = max(scores.values()) if scores else 0
        return {
            "winner": winner, "scores": scores,
            "confidence": min(1.0, max_score / len(votes)) if votes else 0,
            "dissent": [v for v in votes if v.position == "reject"],
        }


class DeliberateMode:
    MAX_ROUNDS = 3
    CONSENSUS_THRESHOLD = 0.8

    @dataclass
    class DeliberationRound:
        round_number: int
        producer_output: str
        reviewer_feedback: Dict[str, str]
        consensus_score: float
        amendments: List[str]

    def build_review_prompt(self, role: AgentRole, proposal: str, topic: str) -> str:
        focus_map = {
            AgentRole.ENKI: "关注实现可行性、技术风险、依赖冲突",
            AgentRole.PERSEPHONE: "关注测试覆盖、边界情况、回归风险",
            AgentRole.SOCRATES: "关注代码质量、安全漏洞、合规性",
            AgentRole.PLOUTOS: "关注资源消耗、ROI、机会成本",
        }
        focus = focus_map.get(role, "关注综合质量")
        return f"""你是{role.value}，正在审议姐妹会的重要提案。

议题: {topic}
提案内容:
{proposal}
你的审查焦点: {focus}

请审查此提案，给出:
- 立场: [approve/conditional_approve/reject]
- 风险等级: [low/medium/high]
- 修改建议: [具体建议]
- 理由: [详细分析]"""

    def measure_consensus(self, feedback: Dict[str, str]) -> Dict:
        positive = 0
        total = len(feedback)
        amendments = []
        for role, text in feedback.items():
            text_lower = text.lower()
            if any(w in text_lower for w in ["同意", "approve", "赞同", "支持", "lgtm"]):
                positive += 1
            if any(w in text_lower for w in ["建议", "修改", "amend", "改进"]):
                amendments.append(text)
        return {"score": positive / total if total else 0, "amendments": amendments}


class TowerConductor:
    @dataclass
    class DeliberationRequest:
        topic: str
        context: str
        options: List[str] = field(default_factory=list)
        initial_proposal: str = ""
        mode: str = "auto"
        priority: str = "normal"

    def select_mode(self, request: "TowerConductor.DeliberationRequest") -> str:
        if request.mode != "auto":
            return request.mode
        if len(request.options) >= 2:
            return "council"
        if request.priority == "high":
            return "deliberate"
        return "council"

    def build_council_agenda(self, request: "TowerConductor.DeliberationRequest") -> CouncilAgenda:
        return CouncilAgenda(topic=request.topic, options=request.options, context=request.context)


class SisterhoodEnhanced:
    def __init__(self):
        self.orchestrator = SisterhoodOrchestrator()
        self.tower = TowerConductor()
        self.council = CouncilMode()
        self.deliberate = DeliberateMode()

    def execute_pipeline(self, goal: str, mode: str = "parallel") -> Dict[str, Any]:
        if mode == "serial":
            return {"goal": goal, "mode": "serial", "stages": ["metis", "enki", "persephone", "socrates"]}
        units = self.orchestrator.decompose_task(goal)
        batch = self.orchestrator.schedule_batch()
        calls = self.orchestrator.build_delegate_calls(batch) if batch else []
        return {
            "goal": goal, "mode": "parallel",
            "units": {u.unit_id: {
                "role": u.role.value, "phase": u.phase.value,
                "status": u.status, "deps": u.dependencies,
            } for u in units},
            "first_batch": {"units": [u.unit_id for u in batch], "delegate_calls": calls} if batch else None,
            "pipeline": self.orchestrator.pipeline.name,
        }

    def execute_deliberation(self, topic: str, options: List[str] = None,
                             context: str = "", mode: str = "auto",
                             priority: str = "normal") -> Dict[str, Any]:
        request = TowerConductor.DeliberationRequest(
            topic=topic, context=context, options=options or [],
            mode=mode, priority=priority,
        )
        selected_mode = self.tower.select_mode(request)
        if selected_mode == "council":
            agenda = self.tower.build_council_agenda(request)
            prompts = self.council.build_voter_prompts(agenda)
            return {
                "topic": topic, "mode": "council",
                "voter_prompts": {r.value: p for r, p in prompts.items()},
                "agenda": {"options": agenda.options, "voters": [v.value for v in agenda.voters],
                           "weights": {r.value: w for r, w in agenda.weights.items()}},
                "status": "prompts_ready",
            }
        return {
            "topic": topic, "mode": "deliberate",
            "max_rounds": self.deliberate.MAX_ROUNDS,
            "consensus_threshold": self.deliberate.CONSENSUS_THRESHOLD,
            "status": "ready",
        }
