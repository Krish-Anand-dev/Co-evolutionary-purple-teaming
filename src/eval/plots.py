"""Figure helpers for the results (T25): metric-per-round curves and per-condition bars, with bootstrap CI bands.

matplotlib is an OPTIONAL dependency (imported inside the functions); the metrics and tables do not need it.
Rows come from `summary.summarise`. Style follows the data-viz checks the project uses:
  * one measure per figure, one axis (never a second y-scale)
  * colours are the first slots of a categorical palette validated for colour-blind separation on a light surface
    (`validate_palette.js`: all checks pass for 5 slots; the contrast warning for aqua, yellow and magenta is why every
    series ALSO has its own marker shape, a legend and a direct end-of-line label, and why summary.format_table is the
    table view of the same numbers)
  * a condition keeps its colour by its position in the `conditions` list, so removing a condition never repaints the rest
  * text uses text colours, never the series colour; thin 2 px lines; CI bands are a light fill with no outline
At most 5 conditions per figure; beyond that, split into several figures or fold conditions together.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

SURFACE = "#fcfcfb"
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4")   # blue, orange, aqua, yellow, magenta
MARKERS = ("o", "s", "^", "D", "v")
MAX_CONDITIONS = len(SERIES)

_LABELS = {"precision": "Precision", "recall": "Recall", "fpr": "False-positive rate",
           "time_to_detect": "Time to detect (steps)", "rule_validity": "Rule validity", "red_success": "Red success"}


def _pyplot():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise ImportError("matplotlib is needed for figures (pip install matplotlib); tables work without it") from exc
    return plt


def _conditions(rows: Sequence[Mapping[str, Any]], conditions: Sequence[str] | None) -> list[str]:
    found = sorted({str(r["condition"]) for r in rows})
    chosen = list(conditions) if conditions is not None else found
    if len(chosen) > MAX_CONDITIONS:
        raise ValueError(f"{len(chosen)} conditions: at most {MAX_CONDITIONS} per figure (split the figure or fold conditions)")
    missing = [c for c in chosen if c not in found]
    if missing:
        raise ValueError(f"no rows for condition(s) {missing}")
    return chosen


def _style(ax, ylabel: str, title: str | None, ylim) -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.set_ylabel(ylabel, color=INK_2, fontsize=10)
    if title:
        ax.set_title(title, color=INK, fontsize=11, loc="left")
    if ylim is not None:
        ax.set_ylim(*ylim)


def _spread(ys: list[float], min_gap: float) -> list[float]:
    """Push end-of-line labels apart (keeping their order) so they do not overprint."""
    order = sorted(range(len(ys)), key=lambda i: ys[i])
    out = list(ys)
    for a, b in zip(order, order[1:]):
        if out[b] - out[a] < min_gap:
            out[b] = out[a] + min_gap
    return out


def plot_round_curves(rows: Sequence[Mapping[str, Any]], metric: str, path: str | Path,
                      conditions: Sequence[str] | None = None, ylabel: str | None = None, title: str | None = None,
                      ylim: tuple[float, float] | None = None) -> Path:
    """Mean of `metric` per round for each condition with its bootstrap CI as a band. rows: summarise(..., group_by=("condition","round"))."""
    plt = _pyplot()
    sel = [r for r in rows if r["metric"] == metric]
    if not sel:
        raise ValueError(f"no rows for metric {metric!r}")
    conds = _conditions(sel, conditions)
    if ylim is None and metric in ("precision", "recall", "fpr", "rule_validity"):
        ylim = (0.0, 1.0)

    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=200)
    ends: list[tuple[str, float, float]] = []
    for i, cond in enumerate(conds):
        pts = sorted((r for r in sel if str(r["condition"]) == cond and r["mean"] is not None), key=lambda r: r["round"])
        if not pts:
            continue
        x, y = [r["round"] for r in pts], [r["mean"] for r in pts]
        lo = [r["ci_low"] if r["ci_low"] is not None else r["mean"] for r in pts]
        hi = [r["ci_high"] if r["ci_high"] is not None else r["mean"] for r in pts]
        ax.fill_between(x, lo, hi, color=SERIES[i], alpha=0.16, linewidth=0, zorder=1)
        ax.plot(x, y, color=SERIES[i], linewidth=2, marker=MARKERS[i], markersize=6.5, markeredgecolor=SURFACE,
                markeredgewidth=1.5, label=cond, zorder=2)
        ends.append((cond, x[-1], y[-1]))
    ax.set_xlabel("Round", color=INK_2, fontsize=10)
    _style(ax, ylabel or _LABELS.get(metric, metric), title, ylim)
    if sel and len({r["round"] for r in sel}) <= 12:
        ax.set_xticks(sorted({r["round"] for r in sel}))
    if len(ends) >= 2:
        ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, loc="best")
    if ends:  # direct labels at the line ends, in text colour
        lo_y, hi_y = ax.get_ylim()
        ys = _spread([e[2] for e in ends], 0.06 * (hi_y - lo_y))
        for (cond, xe, _), ye in zip(ends, ys):
            ax.annotate(cond, (xe, ye), xytext=(8, 0), textcoords="offset points", va="center", fontsize=9,
                        color=INK_2, annotation_clip=False)
        fig.subplots_adjust(right=0.80)
    fig.subplots_adjust(bottom=0.2)
    fig.text(0.01, 0.012, "Line = mean over seeds; band = 95% bootstrap CI over seeds", fontsize=7.5, color=INK_2)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def plot_condition_bars(rows: Sequence[Mapping[str, Any]], metric: str, path: str | Path,
                        conditions: Sequence[str] | None = None, round_number: int | None = None,
                        ylabel: str | None = None, title: str | None = None,
                        ylim: tuple[float, float] | None = None) -> Path:
    """One bar per condition at `round_number` (default: the last round present) with the bootstrap CI as an error bar."""
    plt = _pyplot()
    sel = [r for r in rows if r["metric"] == metric]
    if not sel:
        raise ValueError(f"no rows for metric {metric!r}")
    conds = _conditions(sel, conditions)
    rnd = round_number if round_number is not None else max(r["round"] for r in sel)
    at = {str(r["condition"]): r for r in sel if r["round"] == rnd}
    if ylim is None and metric in ("precision", "recall", "fpr", "rule_validity"):
        ylim = (0.0, 1.0)

    fig, ax = plt.subplots(figsize=(max(4.2, 1.5 * len(conds) + 1.2), 4.2), dpi=200)
    for i, cond in enumerate(conds):
        r = at.get(cond)
        if r is None or r["mean"] is None:
            continue
        ax.bar(i, r["mean"], width=0.5, color=SERIES[i], edgecolor=SURFACE, linewidth=2, zorder=2)
        if r["ci_low"] is not None:
            ax.errorbar(i, r["mean"], yerr=[[r["mean"] - r["ci_low"]], [r["ci_high"] - r["mean"]]], color=INK_2,
                        capsize=4, linewidth=1.5, zorder=3)
        ax.annotate(f"{r['mean']:.2f}", (i, r["ci_high"] if r["ci_high"] is not None else r["mean"]), xytext=(0, 6),
                    textcoords="offset points", ha="center", fontsize=9, color=INK)
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels(conds, fontsize=9, color=INK_2)
    _style(ax, ylabel or _LABELS.get(metric, metric), title or f"Round {rnd}", ylim)
    fig.subplots_adjust(bottom=0.2)
    fig.text(0.01, 0.012, "Bar = mean over seeds; whisker = 95% bootstrap CI over seeds", fontsize=7.5, color=INK_2)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path
