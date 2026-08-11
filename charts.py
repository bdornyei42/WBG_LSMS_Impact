"""
charts.py — LSMS-branded PNG charts for the FLOW and Africa SHARE headline
numbers. Reads the run's CSV, not the workbook, so the charts always show
exactly what was exported.

Palette lives in one place below, pulled from LSMS_Pipeline_Presentation.pptx
(the deck's theme fills plus its own embedded chart images) rather than the
generic WBG palette these used to hold. Swap the hexes here if the team hands
over a revised brand sheet and everything downstream follows.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")            # no display on a server / in a .bat run
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, MaxNLocator

# ── LSMS palette (from LSMS_Pipeline_Presentation.pptx) ─────────────────────
NAVY    = "#004370"   # headline text, darkest brand navy
BLUE    = "#1389C6"   # accent blue (LSMS logo / banner fill in the deck)
SKY     = "#169AF3"   # lighter accent - in-progress / current-FY treatment
MID     = "#163454"   # primary bars/lines - the navy the deck's own charts use
GREEN   = "#008980"
ORANGE  = "#E8702A"   # matches the "first author" line color in the deck's own chart
GRID    = "#C7D2DD"
MUTED   = "#5B6472"

DPI = 200
FIGSIZE = (10, 5.6)

plt.rcParams["font.family"] = ["Calibri", "Segoe UI", "DejaVu Sans"]


def _frame(ax, title, subtitle="", ylabel=""):
    """House style: no box, light horizontal grid only, title block top-left."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, length=0, labelsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED, fontsize=10)
    # title block sits above the legend row, which itself sits above the axes
    ax.set_title(title, color=NAVY, fontsize=15, fontweight="bold",
                 loc="left", pad=48 if subtitle else 12)
    if subtitle:
        ax.annotate(subtitle, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, 34), textcoords="offset points",
                    color=MUTED, fontsize=10.5, va="bottom")


def _source(fig, text):
    fig.text(0.01, 0.01, text, color=MUTED, fontsize=8.5, va="bottom")


def _fy_sort_key(fy: str) -> int:
    # FY80..FY99 are 1980s-90s, FY00..FY79 are 2000s. Same convention the
    # workbook sorts by.
    try:
        n = int(str(fy).replace("FY", ""))
    except ValueError:
        return -1
    return 1900 + n if n >= 80 else 2000 + n


def flow_chart(df, out_path: Path, current_fy: str = "") -> Path:
    """Papers per WBG fiscal year. New-this-run papers stacked on top."""
    d = df[df["fy"].notna() & (df["fy"] != "")]
    fys = sorted(d["fy"].unique(), key=_fy_sort_key)
    fys = [f for f in fys if f != current_fy]        # partial FY distorts the trend
    if not fys:
        return None
    total = [int((d["fy"] == f).sum()) for f in fys]
    if "is_new" in d.columns:
        new = [int(((d["fy"] == f) & (d["is_new"] == "Yes")).sum()) for f in fys]
    else:
        new = [0] * len(fys)
    prior = [t - n for t, n in zip(total, new)]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.bar(fys, prior, color=MID, width=0.68, label="Previously tracked")
    if any(new):
        ax.bar(fys, new, bottom=prior, color=BLUE, width=0.68, label="New this run")
        # above the plot, not inside it -- an in-plot legend collides with
        # whichever bar happens to be tallest
        ax.legend(frameon=False, ncol=2, fontsize=10, labelcolor=MUTED,
                  loc="lower left", bbox_to_anchor=(0, 1.005))
    for x, t in zip(fys, total):
        ax.annotate(f"{t:,}", (x, t), ha="center", va="bottom",
                    fontsize=9.5, color=NAVY, fontweight="bold",
                    xytext=(0, 3), textcoords="offset points")
    _frame(ax, "LSMS research output by fiscal year",
           "Papers using LSMS data, World Bank fiscal years (1 July to 30 June)",
           "Papers")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
    ax.margins(y=0.14)
    _source(fig, "Source: OpenAlex, via the LSMS research impact tracking pipeline.")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, dpi=DPI, facecolor="white")
    plt.close(fig)
    return out_path


def africa_share_chart(df, out_path: Path, current_fy: str = "") -> Path:
    """Share of papers with an African-affiliated author, per fiscal year."""
    d = df[df["fy"].notna() & (df["fy"] != "")]
    fys = sorted(d["fy"].unique(), key=_fy_sort_key)
    fys = [f for f in fys if f != current_fy]
    fys = [f for f in fys if (d["fy"] == f).sum() >= 5]   # tiny FYs are noise
    if not fys:
        return None

    def share(fy, col):
        sub = d[d["fy"] == fy]
        if not len(sub):
            return 0.0
        vals = sub[col].astype(str).str.lower().isin(["true", "yes", "1"])
        return vals.sum() / len(sub)

    any_a = [share(f, "is_any_author_africa") for f in fys]
    first = [share(f, "is_first_author_africa") for f in fys]

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(fys, any_a, color=MID, linewidth=2.6, marker="o", markersize=6,
            label="Any author at an African institution")
    ax.plot(fys, first, color=ORANGE, linewidth=2.6, marker="D", markersize=5.5,
            label="First author at an African institution")
    # label the headline series, flipping the label below the point wherever
    # the other series sits above it (otherwise the text lands on that line)
    for x, y, other in zip(fys, any_a, first):
        below = other > y
        ax.annotate(f"{y:.0%}", (x, y), ha="center",
                    va="top" if below else "bottom", fontsize=9,
                    color=MID, fontweight="bold",
                    xytext=(0, -8 if below else 7), textcoords="offset points")
    _frame(ax, "African authorship of LSMS research",
           "Share of papers per fiscal year, by author institutional affiliation",
           "Share of papers")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylim(0, max(max(any_a), max(first)) * 1.35 + 0.02)
    ax.legend(frameon=False, ncol=2, fontsize=10, labelcolor=MUTED,
              loc="lower left", bbox_to_anchor=(0, 1.005))
    _source(fig, "Source: OpenAlex author affiliations. Institution-based, so it "
                 "undercounts African researchers working at non-African institutions.")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, dpi=DPI, facecolor="white")
    plt.close(fig)
    return out_path


def build_all(csv_path, out_dir=None, current_fy: str = "", verbose: bool = True) -> list:
    """Read the run's CSV and write both charts next to it."""
    import pandas as pd
    csv_path = Path(csv_path)
    out_dir = Path(out_dir or csv_path.parent)
    df = pd.read_csv(csv_path)
    stem = csv_path.stem
    made = []
    for fn, suffix in ((flow_chart, "flow"), (africa_share_chart, "africa_share")):
        try:
            p = fn(df, out_dir / f"{stem}_{suffix}.png", current_fy=current_fy)
        except Exception as e:                       # a chart failing must not kill a run
            print(f"  [warn] {suffix} chart failed: {e}", flush=True)
            continue
        if p:
            made.append(p)
            if verbose:
                print(f"  [chart] {p.name}", flush=True)
    return made
