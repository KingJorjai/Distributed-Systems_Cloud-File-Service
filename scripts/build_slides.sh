#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../docs/presentation"
pdflatex -interaction=nonstopmode -halt-on-error slides.tex
pdflatex -interaction=nonstopmode -halt-on-error slides.tex
mkdir -p ../../site
cp slides.pdf ../../site/presentation.pdf
rm -f slides.pdf slides.aux slides.log slides.nav slides.out slides.snm slides.toc
echo "Slides written to site/presentation.pdf"
