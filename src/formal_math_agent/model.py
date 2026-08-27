import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List

from .audit import AuditLog
from .config import ProviderConfig


def parse_json_content(content: str) -> Dict[str, Any]:
    clean = content.strip()
    if clean.startswith("```") and clean.endswith("```"):
        clean = "\n".join(clean.splitlines()[1:-1]).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        repaired = re.sub(r'(?<!\\)\\(?!["\\\\/bfnrtu])', r'\\\\', clean)
        return json.loads(repaired)


class ModelClient:
    """OpenAI Chat Completions adapter for API, HY3 gateway, and local gateway."""

    def __init__(self, config: ProviderConfig, audit: AuditLog) -> None:
        if config.kind not in {"openai", "hy3", "local"}:
            raise ValueError("provider.kind must be openai, hy3, or local")
        self.config, self.audit, self.calls = config, audit, 0

    def json(self, purpose: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        self.calls += 1
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.config.model, "messages": messages,
            "temperature": self.config.temperature, "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        self.audit.event("model_request", {"purpose": purpose, "provider": self.config.kind, "url": url, "payload": payload})
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Authorization": "Bearer " + self.config.api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            self.audit.event("model_error", {"purpose": purpose, "status": exc.code, "detail": detail})
            raise RuntimeError("Model API HTTP {}: {}".format(exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            self.audit.event("model_error", {"purpose": purpose, "detail": str(exc)})
            raise RuntimeError("Model API connection failed: {}".format(exc)) from exc
        self.audit.event("model_response", {"purpose": purpose, "raw_response": raw})
        body = json.loads(raw)
        choice = body.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content")
        if not content:
            raise RuntimeError(
                "Model returned empty content; finish_reason={!r}, message={!r}. "
                "Inspect events.jsonl".format(choice.get("finish_reason"), choice.get("message"))
            )
        try:
            parsed = parse_json_content(content)
        except json.JSONDecodeError as exc:
            self.audit.event("parse_error", {"purpose": purpose, "content": content})
            raise RuntimeError("Model did not return valid JSON for {}".format(purpose)) from exc
        self.audit.event("model_parsed", {"purpose": purpose, "parsed": parsed})
        return parsed
