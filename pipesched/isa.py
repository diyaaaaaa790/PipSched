"""Instruction set definition (a small MIPS-like ISA) and the Program model."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

R_OPS = {"ADD", "SUB", "AND", "OR", "MUL"}      # op rd, rs, rt
I_OPS = {"ADDI", "SUBI"}                         # op rd, rs, imm
MEM_OPS = {"LW", "SW"}                           # op reg, imm(base)
BR_OPS = {"BEQ", "BNE"}                          # op rs, rt, label
J_OPS = {"J"}                                    # J label
NOP_OPS = {"NOP"}

# mnemonic -> token kind used by the lexer / grammar
MNEMONIC_KIND = {}
for _op in R_OPS:
    MNEMONIC_KIND[_op] = "ROP"
for _op in I_OPS:
    MNEMONIC_KIND[_op] = "IOP"
for _op in MEM_OPS:
    MNEMONIC_KIND[_op] = "MEMOP"
for _op in BR_OPS:
    MNEMONIC_KIND[_op] = "BROP"
for _op in J_OPS:
    MNEMONIC_KIND[_op] = "JOP"
for _op in NOP_OPS:
    MNEMONIC_KIND[_op] = "NOP"

NUM_REGS = 32
_MASK = 0xFFFFFFFF


def wrap32(x: int) -> int:
    """Wrap to a signed 32-bit integer."""
    x &= _MASK
    return x - (1 << 32) if x & 0x80000000 else x


@dataclass
class Instr:
    op: str
    rd: Optional[int] = None
    rs: Optional[int] = None
    rt: Optional[int] = None
    imm: int = 0
    target: Optional[str] = None
    line: int = 0          # source line number
    orig_idx: int = -1     # position in the ORIGINAL program (kept after reordering)

    # ---- classification -------------------------------------------------
    @property
    def is_load(self) -> bool:
        return self.op == "LW"

    @property
    def is_store(self) -> bool:
        return self.op == "SW"

    @property
    def is_mem(self) -> bool:
        return self.op in MEM_OPS

    @property
    def is_branch(self) -> bool:
        return self.op in BR_OPS

    @property
    def is_control(self) -> bool:
        return self.op in BR_OPS or self.op in J_OPS

    # ---- register usage (R0 is the hard-wired zero: never a dependency) --
    def defs(self) -> tuple:
        if self.op in R_OPS or self.op in I_OPS or self.op == "LW":
            return (self.rd,) if self.rd else ()
        return ()

    def uses(self) -> tuple:
        if self.op in R_OPS or self.is_branch:
            regs = (self.rs, self.rt)
        elif self.op in I_OPS or self.op == "LW":
            regs = (self.rs,)
        elif self.op == "SW":
            regs = (self.rs, self.rt)
        else:
            regs = ()
        out = []
        for r in regs:
            if r and r not in out:
                out.append(r)
        return tuple(out)

    def src_needs(self) -> dict:
        """reg -> pipeline stage in which the value is needed ('EX' or 'MEM').

        A store needs its data register only in MEM, everything else in EX.
        """
        needs = {}
        for r in self.uses():
            needs[r] = "EX"
        if self.op == "SW" and self.rt and self.rt != self.rs:
            needs[self.rt] = "MEM"
        return needs

    # ---- text ---------------------------------------------------------------
    def text(self) -> str:
        op = self.op
        if op in R_OPS:
            return f"{op} R{self.rd}, R{self.rs}, R{self.rt}"
        if op in I_OPS:
            return f"{op} R{self.rd}, R{self.rs}, {self.imm}"
        if op == "LW":
            return f"LW R{self.rd}, {self.imm}(R{self.rs})"
        if op == "SW":
            return f"SW R{self.rt}, {self.imm}(R{self.rs})"
        if op in BR_OPS:
            return f"{op} R{self.rs}, R{self.rt}, {self.target}"
        if op in J_OPS:
            return f"J {self.target}"
        return "NOP"


@dataclass
class Program:
    instrs: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)   # label -> instruction index

    def labels_at(self) -> dict:
        out: dict = {}
        for name, idx in self.labels.items():
            out.setdefault(idx, []).append(name)
        return out

    def to_asm(self) -> str:
        at = self.labels_at()
        lines = []
        for i, ins in enumerate(self.instrs):
            for name in at.get(i, []):
                lines.append(f"{name}:")
            lines.append(f"    {ins.text()}")
        for name in at.get(len(self.instrs), []):
            lines.append(f"{name}:")
        return "\n".join(lines)
