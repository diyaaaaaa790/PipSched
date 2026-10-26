"""PipeSched - Assembly Parser and Pipeline Hazard Optimizer.

FLAT : grammar.py, lexer.py, parser.py      (CFG, derivation trees, LL(1) recursive descent)
COA  : pipeline.py, executor.py             (5-stage pipeline, data/control hazards, CPI)
DAA  : dag.py, optimizer.py                 (dependency DAG, Kahn's topological sort)
"""
from .analysis import Analysis, analyze
from .pipeline import PipelineConfig

__all__ = ["analyze", "Analysis", "PipelineConfig"]
