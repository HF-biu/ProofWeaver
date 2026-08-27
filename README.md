# Formal Math Agent

Lean 4 为可信内核的“形式化—规划—解题—检查”数学 Agent。系统支持：

- **solve**：自然语言题目 → 多候选 Lean 规格 → 子目标规划 → Lean 验证证明 → 详细解答；
- **inspect**：题目 + 已有推导 → 逐步骤形式化义务 → Lean 检查 → 最早错误定位；
- OpenAI、HY3 与本地 OpenAI-compatible HTTP 网关；
- 每个 prompt、response、Lean 输出和状态迁移写入独立审计目录。

详细方案见 [docs/design.md](docs/design.md)。

## 安装 Lean 4 与 mathlib4（Windows）

形式验证功能依赖 [Lean 4](https://lean-lang.org/install/manual/)、Lake 与 [mathlib4](https://github.com/leanprover-community/mathlib4)。本项目使用 `elan` 管理 Lean 版本；不要手动安装一个固定版本的 Lean 并长期复用，因为项目的 `lean-toolchain` 会指定与 mathlib 对应的版本。

### 1. 前置条件

安装 [Git for Windows](https://git-scm.com/download/win)。然后在 **PowerShell 7.4+** 或 Windows PowerShell 中安装 elan：

```powershell
curl -O --location https://elan.lean-lang.org/elan-init.ps1
powershell -ExecutionPolicy Bypass -f elan-init.ps1
Remove-Item elan-init.ps1
```

关闭并重新打开终端后验证：

```powershell
elan --version
lake --version
lean --version
```

如果 PowerShell 可运行 `lake`，但 Anaconda CMD 中找不到它，且 Windows 用户名含中文字符，建议创建一个 ASCII 路径的 Junction。


重新执行 `conda activate ` 后，可用 `where lake` 确认。

### 2. 下载并构建本地 mathlib4

本项目的默认目录布局如下：

```text
F:\project\
├─ mathlib4\
└─ formal-math-agent\
   └─ FormalMathLean\
```

若尚未下载 mathlib4：

```bat
cd /d F:\project
git clone https://github.com/leanprover-community/mathlib4.git
cd /d F:\project\mathlib4
"C:\lean-elan\bin\lake.exe" exe cache get
"C:\lean-elan\bin\lake.exe" build
```

`lake exe cache get` 会下载与该 mathlib 版本匹配的预编译依赖，通常远快于从头编译。构建完成后应存在：

```bat
dir F:\project\mathlib4\.lake\build\lib\lean\Mathlib.olean
```

### 3. 配置 Agent 的 Lean 子工程

`F:\project\formal-math-agent\FormalMathLean\lakefile.toml` 使用本地 path dependency：

```toml
name = "formal_math_lean"
version = "0.1.0"
defaultTargets = ["FormalMathLean"]

[[lean_lib]]
name = "FormalMathLean"

[[require]]
name = "mathlib"
path = "../../mathlib4"
```

使两个项目使用**完全相同**的工具链：

```bat
copy /Y F:\project\mathlib4\lean-toolchain F:\project\formal-math-agent\FormalMathLean\lean-toolchain
cd /d F:\project\formal-math-agent\FormalMathLean
"C:\lean-elan\bin\lake.exe" update
"C:\lean-elan\bin\lake.exe" build
```

创建或确认 `FormalMathLean\Main.lean`：

```lean
import Mathlib

example (x : ℝ) : 0 ≤ x ^ 2 := by
  positivity
```

验证本地依赖：

```bat
cd /d F:\project\formal-math-agent\FormalMathLean
"C:\lean-elan\bin\lake.exe" env lean FormalMathLean\Main.lean
```

没有输出即为成功。若出现 `unknown module prefix 'Mathlib'`，依次检查 `lakefile.toml` 的路径、`Mathlib.olean` 是否存在，以及两个 `lean-toolchain` 文件是否相同；详见 [docs/troubleshooting.md](docs/troubleshooting.md)。

### 4. 连接 Python Agent

在 `config.json` 中指定 Lake 命令和 Lean 子工程根目录：

```json
"lean": {
  "command": ["your path of lake.exe", "env", "lean"],
  "project_dir": "F:\\project\\formal-math-agent\\FormalMathLean",
  "timeout_seconds": 60,
  "imports": ["Mathlib"]
}
```

Agent 会把待验证代码写入临时目录，但以 `project_dir` 作为工作目录执行 `lake env lean`，因此 Lake 仍可加载本地 mathlib4。

## 快速开始

要求：Python 3.8+。执行形式验证前，请先完成上方 Lean 4 与 mathlib4 配置。

```cmd
cd F:\project\formal-math-agent
copy config.example.json config.json
set DEEPSEEK_API_KEY=你的密钥
set PYTHONPATH=%CD%\src
python -m formal_math_agent.cli solve --config config.json --problem "证明：对任意实数 x，x^2 ≥ 0。"
```

检查既有过程：

```cmd
python -m formal_math_agent.cli inspect --config config.json --problem "求解 x^2=x" --derivation "两边除以 x 得 x=1，因此唯一解为1。"
```

批量入口仅接受用户有权使用的本地 JSON/JSONL 导出：

```cmd
python -m formal_math_agent.cli bench --config config.json --dataset miniF2F --input F:\data\minif2f.jsonl --limit 100
```

每次任务保存到 `runs/<task-id>/`：

```text
events.jsonl                 全量模型/Lean 事件
formalization_candidates.json
proof_plan.json
proof_trace.json
selected_statement.lean
proof.lean
alignment_report.json
check_report.json
result.json
final_solution.md
```

API Key 仅从环境变量读取；不要写入配置、日志或版本库。
