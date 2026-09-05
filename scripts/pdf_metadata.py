"""Update document identity without discarding the PDF catalog or original file."""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile


def set_pdf_metadata(pdf_path: Path, author: str | None = None) -> None:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return
    if not pdf_path.exists():
        return
    reader = PdfReader(str(pdf_path))
    existing = dict(reader.metadata or {})
    metadata = dict(existing)
    author_value = str(existing.get("/Author", ""))
    if author and "{{" in author_value and "}}" in author_value:
        metadata["/Author"] = author
    metadata.update({"/Producer": "Folio", "/Creator": "Folio"})
    if metadata == existing:
        return
    writer = PdfWriter(clone_from=reader)
    writer.add_metadata(metadata)
    temporary = None
    try:
        with NamedTemporaryFile(suffix=".pdf", dir=pdf_path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            writer.write(handle)
        temporary.replace(pdf_path)
    finally:
        writer.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
