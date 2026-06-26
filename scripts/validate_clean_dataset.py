#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path


REQUIRED_FIELDS = [
    "stock_code",
    "company",
    "year",
    "report_type",
    "title",
    "announcement_date",
    "source",
    "source_url",
    "pdf_url",
    "original_title",
    "original_adjunct_url",
    "original_pdf_filename",
    "normalized_filename",
    "local_path",
    "file_sha256",
    "file_size_bytes",
    "error",
]


def main():
    index_path = Path("data/report_index.csv")
    pdf_dir = Path("data/raw_pdfs")
    if not pdf_dir.is_dir():
        raise AssertionError("data/raw_pdfs does not exist")
    if not index_path.is_file():
        raise AssertionError("data/report_index.csv does not exist")

    with index_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        rows = list(reader)

    missing_fields = [field for field in REQUIRED_FIELDS if field not in fields]
    if missing_fields:
        raise AssertionError(f"missing fields: {missing_fields}")

    if len(rows) < 200:
        raise AssertionError(f"expected at least 200 rows, got {len(rows)}")

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if len(pdfs) != len(rows):
        raise AssertionError(f"pdf count {len(pdfs)} != index rows {len(rows)}")

    filename_pattern = re.compile(r"^[A-Za-z0-9]+_.+_20\d{2}_.+\.pdf$")
    seen_paths = set()
    for row in rows:
        local_path = Path(row["local_path"])
        if not local_path.is_file():
            raise AssertionError(f"missing local_path: {local_path}")
        if local_path in seen_paths:
            raise AssertionError(f"duplicate local_path: {local_path}")
        seen_paths.add(local_path)
        with local_path.open("rb") as fh:
            if fh.read(5) != b"%PDF-":
                raise AssertionError(f"not a PDF: {local_path}")
        if not filename_pattern.match(local_path.name):
            raise AssertionError(f"bad filename: {local_path.name}")
        for field in REQUIRED_FIELDS:
            if field != "error" and not row[field]:
                raise AssertionError(f"empty {field}: {local_path}")
        if row["source"] != "cninfo":
            raise AssertionError(f"unexpected source: {row['source']}")
        if row["error"]:
            raise AssertionError(f"main index has error: {row['error']}")

    if set(pdfs) != seen_paths:
        raise AssertionError("PDF directory and index paths differ")

    print(f"clean dataset ok: {len(rows)} PDFs")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
