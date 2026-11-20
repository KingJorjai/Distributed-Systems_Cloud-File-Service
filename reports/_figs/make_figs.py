#!/usr/bin/env python3
"""Generate chronograms and schematics for DS reports 3.1b, 3.1c and 3.2a."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})

BLUE = "#1f4e79"
RED = "#b3261e"
GREEN = "#2e6b34"
GREY = "#8a8a8a"
LBL = dict(fc="white", ec="none", pad=0.6)


class Chrono:
    """Sequence diagram: participants on x, time flows down on y."""

    def __init__(self, names, ends=None, figsize=(6.4, 5.2), title="", height=12.0):
        self.names = names
        self.xs = [2.0 * i for i in range(len(names))]
        self.height = height
        self.fig, self.ax = plt.subplots(figsize=figsize)
        self.ends = ends if ends is not None else [height] * len(names)
        for x, end in zip(self.xs, self.ends):
            self.ax.plot([x, x], [0, end], color=GREY, lw=1.0, zorder=1)
        for x, name in zip(self.xs, names):
            self.ax.text(x, -0.30, name, ha="center", va="bottom",
                         fontsize=10, fontweight="bold")
        self.ax.set_xlim(-1.4, 2.0 * (len(names) - 1) + 1.4)
        self.ax.set_ylim(height + 0.3, -1.0)
        self.ax.axis("off")
        if title:
            self.ax.set_title(title, fontsize=10.5, pad=16)

    def msg(self, i, j, y, label="", color=BLUE, ls="-", dy=-0.16, fs=8.2, frac=0.5):
        self.ax.annotate(
            "", xy=(self.xs[j], y), xytext=(self.xs[i], y),
            arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5, linestyle=ls,
                            shrinkA=2, shrinkB=2), zorder=3)
        if label:
            x = self.xs[i] + frac * (self.xs[j] - self.xs[i])
            self.ax.text(x, y + dy, label, ha="center", va="bottom",
                         fontsize=fs, color=color, bbox=LBL, zorder=4)

    def dmsg(self, i, j, y1, y2, label="", color=BLUE, ls="-", fs=8.0, dx=0.0):
        """Diagonal message: departs at y1 and arrives at y2 (in-flight)."""
        self.ax.annotate(
            "", xy=(self.xs[j], y2), xytext=(self.xs[i], y1),
            arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4, linestyle=ls,
                            shrinkA=2, shrinkB=2), zorder=2)
        if label:
            self.ax.text((self.xs[i] + self.xs[j]) / 2 + dx, (y1 + y2) / 2,
                         label, ha="center", va="center", fontsize=fs,
                         color=color, bbox=LBL, zorder=4)

    def lost(self, i, j, y, label="", color=GREY):
        """Message that leaves i but never reaches j."""
        x_end = self.xs[j] - (0.5 if self.xs[j] > self.xs[i] else -0.5)
        self.ax.annotate("", xy=(x_end, y), xytext=(self.xs[i], y),
                         arrowprops=dict(arrowstyle="-|>", color=color, lw=1.2,
                                         linestyle="--", shrinkA=2, shrinkB=2))
        self.ax.plot([x_end - 0.12, x_end + 0.12], [y - 0.12, y + 0.12], color=RED, lw=1.8)
        self.ax.plot([x_end - 0.12, x_end + 0.12], [y + 0.12, y - 0.12], color=RED, lw=1.8)
        if label:
            self.ax.text((self.xs[i] + x_end) / 2, y - 0.18, label,
                         ha="center", va="bottom", fontsize=8, color=color, bbox=LBL)

    def action(self, i, y, text, fc="#e8f0f8", ec=BLUE, fs=7.2, dx=0.0, ha="center"):
        self.ax.text(self.xs[i] + dx, y, text, ha=ha, va="center", fontsize=fs,
                     bbox=dict(boxstyle="round,pad=0.26", fc=fc, ec=ec, lw=0.8),
                     zorder=4)

    def crash(self, i, y):
        x = self.xs[i]
        self.ax.plot([x - 0.16, x + 0.16], [y - 0.16, y + 0.16], color=RED, lw=2.2, zorder=5)
        self.ax.plot([x - 0.16, x + 0.16], [y + 0.16, y - 0.16], color=RED, lw=2.2, zorder=5)

    def note(self, text, y, color=RED, fs=8.0):
        xmid = self.xs[-1] / 2
        self.ax.text(xmid, y, text, ha="center", va="center", fontsize=fs,
                     color=color, style="italic",
                     bbox=dict(boxstyle="round,pad=0.35", fc="#fdf1f0",
                               ec=color, lw=0.8, alpha=0.95), zorder=6)

    def save(self, name):
        self.fig.tight_layout()
        self.fig.savefig(OUT / name, dpi=220, bbox_inches="tight", facecolor="white")
        plt.close(self.fig)


# ---------------------------------------------------------------- 3.1b figure
def replication_models():
    from matplotlib.patches import Rectangle
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 3.0))

    def box(ax, x, y, text, tint="#e8f0f8"):
        ax.add_patch(Rectangle((x - 0.8, y - 0.36), 1.6, 0.72,
                               fc=tint, ec=BLUE, lw=1.0))
        ax.text(x, y, text, ha="center", va="center", fontsize=8.5)

    def arrow(ax, p1, p2, color=BLUE, ls="-", rad=0.0):
        ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", color=color, lw=1.4,
                                     linestyle=ls, shrinkA=1, shrinkB=1,
                                     connectionstyle=f"arc3,rad={rad}"))

    # Passive
    ax = axes[0]
    ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.axis("off")
    ax.set_title("Passive replication", fontsize=10)
    box(ax, 1.2, 4.0, "Client"); box(ax, 5.0, 4.0, "Primary", "#d6e6f5")
    box(ax, 8.8, 6.6, "S1"); box(ax, 8.8, 1.4, "S2")
    arrow(ax, (2.0, 4.18), (4.2, 4.18))
    ax.text(3.1, 4.40, "request", ha="center", fontsize=7.4, color=BLUE, bbox=LBL)
    arrow(ax, (4.2, 3.60), (2.0, 3.60), ls=":")
    ax.text(3.1, 3.22, "response", ha="center", fontsize=7.4, color=BLUE, bbox=LBL)
    arrow(ax, (5.8, 4.18), (8.0, 6.35), rad=-0.05)
    arrow(ax, (8.0, 6.10), (5.8, 4.42), color=GREEN, ls="--")
    arrow(ax, (5.8, 3.82), (8.0, 1.65), rad=0.05)
    arrow(ax, (8.0, 1.90), (5.8, 3.58), color=GREEN, ls="--")

    # Active
    ax = axes[1]
    ax.set_xlim(0, 10); ax.set_ylim(0, 8); ax.axis("off")
    ax.set_title("Active replication", fontsize=10)
    box(ax, 1.2, 4.0, "Client")
    for k, yy in enumerate([6.6, 4.0, 1.4]):
        box(ax, 8.8, yy, f"S{k + 1}")
        arrow(ax, (2.0, 4.0), (8.0, yy), rad=0.04)
    arrow(ax, (8.0, 6.32), (2.0, 4.20), color=GREEN, ls="--")

    fig.tight_layout()
    fig.savefig(OUT / "fig-3.1b-models.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- 3.1c figures
def fig_1a():
    c = Chrono(["C1", "C2", "P", "S1", "S2"], ends=[12, 12, 8.2, 12, 12],
               figsize=(6.5, 4.8), height=12,
               title="Proposition 1a — every read goes to an arbitrary secondary")
    c.msg(0, 2, 1.2, "W(x=1)")
    c.msg(2, 3, 2.2, "update")
    c.msg(2, 4, 3.0, "update", frac=0.28)
    c.action(3, 2.8, "x=1")
    c.msg(3, 2, 3.6, "ACK", color=GREEN)
    c.msg(1, 3, 4.6, "R(x)")
    c.msg(3, 1, 5.0, "1", color=GREEN)
    c.msg(1, 4, 5.9, "R(x)")
    c.msg(4, 1, 6.3, "0", color=RED)
    c.msg(4, 2, 7.0, "ACK", color=GREEN, ls="--")
    c.msg(2, 0, 7.8, "OK", ls=":")
    c.action(4, 5.5, "x=0")
    c.note("R1 returns 1 before R2 returns 0, and R1 ends before R2 starts:\n"
           "no total order of x explains both reads → linearizability violated", 9.3)
    c.save("fig-3.1c-1a.png")


def fig_1b():
    c = Chrono(["C1", "C2", "P", "S1", "S2"], ends=[12, 12, 7.6, 12, 12],
               figsize=(6.5, 4.8), height=12,
               title="Proposition 1b — each client reads from its own fixed secondary")
    c.msg(0, 2, 1.2, "W(x=1)")
    c.msg(2, 3, 2.2, "update")
    c.msg(2, 4, 3.0, "update")
    c.action(3, 2.7, "x=1")
    c.msg(3, 2, 3.6, "ACK", color=GREEN)
    c.msg(0, 3, 4.6, "R(x)")
    c.msg(3, 0, 5.0, "1", color=GREEN)
    c.msg(1, 4, 5.9, "R(x)")
    c.msg(4, 1, 6.3, "0", color=RED)
    c.action(4, 2.9, "x=0")
    c.note("C1 reads 1, then C2 reads 0. Each client is monotonic,\n"
           "but there is no single global order → still not linearizable", 8.3)
    c.save("fig-3.1c-1b.png")


def fig_2a():
    c = Chrono(["C", "P", "S1", "S2"], ends=[12, 4.0, 12, 12],
               figsize=(6.4, 4.4), height=11,
               title="Proposition 2a — reply before disseminating the update")
    c.msg(0, 1, 1.2, "W(x=1)")
    c.action(1, 2.0, "x=1", fc="#e6f4ea")
    c.msg(1, 0, 2.7, "OK")
    c.crash(1, 4.0)
    c.note("P fails before sending any update", 5.0)
    c.msg(0, 2, 6.4, "R(x)")
    c.msg(2, 0, 6.8, "0", color=RED)
    c.action(2, 7.4, "new primary: x=0")
    c.note("an acknowledged write is lost → atomicity and durability violated", 8.8)
    c.save("fig-3.1c-2a.png")


def fig_2b():
    c = Chrono(["C", "P", "S1", "S2"], ends=[12, 4.6, 4.9, 12],
               figsize=(6.4, 4.3), height=11,
               title="Proposition 2b — reply after sending, without waiting for ACKs")
    c.msg(0, 1, 1.2, "W(x=1)")
    c.msg(1, 2, 2.2, "update")
    c.action(2, 2.0, "x=1")
    c.lost(1, 3, 2.9, "update lost")
    c.msg(1, 0, 3.7, "OK")
    c.crash(1, 4.6)
    c.crash(2, 4.9)
    c.note("S2 never received the update; P and S1 crash", 5.9)
    c.msg(0, 3, 7.1, "R(x)")
    c.msg(3, 0, 7.5, "0", color=RED)
    c.action(3, 8.1, "new primary: x=0")
    c.note("atomicity violated: one replica handled the request,\n"
           "the correct ones never will", 9.5)
    c.save("fig-3.1c-2b.png")


def fig_combined():
    c = Chrono(["C", "P", "S1"], ends=[12, 4.2, 12],
               figsize=(6.4, 4.1), height=11,
               title="Combination of 1 and 2 — reads at secondaries + early reply")
    c.msg(0, 1, 1.2, "W(x=1)")
    c.msg(1, 0, 1.9, "OK")
    c.action(1, 2.2, "x=1 local", fc="#e6f4ea")
    c.msg(0, 2, 3.0, "R(x)", frac=0.3)
    c.msg(2, 0, 3.3, "0", color=RED)
    c.msg(1, 2, 3.9, "update")
    c.action(2, 4.3, "x=1")
    c.msg(0, 2, 5.2, "R(x)")
    c.msg(2, 0, 5.6, "1", color=GREEN)
    c.note("read-your-writes violated (OK, then 0); the value then jumps to 1.\n"
           "If P had failed before sending, the acknowledged write would be lost", 7.3)
    c.save("fig-3.1c-combined.png")


# ---------------------------------------------------------------- 3.2a figures
def fig_simple_broadcast():
    c = Chrono(["P", "S1", "S2"], ends=[2.6, 10, 10],
               figsize=(6.4, 3.3), height=9,
               title="Simple broadcast(): agreement can fail")
    c.msg(0, 1, 1.4, "m")
    c.action(1, 2.2, "deliver(m)", dx=0.95, ha="left")
    c.crash(0, 2.6)
    c.note("S1 delivered m, S2 never will → agreement violated", 4.3)
    c.action(2, 5.0, "never delivers", fc="#fdf1f0", ec=RED, dx=0.0)
    c.save("fig-3.2a-simple.png")


def fig_rb():
    c = Chrono(["P", "S1", "S2"], ends=[12, 12, 12],
               figsize=(6.4, 4.2), height=11,
               title="R-broadcast(): every receiver re-broadcasts once")
    c.msg(0, 1, 1.2, "m", frac=0.4)
    c.msg(0, 2, 1.7, "m", frac=0.4)
    c.action(1, 2.6, "deliver\n+ re-broadcast", fs=6.6)
    c.msg(1, 2, 3.6, "m")
    c.action(2, 2.6, "deliver\n+ re-broadcast", fs=6.6)
    c.msg(2, 1, 4.2, "m", ls="--")
    c.action(1, 4.9, "duplicate\ndropped", fc="#f2f2f2", ec=GREY, fs=6.8)
    c.action(2, 5.7, "deliver")
    c.note("All correct processes deliver; each message travels O(n²) times", 7.2, color=GREEN)
    c.save("fig-3.2a-rb.png")


if __name__ == "__main__":
    replication_models()
    fig_1a(); fig_1b(); fig_2a(); fig_2b(); fig_combined()
    fig_simple_broadcast(); fig_rb()
    print("figures written to", OUT)
