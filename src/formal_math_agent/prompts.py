import json
from typing import Any, Dict, List

SYSTEM = """你是形式化数学系统中的一个受限 agent。只返回合法 JSON，禁止 Markdown code fence。
不得声称 Lean 未验证的结果已经形式证明。JSON 中优先使用 Unicode 数学符号；如使用 LaTeX，反斜杠必须 JSON 转义。"""


def build(instruction: str, payload: Dict[str, Any]) -> List[Dict[str, str]]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": instruction + "\n输入：\n" + json.dumps(payload, ensure_ascii=False)}]


def formalize(problem: str, count: int) -> List[Dict[str, str]]:
    return build("""你是 Formalizer。生成多个互不重复的 Lean 4 theorem statement 候选，不写 proof。
返回 {"candidates":[{"candidate_id":string,"lean_statement":string,"informal_restatement":string,"assumptions":[string],"ambiguities":[string]}]}。
statement 必须可作为单独 Lean 顶层声明编译。""", {"problem": problem, "count": count})


def align(problem: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return build("""你是独立语义对齐检查器。比较原题与各 Lean 候选的反向表述，检查量词、类型、定义域、假设和结论。
返回 {"selected_candidate_id":string,"verdict":"pass"|"uncertain"|"fail","matched":[string],"missing":[string],"extra":[string],"risks":[string],"explanation":string}。歧义或不等价时不得 pass。""", {"problem": problem, "candidates": candidates})


def plan(statement: str) -> List[Dict[str, str]]:
    return build("""你是 Planner。将 Lean theorem 的证明规划成 AND-OR 子目标图。简单目标可只给一个节点。
返回 {"nodes":[{"node_id":string,"depends_on":[string],"informal_goal":string,"formal_goal":string,"methods":[string]}],"replan_rationale":string}。""", {"lean_statement": statement})


def solve_node(statement: str, node: Dict[str, Any], solved: List[Dict[str, Any]], feedback: str) -> List[Dict[str, str]]:
    return build("""你是 Solver。针对当前子目标生成一个可独立编译的 Lean 4 `example`，其中应包含完成该子目标所需的所有变量、前提与 proof。不要伪造编译结果。
返回 {"lean_example":string,"natural_explanation":string,"used_lemmas":[string],"next_action":"solved"|"replan"}。""", {"selected_statement": statement, "node": node, "solved_nodes": solved, "lean_feedback": feedback})


def assemble(statement: str, nodes: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return build("""你是 Proof Assembler。根据已验证节点构建一个完整、可编译的 Lean 4 theorem proof。返回 {"proof_lean":string,"natural_solution":string,"step_mapping":[{"step":string,"evidence":string}]}。不得把未验证节点作为事实。""", {"statement": statement, "verified_nodes": nodes})


def inspect_chunk(problem: str, context: List[Dict[str, Any]], steps: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Request only Lean obligations for one bounded derivation chunk.

    `context` contains already Lean-verified claims, not the full derivation.
    """
    return build("""为每个给定步骤构造独立 Lean 4 `example`，仅表达“题设和已验证前提蕴含该步骤”。
无法可靠形式化则标记 uncertain。不要解释、不要重述步骤、不要输出证明分析。
返回 {"steps":[{"step_id":integer,"status":"checkable"|"uncertain","lean_example":string,"claim":string,"conditions":[string]}]}。""", {"problem": problem, "verified_context": context, "steps": steps})


def classify_failed_steps(problem: str, failed_steps: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Classify only minimal evidence for failed or unformalizable steps."""
    return build("""判断每项是否已有明确数学错误。Lean 不能证明不等于步骤错误；可修复的缺前提或形式化不足应为 uncertain。
不要复述题目或推导。返回 {"items":[{"step_id":integer,"verdict":"invalid"|"uncertain","error_type":"algebra"|"logic"|"theorem"|"condition"|"gap"|"formalization","reason":string,"repair":string}]}。""", {"problem": problem, "items": failed_steps})
