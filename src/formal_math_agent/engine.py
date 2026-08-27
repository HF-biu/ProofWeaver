import re
from dataclasses import asdict
from typing import Any, Dict, List

from .audit import AuditLog
from .config import AppConfig
from .lean import LeanRunner
from .model import ModelClient
from . import prompts
from .types import ArtifactResult, FormalizationCandidate, GoalNode


class FormalMathAgent:
    def __init__(self, config: AppConfig, config_path: str) -> None:
        self.config = config
        self.audit = AuditLog(config.runs_dir(config_path))
        self.model = ModelClient(config.provider, self.audit)
        self.lean = LeanRunner(config.lean)

    def _ask(self, purpose: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        if self.model.calls >= self.config.search.max_model_calls:
            raise RuntimeError("max_model_calls budget reached")
        return self.model.json(purpose, messages)

    def solve(self, problem: str) -> ArtifactResult:
        raw = self._ask("formalize", prompts.formalize(problem, self.config.search.formalization_candidates))
        candidates = []
        for item in raw.get("candidates", []):
            candidate = FormalizationCandidate(**item)
            checked = self.lean.check(candidate.lean_statement)
            candidate.lean = asdict(checked)
            candidates.append(candidate)
            self.audit.event("statement_checked", {"candidate_id": candidate.candidate_id, "lean": candidate.lean})
        self.audit.json("formalization_candidates.json", [asdict(item) for item in candidates])
        viable = [asdict(item) for item in candidates if item.lean.get("ok")]
        if not viable:
            return self._finish("solve", "formalization_failed", {"reason": "No candidate statement compiled."})
        alignment = self._ask("align", prompts.align(problem, viable))
        self.audit.json("alignment_report.json", alignment)
        selected_id = alignment.get("selected_candidate_id")
        selected = next((item for item in candidates if item.candidate_id == selected_id and item.lean.get("ok")), None)
        if alignment.get("verdict") != "pass" or selected is None:
            return self._finish("solve", "formalization_uncertain", {"alignment": alignment})
        self.audit.text("selected_statement.lean", selected.lean_statement)
        plan = self._ask("plan", prompts.plan(selected.lean_statement))
        nodes = [GoalNode(**item) for item in plan.get("nodes", [])]
        self.audit.json("proof_plan.json", {"plan": plan, "nodes": [asdict(node) for node in nodes]})
        verified = self._solve_graph(selected.lean_statement, nodes)
        if len(verified) != len(nodes):
            return self._finish("solve", "proof_search_failed", {"verified_nodes": verified, "nodes": [asdict(node) for node in nodes]})
        assembled = self._ask("assemble", prompts.assemble(selected.lean_statement, verified))
        final_check = self.lean.check(assembled.get("proof_lean", ""))
        self.audit.event("final_proof_checked", {"lean": asdict(final_check)})
        self.audit.text("proof.lean", assembled.get("proof_lean", ""))
        self.audit.text("final_solution.md", assembled.get("natural_solution", ""))
        status = "verified" if final_check.ok else "assembly_failed"
        return self._finish("solve", status, {"statement": selected.lean_statement, "alignment": alignment, "proof": assembled, "lean": asdict(final_check)})

    def _solve_graph(self, statement: str, nodes: List[GoalNode]) -> List[Dict[str, Any]]:
        verified: List[Dict[str, Any]] = []
        pending = list(nodes)
        replans = 0
        while pending:
            ready = next((node for node in pending if all(dep in {item["node_id"] for item in verified} for dep in node.depends_on)), None)
            if ready is None:
                self.audit.event("graph_deadlock", {"nodes": [asdict(node) for node in pending]})
                break
            feedback = ""
            while ready.attempts < self.config.search.max_node_attempts:
                ready.attempts += 1
                response = self._ask("solve_node", prompts.solve_node(statement, asdict(ready), verified, feedback))
                check = self.lean.check(response.get("lean_example", ""))
                evidence = {"attempt": ready.attempts, "response": response, "lean": asdict(check)}
                ready.evidence.append(evidence)
                self.audit.event("node_checked", {"node_id": ready.node_id, **evidence})
                if check.ok:
                    ready.status = "verified"
                    verified.append({"node_id": ready.node_id, "formal_goal": ready.formal_goal, "evidence": evidence})
                    pending.remove(ready)
                    break
                feedback = check.stderr or check.stdout
            if ready.status != "verified":
                replans += 1
                ready.status = "failed"
                self.audit.event("node_failed", {"node_id": ready.node_id, "replans": replans})
                if replans > self.config.search.max_replans:
                    break
                # A full implementation replaces this local subgraph. This V1 records the
                # failure and lets the next node-independent route proceed if available.
                pending.remove(ready)
        self.audit.json("proof_trace.json", {"nodes": [asdict(node) for node in nodes], "verified": verified})
        return verified

    def _compact_text(self, value: str, limit: int) -> str:
        """Keep a prompt bounded without hiding the fact that it was shortened."""
        value = value.strip()
        if len(value) <= limit:
            return value
        head = max(1, limit * 2 // 3)
        tail = max(1, limit - head - 48)
        return value[:head] + "\n...[本地已截断；见审计文件]...\n" + value[-tail:]

    def _split_derivation(self, derivation: str) -> List[Dict[str, Any]]:
        """Split locally; no model call is spent merely on finding step borders."""
        lines = [item.strip() for item in derivation.splitlines() if item.strip()]
        if len(lines) <= 1:
            lines = [item.strip() for item in re.split(r"(?<=[。；;])\\s+", derivation) if item.strip()]
        if not lines:
            lines = [derivation.strip()] if derivation.strip() else []
        return [{"step_id": index + 1, "text": text} for index, text in enumerate(lines)]

    def _inspection_chunks(self, steps: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        config = self.config.inspection
        chunks: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        current_chars = 0
        for step in steps:
            size = len(step["text"])
            if current and (len(current) >= config.max_steps_per_chunk or current_chars + size > config.max_chunk_chars):
                chunks.append(current)
                current, current_chars = [], 0
            current.append(step)
            current_chars += size
        if current:
            chunks.append(current)
        return chunks

    def _inspection_context(self, verified: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        limit = self.config.inspection.max_context_items
        return [
            {"step_id": item["step_id"], "claim": self._compact_text(item["claim"], 400)}
            for item in verified[-limit:]
        ]

    @staticmethod
    def _lean_feedback(lean: Dict[str, Any], limit: int) -> str:
        text = (lean.get("stderr") or lean.get("stdout") or "Lean rejected the obligation").strip()
        return text if len(text) <= limit else text[:limit] + "...[truncated]"

    def _write_inspection_markdown(self, report: Dict[str, Any]) -> None:
        lines = [
            "# 推导检查报告",
            "",
            "- 判定：`{}`".format(report["verdict"]),
            "- 最早确认错误步骤：{}".format(report.get("first_invalid_step") or "无"),
            "- Lean 已验证步骤数：{}".format(report["summary"]["verified"]),
            "- 不确定步骤数：{}".format(report["summary"]["uncertain"]),
            "",
            "## 步骤结果",
            "",
        ]
        for item in report["steps"]:
            lines.append("### 步骤 {}：{}".format(item["step_id"], item["status"]))
            lines.append("")
            lines.append(item["text"])
            if item.get("reason"):
                lines.extend(["", "原因：" + item["reason"]])
            if item.get("repair"):
                lines.append("修复建议：" + item["repair"])
            lines.append("")
        self.audit.text("inspection_report.md", "\n".join(lines))

    def inspect(self, problem: str, derivation: str) -> ArtifactResult:
        """Audit a derivation in bounded chunks, with Lean as primary evidence.

        The model is asked to emit only local Lean obligations.  It sees Lean
        diagnostics only for failed obligations and never receives the complete
        derivation a second time.  The final verdict is assembled locally.
        """
        settings = self.config.inspection
        source_steps = self._split_derivation(derivation)
        compact_problem = self._compact_text(problem, settings.max_problem_chars)
        results: List[Dict[str, Any]] = []
        verified: List[Dict[str, Any]] = []

        self.audit.json("inspection_input.json", {"problem": problem, "steps": source_steps})
        for chunk_index, chunk in enumerate(self._inspection_chunks(source_steps), start=1):
            oversized = [item for item in chunk if len(item["text"]) > settings.max_chunk_chars]
            for item in oversized:
                results.append({
                    "step_id": item["step_id"], "text": item["text"], "status": "uncertain",
                    "reason": "单一步骤超过本地检查预算，未发送给模型。请拆分该步骤。",
                    "repair": "将该步骤拆为可独立验证的子步骤。",
                })
            active = [item for item in chunk if item not in oversized]
            if not active:
                continue
            payload_steps = [{"step_id": item["step_id"], "text": item["text"]} for item in active]
            self.audit.event("inspection_chunk", {
                "chunk_index": chunk_index,
                "step_ids": [item["step_id"] for item in active],
                "prompt_step_chars": sum(len(item["text"]) for item in active),
            })
            try:
                trace = self._ask("inspect_chunk", prompts.inspect_chunk(compact_problem, self._inspection_context(verified), payload_steps))
            except RuntimeError as exc:
                self.audit.event("inspection_chunk_model_failed", {"chunk_index": chunk_index, "error": str(exc)})
                results.extend({
                    "step_id": item["step_id"], "text": item["text"], "status": "uncertain",
                    "reason": "本块模型调用失败：{}".format(str(exc)), "repair": "检查模型响应和 prompt 预算。",
                } for item in active)
                continue

            formalized = {item.get("step_id"): item for item in trace.get("steps", [])}
            failed: List[Dict[str, Any]] = []
            for source in active:
                item = formalized.get(source["step_id"], {})
                record: Dict[str, Any] = {"step_id": source["step_id"], "text": source["text"]}
                if item.get("status") != "checkable" or not item.get("lean_example"):
                    record.update({"status": "uncertain", "reason": "无法可靠地构造该步骤的 Lean 局部义务。"})
                    failed.append({"step_id": source["step_id"], "claim": item.get("claim", source["text"]), "lean_status": "not_formalized"})
                else:
                    lean = asdict(self.lean.check(item["lean_example"]))
                    record.update({"claim": item.get("claim", ""), "conditions": item.get("conditions", []), "lean": lean})
                    if lean["ok"]:
                        record["status"] = "verified"
                        verified.append({"step_id": source["step_id"], "claim": item.get("claim", source["text"])})
                    else:
                        record["status"] = "lean_failed"
                        failed.append({
                            "step_id": source["step_id"], "claim": item.get("claim", source["text"]),
                            "lean_status": "failed", "lean_feedback": self._lean_feedback(lean, settings.max_lean_feedback_chars),
                        })
                results.append(record)
                self.audit.event("inspection_step_checked", {"step_id": source["step_id"], "status": record["status"], "lean": record.get("lean")})

            if failed:
                try:
                    classified = self._ask("classify_failed_steps", prompts.classify_failed_steps(compact_problem, failed))
                    decisions = {item.get("step_id"): item for item in classified.get("items", [])}
                except RuntimeError as exc:
                    self.audit.event("inspection_classification_failed", {"chunk_index": chunk_index, "error": str(exc)})
                    decisions = {}
                for record in results:
                    decision = decisions.get(record["step_id"])
                    if decision:
                        record.update({
                            "status": "invalid" if decision.get("verdict") == "invalid" else "uncertain",
                            "error_type": decision.get("error_type", "formalization"),
                            "reason": decision.get("reason", record.get("reason", "Lean 未能验证该步骤。")),
                            "repair": decision.get("repair", ""),
                        })

        results.sort(key=lambda item: item["step_id"])
        invalid = [item for item in results if item["status"] == "invalid"]
        uncertain = [item for item in results if item["status"] in {"uncertain", "lean_failed"}]
        verdict = "error_found" if invalid else ("uncertain" if uncertain else "pass")
        report = {
            "verdict": verdict,
            "first_invalid_step": invalid[0]["step_id"] if invalid else None,
            "summary": {"total": len(results), "verified": len(verified), "invalid": len(invalid), "uncertain": len(uncertain)},
            "steps": results,
        }
        self.audit.json("check_report.json", report)
        self._write_inspection_markdown(report)
        return self._finish("inspect", verdict, report)

    def _finish(self, mode: str, status: str, result: Dict[str, Any]) -> ArtifactResult:
        output = ArtifactResult(mode=mode, task_id=self.audit.task_id, status=status, result=result)
        self.audit.json("result.json", output.to_dict())
        return output
