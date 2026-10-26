"""Instruction dependency DAG and Kahn's topological sort (DAA concept).

Dependencies are built *per basic block* (control flow never crosses a block):

  RAW  true data dependency      (write -> later read of the same register)
  WAR  anti dependency           (read  -> later write)
  WAW  output dependency         (write -> later write)
  MEM  memory ordering           (store<->load, store<->store; conservative aliasing)
  CTRL every instruction -> the block's terminating branch/jump

Construction is O(V*R + E) using "last writer" / "readers since last write" tables,
instead of comparing all O(V^2) pairs.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .isa import Program


@dataclass
class Block:
    start: int
    end: int           # exclusive

    @property
    def indices(self):
        return list(range(self.start, self.end))


def split_blocks(program: Program) -> list:
    n = len(program.instrs)
    if n == 0:
        return []
    leaders = {0}
    for idx in program.labels.values():
        if idx < n:
            leaders.add(idx)
    for i, ins in enumerate(program.instrs):
        if ins.is_control and i + 1 < n:
            leaders.add(i + 1)
    ordered = sorted(leaders)
    return [Block(s, ordered[k + 1] if k + 1 < len(ordered) else n)
            for k, s in enumerate(ordered)]


@dataclass
class DAG:
    nodes: list
    edges: dict = field(default_factory=dict)       # (u, v) -> set of kinds
    succ: dict = field(default_factory=dict)
    pred: dict = field(default_factory=dict)

    def add_edge(self, u: int, v: int, kind: str) -> None:
        if u == v:
            return
        self.edges.setdefault((u, v), set()).add(kind)
        self.succ[u].add(v)
        self.pred[v].add(u)

    @property
    def num_edges(self) -> int:
        return len(self.edges)


def build_dag(program: Program, block: Block) -> DAG:
    instrs = program.instrs
    dag = DAG(nodes=block.indices)
    for i in dag.nodes:
        dag.succ[i], dag.pred[i] = set(), set()

    last_def: dict = {}
    uses_since_def: dict = {}
    last_store = None
    loads_since_store: list = []

    for j in dag.nodes:
        ins = instrs[j]
        for r in ins.uses():                                   # RAW
            if r in last_def:
                dag.add_edge(last_def[r], j, "RAW")
        for r in ins.defs():                                   # WAW + WAR
            if r in last_def:
                dag.add_edge(last_def[r], j, "WAW")
            for u in uses_since_def.get(r, []):
                dag.add_edge(u, j, "WAR")
        if ins.is_mem:                                         # memory ordering
            if last_store is not None:
                dag.add_edge(last_store, j, "MEM")
            if ins.is_store:
                for l in loads_since_store:
                    dag.add_edge(l, j, "MEM")
                last_store, loads_since_store = j, []
            else:
                loads_since_store.append(j)
        for r in ins.uses():
            uses_since_def.setdefault(r, []).append(j)
        for r in ins.defs():
            last_def[r] = j
            uses_since_def[r] = []

    last = dag.nodes[-1]
    if instrs[last].is_control:                                # terminator stays last
        for i in dag.nodes[:-1]:
            dag.add_edge(i, last, "CTRL")
    return dag


def edge_latency(dag: DAG, program: Program, u: int, v: int) -> int:
    """Heuristic latency used for critical-path heights (load-use costs one extra)."""
    kinds = dag.edges[(u, v)]
    return 2 if ("RAW" in kinds and program.instrs[u].is_load) else 1


def heights(dag: DAG, program: Program) -> dict:
    """Longest latency-weighted path from each node to a sink (reverse topological DP)."""
    h = {}
    for u in reversed(dag.nodes):          # original order is a valid topological order
        h[u] = max((edge_latency(dag, program, u, v) + h[v] for v in dag.succ[u]), default=0)
    return h


def kahn_fifo(dag: DAG):
    """Plain Kahn's algorithm (FIFO queue). Returns (order, log). O(V + E)."""
    indeg = {v: len(dag.pred[v]) for v in dag.nodes}
    queue = deque(v for v in dag.nodes if indeg[v] == 0)
    order, log = [], []
    while queue:
        ready = list(queue)
        u = queue.popleft()
        order.append(u)
        log.append({"ready": ready, "chosen": u, "stalls": None})
        for v in sorted(dag.succ[u]):
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    return order, log


def is_topological(order: list, dag: DAG) -> bool:
    if sorted(order) != sorted(dag.nodes):
        return False
    pos = {v: k for k, v in enumerate(order)}
    return all(pos[u] < pos[v] for (u, v) in dag.edges)


def dag_to_dot(dag: DAG, program: Program, order: list = None) -> str:
    colors = {"RAW": "#d62728", "WAR": "#ff7f0e", "WAW": "#9467bd",
              "MEM": "#1f77b4", "CTRL": "#999999"}
    lines = ["digraph DAG {", "  rankdir=TB;",
             '  node [shape=box, style="rounded,filled", fillcolor="#eef3fb", fontname="Courier", fontsize=11];',
             '  edge [fontname="Helvetica", fontsize=9];']
    for v in dag.nodes:
        lab = f"{v + 1}: {program.instrs[v].text()}".replace('"', '\\"')
        lines.append(f'  n{v} [label="{lab}"];')
    for (u, v), kinds in sorted(dag.edges.items()):
        if kinds == {"CTRL"} and dag.num_edges > 25:
            continue                      # keep big graphs readable
        main = next(k for k in ("RAW", "MEM", "WAW", "WAR", "CTRL") if k in kinds)
        style = "dashed" if main in ("WAR", "WAW") else ("dotted" if main == "CTRL" else "solid")
        lines.append(f'  n{u} -> n{v} [label="{"/".join(sorted(kinds))}", color="{colors[main]}", '
                     f'fontcolor="{colors[main]}", style={style}];')
    lines.append("}")
    return "\n".join(lines)
