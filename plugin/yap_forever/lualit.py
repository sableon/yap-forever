"""Parse Lua table literals (the generated data files of WoW addons).

Supports numbers, strings, nil, true/false, `[key] = v`, `name = v` and positional
values. A positional nil keeps its slot (None). Tables with only positional values
become lists; others become dicts (positional values keyed 1..n).
"""
import re

_TOKEN = re.compile(r"""
    (?P<ws>\s+|--[^\n]*)
  | (?P<str>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | (?P<num>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)
  | (?P<name>[A-Za-z_]\w*)
  | (?P<punct>[{}\[\]=,;])
""", re.VERBOSE)

_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'"}


def _tokens(text: str):
    pos = 0
    out = []
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"unexpected character {text[pos]!r} at {pos}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        out.append((kind, m.group()))
    return out


def _unquote(s: str) -> str:
    body = s[1:-1]
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), body)


class _Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None)

    def take(self, expected=None):
        tok = self.toks[self.i]
        if expected is not None and tok[1] != expected:
            raise ValueError(f"expected {expected!r}, got {tok[1]!r}")
        self.i += 1
        return tok

    def value(self):
        kind, v = self.peek()
        if v == "{":
            return self.table()
        self.take()
        if kind == "str":
            return _unquote(v)
        if kind == "num":
            return float(v) if any(c in v for c in ".eE") else int(v)
        if kind == "name" and v in ("nil", "true", "false"):
            return {"nil": None, "true": True, "false": False}[v]
        raise ValueError(f"unexpected token {v!r}")

    def table(self):
        self.take("{")
        positional, keyed = [], {}
        while self.peek()[1] != "}":
            kind, v = self.peek()
            if v == "[":
                self.take("[")
                key = self.value()
                self.take("]")
                self.take("=")
                keyed[key] = self.value()
            elif kind == "name" and self.peek(1)[1] == "=":
                self.take()
                self.take("=")
                keyed[v] = self.value()
            else:
                positional.append(self.value())
            if self.peek()[1] in (",", ";"):
                self.take()
        self.take("}")
        if not keyed:
            return positional
        for n, v in enumerate(positional, 1):
            keyed[n] = v
        return keyed


def parse(text: str):
    p = _Parser(_tokens(text))
    return p.value()


def extract_table(source: str, name: str) -> str:
    """Return the `{...}` literal assigned to `ns.<name>` or `QuestieDB.<name>`."""
    m = re.search(r"(?:ns|QuestieDB)\." + re.escape(name) + r"\s*=\s*(?:\[\[return\s*)?\{", source)
    if not m:
        raise KeyError(name)
    start = m.end() - 1
    depth, i, n = 0, start, len(source)
    while i < n:
        c = source[i]
        if c in "\"'":
            j = i + 1
            while source[j] != c:
                j += 2 if source[j] == "\\" else 1
            i = j
        elif c == "-" and source.startswith("--", i):
            i = source.find("\n", i)
            if i < 0:
                break
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1
    raise ValueError(f"unbalanced table {name}")
