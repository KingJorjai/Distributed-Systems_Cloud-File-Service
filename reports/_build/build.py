#!/usr/bin/env python3
"""Build the DS reports as ODT matching the ABGR template."""
import re
import shutil
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Twips

REPORTS = Path("/home/jorjai/Documents/DS/Distributed-Systems_Cloud-File-Service/reports")
BUILD = REPORTS / "_build"
BUILD.mkdir(exist_ok=True)
TMP = Path("/tmp/dsbuild")
TMP.mkdir(exist_ok=True)

BLUE = RGBColor(0x0F, 0x47, 0x61)
FONT = "Aptos"
DISPLAY = "Aptos Display"

REPORTS_LIST = ["3.1b", "3.1c", "3.2a"]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def drop_border(style):
    pPr = style.element.find(qn("w:pPr"))
    if pPr is None:
        return
    for tag in ("w:pBdr", "w:shd"):
        el = pPr.find(qn(tag))
        if el is not None:
            pPr.remove(el)


def set_font(style, name, size=None, color=None, bold=None):
    style.font.name = name
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rFonts.set(qn(attr), name)
    if size is not None:
        style.font.size = Pt(size)
    if color is not None:
        style.font.color.rgb = color
    if bold is not None:
        style.font.bold = bold


def make_reference():
    base = TMP / "pandoc-reference.docx"
    base.write_bytes(subprocess.run(
        ["pandoc", "--print-default-data-file", "reference.docx"],
        check=True, capture_output=True).stdout)

    doc = Document(str(base))
    sec = doc.sections[0]
    sec.page_width = Twips(11906)   # A4
    sec.page_height = Twips(16838)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Twips(1440))

    styles = doc.styles
    normal = styles["Normal"]
    set_font(normal, FONT, 11, RGBColor(0, 0, 0))
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    normal.paragraph_format.space_before = Pt(0)

    title = styles["Title"]
    set_font(title, DISPLAY, 28, RGBColor(0, 0, 0), bold=False)
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(6)
    title.paragraph_format.line_spacing = 1.0
    title.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    drop_border(title)

    author = styles["Author"]
    set_font(author, FONT, 11, RGBColor(0, 0, 0))
    author.paragraph_format.space_before = Pt(0)
    author.paragraph_format.space_after = Pt(6)
    author.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    h1 = styles["Heading 1"]
    set_font(h1, DISPLAY, 20, BLUE, bold=False)
    h1.paragraph_format.space_before = Pt(18)
    h1.paragraph_format.space_after = Pt(8)
    h1.paragraph_format.line_spacing = 1.0
    h1.paragraph_format.keep_with_next = True
    h1.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    drop_border(h1)

    for name in ("Body Text", "First Paragraph"):
        try:
            st = styles[name]
        except KeyError:
            continue
        st.font.name = FONT
        st.font.size = Pt(11)
        st.paragraph_format.line_spacing = 1.15
        st.paragraph_format.space_after = Pt(8)
        st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

    try:
        cap = styles["Image Caption"]
        cap.font.name = FONT
        cap.font.size = Pt(9)
        cap.font.italic = True
        cap.paragraph_format.space_after = Pt(12)
    except KeyError:
        pass

    out = TMP / "abgr-reference.docx"
    doc.save(str(out))
    return out


def insert_paragraph_after(paragraph, style=None):
    new_p = OxmlElement("w:p")
    paragraph._p.addnext(new_p)
    from docx.text.paragraph import Paragraph
    p = Paragraph(new_p, paragraph._parent)
    if style is not None:
        p.style = style
    return p


def add_page_footer(doc):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    sec = doc.sections[0]
    sec.different_first_page_header_footer = True
    para = sec.footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = para.add_run()
    run.font.size = Pt(10)
    run.font.name = FONT
    f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = " PAGE "
    f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t"); t.text = "1"
    f3 = OxmlElement("w:fldChar"); f3.set(qn("w:fldCharType"), "end")
    for el in (f1, it, f2, t, f3):
        run._r.append(el)
    sectPr = sec._sectPr
    pg = sectPr.find(qn("w:pgNumType"))
    if pg is None:
        pg = OxmlElement("w:pgNumType")
        sectPr.append(pg)
    pg.set(qn("w:start"), "0")


