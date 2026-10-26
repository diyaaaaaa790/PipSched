"""Command-line interface:  python main.py examples/load_use.asm [--no-forwarding] [--mode fifo]"""
import argparse
import sys

from pipesched import PipelineConfig, analyze
from pipesched.grammar import grammar_text
from pipesched.parser import leftmost_derivation, tree_to_text
from pipesched.render import diagram_text


def main() -> int:
    ap = argparse.ArgumentParser(description="PipeSched - assembly parser and pipeline hazard optimizer")
    ap.add_argument("file")
    ap.add_argument("--no-forwarding", action="store_true", help="disable data forwarding")
    ap.add_argument("--branch-penalty", type=int, default=2)
    ap.add_argument("--mode", choices=["hazard_aware", "fifo"], default="hazard_aware")
    ap.add_argument("--tree", action="store_true", help="print parse tree + derivation of the first line")
    args = ap.parse_args()

    cfg = PipelineConfig(forwarding=not args.no_forwarding, branch_penalty=args.branch_penalty)
    res = analyze(open(args.file).read(), cfg, args.mode)

    print("=== FLAT: parsing ===")
    if not res.parse.ok:
        for e in res.parse.errors:
            print(f"  line {e.line}:{e.col}  [{e.kind}] {e.message}\n      {e.source}")
        return 1
    print(f"  OK - {len(res.parse.program.instrs)} instructions, labels: {list(res.parse.program.labels) or '-'}")
    if args.tree:
        print("\nGrammar:\n" + grammar_text())
        first = res.parse.lines[0]
        print(f"\nParse tree of line {first.line_no}:\n{tree_to_text(first.node)}")
        print("\nLeftmost derivation:")
        for s in leftmost_derivation(first.node):
            print("  =>", s)

    print("\n=== DAA: dependency DAG + Kahn's algorithm ===")
    for k, b in enumerate(res.opt.blocks, 1):
        print(f"  block {k}: instrs {b.block.start + 1}-{b.block.end}  V={len(b.dag.nodes)} E={b.dag.num_edges}  "
              f"moved={b.moved}  valid-topological-order={b.valid}  est. cycles {b.est_before}->{b.est_after}"
              + ("  (kept original)" if b.fallback else ""))
    print("\nOptimized program:\n" + res.opt.program.to_asm())

    print("\n=== COA: pipeline ===")
    for name, s in (("before", res.before), ("after ", res.after)):
        print(f"  {name}: cycles={s.cycles}  instr={s.instructions}  CPI={s.cpi:.2f}  "
              f"data-stalls={s.data_stalls}  control-bubbles={s.control_bubbles}")
    print(f"  speedup = {res.speedup:.2f}x   equivalence: {res.equivalence[0]} ({res.equivalence[1]})")
    print("\nPipeline diagram (original):\n" + diagram_text(res.before.records, 16))
    print("\nPipeline diagram (optimized):\n" + diagram_text(res.after.records, 16))
    return 0


if __name__ == "__main__":
    sys.exit(main())
