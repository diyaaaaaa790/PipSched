"""Functional interpreter.

Used for two things:
  1. producing the *dynamic* instruction trace (loops/branches unrolled) that the
     pipeline simulator times, and
  2. proving that an optimized program is functionally equivalent to the original.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .isa import NUM_REGS, Program, wrap32


def default_memory(addr: int) -> int:
    """Deterministic content of an address that was never written."""
    return (addr * 37 + 11) % 1000


def initial_registers(seed: int = 0) -> list:
    rng = random.Random(seed)
    return [0] + [rng.randint(-50, 50) for _ in range(NUM_REGS - 1)]


@dataclass
class ExecResult:
    trace: list = field(default_factory=list)      # [(static_index, taken)]
    regs: list = field(default_factory=list)
    mem: dict = field(default_factory=dict)
    truncated: bool = False


def run(program: Program, regs=None, max_steps: int = 5000) -> ExecResult:
    regs = list(regs) if regs is not None else [0] * NUM_REGS
    regs[0] = 0
    mem: dict = {}
    trace: list = []
    n = len(program.instrs)
    pc = 0
    while pc < n:
        if len(trace) >= max_steps:
            return ExecResult(trace, regs, mem, truncated=True)
        ins = program.instrs[pc]
        op = ins.op
        taken = False
        nxt = pc + 1
        if op == "ADD":
            regs[ins.rd] = wrap32(regs[ins.rs] + regs[ins.rt])
        elif op == "SUB":
            regs[ins.rd] = wrap32(regs[ins.rs] - regs[ins.rt])
        elif op == "AND":
            regs[ins.rd] = wrap32(regs[ins.rs] & regs[ins.rt])
        elif op == "OR":
            regs[ins.rd] = wrap32(regs[ins.rs] | regs[ins.rt])
        elif op == "MUL":
            regs[ins.rd] = wrap32(regs[ins.rs] * regs[ins.rt])
        elif op == "ADDI":
            regs[ins.rd] = wrap32(regs[ins.rs] + ins.imm)
        elif op == "SUBI":
            regs[ins.rd] = wrap32(regs[ins.rs] - ins.imm)
        elif op == "LW":
            addr = regs[ins.rs] + ins.imm
            regs[ins.rd] = mem[addr] if addr in mem else default_memory(addr)
        elif op == "SW":
            mem[regs[ins.rs] + ins.imm] = regs[ins.rt]
        elif op in ("BEQ", "BNE"):
            eq = regs[ins.rs] == regs[ins.rt]
            taken = eq if op == "BEQ" else not eq
            if taken:
                nxt = program.labels[ins.target]
        elif op == "J":
            taken = True
            nxt = program.labels[ins.target]
        regs[0] = 0
        trace.append((pc, taken))
        pc = nxt
    return ExecResult(trace, regs, mem, truncated=False)


def check_equivalence(a: Program, b: Program, seeds=(1, 2, 3), max_steps: int = 5000):
    """Run both programs from identical random states and compare final state.

    Returns (status, message) with status in {'equivalent','different','inconclusive'}.
    """
    for seed in seeds:
        regs = initial_registers(seed)
        ra = run(a, regs, max_steps)
        rb = run(b, regs, max_steps)
        if ra.truncated or rb.truncated:
            return "inconclusive", f"step limit ({max_steps}) reached - cannot compare final states"
        if ra.regs != rb.regs:
            diff = [f"R{i}" for i in range(NUM_REGS) if ra.regs[i] != rb.regs[i]]
            return "different", f"register mismatch in {', '.join(diff)} (seed {seed})"
        if ra.mem != rb.mem:
            return "different", f"memory mismatch (seed {seed})"
        if len(ra.trace) != len(rb.trace):
            return "different", f"executed instruction counts differ (seed {seed})"
    return "equivalent", f"identical registers and memory on {len(seeds)} random initial states"
