# PipeSched — Assembly Parser and Pipeline Hazard Optimizer

One application that combines three subjects of the micro project:

| Subject | Module / concept used | Where it lives | What it does in PipeSched |
|---|---|---|---|
| **FLAT** | Module 3 — Context-Free Grammar, derivation (parse) trees, ambiguity (LU 3.1–3.3) | `pipesched/grammar.py`, `lexer.py`, `parser.py` | Defines a CFG for a MIPS-like assembly language, proves it is LL(1) (FIRST/FOLLOW, no table conflicts), parses programs with a hand-written recursive-descent parser, builds parse trees, prints leftmost derivations, reports every syntax/semantic error |
| **DAA** | Module 1 — Topological sorting, Kahn's algorithm (LU 1.11) | `pipesched/dag.py`, `optimizer.py` | Builds an instruction dependency DAG per basic block (RAW/WAR/WAW/memory/control edges) and reorders instructions with a (hazard-aware) Kahn's algorithm |
| **COA** | Module 3 — Pipelining, data/control hazards, CPI (LU 3.1, 3.5–3.9, 3.12, 3.14) | `pipesched/pipeline.py`, `executor.py` | Cycle-accurate 5-stage pipeline (IF-ID-EX-MEM-WB), forwarding on/off, load-use stalls, branch penalty, pipeline diagram, CPI and speedup before vs after |

```
Assembly text ─▶ [FLAT] lexer + CFG parser ─▶ parse tree / errors
                         │ Program
                         ▼
              [DAA] dependency DAG per basic block ─▶ Kahn's topological sort ─▶ reordered program
                         │                                              │
                         ▼                                              ▼
              [COA] 5-stage pipeline simulator (original)    [COA] pipeline simulator (optimized)
                                   └──────▶ stalls · CPI · cycles · speedup ◀──────┘
                    + functional interpreter proves both programs compute the same result
```

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py                       # web UI (4 tabs)
python main.py examples/load_use.asm --tree   # command line
python main.py examples/array_sum_loop.asm --no-forwarding --mode fifo
python -m pytest -q                        # 148 tests
```

## Project layout

```
app.py                 Streamlit UI  (FLAT tab · DAA tab · COA tab · Results tab)
main.py                command-line interface
pipesched/
  isa.py               instruction set, Instr / Program model, register def/use
  lexer.py             tokenizer
  grammar.py           the CFG as data + FIRST/FOLLOW + LL(1) table      (FLAT)
  parser.py            recursive-descent parser, parse trees, derivations, error recovery (FLAT)
  dag.py               basic blocks, dependency DAG, plain Kahn, DOT export          (DAA)
  optimizer.py         hazard-aware Kahn scheduler                                   (DAA)
  executor.py          functional interpreter: dynamic trace + equivalence check
  pipeline.py          5-stage pipeline timing model, hazards, diagram               (COA)
  analysis.py          parse -> optimize -> simulate -> verify in one call
examples/              load_use · array_sum_loop · mixed_hazards · two_blocks · invalid_program
tests/                 pytest suite (parser, DAG, pipeline, optimizer, property tests)
docs/sample_outputs/   ready-made outputs/screens text for the reports
```

## The assembly language

`ADD SUB AND OR MUL rd, rs, rt` · `ADDI SUBI rd, rs, imm` · `LW rd, off(rs)` · `SW rt, off(rs)` ·
`BEQ BNE rs, rt, label` · `J label` · `NOP` · `label:` · comments with `#` or `;` · registers `R0–R31` (`R0` = 0).

Grammar (LL(1), hence unambiguous):

```
Program  → Lines
Lines    → Line Lines  |  ε
Line     → ID COLON OptInstr NL  |  Instr NL
OptInstr → Instr  |  ε
Instr    → RInstr | IInstr | MemInstr | BrInstr | JInstr | NOP
RInstr   → ROP REG COMMA REG COMMA REG
IInstr   → IOP REG COMMA REG COMMA NUM
MemInstr → MEMOP REG COMMA NUM LPAREN REG RPAREN
BrInstr  → BROP REG COMMA REG COMMA ID
JInstr   → JOP ID
```

## Modelling assumptions (state these in the reports)

* In-order, single-issue, 5-stage pipeline; separate instruction/data memory (no structural hazards).
* **With forwarding:** ALU results usable by the next instruction's EX; load results one cycle later ⇒ a load-use pair costs **1 stall**. A store needs its data register only in MEM.
* **Without forwarding:** register file writes in the first half of a cycle and reads in the second half ⇒ back-to-back dependent instructions cost **2 stalls**.
* **Control:** branches/jumps resolve in EX, predict-not-taken ⇒ a *taken* branch/jump costs `branch_penalty` bubbles (default 2).
* Loops are timed on the *dynamic* trace produced by the interpreter (default limit 5000 executed instructions).
* Scheduling is done inside basic blocks only; memory accesses are treated as possibly aliasing (conservative). Every output is checked by running original and optimized code from random start states.

## Complexity (for the DAA report)

| Step | Time |
|---|---|
| DAG construction (last-writer / readers-since-write tables) | O(V·R + E), R = 32 registers |
| Plain Kahn (FIFO queue) | O(V + E) |
| Hazard-aware Kahn (scan ready set each step) | O(V² + E) worst case |
| Critical-path heights | O(V + E) |

## Results on the bundled examples (forwarding ON, branch penalty 2)

| Program | Cycles before → after | CPI before → after |
|---|---|---|
| load_use | 15 → 12 | 1.88 → 1.50 |
| array_sum_loop | 50 → 42 | 1.56 → 1.31 |
| mixed_hazards | 18 → 16 | 1.50 → 1.33 |
| two_blocks | 19 → 15 | 1.73 → 1.36 |

## Submission checklist (per subject ZIP)

* ZIP name: `StudentName_SubjectName_MicroProject.zip` (e.g. `Diya_FLAT_MicroProject.zip`)
* Contains: this project folder + that subject's report (PDF/DOCX) + screenshots
* GitHub repository: **<paste link here>**
* Deployed application: **<paste Streamlit Community Cloud link here>**

## Deploy (free)

1. Push this folder to a GitHub repository (`app.py` and `requirements.txt` at the repo root).
2. Go to share.streamlit.io → *New app* → pick the repo, branch `main`, main file `app.py` → Deploy.
