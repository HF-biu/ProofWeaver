import unittest

from formal_math_agent.model import parse_json_content


class ModelJsonTests(unittest.TestCase):
    def test_repairs_raw_latex_escape(self):
        result = parse_json_content(r'{"proof":"\sum_{n=1}^{∞} n"}')
        self.assertEqual(result["proof"], r"\sum_{n=1}^{∞} n")

    def test_parses_fenced_json(self):
        result = parse_json_content('```json\n{"ok": true}\n```')
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
