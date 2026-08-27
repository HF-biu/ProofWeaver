# Formal Math Agent：设计方案

## 1. 目标与可信边界

系统面向两项任务：

1. **解题**：从自然语言题目产生详细解答和 Lean 4 可检查证明。
2. **过程检查**：将用户给出的推导拆为局部证明义务，定位最早错误步骤并给出反例或修复。

可信边界必须分层：

| 等级 | 含义 |
|---|---|
| L0 | 仅模型自然语言推理，未验证。 |
| L1 | 数值或符号工具检查。 |
| L2 | Lean statement 可编译；不代表与原题语义一致。 |
| L3 | Lean 完整 proof 通过。 |
| L4 | L3 且自然语言—Lean 对齐审查通过。 |
| L5 | L4 且高风险歧义经人工专家确认。 |

Lean 接受的证明只保证形式定理成立。自然语言题目被错误形式化时，Lean 仍可能证明一个不等价命题。因此语义对齐是独立模块，不能由编译结果替代。

## 2. 总体架构

```text
题目 / 题目+过程
        │
        ▼
语义建模器 ──→ 多候选 Formalizer ──→ Lean typecheck
        │                                  │
        └──────────── Alignment Checker ◄──┘
                         │ selected statement
                         ▼
                  AND-OR 证明规划图
                         │
                         ▼
        Solver ──→ Lean proof-state/checker ──→ 修复或重规划
                         │
                         ▼
       完整 proof 审计 ──→ 自然语言证据映射 ──→ 最终解答
```

所有模型调用都经过 `ModelClient`；所有 Lean 结果都经过 `LeanRunner`；所有状态改变都写入 JSONL 审计日志。

## 3. 解题模式

### 3.1 候选形式化

Formalizer 一次生成多个候选 Lean statement，并同时给出变量类型、假设、量词、自然语言反向表述和歧义。每个候选先由 Lean 检查语法/类型，再由独立 Checker 对照原题审查量词、定义域、假设与结论。

不满足以下条件的候选不能进入证明：

```text
Lean 可编译 AND 没有高风险语义差异 AND 无待确认歧义
```

### 3.2 规划图

规划器输出 AND-OR 子目标图而非固定线性计划。

- AND 节点：全部依赖子目标成立后主目标才能成立。
- OR 节点：存在多条可能路线，例如归纳、ring、已有引理。
- 节点持有 formal goal、依赖、候选方法、风险、成本和验证证据。

调度优先级为：

```text
可验证性 × 预计成功率 × 主目标影响 / 预计成本
```

### 3.3 证明、修复与回退

Solver 为每个节点生成可检查 Lean 片段或完整 `example`。Lean 返回成功、未闭合目标、类型错误或 theorem 检索失败。失败后按错误类型处理：

| 失败 | 动作 |
|---|---|
| type mismatch | 修正变量类型、coercion 或量词。 |
| theorem 不存在 | 检索 mathlib，再选替代引理。 |
| tactic 无法关闭 | 增加中间引理或拆分目标。 |
| 缺少假设 | 回到形式化层，检查规格与题意。 |
| 多次失败 | 替换 OR 路线或重建局部子图。 |

局部节点成功不等于全题成功；最后必须构建、编译和审计完整 `proof.lean`。

## 4. 过程检查模式

输入为题目和已有自然语言推导。Trace Formalizer 将每个步骤转成：

```text
已验证历史 Γ ⊢ 当前 claim C
```

Lean 试图验证该局部义务。若失败，Checker 综合 Lean error、候选缺失前提、反例搜索和原始文本，报告最早错误。

示例：从 `x²=x` 直接“除以 x”得到 `x=1`。局部义务无法由 `x²=x` 推出；加入 `x≠0` 后可成立，而 `x=0` 是反例。因此归类为 `missing_precondition`，并指出后续“唯一解”受影响。

错误 taxonomy：

```text
formalization_mismatch, syntax_or_type_error, missing_precondition,
invalid_inference, misused_theorem, unfinished_subgoal,
circular_reasoning, unsupported_claim, numerical_only_evidence,
pedagogical_gap, ambiguous_statement
```

## 5. 三类 agent

| Agent | 职责 | 不能承担的职责 |
|---|---|---|
| Formalizer | 生成 Lean 候选、变量/量词/假设表、步骤义务。 | 宣称语义必然正确。 |
| Planner/Solver | 构建子目标图、检索引理、生成 Lean tactic/proof。 | 以自然语言自评代替 Lean。 |
| Alignment/Checker | 原题↔Lean、步骤↔证据对齐；错误分类和解释。 | 覆盖 Lean kernel 的形式验证职责。 |

## 6. 重点技术

### Structured output 和 JSON 恢复

所有模型要求 JSON。客户端会剥离 Markdown code fence，并仅修复 JSON 字符串内非法单反斜杠 LaTeX 命令，例如 `\sum`，原始响应仍保留在日志中。

### Lean Runner

Lean Runner 使用临时 `.lean` 文件与 `lake env lean` 执行验证，捕获 stdout、stderr、exit code 与耗时。生产部署应在容器或受限工作目录运行 Lean，禁止模型控制 shell 参数。

### 证据映射

最终解答的每个自然语言步骤要映射到：Lean declaration、tactic、已有 theorem 或明确“未验证”的标签。这样“解释详细”与“形式证明正确”不会混淆。

### 成本控制

不要每一步重发完整历史。传递当前 formal goal、必要祖先引理、最近 Lean error 与压缩状态摘要；仅在量词变更、除法、极限、积分交换、强 theorem 等高风险点调用 Alignment Checker。

## 7. 接口和部署

模型 API 通过统一 OpenAI Chat Completions 请求格式接入：

```text
openai：官方 API
hy3：OpenAI-compatible 网关
local：vLLM、SGLang、Ollama 的 OpenAI-compatible 网关
```

业务代码不依赖具体模型提供方。Lean 作为独立硬验证工具，不属于模型 adapter。

## 8. Benchmark

| 能力 | 数据集 |
|---|---|
| 非形式解答 | MATH-500、TheoremQA |
| statement autoformalization | ProofNet、FormalMATH、LeanEuclid |
| Lean proof search | miniF2F、PutnamBench、LeanDojo |
| 错误定位 | 自建人工标注/注入错误推导集 |

报告指标：statement compile rate、semantic alignment rate、Lean pass@k、end-to-end solve rate、repair success rate、最早错误定位准确率、错误分类 Macro-F1、API token/成本/时延。

## 9. 预期效果与边界

预期在初高中代数、数论、组合、基础不等式和有限求和上形成可审计闭环。复杂几何、研究级分析、图像题和歧义极强的题目应返回 `uncertain` 或请求人工确认。

系统的创新空间不在“多 agent 分工”本身，而在：以形式证明义务为中心的自然语言过程错误定位、语义忠实性度量、异构验证证据路由与成本感知的 AND-OR 证明搜索。
