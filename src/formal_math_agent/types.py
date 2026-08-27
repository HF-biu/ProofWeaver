from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class LeanResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: int


@dataclass
class FormalizationCandidate:
    candidate_id: str
    lean_statement: str
    informal_restatement: str
    assumptions: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)
    lean: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GoalNode:
    node_id: str
    depends_on: List[str]
    informal_goal: str
    formal_goal: str
    methods: List[str]
    status: str = "queued"
    attempts: int = 0
    evidence: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ArtifactResult:
    mode: str
    task_id: str
    status: str
    result: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
