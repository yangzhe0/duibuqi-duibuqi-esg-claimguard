#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 scripts/paper_data.py
python3 scripts/build_figures.py
python3 scripts/write_contracts.py
python3 scripts/build_gallery.py
latexmk -xelatex -interaction=nonstopmode -halt-on-error MathModel.tex
python3 scripts/verify_final.py
