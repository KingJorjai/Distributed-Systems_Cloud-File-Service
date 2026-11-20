#!/usr/bin/env python3
"""Space-time diagrams (time left to right) rendered with TikZ.

Each participant is a horizontal line; messages are diagonal arrows.
Output: one .tex per figure, compiled to PDF and PNG at 300 dpi.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent / "tikz"
OUT.mkdir(exist_ok=True)

BLUE = "cblue"
GREEN = "cgreen"
RED = "cred"
GREY = "cgrey"

PREAMBLE = r"""\documentclass[tikz,border=6pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{helvet}
\renewcommand{\familydefault}{\sfdefault}
\usepackage{xcolor}
\usetikzlibrary{arrows.meta}
\definecolor{cblue}{HTML}{1F4E79}
\definecolor{cgreen}{HTML}{2E7D32}
\definecolor{cred}{HTML}{C62828}
\definecolor{cgrey}{HTML}{808080}
\definecolor{paleblue}{HTML}{E8F0F8}
\definecolor{palegreen}{HTML}{E8F5E9}
\definecolor{palered}{HTML}{FFEBEE}
\definecolor{palegrey}{HTML}{F5F5F5}
\begin{document}
"""


class ST:
    def __init__(self, names, width=9.5, ystep=1.15, title=None):
        self.names = names
        self.sx = 1.45
        self.w = width * self.sx
        self.dy = ystep
        self.title = title
        self.y = {n: -i * ystep for i, n in enumerate(names)}
        self.body = []

    # ---------------------------------------------------------------- drawing
    def lifeline(self, name, end=None):
        y = self.y[name]
        self.body.append(
            rf"\draw[cgrey!60,line width=0.4pt,dashed] (0,{y:.3f}) -- ({end or self.w},{y:.3f});")

    def label(self, name):
        y = self.y[name]
        self.body.append(
            rf"\node[anchor=east,font=\small\bfseries] at (-0.15,{y:.3f}) {{{name}}};")

    def msg(self, t, a, b, text, color=BLUE, dashed=False, above=True,
            fs=r"\scriptsize", frac=0.35, dt=0.45):
        ya, yb = self.y[a], self.y[b]
        style = "dashed" if dashed else "solid"
        pos = "above" if above else "below"
        t = t * self.sx
        self.body.append(
            rf"\draw[-{{Latex[length=1.8mm]}},{color},{style},line width=0.75pt] "
            rf"({t:.2f},{ya:.3f}) -- ({t+dt:.2f},{yb:.3f}) "
            rf"node[pos={frac},{pos},yshift=3pt,fill=white,inner sep=1pt,font={fs}] {{{text}}};")

    def lost(self, t, a, b, text, dt=0.9):
        t = t * self.sx
        ya, yb = self.y[a], self.y[b]
        self.body.append(
            rf"\draw[-{{Latex[length=1.8mm]}},{RED},line width=0.75pt] "
            rf"({t:.2f},{ya:.3f}) -- ({t+dt:.2f},{yb:.3f}) "
            rf"node[midway,above,fill=white,inner sep=1pt,font=\scriptsize] {{{text}}};")
        # cross over the arrow head side
        self.body.append(
            rf"\draw[{RED},line width=1pt] ({t+dt-0.12:.2f},{yb-0.12:.3f}) -- ({t+dt+0.12:.2f},{yb+0.12:.3f});")

    def box(self, t, name, text, fill="paleblue", border=BLUE, fs=r"\scriptsize"):
        t = t * self.sx
        y = self.y[name]
        self.body.append(
            rf"\node[draw={border},fill={fill},line width=0.5pt,inner sep=2pt,"
            rf"font={fs},align=center] at ({t:.2f},{y:.3f}) {{{text}}};")

    def crash(self, t, name):
        t = t * self.sx
        y = self.y[name]
        # hide the rest of the lifeline: the process stops here
        self.body.append(
            rf"\draw[white,line width=1.6pt] ({t+0.1:.2f},{y:.3f}) -- ({self.w},{y:.3f});")
        self.body.append(
            rf"\draw[{RED},line width=1.1pt] ({t-0.14:.2f},{y-0.14:.3f}) -- ({t+0.14:.2f},{y+0.14:.3f});")
        self.body.append(
            rf"\draw[{RED},line width=1.1pt] ({t-0.14:.2f},{y+0.14:.3f}) -- ({t+0.14:.2f},{y-0.14:.3f});")

    def note(self, x, text, color="palegrey", border=GREY, width=None, y=None):
        x = x * self.sx
        ymin = y if y is not None else min(self.y.values()) - 0.95
        tw = width or (self.w - 0.4)
        self.body.append(
            rf"\node[anchor=north west,draw={border},fill={color},line width=0.5pt,"
            rf"inner sep=3pt,text width={tw}cm,align=left,font=\scriptsize] "
            rf"at ({x:.2f},{ymin:.3f}) {{{text}}};")

    def save(self, name, pad_bottom=0.2):
        lines = [PREAMBLE, r"\begin{tikzpicture}[x=1cm,y=1cm]"]
        if self.title:
            lines.append(
                rf"\node[font=\small\bfseries] at ({self.w/2:.2f},{0.55:.2f}) {{{self.title}}};")
        for n in self.names:
            self.lifeline(n)
            self.label(n)
        lines += self.body
        lines.append(r"\end{tikzpicture}")
        lines.append(r"\end{document}")
        (OUT / (name + ".tex")).write_text("\n".join(lines) + "\n")


# ------------------------------------------------------------------ figures
def fig_1a():
    c = ST(["C1", "C2", "P", "S1", "S2"], width=9.2)
    c.msg(1.0, "C1", "P", "W(x=1)")
    c.msg(2.0, "P", "S1", "update")
    c.msg(2.7, "P", "S2", "update")
    c.box(2.35, "S1", "x=1")
    c.msg(3.3, "S1", "P", "ACK", GREEN)
    c.msg(4.3, "C2", "S1", "R(x)")
    c.msg(4.7, "S1", "C2", "1", GREEN)
    c.msg(5.5, "C2", "S2", "R(x)")
    c.msg(5.9, "S2", "C2", "0", RED)
    c.box(6.6, "S2", "x=0")
    c.msg(7.2, "S2", "P", "ACK", GREEN, dashed=True)
    c.msg(7.9, "P", "C1", "OK")
    c.note(0.1, "R1 returns 1 before R2 returns 0, and R1 ends before R2 starts: "
                "no total order of x explains both reads $\\rightarrow$ linearizability violated",
           "palered", RED)
    c.save("c-1a")


def fig_1b():
    c = ST(["C1", "C2", "P", "S1", "S2"], width=9.2)
    c.msg(1.0, "C1", "P", "W(x=1)")
    c.msg(2.0, "P", "S1", "update")
    c.msg(2.7, "P", "S2", "update")
    c.box(2.35, "S1", "x=1")
    c.msg(3.3, "S1", "P", "ACK", GREEN)
    c.msg(4.3, "C1", "S1", "R(x)")
    c.msg(4.7, "S1", "C1", "1", GREEN)
    c.msg(5.5, "C2", "S2", "R(x)")
    c.msg(5.9, "S2", "C2", "0", RED)
    c.box(6.6, "S2", "x=0")
    c.note(0.1, "C1 reads 1, then C2 reads 0. Each client is monotonic, but there is "
                "no single global order $\\rightarrow$ still not linearizable",
           "palered", RED)
    c.save("c-1b")


def fig_2a():
    c = ST(["C", "P", "S1", "S2"], width=8.6)
    c.msg(1.0, "C", "P", "W(x=1)")
    c.box(1.9, "P", "x=1", "palegreen", GREEN)
    c.msg(2.5, "P", "C", "OK")
    c.crash(3.6, "P")
    c.note(0.1, "P fails before sending any update", "palegrey", GREY, y=-3.5)
    c.msg(5.6, "C", "S1", "R(x)")
    c.msg(6.0, "S1", "C", "0", RED)
    c.box(6.9, "S1", "new primary: x=0")
    c.note(0.1, "an acknowledged write is lost $\\rightarrow$ atomicity and durability violated",
           "palered", RED, y=-4.9)
    c.save("c-2a")


def fig_2b():
    c = ST(["C", "P", "S1", "S2"], width=9.2)
    c.msg(1.0, "C", "P", "W(x=1)")
    c.msg(2.0, "P", "S1", "update")
    c.box(2.2, "S1", "x=1")
    c.lost(2.9, "P", "S2", "update lost")
    c.msg(3.9, "P", "C", "OK")
    c.crash(4.8, "P")
    c.crash(5.1, "S1")
    c.note(0.1, "S2 never received the update; P and S1 crash", "palegrey", GREY, y=-4.3)
    c.msg(7.0, "C", "S2", "R(x)")
    c.msg(7.4, "S2", "C", "0", RED)
    c.box(8.1, "S2", "new primary: x=0")
    c.note(0.1, "atomicity violated: one replica handled the request, "
                "the correct ones never will", "palered", RED, y=-5.7)
    c.save("c-2b")


def fig_combined():
    c = ST(["C", "P", "S1"], width=8.4)
    c.msg(1.0, "C", "P", "W(x=1)")
    c.msg(1.7, "P", "C", "OK")
    c.box(2.0, "P", "x=1 local", "palegreen", GREEN)
    c.msg(3.0, "C", "S1", "R(x)")
    c.msg(3.4, "S1", "C", "0", RED)
    c.msg(4.0, "P", "S1", "update")
    c.box(4.5, "S1", "x=1")
    c.msg(5.3, "C", "S1", "R(x)")
    c.msg(5.7, "S1", "C", "1", GREEN)
    c.note(0.1, "read-your-writes violated (OK, then 0); the value then jumps to 1. "
                "If P had failed before sending, the acknowledged write would be lost",
           "palered", RED)
    c.save("c-combined")


def fig_simple():
    c = ST(["P", "S1", "S2"], width=7.6)
    c.msg(1.2, "P", "S1", "m")
    c.box(2.2, "S1", "deliver(m)", "paleblue", BLUE)
    c.crash(2.7, "P")
    c.box(5.0, "S2", "never delivers", "palered", RED)
    c.note(0.1, "S1 delivered m, S2 never will $\\rightarrow$ agreement violated",
           "palered", RED)
    c.save("s-simple")


def fig_rb():
    c = ST(["P", "S1", "S2"], width=8.6)
    c.msg(1.0, "P", "S1", "m")
    c.msg(1.5, "P", "S2", "m")
    c.box(2.6, "S1", "deliver + re-broadcast")
    c.msg(3.4, "S1", "S2", "m")
    c.box(2.6, "S2", "deliver + re-broadcast")
    c.msg(4.4, "S2", "S1", "m", dashed=True)
    c.box(5.2, "S1", "duplicate dropped", "palegrey", GREY)
    c.box(5.9, "S2", "deliver")
    c.note(0.1, "All correct processes deliver; each message travels $O(n^2)$ times",
           "palegreen", GREEN)
    c.save("s-rb")


def fig_models():
    p = ST(["Client", "Primary", "S1", "S2"], width=6.0)
    p.title = "Passive replication"
    p.msg(0.8, "Client", "Primary", "request")
    p.msg(1.8, "Primary", "S1", "update")
    p.msg(2.5, "Primary", "S2", "update")
    p.msg(3.2, "S1", "Primary", "ACK", GREEN, dashed=True)
    p.msg(3.9, "S2", "Primary", "ACK", GREEN, dashed=True)
    p.msg(4.8, "Primary", "Client", "response")
    p.save("models-passive")

    a = ST(["Client", "S1", "S2", "S3"], width=6.0)
    a.title = "Active replication"
    a.msg(0.8, "Client", "S1", "request")
    a.msg(1.5, "Client", "S2", "request")
    a.msg(2.2, "Client", "S3", "request")
    a.msg(3.1, "S1", "Client", "response", GREEN, dashed=True)
    a.msg(3.8, "S2", "Client", "response (discarded)", GREEN, dashed=True)
    a.msg(4.5, "S3", "Client", "response (discarded)", GREEN, dashed=True)
    a.save("models-active")
    return

    # two panels, drawn in two separate tikzpictures inside one document
    p = ST(["Client", "Primary", "S1", "S2"], width=6.4)
    p.title = None
    p.msg(0.8, "Client", "Primary", "request")
    p.msg(1.8, "Primary", "S1", "update")
    p.msg(2.5, "Primary", "S2", "update")
    p.msg(3.2, "S1", "Primary", "ACK", GREEN, dashed=True)
    p.msg(3.9, "S2", "Primary", "ACK", GREEN, dashed=True)
    p.msg(4.8, "Primary", "Client", "response")

    a = ST(["Client", "S1", "S2", "S3"], width=6.4)
    a.msg(0.8, "Client", "S1", "request")
    a.msg(1.5, "Client", "S2", "request")
    a.msg(2.2, "Client", "S3", "request")
    a.msg(3.1, "S1", "Client", "response", GREEN, dashed=True)
    a.msg(3.8, "S2", "Client", "response (discarded)", GREEN, dashed=True)
    a.msg(4.5, "S3", "Client", "response (discarded)", GREEN, dashed=True)

    # build one document with both panels side by side
    def panel(st, title):
        lines = [r"\begin{tikzpicture}[x=1cm,y=1cm]",
                 rf"\node[font=\small\bfseries] at ({st.w/2:.2f},{0.6:.2f}) {{{title}}};"]
        for n in st.names:
            st.lifeline(n)
            st.label(n)
        lines += st.body
        lines.append(r"\end{tikzpicture}")
        return "\n".join(lines)

    doc = [PREAMBLE,
           panel(p, "Passive replication"),
           r"\hspace{0.8cm}",
           panel(a, "Active replication"),
           r"\end{document}", ""]
    (OUT / "models.tex").write_text("\n".join(doc))


if __name__ == "__main__":
    fig_1a(); fig_1b(); fig_2a(); fig_2b(); fig_combined()
    fig_simple(); fig_rb(); fig_models()
    print("tex written to", OUT)