def add_index(docx_path, headings, page_numbers):
    doc = Document(str(docx_path))
    author = None
    for p in doc.paragraphs:
        if p.style is not None and p.style.name == "Author":
            author = p
            break
    if author is None:
        raise SystemExit("author paragraph not found in " + str(docx_path))

    anchor = author
    title = insert_paragraph_after(anchor)
    title.style = doc.styles["Heading 1"]
    title.add_run("Index")
    anchor = title

    for h in headings:
        p = insert_paragraph_after(anchor)
        pf = p.paragraph_format
        pf.line_spacing = 1.15
        pf.space_after = Pt(12)
        pf.space_before = Pt(0)
        pf.tab_stops.add_tab_stop(Twips(9071), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        p.add_run(h)
        p.add_run("\t")
        p.add_run(str(page_numbers.get(h, 0)))
        anchor = p

    brk = insert_paragraph_after(anchor)
    brk.paragraph_format.space_after = Pt(0)
    brk.add_run().add_break()
    # turn the break into a page break
    for run in brk.runs:
        for br in run._element.findall(qn("w:br")):
            br.set(qn("w:type"), "page")

    # bold run-in labels act as subheadings: keep them with the following text
    for para in doc.paragraphs:
        text = para.text.strip()
        runs = [r for r in para.runs if r.text.strip()]
        if 0 < len(text) < 90 and runs and all(r.bold for r in runs):
            para.paragraph_format.keep_with_next = True
            para.paragraph_format.space_before = Pt(10)
            para.paragraph_format.space_after = Pt(4)

    # compact table typography so summary tables fit on one page
    from docx.shared import Pt as _Pt
    for table in doc.tables:
        for ridx, row in enumerate(table.rows):
            for cell in row.cells:
                for para in cell.paragraphs:
                    para.paragraph_format.space_before = _Pt(1)
                    para.paragraph_format.space_after = _Pt(1)
                    para.paragraph_format.line_spacing = 1.0
                    for run in para.runs:
                        run.font.size = _Pt(9.5)
                        if ridx == 0:
                            run.font.bold = True

    for para in doc.paragraphs:
        if para.text.strip() == "Comparison" and para.style.name.lower().startswith("heading"):
            para.paragraph_format.page_break_before = True

    add_page_footer(doc)

    doc.save(str(docx_path))


def headings_of(md_path):
    out = []
    for line in md_path.read_text().splitlines():
        if line.startswith("## "):
            out.append(line[3:].strip())
    return out


def docx_to_pdf(docx_path, outdir):
    run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(docx_path)])
    return Path(outdir) / (docx_path.stem + ".pdf")


def page_of_headings(pdf_path, headings):
    txt = run(["pdftotext", "-layout", str(pdf_path), "-"]).stdout
    pages = txt.split("\f")
    found = {}
    for h in headings:
        needle = h[:30].strip()
        for i, page in enumerate(pages[1:], start=2):  # skip the index page
            if needle in page:
                found[h] = i - 1  # title page counts as 0
                break
    return found


def main():
    ref = make_reference()
    for act in REPORTS_LIST:
        folder = REPORTS / f"A{act}"
        md = folder / f"DS report {act}.md"
        work_docx = TMP / f"DS report {act}.docx"
        run(["pandoc", md.name, "-o", str(work_docx), "--from", "markdown+smart",
             f"--reference-doc={ref}"], cwd=str(folder))
        heads = headings_of(md)

        numbers = {h: 0 for h in heads}
        for iteration in range(3):
            # rebuild from pandoc output, then insert the index
            run(["pandoc", md.name, "-o", str(work_docx), "--from", "markdown+smart",
                 f"--reference-doc={ref}"], cwd=str(folder))
            add_index(work_docx, heads, numbers)
            pdf = docx_to_pdf(work_docx, TMP)
            got = page_of_headings(pdf, heads)
            if all(got.get(h, 0) == numbers.get(h, 0) for h in heads):
                break
            numbers = {h: got.get(h, numbers.get(h, 0)) for h in heads}

        # final render and ODT conversion
        final_docx = TMP / f"DS report {act}.docx"
        run(["pandoc", md.name, "-o", str(final_docx), "--from", "markdown+smart",
             f"--reference-doc={ref}"], cwd=str(folder))
        add_index(final_docx, heads, numbers)
        run(["soffice", "--headless", "--convert-to", "odt", "--outdir", str(folder),
             str(final_docx)])
        odt = folder / f"DS report {act}.odt"
        odt.replace(folder / f"DS_2026_27_ABGR_A{act}.odt")
        pdf = docx_to_pdf(final_docx, TMP)
        shutil.copy(pdf, BUILD / f"DS report {act}.pdf")
        print(f"{act}: {numbers}")

    print("done")


if __name__ == "__main__":
    main()
