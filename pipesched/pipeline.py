"""Cycle-accurate model of the classic 5-stage in-order pipeline (COA concept).

Stages: IF -> ID -> EX -> MEM -> WB.

Hazard model
------------
* Data (RAW) hazards
    - with forwarding   : ALU results are forwardable after EX, load results after MEM
                          (=> 1 stall for a load-use pair, 0 for ALU->ALU).  A store needs
                          its data register only in MEM.
    - without forwarding: a value can be read in ID in the same cycle the producer is in WB
                          (register file writes in the first half, reads in the second half)
                          => 2 stalls for back-to-back dependent instructions.
* Control hazards: branches/jumps resolve in EX with a "predict not taken" policy, so a
  taken branch/jump costs ``branch_penalty`` bubbles (default 2).
* Structural hazards are assumed absent (separate instruction/data memory, 2-read/1-write
  register file).

Timing is computed per instruction: ``d`` = the last cycle the instruction spends in ID,
then EX = d+1, MEM = d+2, WB = d+3.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .executor import run
from .isa import Instr, Program


@dataclass
class PipelineConfig:
    forwarding: bool = True
    branch_penalty: int = 2


@dataclass
class Cause:
    producer_pos: int      # trace position of the producing instruction
    reg: int
    stalls: int            # stall cycles this dependency demanded


@dataclass
class IssueRecord:
    pos: int                       # position in the dynamic trace
    instr: Instr
    taken: bool
    fetch: int
    id_start: int
    id_end: int
    data_stalls: int
    control_bubbles: int           # bubbles inserted *before* this instr (previous taken branch)
    causes: list = field(default_factory=list)

    @property
    def ex(self): return self.id_end + 1
    @property
    def mem(self): return self.id_end + 2
    @property
    def wb(self): return self.id_end + 3


class PipelineTimer:
    """Incremental timing engine (also used by the hazard-aware optimizer)."""

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.count = 0
        self.prev_id_start = None
        self.prev_id_end = None
        self.prev_taken = False
        self.writers: dict = {}      # reg -> (id_end, is_load, pos)

    def _start(self):
        if self.prev_id_end is None:
            return 1, 2, 0
        if self.prev_taken:
            id_start = self.prev_id_end + 1 + self.cfg.branch_penalty
            return id_start - 1, id_start, self.cfg.branch_penalty
        return self.prev_id_start, self.prev_id_end + 1, 0

    def _required(self, ins: Instr, id_start: int):
        d, causes = id_start, []
        for reg, need in ins.src_needs().items():
            w = self.writers.get(reg)
            if w is None:
                continue
            dp, is_load, pos = w
            if self.cfg.forwarding:
                ready = 2 if is_load else 1            # offset from dp of last producing stage
                need_off = 2 if need == "MEM" else 1
                req = dp + ready + 1 - need_off
            else:
                req = dp + 3                            # read in ID during producer's WB
            if req > id_start:
                causes.append(Cause(pos, reg, req - id_start))
            d = max(d, req)
        return d, causes

    def peek_stalls(self, ins: Instr) -> int:
        _, id_start, _ = self._start()
        d, _ = self._required(ins, id_start)
        return d - id_start

    def issue(self, ins: Instr, taken: bool = False) -> IssueRecord:
        fetch, id_start, bubbles = self._start()
        d, causes = self._required(ins, id_start)
        rec = IssueRecord(self.count, ins, taken and ins.is_control, fetch, id_start, d,
                          d - id_start, bubbles, causes)
        for r in ins.defs():
            self.writers[r] = (d, ins.is_load, self.count)
        self.prev_id_start, self.prev_id_end = id_start, d
        self.prev_taken = rec.taken
        self.count += 1
        return rec


@dataclass
class SimResult:
    records: list
    cycles: int
    instructions: int
    data_stalls: int
    control_bubbles: int
    truncated: bool = False

    @property
    def cpi(self) -> float:
        return self.cycles / self.instructions if self.instructions else 0.0

    @property
    def ideal_cycles(self) -> int:
        return self.instructions + 4 if self.instructions else 0

    def hazards(self) -> list:
        """Flat list of RAW hazards that caused stalls."""
        out = []
        for r in self.records:
            for c in r.causes:
                prod = self.records[c.producer_pos]
                out.append({"producer": prod.instr.text(), "consumer": r.instr.text(),
                            "register": f"R{c.reg}", "stall_cycles": c.stalls,
                            "trace_pos": r.pos})
        return out


def simulate(program: Program, cfg: PipelineConfig, regs=None, max_steps: int = 5000) -> SimResult:
    ex = run(program, regs, max_steps)
    timer = PipelineTimer(cfg)
    records = [timer.issue(program.instrs[idx], taken) for idx, taken in ex.trace]
    cycles = records[-1].wb if records else 0
    return SimResult(records, cycles, len(records),
                     sum(r.data_stalls for r in records),
                     sum(r.control_bubbles for r in records), ex.truncated)


def block_cycles(instrs: list, cfg: PipelineConfig) -> int:
    """Cycle estimate of a straight-line sequence starting on an empty pipeline."""
    t = PipelineTimer(cfg)
    last = None
    for ins in instrs:
        last = t.issue(ins, False)
    return last.wb if last else 0


# ---- diagram -------------------------------------------------------------
def build_diagram(records: list, max_rows: int = 30):
    """Return (cycle_count, rows); each row = (label, {cycle: stage_label})."""
    rows, last_cycle = [], 0
    for r in records[:max_rows]:
        cells = {r.fetch: "IF"}
        for c in range(r.fetch + 1, r.id_start):
            cells[c] = "STALL"
        cells[r.id_start] = "ID"
        for c in range(r.id_start + 1, r.id_end + 1):
            cells[c] = "STALL"
        cells[r.ex], cells[r.mem], cells[r.wb] = "EX", "MEM", "WB"
        last_cycle = max(last_cycle, r.wb)
        rows.append((f"{r.pos + 1}. {r.instr.text()}", cells))
    return last_cycle, rows
