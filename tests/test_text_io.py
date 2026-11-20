import ast
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "plugin" / "yap_forever"


def _mode(call: ast.Call) -> str:
    """Mode string of an open() call, '' when absent or not a literal."""
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    if len(call.args) > 1 and isinstance(call.args[1], ast.Constant):
        return str(call.args[1].value)
    return ""


def offenders() -> list[str]:
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name not in ("read_text", "write_text", "open"):
                continue
            if isinstance(f, ast.Attribute) and name == "open" and getattr(f.value, "id", "") == "os":
                continue  # os.open works on bytes
            if name == "open" and "b" in _mode(node):
                continue
            if not any(kw.arg == "encoding" for kw in node.keywords):
                found.append(f"{path.relative_to(PACKAGE.parent)}:{node.lineno}")
    return found


class TextIoTests(unittest.TestCase):
    def test_text_io_declares_encoding(self):
        self.assertEqual(offenders(), [])


if __name__ == "__main__":
    unittest.main()
