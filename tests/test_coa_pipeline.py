import pytest

from pipesched.parser import parse
from pipesched.pipeline import PipelineConfig, simulate

FWD = PipelineConfig(forwarding=True)
NOFWD = PipelineConfig(forwarding=False)


def cyc(src, cfg):
    return simulate(parse(src).program, cfg)


def test_no_hazard_cpi():
    r = cyc("ADD R1,R2,R3\nADD R4,R5,R6\nADD R7,R8,R9\nADD R10,R11,R12\n", FWD)
    assert r.cycles == 4 + 4 and r.data_stalls == 0           # n + 4
    assert r.cpi == pytest.approx(2.0)


def test_alu_to_alu_forwarding_no_stall():
    assert cyc("ADD R1,R2,R3\nADD R4,R1,R5\n", FWD).data_stalls == 0


def test_load_use_one_stall_with_forwarding():
    r = cyc("LW R1,0(R2)\nADD R3,R1,R4\n", FWD)
    assert r.data_stalls == 1 and r.cycles == 2 + 4 + 1


def test_load_then_gap_removes_stall():
    assert cyc("LW R1,0(R2)\nADD R5,R6,R7\nADD R3,R1,R4\n", FWD).data_stalls == 0


def test_back_to_back_two_stalls_without_forwarding():
    assert cyc("ADD R1,R2,R3\nADD R4,R1,R5\n", NOFWD).data_stalls == 2


def test_one_gap_one_stall_without_forwarding():
    assert cyc("ADD R1,R2,R3\nNOP\nADD R4,R1,R5\n", NOFWD).data_stalls == 1


def test_two_gaps_no_stall_without_forwarding():
    assert cyc("ADD R1,R2,R3\nNOP\nNOP\nADD R4,R1,R5\n", NOFWD).data_stalls == 0


def test_store_data_forwarded_from_load_without_stall():
    assert cyc("LW R1,0(R2)\nSW R1,4(R2)\n", FWD).data_stalls == 0     # data needed only in MEM


def test_store_base_register_needs_ex():
    assert cyc("LW R1,0(R2)\nSW R5,4(R1)\n", FWD).data_stalls == 1


def test_r0_never_stalls():
    assert cyc("ADDI R0,R1,1\nADD R2,R0,R3\n", NOFWD).data_stalls == 0


def test_taken_branch_penalty_and_loop():
    src = "ADDI R1,R0,3\nloop: SUBI R1,R1,1\nBNE R1,R0,loop\n"
    r = cyc(src, PipelineConfig(forwarding=True, branch_penalty=2))
    assert r.instructions == 1 + 3 * 2                     # trace is unrolled
    assert r.control_bubbles == 2 * 2                      # 2 taken branches
    r0 = cyc(src, PipelineConfig(forwarding=True, branch_penalty=0))
    assert r.cycles - r0.cycles == 4


def test_step_limit_flagged():
    r = simulate(parse("loop: J loop\n").program, FWD, max_steps=50)
    assert r.truncated and r.instructions == 50


def test_empty_program():
    r = simulate(parse("# nothing\n").program, FWD)
    assert r.cycles == 0 and r.cpi == 0
