"""Build a printable PDF from the MkDocs site."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

PAGES = (
    ("Home", "index.html"),
    ("Quick Start", "quick-start/index.html"),
    ("Configuration", "configuration/index.html"),
    ("Docker", "docker/index.html"),
    ("Architecture", "architecture/index.html"),
    ("Protocol", "protocol/index.html"),
    ("Limitations", "limitations/index.html"),
    ("Server API", "api/server/index.html"),
    ("Protocol Helpers API", "api/protocol/index.html"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    parser.add_argument("--output", type=Path, default=Path("site/cloud-file-service.pdf"))
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("docs/pdf-metadata.json"),
    )
    return parser.parse_args()


def find_browser() -> str:
    for command in (
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
    ):
        if shutil.which(command):
            return command
    raise RuntimeError(
        "Chromium is required to build the PDF. Install chromium or set up a "
        "compatible Chrome executable."
    )


def article_from_page(page: Path) -> str:
    source = page.read_text(encoding="utf-8")
    match = re.search(r"<article\b[^>]*>(.*?)</article>", source, re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not find the article content in {page}")
    return match.group(1)


def prepare_article(article: str) -> str:
    """Remove web-only controls and prepare diagrams for the print document."""
    article = re.sub(r"<h1\b[^>]*>.*?</h1>", "", article, count=1, flags=re.DOTALL)
    article = re.sub(
        r"<details\b(?![^>]*\bopen\b)([^>]*)>",
        r"<details open\1>",
        article,
    )
    article = re.sub(
        r"<p>\s*(?:<a[^>]*class=\"[^\"]*md-button[^\"]*\"[^>]*>.*?</a>\s*)+</p>",
        "",
        article,
        flags=re.DOTALL,
    )

    def render_mermaid(match: re.Match[str]) -> str:
        diagram = re.sub(r"<[^>]+>", "", match.group(1))
        return f'<div class="mermaid">{html.unescape(diagram)}</div>'

    return re.sub(
        r"<pre class=\"mermaid\"><code>(.*?)</code></pre>",
        render_mermaid,
        article,
        flags=re.DOTALL,
    )


def render_mermaid_diagrams(article: str, browser: str) -> str:
    """Replace Mermaid source blocks with SVG generated before printing."""
    with tempfile.TemporaryDirectory(prefix="cloud-file-service-mermaid-") as directory:
        directory_path = Path(directory)
        counter = 0

        def render(match: re.Match[str]) -> str:
            nonlocal counter
            counter += 1
            source = directory_path / f"diagram-{counter}.html"
            source.write_text(
                f"""<!doctype html>
