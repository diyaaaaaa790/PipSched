"""One-call pipeline: parse -> DAG/optimize -> simulate -> verify."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .executor import check_equivalence
from .optimizer import OptResult, optimize
from .parser import ParseResult, parse
from .pipeline import PipelineConfig, SimResult, simulate


@dataclass
class Analysis:
    parse: ParseResult
    cfg: PipelineConfig
    mode: str
    opt: Optional[OptResult] = None
    before: Optional[SimResult] = None
    after: Optional[SimResult] = None
    equivalence: tuple = ("inconclusive", "")

    @property
    def ok(self) -> bool:
        return self.parse.ok and self.opt is not None

    @property
    def speedup(self) -> float:
        if not self.ok or not self.after or not self.after.cycles:
            return 1.0
        return self.before.cycles / self.after.cycles


def analyze(source: str, cfg: PipelineConfig = None, mode: str = "hazard_aware",
            max_steps: int = 5000) -> Analysis:
    cfg = cfg or PipelineConfig()
    pr = parse(source)
    res = Analysis(pr, cfg, mode)
    if not pr.ok or not pr.program.instrs:
        return res
    res.opt = optimize(pr.program, cfg, mode)
    res.before = simulate(pr.program, cfg, max_steps=max_steps)
    res.after = simulate(res.opt.program, cfg, max_steps=max_steps)
    res.equivalence = check_equivalence(pr.program, res.opt.program, max_steps=max_steps)
    return res
