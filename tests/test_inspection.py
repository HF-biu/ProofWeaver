import unittest
from types import SimpleNamespace

from formal_math_agent.engine import FormalMathAgent


class InspectionHelpersTests(unittest.TestCase):
    def setUp(self):
        self.agent = FormalMathAgent.__new__(FormalMathAgent)
        self.agent.config = SimpleNamespace(
            inspection=SimpleNamespace(max_steps_per_chunk=2, max_chunk_chars=20, max_context_items=2)
        )

    def test_splits_lines_without_a_model_call(self):
        steps = self.agent._split_derivation("第一步\n第二步\n第三步")
        self.assertEqual([item["step_id"] for item in steps], [1, 2, 3])
        self.assertEqual(steps[1]["text"], "第二步")

    def test_respects_step_count_chunk_budget(self):
        steps = self.agent._split_derivation("a\nb\nc")
        chunks = self.agent._inspection_chunks(steps)
        self.assertEqual([[item["step_id"] for item in chunk] for chunk in chunks], [[1, 2], [3]])


class _Audit:
    def __init__(self):
        self.task_id = "test-task"
        self.events = []
        self.files = {}

    def event(self, event, data):
        self.events.append((event, data))

    def json(self, name, data):
        self.files[name] = data

    def text(self, name, data):
        self.files[name] = data


class _Lean:
    def check(self, code):
        from formal_math_agent.types import LeanResult
        return LeanResult("good" in code, "", "not provable", 0 if "good" in code else 1, 1)


class _Model:
    def __init__(self):
        self.calls = 0
        self.requests = []

    def json(self, purpose, messages):
        self.calls += 1
        self.requests.append((purpose, messages))
        if purpose == "inspect_chunk":
            return {"steps": [
                {"step_id": 1, "status": "checkable", "lean_example": "good", "claim": "A", "conditions": []},
                {"step_id": 2, "status": "checkable", "lean_example": "bad", "claim": "B", "conditions": []},
            ]}
        return {"items": [{"step_id": 2, "verdict": "invalid", "error_type": "algebra", "reason": "错误", "repair": "修正"}]}


class InspectionPipelineTests(unittest.TestCase):
    def test_lean_first_and_local_merge(self):
        agent = FormalMathAgent.__new__(FormalMathAgent)
        agent.config = SimpleNamespace(
            search=SimpleNamespace(max_model_calls=10),
            inspection=SimpleNamespace(
                max_problem_chars=3000, max_steps_per_chunk=8, max_chunk_chars=9000,
                max_context_items=8, max_lean_feedback_chars=1000,
            ),
        )
        agent.audit, agent.model, agent.lean = _Audit(), _Model(), _Lean()

        result = agent.inspect("题目", "步骤一\n步骤二")

        self.assertEqual(result.status, "error_found")
        self.assertEqual(result.result["first_invalid_step"], 2)
        self.assertEqual([item[0] for item in agent.model.requests], ["inspect_chunk", "classify_failed_steps"])
        classifier_payload = agent.model.requests[1][1][1]["content"]
        self.assertNotIn("步骤一", classifier_payload)
        self.assertIn('"claim": "B"', classifier_payload)
        self.assertIn("inspection_report.md", agent.audit.files)


if __name__ == "__main__":
    unittest.main()
