"""The context-free grammar of the assembly language (FLAT concept).

The grammar is stored as data so that the same definition is used for
documentation, FIRST/FOLLOW computation, the LL(1) check and the parse tree.
"""
from __future__ import annotations

EPS = "ε"

# (lhs, rhs) -- rhs is a list of grammar symbols; [EPS] is the empty string
PRODUCTIONS = [
    ("Program",  ["Lines"]),
    ("Lines",    ["Line", "Lines"]),
    ("Lines",    [EPS]),
    ("Line",     ["ID", "COLON", "OptInstr", "NL"]),
    ("Line",     ["Instr", "NL"]),
    ("OptInstr", ["Instr"]),
    ("OptInstr", [EPS]),
    ("Instr",    ["RInstr"]),
    ("Instr",    ["IInstr"]),
    ("Instr",    ["MemInstr"]),
    ("Instr",    ["BrInstr"]),
    ("Instr",    ["JInstr"]),
    ("Instr",    ["NOP"]),
    ("RInstr",   ["ROP", "REG", "COMMA", "REG", "COMMA", "REG"]),
    ("IInstr",   ["IOP", "REG", "COMMA", "REG", "COMMA", "NUM"]),
    ("MemInstr", ["MEMOP", "REG", "COMMA", "NUM", "LPAREN", "REG", "RPAREN"]),
    ("BrInstr",  ["BROP", "REG", "COMMA", "REG", "COMMA", "ID"]),
    ("JInstr",   ["JOP", "ID"]),
]

START = "Program"
END = "$"
NONTERMINALS = {lhs for lhs, _ in PRODUCTIONS}
TERMINALS = {s for _, rhs in PRODUCTIONS for s in rhs
             if s not in NONTERMINALS and s != EPS}

TERMINAL_HELP = {
    "ROP": "ADD | SUB | AND | OR | MUL",
    "IOP": "ADDI | SUBI",
    "MEMOP": "LW | SW",
    "BROP": "BEQ | BNE",
    "JOP": "J",
    "NOP": "NOP",
    "REG": "R0 ... R31",
    "NUM": "integer (decimal or 0x hex)",
    "ID": "label name",
    "COMMA": ",", "COLON": ":", "LPAREN": "(", "RPAREN": ")",
    "NL": "end of line",
}


def grammar_text() -> str:
    """Pretty-print the grammar, grouping alternatives of the same lhs."""
    order, groups = [], {}
    for lhs, rhs in PRODUCTIONS:
        if lhs not in groups:
            groups[lhs] = []
            order.append(lhs)
        groups[lhs].append(" ".join(rhs))
    width = max(len(n) for n in order)
    return "\n".join(f"{n:<{width}} → " + "  |  ".join(groups[n]) for n in order)


def first_of_sequence(seq, first) -> set:
    out = set()
    for sym in seq:
        if sym == EPS:
            continue
        if sym in TERMINALS:
            out.add(sym)
            return out
        out |= first[sym] - {EPS}
        if EPS not in first[sym]:
            return out
    out.add(EPS)
    return out


def compute_first() -> dict:
    first = {nt: set() for nt in NONTERMINALS}
    changed = True
    while changed:
        changed = False
        for lhs, rhs in PRODUCTIONS:
            new = first_of_sequence(rhs, first)
            if not new <= first[lhs]:
                first[lhs] |= new
                changed = True
    return first


def compute_follow(first=None) -> dict:
    first = first or compute_first()
    follow = {nt: set() for nt in NONTERMINALS}
    follow[START].add(END)
    changed = True
    while changed:
        changed = False
        for lhs, rhs in PRODUCTIONS:
            for i, sym in enumerate(rhs):
                if sym not in NONTERMINALS:
                    continue
                rest_first = first_of_sequence(rhs[i + 1:], first)
                add = rest_first - {EPS}
                if EPS in rest_first:
                    add |= follow[lhs]
                if not add <= follow[sym]:
                    follow[sym] |= add
                    changed = True
    return follow


def ll1_table():
    """Return (table, conflicts). table[(nonterminal, terminal)] = production index."""
    first = compute_first()
    follow = compute_follow(first)
    table, conflicts = {}, []
    for idx, (lhs, rhs) in enumerate(PRODUCTIONS):
        f = first_of_sequence(rhs, first)
        select = (f - {EPS}) | (follow[lhs] if EPS in f else set())
        for t in select:
            key = (lhs, t)
            if key in table:
                conflicts.append((key, table[key], idx))
            else:
                table[key] = idx
    return table, conflicts


def is_ll1() -> bool:
    return not ll1_table()[1]
