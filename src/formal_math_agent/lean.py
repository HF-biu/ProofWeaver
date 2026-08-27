import subprocess
import tempfile
import time
from pathlib import Path
from typing import List

from .config import LeanConfig
from .types import LeanResult


class LeanRunner:
    def __init__(self, config: LeanConfig) -> None:
        self.config = config

    def check(self, code: str) -> LeanResult:
        imports = "\n".join("import " + item for item in self.config.imports)
        source = imports + "\n\n" + code
        start = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="formal_math_agent_") as folder:
            path = Path(folder) / "Main.lean"
            path.write_text(source, encoding="utf-8")
            try:
                completed = subprocess.run(
                    self.config.command + [str(path)], cwd=self.config.project_dir or None, capture_output=True, text=True,
                    timeout=self.config.timeout_seconds, shell=False,
                )
                return LeanResult(completed.returncode == 0, completed.stdout, completed.stderr, completed.returncode, int((time.monotonic() - start) * 1000))
            except FileNotFoundError as exc:
                return LeanResult(False, "", "Lean command unavailable: {}".format(exc), 127, int((time.monotonic() - start) * 1000))
            except OSError as exc:
                return LeanResult(False, "", "Lean process could not start: {}".format(exc), 127, int((time.monotonic() - start) * 1000))
            except subprocess.TimeoutExpired as exc:
                return LeanResult(False, exc.stdout or "", "Lean timeout", 124, int((time.monotonic() - start) * 1000))
