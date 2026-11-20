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
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(1, 2, figsize=(6.7, 3.5))
    fig.subplots_adjust(bottom=0.14, wspace=0.30)

    def panel(ax, names, title):
        xs = [2.35 * i for i in range(len(names))]
        ax.set_xlim(-0.9, xs[-1] + 0.9)
        ax.set_ylim(5.5, -1.15)
        ax.axis("off")
        ax.set_title(title, fontsize=10)
        for x, name in zip(xs, names):
            ax.add_patch(Rectangle((x - 0.92, -0.72), 1.84, 0.46,
                                   fc="#e8f0f8", ec=BLUE, lw=1.0, zorder=4))
            ax.text(x, -0.49, name, ha="center", va="center", fontsize=8.4, zorder=5)
            ax.plot([x, x], [0.0, 5.1], color="#b8b8b8", lw=0.9,
                    ls=(0, (4, 3)), zorder=1)
        return xs

    def msg(ax, xs, i, j, y, label="", color=BLUE, ls="-", lw=1.5,
            badge=None, bx=None, lx=None):
        ax.annotate("", xy=(xs[j], y), xytext=(xs[i], y),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=lw,
                                    linestyle=ls, shrinkA=3, shrinkB=3,
                                    mutation_scale=13), zorder=3)
        if label:
            x = lx if lx is not None else (xs[i] + xs[j]) / 2
            ax.text(x, y - 0.20, label, ha="center", va="bottom", fontsize=8.0,
                    color=color, bbox=LBL, zorder=5)
        if badge is not None:
            ax.text(bx, y, str(badge), ha="center", va="center", fontsize=7.0,
                    color=color, fontweight="bold", zorder=6,
                    bbox=dict(boxstyle="circle,pad=0.30", fc="white", ec=color, lw=1.1))

    # ---------------- Passive ----------------
    ax = axes[0]
    xs = panel(ax, ["Client", "Primary", "S1", "S2"], "Passive replication")
    msg(ax, xs, 0, 1, 0.85, "request", badge=1, bx=0.55, lx=1.60)
    msg(ax, xs, 1, 2, 2.00, "update", badge=2, bx=2.85, lx=3.95)
    msg(ax, xs, 1, 3, 2.28)
    msg(ax, xs, 2, 1, 3.45, "ACK", color=GREEN, ls="--", badge=3, bx=3.55, lx=4.20)
    msg(ax, xs, 3, 1, 3.73, color=GREEN, ls="--")
    msg(ax, xs, 1, 0, 4.90, "response", ls=":", badge=4, bx=0.55, lx=1.60)

    # ---------------- Active ----------------
    ax = axes[1]
    xs = panel(ax, ["Client", "S1", "S2", "S3"], "Active replication")
    msg(ax, xs, 0, 1, 0.85, "request", badge=1, bx=0.55, lx=1.60)
    msg(ax, xs, 0, 2, 1.10)
    msg(ax, xs, 0, 3, 1.35)
    msg(ax, xs, 1, 0, 2.30, "response", color=GREEN, lw=1.6, badge=2, bx=0.55, lx=1.60)
    msg(ax, xs, 2, 0, 2.58, color=GREEN, ls=":", lw=1.0)
    msg(ax, xs, 3, 0, 2.86, color=GREEN, ls=":", lw=1.0)
    ax.text(2.35, 3.35, "client keeps the first response",
            ha="center", va="top", fontsize=7.0, color=GREEN, style="italic")

    handles = [
        Line2D([0], [0], color=BLUE, lw=1.5, label="request / update"),
        Line2D([0], [0], color=GREEN, lw=1.4, ls="--", label="ACK"),
        Line2D([0], [0], color=GREEN, lw=1.5, label="first response kept"),
        Line2D([0], [0], color=GREEN, lw=1.0, ls=":", label="discarded response"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False,
               fontsize=6.8, bbox_to_anchor=(0.5, 0.0), handlelength=2.0,
               columnspacing=0.9)

    fig.savefig(OUT / "fig-3.1b-models.png", dpi=220, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- 3.1c figures
def fig_1a():
    c = Chrono(["C1", "C2", "P", "S1", "S2"], ends=[12, 12, 8.2, 12, 12],
               figsize=(6.5, 4.4), height=10.0,
)
    c.msg(0, 2, 1.2, "W(x=1)")
    c.msg(2, 3, 2.2, "update")
    c.msg(2, 4, 3.0, "update", frac=0.28)
    c.action(3, 2.55, "x=1", dx=0.5, ha="left")
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
               figsize=(6.5, 4.4), height=10.0,
)
    c.msg(0, 2, 1.2, "W(x=1)")
    c.msg(2, 3, 2.2, "update")
    c.msg(2, 4, 3.0, "update")
    c.action(3, 2.45, "x=1", dx=0.5, ha="left")
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
               figsize=(6.4, 4.0), height=9.6,
)
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
               figsize=(6.4, 4.2), height=10.2,
)
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
               figsize=(6.4, 3.6), height=8.0,
)
    c.msg(0, 1, 1.2, "W(x=1)")
    c.msg(1, 0, 1.9, "OK")
    c.action(1, 2.0, "x=1 local", fc="#e6f4ea")
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
               figsize=(6.4, 2.6), height=5.2,
)
    c.msg(0, 1, 1.4, "m")
    c.action(1, 2.2, "deliver(m)", dx=0.95, ha="left")
    c.crash(0, 2.6)
    c.note("S1 delivered m, S2 never will → agreement violated", 4.3)
    c.action(2, 5.0, "never delivers", fc="#fdf1f0", ec=RED, dx=0.0)
    c.save("fig-3.2a-simple.png")


def fig_rb():
    c = Chrono(["P", "S1", "S2"], ends=[12, 12, 12],
               figsize=(6.4, 3.4), height=8.0,
)
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
