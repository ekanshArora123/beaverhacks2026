"""Convert PDF files to Markdown using pymupdf4llm.

Examples:
    python backend/ApiScripts/pdf_to_md.py --input machine_docs/manual.pdf
    python backend/ApiScripts/pdf_to_md.py --input machine_docs --recursive
    python backend/ApiScripts/pdf_to_md.py --input in.pdf --output out.md --pages 1-5
"""

from __future__ import annotations

import argparse
from pathlib import Path


def _parse_pages(pages: str | None) -> list[int] | None:
    """Parse page selection string into 0-based page indices."""
    if not pages:
        return None

    selected: set[int] = set()
    for segment in pages.split(","):
        part = segment.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", maxsplit=1)
            start = int(start_str.strip())
            end = int(end_str.strip())
            if start <= 0 or end <= 0:
                raise ValueError("Page numbers must be >= 1.")
            if end < start:
                raise ValueError(f"Invalid page range: {part}")
            for page in range(start, end + 1):
                selected.add(page - 1)
        else:
            page = int(part)
            if page <= 0:
                raise ValueError("Page numbers must be >= 1.")
            selected.add(page - 1)

    return sorted(selected)


def _pdf_candidates(input_path: Path, recursive: bool) -> list[Path]:
    """Collect PDF files from an input path."""
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Input file must be a PDF: {input_path}")
        return [input_path]

    if not input_path.is_dir():
        raise ValueError(f"Input path not found: {input_path}")

    if recursive:
        return sorted(input_path.rglob("*.pdf"))
    return sorted(input_path.glob("*.pdf"))


def _write_markdown(
    pdf_path: Path,
    output_path: Path | None,
    pages: list[int] | None,
) -> Path:
    """Convert one PDF into Markdown and write it to disk."""
    import pymupdf4llm

    md_text = pymupdf4llm.to_markdown(str(pdf_path), pages=pages)

    if output_path is None:
        destination = pdf_path.with_suffix(".md")
    else:
        destination = output_path

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(md_text, encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert PDFs to Markdown using pymupdf4llm."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input PDF file or directory containing PDFs.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Output Markdown path for single-file conversion. "
            "For directory input, outputs are written beside each PDF."
        ),
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="When input is a directory, include PDFs from subdirectories.",
    )
    parser.add_argument(
        "--pages",
        help="Optional page selection, e.g. '1-5' or '1,3,8-12'.",
    )

    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    pages = _parse_pages(args.pages)

    try:
        pdfs = _pdf_candidates(input_path, recursive=args.recursive)
        if not pdfs:
            raise ValueError(f"No PDF files found in: {input_path}")

        if input_path.is_dir() and output_path is not None:
            raise ValueError("--output is only supported when --input is a single PDF file.")

        for pdf in pdfs:
            destination = _write_markdown(pdf, output_path, pages)
            print(f"Converted: {pdf} -> {destination}")

        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
