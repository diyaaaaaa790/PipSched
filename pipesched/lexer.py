"""Lexer: turns assembly text into tokens (terminals of the grammar)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .isa import MNEMONIC_KIND


@dataclass
class Token:
    kind: str
    text: str
    line: int
    col: int

    def __repr__(self) -> str:  # compact, handy in tests
        return f"{self.kind}({self.text!r})@{self.line}:{self.col}"


_SPEC = [
    ("WS", r"[ \t\r]+"),
    ("COMMENT", r"(?:#|;)[^\n]*"),
    ("NL", r"\n"),
    ("NUM", r"-?(?:0[xX][0-9a-fA-F]+|\d+)"),
    ("IDENT", r"[A-Za-z_][A-Za-z_0-9]*"),
    ("COMMA", r","),
    ("COLON", r":"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("ERROR", r"."),
]
_RE = re.compile("|".join(f"(?P<{n}>{p})" for n, p in _SPEC))
_REG_RE = re.compile(r"R\d+", re.IGNORECASE)


def tokenize(source: str) -> list:
    """Tokenize ``source``.

    Blank lines and comment-only lines produce no tokens (consecutive NL tokens
    are collapsed), so the grammar never has to deal with empty lines.
    """
    tokens: list = []
    line, line_start = 1, 0
    for m in _RE.finditer(source):
        kind, text = m.lastgroup, m.group()
        col = m.start() - line_start + 1
        if kind in ("WS", "COMMENT"):
            continue
        if kind == "NL":
            if tokens and tokens[-1].kind != "NL":
                tokens.append(Token("NL", "\\n", line, col))
            line += 1
            line_start = m.end()
            continue
        if kind == "IDENT":
            up = text.upper()
            if up in MNEMONIC_KIND:
                kind = MNEMONIC_KIND[up]
            elif _REG_RE.fullmatch(text):
                kind = "REG"
            else:
                kind = "ID"
        tokens.append(Token(kind, text, line, col))
    if tokens and tokens[-1].kind != "NL":
        tokens.append(Token("NL", "\\n", line, 0))
    tokens.append(Token("EOF", "", line, 0))
    return tokens
