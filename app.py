"""PipeSched - Assembly Parser and Pipeline Hazard Optimizer (Streamlit UI).

Run:  streamlit run app.py
"""
import glob
import os

import pandas as pd
import streamlit as st

from pipesched import PipelineConfig, analyze
from pipesched.dag import dag_to_dot
from pipesched.grammar import (PRODUCTIONS, TERMINAL_HELP, compute_first, compute_follow,
                               grammar_text, ll1_table)
from pipesched.parser import leftmost_derivation, tree_to_dot, tree_to_text
from pipesched.render import diagram_html

st.set_page_config(page_title="PipeSched", page_icon="⚙️", layout="wide")

HERE = os.path.dirname(os.path.abspath(__file__))
_PATHS = sorted(glob.glob(os.path.join(HERE, "examples", "*.asm")),
                key=lambda p: (os.path.basename(p) != "load_use.asm", os.path.basename(p)))
EXAMPLES = {os.path.basename(p): open(p).read() for p in _PATHS}

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("⚙️ PipeSched")
    st.caption("Assembly parser + pipeline hazard optimizer")
    example = st.selectbox("Example program", list(EXAMPLES) + ["(my own code)"])
    st.subheader("Pipeline settings (COA)")
    forwarding = st.toggle("Data forwarding", value=True,
                           help="ON: ALU results forwarded after EX, loads after MEM. OFF: wait for WB.")
    penalty = st.slider("Taken-branch penalty (cycles)", 0, 4, 2,
                        help="Branches resolve in EX with predict-not-taken => 2 bubbles when taken.")
    st.subheader("Optimizer (DAA)")
    mode_label = st.radio("Kahn's algorithm variant",
                          ["Hazard-aware (greedy ready-set)", "Plain FIFO queue"])
    mode = "hazard_aware" if mode_label.startswith("Hazard") else "fifo"
    max_steps = st.number_input("Max executed instructions", 100, 50000, 5000, step=500)

default_src = EXAMPLES.get(example, "")
src = st.text_area("Assembly source", value=default_src, height=260, key=f"src_{example}",
                   help="Supported: ADD SUB AND OR MUL | ADDI SUBI | LW SW | BEQ BNE | J | NOP | labels")

cfg = PipelineConfig(forwarding=forwarding, branch_penalty=penalty)
res = analyze(src, cfg, mode, max_steps=int(max_steps))

st.title("PipeSched")
st.caption("FLAT: grammar & parser  →  DAA: dependency DAG & Kahn's topological sort  →  "
           "COA: 5-stage pipeline simulation")

tab_flat, tab_daa, tab_coa, tab_sum = st.tabs(
    ["1 · FLAT — Parser", "2 · DAA — DAG & Kahn", "3 · COA — Pipeline", "4 · Results"])

# ================================================================= FLAT
with tab_flat:
    c1, c2 = st.columns([1, 1])
    with c1:
        st.subheader("Context-free grammar")
        st.code(grammar_text(), language="text")
        first, follow = compute_first(), compute_follow()
        _, conflicts = ll1_table()
        if conflicts:
            st.error(f"Grammar is NOT LL(1): {len(conflicts)} conflict(s)")
        else:
            st.success("Grammar is LL(1): FIRST/FOLLOW selection sets never overlap, "
                       "so the grammar is unambiguous and a predictive parser works.")
        with st.expander("FIRST and FOLLOW sets"):
            df = pd.DataFrame({
                "FIRST": {k: ", ".join(sorted(v)) for k, v in first.items()},
                "FOLLOW": {k: ", ".join(sorted(v)) for k, v in follow.items()}})
            st.dataframe(df, width="stretch")
        with st.expander("Terminals (tokens)"):
            st.table(pd.DataFrame({"token": list(TERMINAL_HELP), "meaning": list(TERMINAL_HELP.values())}))
    with c2:
        st.subheader("Parse result")
        pr = res.parse
        if pr.ok:
            st.success(f"Valid program: {len(pr.program.instrs)} instructions, "
                       f"{len(pr.program.labels)} label(s), {len(pr.tokens)} tokens.")
        else:
            st.error(f"{len(pr.errors)} error(s) found")
            st.dataframe(pd.DataFrame([{"line": e.line, "col": e.col, "type": e.kind,
                                        "message": e.message, "source": e.source} for e in pr.errors]),
                         width="stretch", hide_index=True)
        with st.expander("Token stream"):
            st.dataframe(pd.DataFrame([{"kind": t.kind, "lexeme": t.text, "line": t.line, "col": t.col}
                                       for t in pr.tokens]), width="stretch", hide_index=True)

    if pr.lines:
        st.subheader("Derivation tree")
        labels = [f"line {li.line_no}:  {li.source.strip()}" for li in pr.lines]
        pick = st.selectbox("Choose a line", range(len(labels)), format_func=lambda i: labels[i])
        node = pr.lines[pick].node
        t1, t2 = st.columns([3, 2])
        with t1:
            st.graphviz_chart(tree_to_dot(node), width="stretch")
        with t2:
            st.markdown("**Leftmost derivation**")
            st.code("\n".join(f"⇒ {s}" for s in leftmost_derivation(node)), language="text")
            with st.expander("Tree as text"):
                st.code(tree_to_text(node), language="text")

