"""Plain-text and HTML tickets for a ``PriceResult``."""

from __future__ import annotations

from argentum.types import PriceResult


def text_ticket(result: PriceResult, *, title: str = "Argentum ticket") -> str:
    lines = [title, "=" * len(title), f"NPV          {result.npv:,.8f} {result.currency}", f"engine       {result.engine or '—'}"]
    if result.implied_vol is not None:
        lines.append(f"implied vol  {result.implied_vol:.6%}")
    if result.error is not None:
        lines.append(f"std error    {result.error:.6f}")
    g = result.greeks
    if g is not None:
        lines.append("")
        lines.append("Greeks")
        lines.append("------")
        for key, val in g.as_dict().items():
            lines.append(f"  {key:<12} {val: .8f}")
    return "\n".join(lines) + "\n"


def html_ticket(result: PriceResult, *, title: str = "Argentum ticket") -> str:
    rows = [f"<tr><th>NPV</th><td>{result.npv:,.8f} {result.currency}</td></tr>"]
    rows.append(f"<tr><th>engine</th><td>{result.engine or '—'}</td></tr>")
    if result.greeks is not None:
        for key, val in result.greeks.as_dict().items():
            rows.append(f"<tr><th>{key}</th><td>{val:.8f}</td></tr>")
    body = "\n".join(rows)
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>"
        f"{title}</title></head><body><h1>{title}</h1><table>{body}</table></body></html>"
    )
