import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ProviderConfig:
    kind: str
    base_url: str
    model: str
    api_key_env: str
    temperature: float = 0.25
    max_tokens: int = 8000
    timeout_seconds: int = 180

    @property
    def api_key(self) -> str:
        value = os.getenv(self.api_key_env)
        if not value:
            raise RuntimeError("Missing API key in environment variable: {}".format(self.api_key_env))
        return value


@dataclass
class LeanConfig:
    command: List[str] = field(default_factory=lambda: ["lake", "env", "lean"])
    timeout_seconds: int = 60
    imports: List[str] = field(default_factory=lambda: ["Mathlib"])
    project_dir: str = ""


@dataclass
class SearchConfig:
    formalization_candidates: int = 3
    max_node_attempts: int = 3
    max_replans: int = 2
    max_model_calls: int = 40


@dataclass
class InspectionConfig:
    """Bounds prompts used by derivation auditing.

    Limits are character based deliberately: they work consistently across the
    OpenAI-compatible, HY3, and local adapters used by this project.
    """
    max_problem_chars: int = 3000
    max_steps_per_chunk: int = 8
    max_chunk_chars: int = 9000
    max_context_items: int = 8
    max_lean_feedback_chars: int = 1000


@dataclass
class LoggingConfig:
    runs_dir: str = "runs"


@dataclass
class AppConfig:
    provider: ProviderConfig
    lean: LeanConfig = field(default_factory=LeanConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    inspection: InspectionConfig = field(default_factory=InspectionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def from_file(cls, path: str) -> "AppConfig":
        with open(path, "r", encoding="utf-8") as handle:
            raw: Dict[str, Any] = json.load(handle)
        return cls(
            provider=ProviderConfig(**raw["provider"]),
            lean=LeanConfig(**raw.get("lean", {})),
            search=SearchConfig(**raw.get("search", {})),
            inspection=InspectionConfig(**raw.get("inspection", {})),
            logging=LoggingConfig(**raw.get("logging", {})),
        )

    def runs_dir(self, config_path: str) -> Path:
        return Path(config_path).resolve().parent / self.logging.runs_dir
