import random

from pipesched.dag import build_dag, is_topological, kahn_fifo, split_blocks
from pipesched.parser import parse


def dag_of(src, block=0):
    p = parse(src).program
    return p, build_dag(p, split_blocks(p)[block])


def test_raw_war_waw_edges():
    p, d = dag_of("ADD R1, R2, R3\nSUB R4, R1, R5\nADD R2, R6, R7\nADD R1, R6, R6\n")
    assert d.edges[(0, 1)] == {"RAW"}            # R1 written then read
    assert "WAR" in d.edges[(0, 2)]              # R2 read by #0, written by #2
    assert "WAW" in d.edges[(0, 3)]              # R1 written twice
    assert "WAR" in d.edges[(1, 3)]              # R1 read by #1, rewritten by #3


def test_r0_creates_no_dependency():
    _, d = dag_of("ADDI R0, R1, 5\nADD R2, R0, R3\n")
    assert d.num_edges == 0


def test_memory_ordering():
    _, d = dag_of("SW R1, 0(R2)\nLW R3, 0(R2)\nLW R4, 4(R2)\nSW R5, 8(R2)\n")
    assert (0, 1) in d.edges and (0, 2) in d.edges          # store -> loads
    assert (1, 3) in d.edges and (2, 3) in d.edges          # loads -> next store
    assert (1, 2) not in d.edges                            # loads can be reordered


def test_terminator_is_last_and_blocks_split():
    p = parse("A: ADD R1,R2,R3\nBEQ R1,R0,B\nADD R4,R5,R6\nB: NOP\n").program
    blocks = split_blocks(p)
    assert [(b.start, b.end) for b in blocks] == [(0, 2), (2, 3), (3, 4)]
    d = build_dag(p, blocks[0])
    assert (0, 1) in d.edges


def test_kahn_produces_valid_topological_order():
    _, d = dag_of("LW R1,0(R2)\nADD R3,R1,R4\nLW R5,4(R2)\nSUB R6,R5,R4\n")
    order, log = kahn_fifo(d)
    assert is_topological(order, d)
    assert len(log) == len(order) == 4


def test_is_topological_rejects_violations():
    _, d = dag_of("ADD R1,R2,R3\nADD R4,R1,R1\n")
    assert is_topological([0, 1], d)
    assert not is_topological([1, 0], d)
    assert not is_topological([0], d)


def test_kahn_detects_all_nodes_on_random_dags():
    rng = random.Random(7)
    for _ in range(50):
        lines = [f"ADD R{rng.randint(1,6)}, R{rng.randint(0,6)}, R{rng.randint(0,6)}" for _ in range(rng.randint(1, 25))]
        p = parse("\n".join(lines)).program
        d = build_dag(p, split_blocks(p)[0])
        order, _ = kahn_fifo(d)
        assert is_topological(order, d)
