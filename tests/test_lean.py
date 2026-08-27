import unittest
from unittest.mock import patch

from formal_math_agent.config import LeanConfig
from formal_math_agent.lean import LeanRunner


class LeanRunnerTests(unittest.TestCase):
    def test_missing_lean_is_reported_not_raised(self):
        runner = LeanRunner(LeanConfig(command=["definitely-missing-lean-command"]))
        result = runner.check("example : True := by trivial")
        self.assertFalse(result.ok)
        self.assertEqual(result.exit_code, 127)


if __name__ == "__main__":
    unittest.main()
