"""The ``when`` expression grammar — deliberately minimal, per the PRD.

Identifiers denote state fields. String/enum literals are single-quoted;
numbers and ``true``/``false`` are bare. Operators: ``== != < <= > >= && || !``
and parentheses. Nothing else — no arithmetic, no function calls, no indexing.

AST nodes are plain tuples:
    ("ident", name) | ("lit", value) | ("not", expr)
    | ("cmp", op, left, right) | ("and", l, r) | ("or", l, r)
"""

from __future__ import annotations


class ExprError(ValueError):
    pass


_CMP_OPS = ("==", "!=", "<=", ">=", "<", ">")
_TWO_CHAR = ("==", "!=", "<=", ">=", "&&", "||")


def tokenize(src: str) -> list[tuple[str, object]]:
    tokens: list[tuple[str, object]] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
            continue
        two = src[i:i + 2]
        if two in _TWO_CHAR:
            tokens.append(("op", two))
            i += 2
            continue
        if c in "<>!()":
            tokens.append(("op", c))
            i += 1
            continue
        if c == "'":
            j = src.find("'", i + 1)
            if j == -1:
                raise ExprError(f"unterminated string literal at position {i}")
            tokens.append(("str", src[i + 1:j]))
            i = j + 1
            continue
        if c == '"':
            raise ExprError("double-quoted strings are not allowed; use single quotes: 'value'")
        if c.isdigit() or (c == "-" and i + 1 < n and src[i + 1].isdigit()):
            j = i + 1
            while j < n and (src[j].isdigit() or src[j] == "."):
                j += 1
            text = src[i:j]
            tokens.append(("num", float(text) if "." in text else int(text)))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            word = src[i:j]
            if word in ("true", "false"):
                tokens.append(("bool", word == "true"))
            else:
                tokens.append(("ident", word))
            i = j
            continue
        raise ExprError(f"unexpected character {c!r} — the when grammar has no arithmetic, "
                        "function calls or indexing; compute in a function node instead")
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, object]]):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self):
        tok = self.peek()
        if tok is None:
            raise ExprError("unexpected end of expression")
        self.pos += 1
        return tok

    def expect_op(self, op: str):
        tok = self.take()
        if tok != ("op", op):
            raise ExprError(f"expected {op!r}, got {tok[1]!r}")

    def parse(self):
        expr = self.or_expr()
        if self.peek() is not None:
            raise ExprError(f"unexpected trailing token {self.peek()[1]!r}")
        return expr

    def or_expr(self):
        left = self.and_expr()
        while self.peek() == ("op", "||"):
            self.take()
            left = ("or", left, self.and_expr())
        return left

    def and_expr(self):
        left = self.not_expr()
        while self.peek() == ("op", "&&"):
            self.take()
            left = ("and", left, self.not_expr())
        return left

    def not_expr(self):
        if self.peek() == ("op", "!"):
            self.take()
            return ("not", self.not_expr())
        return self.cmp_expr()

    def cmp_expr(self):
        left = self.atom()
        tok = self.peek()
        if tok is not None and tok[0] == "op" and tok[1] in _CMP_OPS:
            op = self.take()[1]
            return ("cmp", op, left, self.atom())
        return left

    def atom(self):
        tok = self.take()
        kind, value = tok
        if kind == "ident":
            return ("ident", value)
        if kind in ("str", "num", "bool"):
            return ("lit", value)
        if tok == ("op", "("):
            inner = self.or_expr()
            self.expect_op(")")
            return inner
        raise ExprError(f"unexpected token {value!r}")


def parse_when(src: str):
    """Parse a when expression; raises :class:`ExprError` on grammar violations."""
    return _Parser(tokenize(src)).parse()


def identifiers(src: str) -> set[str]:
    """State-field identifiers referenced by *src* (literals excluded)."""
    found: set[str] = set()

    def walk(node):
        tag = node[0]
        if tag == "ident":
            found.add(node[1])
        elif tag == "not":
            walk(node[1])
        elif tag == "cmp":
            walk(node[2]); walk(node[3])
        elif tag in ("and", "or"):
            walk(node[1]); walk(node[2])

    walk(parse_when(src))
    return found