<html><head><meta charset="utf-8"></head><body>
<div class="mermaid">{match.group(1)}</div>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
mermaid.initialize({{ startOnLoad: false, securityLevel: "strict", theme: "neutral" }});
window.addEventListener("load", async () => {{
  await mermaid.run({{ nodes: document.querySelectorAll(".mermaid") }});
}});
</script>
</body></html>""",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    browser,
                    "--headless",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--virtual-time-budget=10000",
                    "--dump-dom",
                    source.as_uri(),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            svg = re.search(r"<svg\b.*?</svg>", result.stdout, re.DOTALL)
            if svg is None:
                raise RuntimeError(f"Could not render Mermaid diagram {counter}.")
            return svg.group(0)

        return re.sub(
            r'<div class="mermaid">(.*?)</div>',
            render,
            article,
            flags=re.DOTALL,
        )


def build_document(site_dir: Path, metadata_path: Path, browser: str) -> str:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    review_date = date.today().isoformat()
    sections = []
    toc = []

    for section_number, (label, relative_page) in enumerate(PAGES, start=1):
        page_path = site_dir / relative_page
        page_id = f"section-{section_number}"
        article = render_mermaid_diagrams(
            prepare_article(article_from_page(page_path)),
            browser,
        )
        sections.append(
            f'<section class="pdf-section" id="{page_id}">'
            f"<h1>{html.escape(label)}</h1>{article}</section>"
        )
        toc.append((label, page_id))

    authors = "".join(f"<li>{html.escape(author)}</li>" for author in metadata["authors"])
    toc_html = "".join(
        f'<li><a href="#{section_id}">{html.escape(label)}</a></li>'
        for label, section_id in toc
    )
    stylesheet = next(
        site_dir.glob("assets/stylesheets/main.*.min.css"),
        None,
    )
    if stylesheet is None:
        raise RuntimeError("Could not find the MkDocs Material stylesheet.")
    stylesheet_href = stylesheet.relative_to(site_dir).as_posix()
    extra_styles = """
      @page { size: A4; margin: 18mm 16mm 20mm; }
      @page:first { margin: 0; }
      body { background: white; }
      .pdf-cover {
        min-height: 250mm; display: flex; flex-direction: column;
        justify-content: center; page-break-after: always;
      }
      .pdf-cover h1 { font-size: 2.4rem; margin-bottom: 0.3rem; }
      .pdf-cover h2 { font-weight: 400; }
      .pdf-cover .metadata { margin-top: 2.5rem; }
      .pdf-cover ul { padding-left: 1.2rem; }
      .pdf-toc { page-break-after: always; }
      .pdf-toc h1 { margin-top: 0; }
      .pdf-toc ol { margin: 0; padding-left: 2.5em; }
      .pdf-toc li { padding-left: 0.35em; }
      .pdf-section { page-break-before: always; }
      .pdf-section > h1 { border-bottom: 2px solid #526cfe; }
      .pdf-section:first-of-type { page-break-before: auto; }
      .pdf-section h2 { break-after: avoid; page-break-after: avoid; }
      pre, table, figure, .admonition, .mermaid { break-inside: avoid; }
      .admonition {
        border: 1px solid #9aa4b2; border-left: 4px solid #526cfe;
        border-radius: 3px; margin: 1em 0; padding: 0.7em 1em;
        background: #f7f8fa;
      }
      .admonition-title {
        position: relative; background: transparent; font-weight: 700;
        margin: 0 0 0.4em; padding: 0;
      }
      .admonition-title::before {
        position: static !important; display: inline-block !important;
        width: 1.5em; margin: 0 0.35em 0 0; vertical-align: -0.1em;
      }
      .admonition p:last-child { margin-bottom: 0; }
      .mermaid {
        display: block; width: 100%; margin: 1.5em auto; text-align: center;
        break-inside: avoid; page-break-inside: avoid; overflow: visible;
      }
      .mermaid svg {
        display: block; width: 100% !important; max-width: 100% !important;
        height: auto !important; max-height: none !important; margin: 0 auto;
      }
      details.mkdocstrings-source {
        display: block; margin: 1em 0; break-inside: auto;
        page-break-inside: auto;
      }
      details.mkdocstrings-source > summary {
        display: block; list-style: none !important; cursor: default;
        padding: 0.5em 0.8em; font-weight: 700;
        border: 1px solid #d6d9df; background: #f0f2f5;
      }
      details.mkdocstrings-source > summary::-webkit-details-marker {
        display: none !important;
      }
      details.mkdocstrings-source > summary::marker {
        content: "" !important;
      }
      details.mkdocstrings-source > summary::before {
        content: ""; display: inline-block; width: 0; margin-right: 0;
      }
      details.mkdocstrings-source pre {
        margin-top: 0; border-top: 0; break-inside: auto;
      }
      a { color: #4051b5; }
    """
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>{html.escape(metadata["title"])}</title>
    <link rel="stylesheet" href="{stylesheet_href}">
    <link rel="stylesheet" href="assets/_mkdocstrings.css">
    <style>{extra_styles}</style>
  </head>
  <body class="md-typeset">
    <main class="md-content__inner">
      <section class="pdf-cover">
        <h1>{html.escape(metadata["title"])}</h1>
        <h2>{html.escape(metadata["degree"])}</h2>
        <h2>{html.escape(metadata["course"])}</h2>
        <div class="metadata">
          <p><strong>Authors</strong></p>
          <ul>{authors}</ul>
          <p><strong>Review date:</strong> {review_date}</p>
        </div>
      </section>
      <section class="pdf-toc">
        <h1>Contents</h1>
        <ol>{toc_html}</ol>
      </section>
      {"".join(sections)}
    </main>
  </body>
</html>
"""


def main() -> None:
    args = parse_args()
    if not args.site_dir.is_dir():
        raise SystemExit(
            f"{args.site_dir} does not exist; run 'mkdocs build --strict' first."
        )
    browser = find_browser()
    document = build_document(args.site_dir, args.metadata, browser)
    source = args.site_dir / "pdf.html"
    source.write_text(document, encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            browser,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--virtual-time-budget=10000",
            f"--print-to-pdf={args.output.resolve()}",
            source.resolve().as_uri(),
        ],
        check=True,
    )
    source.unlink()
    print(f"PDF written to {args.output}")


if __name__ == "__main__":
    main()
