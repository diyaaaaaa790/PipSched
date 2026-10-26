import pytest

from pipesched.grammar import PRODUCTIONS, compute_first, compute_follow, is_ll1, ll1_table
from pipesched.lexer import tokenize
from pipesched.parser import leftmost_derivation, parse, tree_to_dot, tree_to_text


# ---------------- grammar ----------------
def test_grammar_is_ll1():
    table, conflicts = ll1_table()
    assert conflicts == [] and is_ll1()
    assert table  # non-empty


def test_first_follow_known_values():
    first, follow = compute_first(), compute_follow()
    assert first["Instr"] == {"ROP", "IOP", "MEMOP", "BROP", "JOP", "NOP"}
    assert first["Line"] == first["Instr"] | {"ID"}
    assert "ε" in first["Lines"] and "ε" in first["OptInstr"]
    assert follow["Lines"] == {"$"}
    assert follow["OptInstr"] == {"NL"}


# ---------------- lexer ----------------
def test_lexer_kinds_and_comments():
    toks = tokenize("loop: LW r1, -4(R2)  # comment\n\n\nJ loop")
    kinds = [t.kind for t in toks]
    assert kinds == ["ID", "COLON", "MEMOP", "REG", "COMMA", "NUM", "LPAREN", "REG", "RPAREN",
                     "NL", "JOP", "ID", "NL", "EOF"]


def test_lexer_illegal_char():
    assert any(t.kind == "ERROR" for t in tokenize("ADD R1, R2, R3 @"))


# ---------------- valid programs ----------------
VALID = """
start:  ADDI R1, R0, 0x10     # hex immediate
        LW   R2, 0(R1)
        SW   R2, -8(R1)
        ADD  R3, R1, R2
        MUL  R4, R3, R3
        BEQ  R4, R0, start
        J    end
        NOP
end:
"""


def test_valid_program_parses_fully():
    r = parse(VALID)
    assert r.ok, r.errors
    assert len(r.program.instrs) == 8
    assert r.program.labels == {"start": 0, "end": 8}
    assert r.program.instrs[0].imm == 16
    assert r.program.instrs[2].imm == -8 and r.program.instrs[2].op == "SW"


def test_tree_leaves_reproduce_token_stream():
    r = parse(VALID)
    leaves, stack = [], [r.tree]
    while stack:
        n = stack.pop()
        if n.is_terminal:
            if n.token is not None:
                leaves.append(n.token.text)
        else:
            stack.extend(reversed(n.children))
    expected = [t.text for t in r.tokens if t.kind != "EOF"]
    assert leaves == expected          # yield of the parse tree == input


def test_derivation_ends_with_terminals_and_starts_with_root():
    r = parse("ADD R1, R2, R3\n")
    steps = leftmost_derivation(r.lines[0].node)
    assert steps[0] == "<Line>"
    assert "<" not in steps[-1]
    assert "ADD R1 , R2 , R3" in steps[-1]


def test_tree_renderers_work():
    r = parse(VALID)
    assert "digraph" in tree_to_dot(r.tree)
    assert tree_to_text(r.tree).startswith("Program")


def test_deep_program_no_recursion_error():
    src = "\n".join("ADD R1, R2, R3" for _ in range(3000))
    r = parse(src)
    assert r.ok and len(r.program.instrs) == 3000
    tree_to_dot(r.tree)
    tree_to_text(r.tree)


# ---------------- invalid programs ----------------
@pytest.mark.parametrize("src,fragment", [
    ("ADD R1, R2 R3", "expected ','"),
    ("LW R4, 0(R2", "expected ')'"),
    ("FOO R1, R2, R3", "unknown instruction"),
    ("ADDI R1, R2, R3", "expected a number"),
    ("SUB R40, R1, R2", "does not exist"),
    ("ADD R1, R2,", "expected a register"),
    ("loop: loop2: NOP", "expected an instruction or end of line"),
    ("BEQ R1, R2, nowhere", "undefined label"),
    ("x: NOP\nx: NOP", "already defined"),
    ("@", "illegal character"),
])
def test_error_messages(src, fragment):
    r = parse(src)
    assert not r.ok
    assert any(fragment in e.message for e in r.errors), r.errors


def test_multiple_errors_reported_with_recovery():
    r = parse("ADD R1, R2 R3\nNOP\nLW R1, 0(R2\nSUB R1, R2, R3\n")
    assert [e.line for e in r.errors] == [1, 3]
    assert len(r.program.instrs) == 2            # NOP and SUB still parsed
