# Formal Math Agent：已知问题与排查手册

本文记录 `F:\project\formal-math-agent` 在 Windows + Anaconda + Lean 4 + 本地 mathlib4 环境下已经遇到的问题、根因、解决方案及验证方法。命令示例均以 Windows Anaconda CMD 为例。

## 1. 总体目录与运行关系

推荐目录结构：

```text
F:\project\
├─ mathlib4\                        # 本地 mathlib4 仓库
└─ formal-math-agent\                # Python Agent 项目
   ├─ config.json
   ├─ src\formal_math_agent\
   ├─ docs\
   └─ FormalMathLean\                # Lake / Lean 子工程
      ├─ lakefile.toml
      ├─ lean-toolchain
      └─ FormalMathLean\Main.lean
```

Python Agent 会把待检查的 Lean 代码写入一个临时目录下的 `Main.lean`，再使用：

```text
lake env lean <临时Main.lean的绝对路径>
```

执行时的工作目录（`cwd`）必须是 `F:\project\formal-math-agent\FormalMathLean`。Lake 根据该目录的 `lakefile.toml` 定位本地 mathlib4。

## 2. 模型 API 配置问题

### 2.1 `Missing API key in environment variable`

**现象**：

```text
RuntimeError: Missing API key in environment variable: sk-...
```

**根因**：`api_key_env` 需要填写环境变量名称，不是 API Key 本身。

**正确配置**：

```json
{
  "provider": {
    "api_key_env": "DEEPSEEK_API_KEY"
  }
}
```

在当前 Anaconda CMD 会话中设置：

```bat
set "DEEPSEEK_API_KEY=你的真实密钥"
```

验证：

```bat
echo %DEEPSEEK_API_KEY%
```

不要把真实密钥写入 `config.json`、日志或 Git 仓库；已泄露的密钥应当立即在服务商后台撤销并重新生成。

### 2.2 OpenAI 兼容接口返回 HTTP 404

**现象**：

```text
RuntimeError: Model API HTTP 404
```

**根因**：客户端调用的是 OpenAI Chat Completions 风格端点，但 `base_url` 却填写成 Anthropic 兼容路径，例如：

```json
"base_url": "https://api.deepseek.com/anthropic"
```

**解决**：OpenAI 兼容调用应使用服务商对应的 OpenAI 根地址，例如：

```json
{
  "provider": {
    "kind": "openai",
    "base_url": "https://api.deepseek.com",
    "model": "<服务商实际支持的模型名>",
    "api_key_env": "DEEPSEEK_API_KEY"
  }
}
```

模型名与端点应以服务商当期官方文档为准。Anthropic 协议需要独立的请求格式和客户端适配器，不能只替换 URL。

### 2.3 `Model did not return JSON for next_step`

**现象**：模型声称输出 JSON，但客户端 JSON 解析失败。

**常见根因**：模型在 JSON 字符串中直接输出 LaTeX，如 `\sum`、`\frac`、`\theta`。JSON 会把反斜杠视为转义起始符，`\s`、`\f`（语义错误）等会导致无效或被错误解析。

**解决策略**：

1. Prompt 明确要求：只返回 JSON；数学内容优先使用 Unicode 或将反斜杠写成 `\\`。
2. 客户端先移除 Markdown 代码围栏，再解析 JSON。
3. 对受控的模型输出，可在解析前仅修复非法反斜杠；不要用过于激进的正则破坏合法 JSON 转义。
4. 每一次 prompt、原始 response、解析后 JSON、解析异常都写入 `events.jsonl`，便于复盘。

## 3. Windows、Conda 与 Lake 命令

### 3.1 PowerShell 能用 `lake`，Anaconda CMD 找不到

**根因**：Conda CMD 的 `PATH` 与 PowerShell 不同；同时用户名 `张宇恒` 的路径在部分 CMD/编码环境中变成乱码，导致 `C:\Users\张宇恒\.elan\bin` 无法正确解析。

