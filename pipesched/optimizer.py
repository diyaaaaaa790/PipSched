"""Hazard-aware instruction scheduler built on Kahn's algorithm (DAA + COA).

For every basic block we build the dependency DAG and emit a topological order.
  mode "fifo"          : plain Kahn (FIFO queue)  - valid order, but hazard-blind
  mode "hazard_aware"  : Kahn where the ready set is *prioritised*: at every step pick the
                         ready instruction that causes the fewest stalls now, break ties by
                         the longest critical path, then by original position.
The hazard-aware result is compared with the original block and the better one is kept,
so the optimizer never makes a block slower (under the block-local timing model).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .dag import DAG, Block, build_dag, heights, is_topological, kahn_fifo, split_blocks
from .isa import Program
from .pipeline import PipelineConfig, PipelineTimer, block_cycles


@dataclass
class BlockResult:
    block: Block
    dag: DAG
    original_order: list
    order: list
    log: list
    est_before: int
    est_after: int
    fallback: bool = False

    @property
    def moved(self) -> int:
        return sum(1 for a, b in zip(self.original_order, self.order) if a != b)

    @property
    def valid(self) -> bool:
        return is_topological(self.order, self.dag)


@dataclass
class OptResult:
    program: Program
    blocks: list
    mode: str


def hazard_aware_kahn(dag: DAG, program: Program, cfg: PipelineConfig):
    h = heights(dag, program)
    indeg = {v: len(dag.pred[v]) for v in dag.nodes}
    ready = {v for v in dag.nodes if indeg[v] == 0}
    timer = PipelineTimer(cfg)
    order, log = [], []
    while ready:
        scored = sorted((timer.peek_stalls(program.instrs[v]), -h[v], v) for v in ready)
        stalls, _, best = scored[0]
        log.append({"ready": sorted(ready), "chosen": best, "stalls": stalls,
                    "scores": {v: s for s, _, v in scored}})
        timer.issue(program.instrs[best], False)
        order.append(best)
        ready.remove(best)
        for v in dag.succ[best]:
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.add(v)
    return order, log


def optimize(program: Program, cfg: PipelineConfig, mode: str = "hazard_aware") -> OptResult:
    new_instrs = list(program.instrs)
    results = []
    for block in split_blocks(program):
        dag = build_dag(program, block)
        original = block.indices
        if mode == "fifo":
            order, log = kahn_fifo(dag)
        else:
            order, log = hazard_aware_kahn(dag, program, cfg)
        est_before = block_cycles([program.instrs[i] for i in original], cfg)
        est_after = block_cycles([program.instrs[i] for i in order], cfg)
        fallback = False
        if mode != "fifo" and est_after > est_before:
            order, fallback, est_after = original, True, est_before
        for k, src in enumerate(order):
            new_instrs[block.start + k] = replace(program.instrs[src])
        results.append(BlockResult(block, dag, original, order, log, est_before, est_after, fallback))
    # labels stay valid: reordering never moves a block boundary
    return OptResult(Program(new_instrs, dict(program.labels)), results, mode)
