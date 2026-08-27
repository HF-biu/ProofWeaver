import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class AuditLog:
    def __init__(self, root: Path) -> None:
        task_id = datetime.now(timezone.utc).strftime("task_%Y%m%dT%H%M%SZ")
        self.task_id = task_id
        self.path = root / task_id
        self.path.mkdir(parents=True, exist_ok=False)
        self.events = self.path / "events.jsonl"

    def event(self, event: str, data: Dict[str, Any]) -> None:
        row = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **data}
        with self.events.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def json(self, name: str, data: Any) -> None:
        (self.path / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def text(self, name: str, data: str) -> None:
        (self.path / name).write_text(data, encoding="utf-8")
