import json
from pathlib import Path
from typing import Any, Dict, List


def load_examples(path: str, limit: int) -> List[Dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".jsonl":
        raw = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        raw = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("data", [])
    examples = []
    for item in raw:
        problem = item.get("problem") or item.get("question") or item.get("formal_statement")
        if problem:
            examples.append({"problem": problem, "expected": item.get("answer") or item.get("final_answer"), "source": item})
        if len(examples) >= limit:
            break
    return examples
