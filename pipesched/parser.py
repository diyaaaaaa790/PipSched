"""Recursive-descent parser for the assembly grammar (FLAT concept).

One parse procedure per non-terminal of the LL(1) grammar in ``grammar.py``.
The parser builds a parse (derivation) tree, collects *all* syntax errors using
panic-mode recovery (skip to the end of the line) and also runs a small semantic
pass (duplicate / undefined labels).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .grammar import EPS, NONTERMINALS
from .isa import NUM_REGS, Instr, Program
from .lexer import Token, tokenize

INSTR_FIRST = {"ROP", "IOP", "MEMOP", "BROP", "JOP", "NOP"}


# --------------------------------------------------------------------------
# parse tree
# --------------------------------------------------------------------------
@dataclass
class Node:
    name: str
    children: list = field(default_factory=list)
    token: Optional[Token] = None

    @property
    def is_terminal(self) -> bool:
        return self.name not in NONTERMINALS

    @property
    def symbol_text(self) -> str:
        """Lexeme for terminals, name for non-terminals."""
        if self.token is not None:
            return self.token.text
        return self.name


def tree_to_text(root: Node) -> str:
    """Indented text rendering (iterative, safe for very deep trees)."""
    out = []
    stack = [(root, "", True, True)]
    while stack:
        node, prefix, last, is_root = stack.pop()
        if is_root:
            out.append(node.name)
            child_prefix = ""
        else:
            label = node.name if node.token is None else f"{node.name}  '{node.token.text}'"
            out.append(prefix + ("└── " if last else "├── ") + label)
            child_prefix = prefix + ("    " if last else "│   ")
        for i in range(len(node.children) - 1, -1, -1):
            stack.append((node.children[i], child_prefix, i == len(node.children) - 1, False))
    return "\n".join(out)


def tree_to_dot(root: Node) -> str:
    """Graphviz DOT source of a parse tree."""
    lines = ["digraph ParseTree {", '  node [fontname="Helvetica", fontsize=11];',
             "  edge [color=\"#888888\"];"]
    counter = 0
    stack = [(root, None)]
    while stack:
        node, parent = stack.pop()
        nid = counter
        counter += 1
        if node.name == EPS:
            lines.append(f'  n{nid} [label="ε", shape=plaintext];')
        elif node.is_terminal:
            lab = f"{node.name}\\n{node.token.text}".replace('"', '\\"')
            lines.append(f'  n{nid} [label="{lab}", shape=box, style="filled,rounded", '
                         f'fillcolor="#fff3cd", color="#d4a017"];')
        else:
            lines.append(f'  n{nid} [label="{node.name}", shape=ellipse, style=filled, '
                         f'fillcolor="#d6e9ff", color="#4a86c5"];')
        if parent is not None:
            lines.append(f"  n{parent} -> n{nid};")
        for child in reversed(node.children):
            stack.append((child, nid))
    lines.append("}")
    return "\n".join(lines)


def leftmost_derivation(root: Node) -> list:
    """Leftmost derivation (list of sentential forms) read off a parse tree."""
    def show(sentential):
        parts = []
        for n in sentential:
            if n.name == EPS:
                continue
            parts.append(n.token.text if n.is_terminal else f"<{n.name}>")
        return " ".join(parts) if parts else "ε"

    forms = [[root]]
    steps = [show(forms[0])]
    current = [root]
    while True:
        pos = next((i for i, n in enumerate(current) if not n.is_terminal), None)
        if pos is None:
            break
        node = current[pos]
        current = current[:pos] + node.children + current[pos + 1:]
        steps.append(show(current))
    return steps


# --------------------------------------------------------------------------
# result containers
# --------------------------------------------------------------------------
@dataclass
class Issue:
    line: int
    col: int
    message: str
    kind: str = "syntax"        # 'syntax' | 'semantic'
    source: str = ""


@dataclass
class LineInfo:
    line_no: int
    source: str
    node: Node


@dataclass
class ParseResult:
    tokens: list
    tree: Node
    lines: list
    program: Program
    errors: list

    @property
    def ok(self) -> bool:
        return not self.errors


class ParseError(Exception):
    def __init__(self, token: Token, message: str):
        super().__init__(message)
        self.token = token
        self.message = message


_KIND_NAME = {
    "REG": "a register (R0-R31)", "NUM": "a number", "ID": "a label name",
    "COMMA": "','", "COLON": "':'", "LPAREN": "'('", "RPAREN": "')'",
    "NL": "end of line", "ROP": "an R-type mnemonic", "IOP": "an immediate mnemonic",
    "MEMOP": "LW/SW", "BROP": "BEQ/BNE", "JOP": "J", "NOP": "NOP",
}


def _describe(tok: Token) -> str:
    if tok.kind == "NL":
        return "end of line"
    if tok.kind == "EOF":
        return "end of file"
    if tok.kind == "ERROR":
        return f"illegal character '{tok.text}'"
    return f"'{tok.text}'"


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
class Parser:
    def __init__(self, tokens: list):
        self.toks = tokens
        self.i = 0

    # -- token helpers --
    def peek(self) -> Token:
        return self.toks[self.i]

    def expect(self, kind: str) -> Node:
        tok = self.peek()
        if tok.kind != kind:
            raise ParseError(tok, f"expected {_KIND_NAME.get(kind, kind)}, found {_describe(tok)}")
        if kind == "REG":
            num = int(tok.text[1:])
            if num >= NUM_REGS:
                raise ParseError(tok, f"register {tok.text} does not exist (valid: R0-R{NUM_REGS - 1})")
        self.i += 1
        return Node(kind, token=tok)

    def sync(self) -> None:
        """Panic-mode recovery: skip to (and past) the end of the current line."""
        while self.peek().kind not in ("NL", "EOF"):
            self.i += 1
        if self.peek().kind == "NL":
            self.i += 1

    # -- non-terminals --
    def line(self):
        """Line -> ID ':' OptInstr NL | Instr NL.  Returns (node, label, instr)."""
        tok = self.peek()
        if tok.kind == "ID":
            idn = self.expect("ID")
            if self.peek().kind != "COLON":
                raise ParseError(tok, f"unknown instruction '{tok.text}' (a label needs a ':' after it)")
            colon = self.expect("COLON")
            opt, ins = self.opt_instr()
            nl = self.expect("NL")
            return Node("Line", [idn, colon, opt, nl]), tok.text, ins
        if tok.kind in INSTR_FIRST:
            inode, ins = self.instr()
            nl = self.expect("NL")
            return Node("Line", [inode, nl]), None, ins
        raise ParseError(tok, f"expected an instruction or a label, found {_describe(tok)}")

    def opt_instr(self):
        tok = self.peek()
        if tok.kind in INSTR_FIRST:
            inode, ins = self.instr()
            return Node("OptInstr", [inode]), ins
        if tok.kind == "NL":
            return Node("OptInstr", [Node(EPS)]), None
        raise ParseError(tok, f"expected an instruction or end of line, found {_describe(tok)}")

    def instr(self):
        kind = self.peek().kind
        method = {"ROP": self.r_instr, "IOP": self.i_instr, "MEMOP": self.mem_instr,
                  "BROP": self.br_instr, "JOP": self.j_instr, "NOP": self.nop_instr}[kind]
        sub, ins = method()
        return Node("Instr", [sub]), ins

    def r_instr(self):
        op = self.expect("ROP")
        rd = self.expect("REG"); c1 = self.expect("COMMA")
        rs = self.expect("REG"); c2 = self.expect("COMMA")
        rt = self.expect("REG")
        ins = Instr(op.token.text.upper(), rd=int(rd.token.text[1:]), rs=int(rs.token.text[1:]),
                    rt=int(rt.token.text[1:]), line=op.token.line)
        return Node("RInstr", [op, rd, c1, rs, c2, rt]), ins

    def i_instr(self):
        op = self.expect("IOP")
        rd = self.expect("REG"); c1 = self.expect("COMMA")
        rs = self.expect("REG"); c2 = self.expect("COMMA")
        num = self.expect("NUM")
        ins = Instr(op.token.text.upper(), rd=int(rd.token.text[1:]), rs=int(rs.token.text[1:]),
                    imm=int(num.token.text, 0), line=op.token.line)
        return Node("IInstr", [op, rd, c1, rs, c2, num]), ins

    def mem_instr(self):
        op = self.expect("MEMOP")
        reg = self.expect("REG"); c = self.expect("COMMA")
        num = self.expect("NUM"); lp = self.expect("LPAREN")
        base = self.expect("REG"); rp = self.expect("RPAREN")
        r, b = int(reg.token.text[1:]), int(base.token.text[1:])
        name = op.token.text.upper()
        ins = (Instr(name, rd=r, rs=b, imm=int(num.token.text, 0), line=op.token.line)
               if name == "LW" else
               Instr(name, rt=r, rs=b, imm=int(num.token.text, 0), line=op.token.line))
        return Node("MemInstr", [op, reg, c, num, lp, base, rp]), ins

    def br_instr(self):
        op = self.expect("BROP")
        rs = self.expect("REG"); c1 = self.expect("COMMA")
        rt = self.expect("REG"); c2 = self.expect("COMMA")
        lab = self.expect("ID")
        ins = Instr(op.token.text.upper(), rs=int(rs.token.text[1:]), rt=int(rt.token.text[1:]),
                    target=lab.token.text, line=op.token.line)
        return Node("BrInstr", [op, rs, c1, rt, c2, lab]), ins

    def j_instr(self):
        op = self.expect("JOP")
        lab = self.expect("ID")
        ins = Instr("J", target=lab.token.text, line=op.token.line)
        return Node("JInstr", [op, lab]), ins

    def nop_instr(self):
        op = self.expect("NOP")
        return op, Instr("NOP", line=op.token.line)


def parse(source: str) -> ParseResult:
    """Parse assembly ``source``; never raises, returns every error found."""
    tokens = tokenize(source)
    src_lines = source.split("\n")
    p = Parser(tokens)
    errors: list = []
    line_infos: list = []
    program = Program()

    def src_of(n: int) -> str:
        return src_lines[n - 1].rstrip() if 1 <= n <= len(src_lines) else ""

    label_lines: dict = {}
    while p.peek().kind != "EOF":
        start_tok = p.peek()
        try:
            node, label, ins = p.line()
        except ParseError as e:
            errors.append(Issue(e.token.line, e.token.col, e.message, "syntax", src_of(e.token.line)))
            p.sync()
            continue
        if label is not None:
            if label in program.labels:
                errors.append(Issue(start_tok.line, start_tok.col,
                                    f"label '{label}' is already defined on line {label_lines[label]}",
                                    "semantic", src_of(start_tok.line)))
            else:
                program.labels[label] = len(program.instrs)
                label_lines[label] = start_tok.line
        if ins is not None:
            ins.orig_idx = len(program.instrs)
            program.instrs.append(ins)
        line_infos.append(LineInfo(start_tok.line, src_of(start_tok.line), node))

    for ins in program.instrs:
        if ins.target is not None and ins.target not in program.labels:
            errors.append(Issue(ins.line, 1, f"undefined label '{ins.target}'",
                                "semantic", src_of(ins.line)))
    errors.sort(key=lambda e: (e.line, e.col))

    lines_node = Node("Lines", [Node(EPS)])
    for info in reversed(line_infos):
        lines_node = Node("Lines", [info.node, lines_node])
    tree = Node("Program", [lines_node])
    return ParseResult(tokens, tree, line_infos, program, errors)
