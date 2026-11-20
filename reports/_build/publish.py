#!/usr/bin/env python3
"""Export the final PDFs with the same naming as the delivered reports."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = [("A3.1b", "3.1b"), ("A3.1c", "3.1c"), ("A3.2a", "3.2a")]

for folder, act in REPORTS:
    src = ROOT / folder / f"DS_2026_27_ABGR_A{act}.odt"
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", str(ROOT / folder), str(src)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    target = ROOT / folder / f"DS_2026_27_ABGR_A{act}.pdf"
    print(target.relative_to(ROOT), target.stat().st_size)
