"""Presentation helpers (HTML pipeline diagram, text diagram)."""
from __future__ import annotations

from html import escape

from .pipeline import build_diagram

_COLORS = {"IF": "#9ecbff", "ID": "#a5e8b0", "EX": "#ffd59e", "MEM": "#d9b8f5",
           "WB": "#8fe3d8", "STALL": "#ff9c9c"}


def diagram_html(records: list, max_rows: int = 30) -> str:
    total, rows = build_diagram(records, max_rows)
    if not rows:
        return "<p>No instructions executed.</p>"
    head = "".join(f"<th style='padding:2px 5px;font-size:11px'>{c}</th>" for c in range(1, total + 1))
    body = []
    for label, cells in rows:
        tds = []
        for c in range(1, total + 1):
            st = cells.get(c)
            if st is None:
                tds.append("<td style='padding:2px 5px'></td>")
            else:
                txt = "stall" if st == "STALL" else st
                tds.append(f"<td style='background:{_COLORS[st]};color:#111;text-align:center;"
                           f"padding:2px 5px;font-size:11px;border:1px solid #fff'>{txt}</td>")
        body.append(f"<tr><td style='white-space:nowrap;padding:2px 8px;font-family:monospace;"
                    f"font-size:12px'>{escape(label)}</td>{''.join(tds)}</tr>")
    note = ""
    if len(records) > max_rows:
        note = f"<p style='font-size:12px'>Showing first {max_rows} of {len(records)} executed instructions.</p>"
    return (f"<div style='overflow-x:auto'><table style='border-collapse:collapse'>"
            f"<tr><th></th>{head}</tr>{''.join(body)}</table></div>{note}")


def diagram_text(records: list, max_rows: int = 30) -> str:
    total, rows = build_diagram(records, max_rows)
    width = max((len(l) for l, _ in rows), default=0)
    out = [" " * width + " | " + " ".join(f"{c:>4}" for c in range(1, total + 1))]
    for label, cells in rows:
        out.append(f"{label:<{width}} | " + " ".join(f"{('--' if cells.get(c) == 'STALL' else cells.get(c, '')):>4}"
                                                      for c in range(1, total + 1)))
    return "\n".join(out)