# ================================================================= DAA
with tab_daa:
    if not res.ok:
        st.warning("Fix the syntax errors (tab 1) to build the dependency graph.")
    else:
        prog, opt = res.parse.program, res.opt
        st.markdown(
            "Each **basic block** becomes a DAG: nodes are instructions, edges are dependencies "
            "(**RAW**, **WAR**, **WAW**, memory order, and control). Kahn's algorithm repeatedly removes a "
            "node with in-degree 0, so every output is a *valid topological order* (never breaks a dependency).")
        bsel = st.selectbox("Basic block", range(len(opt.blocks)),
                            format_func=lambda k: f"Block {k + 1}: instructions "
                                                  f"{opt.blocks[k].block.start + 1}–{opt.blocks[k].block.end}")
        b = opt.blocks[bsel]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Nodes (V)", len(b.dag.nodes))
        m2.metric("Edges (E)", b.dag.num_edges)
        m3.metric("Instructions moved", b.moved)
        m4.metric("Valid topological order", "✅" if b.valid else "❌")
        if b.fallback:
            st.info("Greedy order was not better than the original for this block, so the original was kept.")

        st.graphviz_chart(dag_to_dot(b.dag, prog), width="stretch")
        st.caption("Edge colours: RAW red · WAR orange (dashed) · WAW purple (dashed) · MEM blue · CTRL grey (dotted)")

        o1, o2 = st.columns(2)
        with o1:
            st.markdown("**Original order**")
            st.code("\n".join(f"{i + 1:>3}: {prog.instrs[i].text()}" for i in b.original_order), language="text")
        with o2:
            st.markdown("**Kahn order (optimized)**")
            st.code("\n".join(f"{i + 1:>3}: {prog.instrs[i].text()}" for i in b.order), language="text")

        st.markdown("**Kahn's algorithm, step by step**")
        rows = []
        for k, step in enumerate(b.log, 1):
            row = {"step": k,
                   "ready set (in-degree 0)": ", ".join(str(v + 1) for v in step["ready"]),
                   "chosen": f"{step['chosen'] + 1}: {prog.instrs[step['chosen']].text()}"}
            if step["stalls"] is not None:
                row["stalls if chosen"] = step["stalls"]
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        with st.expander("Complexity"):
            st.markdown(
                "- DAG construction: **O(V·R + E)** (last-writer / readers-since-write tables, R = 32 registers)\n"
                "- Plain Kahn (FIFO queue): **O(V + E)**\n"
                "- Hazard-aware Kahn: each step scans the ready set and evaluates its stall cost: "
                "**O(V² + E)** worst case (O(V·W + E) with W = max ready-set width)\n"
                "- Heights (critical path): **O(V + E)**")
        st.subheader("Optimized program")
        st.code(opt.program.to_asm(), language="text")
        status, msg = res.equivalence
        (st.success if status == "equivalent" else st.warning if status == "inconclusive" else st.error)(
            f"Equivalence check — {status}: {msg}")

# ================================================================= COA
with tab_coa:
    if not res.ok:
        st.warning("Fix the syntax errors (tab 1) to simulate the pipeline.")
    else:
        st.markdown(
            "**5-stage in-order pipeline**: IF → ID → EX → MEM → WB.  "
            f"Forwarding **{'ON' if forwarding else 'OFF'}**, taken-branch penalty **{penalty}** cycles. "
            "`CPI = total cycles / instructions`; ideal CPI → 1 when there are no stalls.")
        a, z = res.before, res.after
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Cycles", z.cycles, z.cycles - a.cycles, delta_color="inverse")
        c2.metric("CPI", f"{z.cpi:.2f}", f"{z.cpi - a.cpi:.2f}", delta_color="inverse")
        c3.metric("Data stalls", z.data_stalls, z.data_stalls - a.data_stalls, delta_color="inverse")
        c4.metric("Control bubbles", z.control_bubbles)
        c5.metric("Speedup", f"{res.speedup:.2f}×")
        if a.truncated or z.truncated:
            st.warning("Execution stopped at the step limit; totals cover only the executed prefix.")

        rows = st.slider("Instructions shown in diagram", 5, 60, 20)
        st.markdown("**Original program**")
        st.markdown(diagram_html(a.records, rows), unsafe_allow_html=True)
        st.markdown("**Optimized program**")
        st.markdown(diagram_html(z.records, rows), unsafe_allow_html=True)

        h1, h2 = st.columns(2)
        with h1:
            st.markdown("**RAW hazards causing stalls — original**")
            hz = a.hazards()
            st.dataframe(pd.DataFrame(hz) if hz else pd.DataFrame({"result": ["no stalls 🎉"]}),
                         width="stretch", hide_index=True)
        with h2:
            st.markdown("**RAW hazards causing stalls — optimized**")
            hz = z.hazards()
            st.dataframe(pd.DataFrame(hz) if hz else pd.DataFrame({"result": ["no stalls 🎉"]}),
                         width="stretch", hide_index=True)

# ================================================================= RESULTS
with tab_sum:
    if not res.ok:
        st.warning("Fix the syntax errors (tab 1) first.")
    else:
        a, z = res.before, res.after
        df = pd.DataFrame({"Original": [a.cycles, a.data_stalls, round(a.cpi, 3)],
                           "Optimized": [z.cycles, z.data_stalls, round(z.cpi, 3)]},
                          index=["Total cycles", "Data-stall cycles", "CPI"])
        st.subheader("Before vs after (current program)")
        st.dataframe(df, width="stretch")
        st.bar_chart(df.loc[["Total cycles", "Data-stall cycles"]])

        st.subheader("Benchmark: all bundled examples with the current settings")
        bench = []
        for name, text in EXAMPLES.items():
            r = analyze(text, cfg, mode, max_steps=int(max_steps))
            if r.ok:
                bench.append({"program": name, "instructions executed": r.before.instructions,
                              "cycles before": r.before.cycles, "cycles after": r.after.cycles,
                              "CPI before": round(r.before.cpi, 2), "CPI after": round(r.after.cpi, 2),
                              "speedup": round(r.speedup, 2), "equivalent": r.equivalence[0]})
        st.dataframe(pd.DataFrame(bench), width="stretch", hide_index=True)
