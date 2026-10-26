import glob
import os
import random

import pytest

from pipesched import PipelineConfig, analyze
from pipesched.dag import is_topological
from pipesched.executor import check_equivalence
from pipesched.optimizer import optimize
from pipesched.parser import parse

EX = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "examples", "*.asm")))
VALID_EX = [p for p in EX if "invalid" not in p]


@pytest.mark.parametrize("path", VALID_EX)
@pytest.mark.parametrize("fwd", [True, False])
@pytest.mark.parametrize("mode", ["hazard_aware", "fifo"])
def test_examples_equivalent_and_valid(path, fwd, mode):
    res = analyze(open(path).read(), PipelineConfig(forwarding=fwd), mode)
    assert res.ok
    assert all(b.valid for b in res.opt.blocks)
    assert res.equivalence[0] == "equivalent", res.equivalence


@pytest.mark.parametrize("path", VALID_EX)
@pytest.mark.parametrize("fwd", [True, False])
def test_hazard_aware_never_slower_on_examples(path, fwd):
    res = analyze(open(path).read(), PipelineConfig(forwarding=fwd), "hazard_aware")
    assert res.after.cycles <= res.before.cycles


def test_load_use_example_reaches_ideal():
    res = analyze(open(VALID_EX[[os.path.basename(p) for p in VALID_EX].index("load_use.asm")]).read())
    assert (res.before.cycles, res.after.cycles) == (15, 12)
    assert res.after.data_stalls == 0


def test_branch_stays_last_and_labels_valid():
    res = analyze("""
        LW R1,0(R2)
        ADD R3,R1,R1
        LW R4,4(R2)
        ADD R5,R4,R3
        BNE R5,R0,skip
        NOP
skip:   SW R5,0(R2)
""")
    p = res.opt.program
    assert p.instrs[4].op == "BNE"
    assert p.labels == res.parse.program.labels


def test_original_program_not_mutated():
    pr = parse("LW R1,0(R2)\nADD R3,R1,R4\nLW R5,4(R2)\nSUB R6,R5,R4\n")
    before = pr.program.to_asm()
    optimize(pr.program, PipelineConfig())
    assert pr.program.to_asm() == before


def _random_program(rng, n):
    ops = []
    for _ in range(n):
        k = rng.random()
        r = lambda: rng.randint(0, 7)
        if k < 0.30:
            ops.append(f"LW R{rng.randint(1,7)}, {rng.choice([0,4,8,12])}(R{rng.randint(0,3)})")
        elif k < 0.45:
            ops.append(f"SW R{r()}, {rng.choice([0,4,8,12])}(R{rng.randint(0,3)})")
        elif k < 0.60:
            ops.append(f"ADDI R{rng.randint(1,7)}, R{r()}, {rng.randint(-5,5)}")
        else:
            ops.append(f"{rng.choice(['ADD','SUB','AND','OR','MUL'])} R{rng.randint(1,7)}, R{r()}, R{r()}")
    return "\n".join(ops)


@pytest.mark.parametrize("seed", range(40))
@pytest.mark.parametrize("mode", ["hazard_aware", "fifo"])
def test_random_programs_stay_equivalent(seed, mode):
    """Property test: any random straight-line program keeps identical behaviour."""
    rng = random.Random(seed)
    src = _random_program(rng, rng.randint(2, 30))
    for fwd in (True, False):
        pr = parse(src)
        assert pr.ok
        opt = optimize(pr.program, PipelineConfig(forwarding=fwd), mode)
        assert all(is_topological(b.order, b.dag) for b in opt.blocks)
        status, msg = check_equivalence(pr.program, opt.program, seeds=(1, 2, 3, 4))
        assert status == "equivalent", (src, msg)


def test_equivalence_checker_detects_a_wrong_reordering():
    a = parse("ADD R1,R2,R3\nSUB R4,R1,R5\n").program
    b = parse("SUB R4,R1,R5\nADD R1,R2,R3\n").program      # breaks RAW
    assert check_equivalence(a, b)[0] == "different"