**推荐方案：创建 ASCII 路径的 Junction**（在 PowerShell 中执行一次）：

```powershell
New-Item -ItemType Junction -Path C:\lean-elan -Target 'C:\Users\张宇恒\.elan'
```

然后创建 Conda 环境激活脚本：

```text
F:\conda\dire\etc\conda\activate.d\lean-path.bat
```

内容：

```bat
@echo off
set "PATH=C:\lean-elan\bin;%PATH%"
```

重新激活环境后验证：

```bat
conda activate F:\conda\dire
lake --version
where lake
```

Python 配置中也推荐直接使用 ASCII 绝对路径，避免依赖当前 `PATH`：

```json
"command": ["C:\\lean-elan\\bin\\lake.exe", "env", "lean"]
```

### 3.2 在 `F:\project` 运行 `lake clean` 报没有配置文件

**现象**：

```text
error: [root]: no configuration file with a supported extension:
F:\project\lakefile.lean
F:\project\lakefile.toml
```

**根因**：`lake clean` 只能在包含 `lakefile.toml` 或 `lakefile.lean` 的 Lake 项目根目录运行；`F:\project` 只是父目录。

**解决**：进入目标项目，例如：

```bat
cd /d F:\project\formal-math-agent\FormalMathLean
lake clean
```

## 4. 建立本地 mathlib4 Path Dependency

### 4.1 `lake new FormalMathLean mathlib` 报未知模板

**根因**：`mathlib` 不是 Lake 内置项目模板。

**处理方式**：可使用 `lake new FormalMathLean math` 建立基础项目；已有本地 mathlib4 时，更稳妥的是手动配置依赖。

### 4.2 `FormalMathLean/lakefile.toml`

确保内容包含本地路径依赖：

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

路径以 `lakefile.toml` 所在目录为基准：

```text
F:\project\formal-math-agent\FormalMathLean
  -> ..\..\mathlib4
  -> F:\project\mathlib4
```

`FormalMathLean\lean-toolchain` 应复制自 `F:\project\mathlib4\lean-toolchain`，两个文件必须完全一致。

## 5. `unknown module prefix 'Mathlib'`

### 5.1 症状与判断

典型日志：

```text
error: unknown module prefix 'Mathlib'
No directory 'Mathlib' or file 'Mathlib.olean' in the search path entries
```

若搜索路径仅包含：

```text
...\.elan\toolchains\...\lib\lean
```

说明程序直接调用了 `lean`，没有进入 Lake 项目环境。

若搜索路径已包含：

```text
F:\project\mathlib4\.lake\build\lib\lean
```

但仍找不到 `Mathlib`，说明 `Mathlib.olean` 尚未生成，或生成它的 Lean 版本与当前版本不一致。

### 5.2 Python 配置

`config.json`：

```json
{
  "lean": {
    "command": [
      "C:\\lean-elan\\bin\\lake.exe",
      "env",
      "lean"
    ],
    "project_dir": "F:\\project\\formal-math-agent\\FormalMathLean",
    "timeout_seconds": 60,
    "imports": ["Mathlib"]
  }
}
```

`LeanConfig` 必须声明 `project_dir`，否则会报 `unexpected keyword argument 'project_dir'`：

```python
@dataclass
class LeanConfig:
    command: List[str] = field(default_factory=lambda: ["lake", "env", "lean"])
    project_dir: str = ""
    timeout_seconds: int = 60
    imports: List[str] = field(default_factory=lambda: ["Mathlib"])
```

`lean.py` 必须将该目录传给子进程：

```python
completed = subprocess.run(
    self.config.command + [str(path)],
    cwd=self.config.project_dir,
    capture_output=True,
    text=True,
    timeout=self.config.timeout_seconds,
    shell=False,
)
```

临时文件位于 `%TEMP%` 是预期行为；决定依赖解析结果的是 `cwd`，不是临时文件的位置。

### 5.3 构建与验证

先构建与下载本地 mathlib4 对应的缓存：

```bat
cd /d F:\project\mathlib4
"C:\lean-elan\bin\lake.exe" exe cache get
"C:\lean-elan\bin\lake.exe" build
dir F:\project\mathlib4\.lake\build\lib\lean\Mathlib.olean
```

再更新并构建 Agent 的 Lean 子项目：

```bat
cd /d F:\project\formal-math-agent\FormalMathLean
"C:\lean-elan\bin\lake.exe" update
"C:\lean-elan\bin\lake.exe" build
"C:\lean-elan\bin\lake.exe" env lean FormalMathLean\Main.lean
```

最后一条命令没有输出即代表检查通过。

如果日志显示 Lean 工具链版本不同，例如一个是 `v4.33.1`、另一个是 `v4.33.0-rc2`，先同步两个 `lean-toolchain` 文件，再重新执行以上构建步骤。`.olean` 文件不能在不同 Lean 版本之间复用。

## 6. Lean tactic：`positivity`、`linarith` 与 `nlinarith`

三者均来自 `import Mathlib`：

```lean
import Mathlib
```

### 6.1 `positivity`

用于证明表达式为正或非负：

```lean
example (x : ℝ) : 0 ≤ x ^ 2 := by
  positivity
```

### 6.2 `linarith`

用于线性等式和不等式推理。例如由 `x - 1 = 0` 得出 `x = 1`：

```lean
example (x : ℝ) (h : x - 1 = 0) : x = 1 := by
  linarith
```

### 6.3 `nlinarith`

用于多项式形式的非线性算术，如平方或变量乘积：

```lean
example (x : ℝ) (h : x ^ 2 = x) : x * (x - 1) = 0 := by
  nlinarith [h]
```

它不能直接证明析取（`P ∨ Q`）之类的逻辑结构，也不能把一致的假设推导为矛盾。

以下目标：

```lean
example (x : ℝ) (h : x ^ 2 = x) : x = 0 ∨ x = 1 := by
  nlinarith
```

会失败，因为 `x = 0 ∨ x = 1` 要先做逻辑分支。正确写法：

```lean
example (x : ℝ) (h : x ^ 2 = x) : x = 0 ∨ x = 1 := by
  have hfactor : x * (x - 1) = 0 := by
    nlinarith [h]
  rcases mul_eq_zero.mp hfactor with hx | hx
  · exact Or.inl hx
  · right
    linarith
```

流程是：`nlinarith` 完成代数变形，`mul_eq_zero.mp` 使用零乘积定理拆成两支，最后用 `linarith` 完成线性整理。

## 7. 日志记录与安全要求

每个任务建议创建独立目录：

```text
runs\task_<UTC时间戳>\
├─ events.jsonl
├─ prompts\
├─ responses\
├─ formalizations.json
├─ proof_trace.json
└─ audit.json
```

`events.jsonl` 每行使用独立 JSON 对象，至少记录事件时间、候选 ID、命令、工作目录、输入文件路径、退出码、stdout、stderr 和耗时。调试时可记录 API prompt/response，但生产环境必须脱敏 API Key、授权头、个人信息和不应公开的题目数据。

## 8. 最小健康检查清单

在运行 Agent 前依次确认：

```bat
conda activate F:\conda\dire
"C:\lean-elan\bin\lake.exe" --version
cd /d F:\project\mathlib4
"C:\lean-elan\bin\lake.exe" build
cd /d F:\project\formal-math-agent\FormalMathLean
"C:\lean-elan\bin\lake.exe" build
"C:\lean-elan\bin\lake.exe" env lean FormalMathLean\Main.lean
cd /d F:\project\formal-math-agent
python -m formal_math_agent.cli solve --config config.json --problem "证明任意实数的平方非负"
```

若最后一步失败，优先检查该次任务目录内 `events.jsonl` 中的 `command`、`cwd`、`stdout`、`stderr` 与 `exit_code`。
