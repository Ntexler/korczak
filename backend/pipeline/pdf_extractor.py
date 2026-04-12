"""
PDF text and metadata extraction using PyMuPDF (fitz).

Usage:
    from backend.pipeline.pdf_extractor import extract_text_from_pdf, extract_metadata_from_pdf
"""

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None
    print(
        "WARNING: PyMuPDF (fitz) not installed. "
        "Install with: pip install pymupdf"
    )


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF file.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        Extracted text as a single string, or empty string on failure.
    """
    if fitz is None:
        print("ERROR: PyMuPDF not available — cannot extract text.")
        return ""

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            text = page.get_text("text")
            if text:
                pages.append(text)
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        print(f"ERROR extracting text from PDF: {e}")
        return ""


def extract_metadata_from_pdf(pdf_bytes: bytes) -> dict:
    """Extract metadata (title, author, etc.) from a PDF file.

    Args:
        pdf_bytes: Raw PDF file bytes.

    Returns:
        Dict with keys: title, author, subject, keywords, creator, producer.
        Values are strings (empty string if not found).
    """
    default = {
        "title": "",
        "author": "",
        "subject": "",
        "keywords": "",
        "creator": "",
        "producer": "",
    }

    if fitz is None:
        print("ERROR: PyMuPDF not available — cannot extract metadata.")
        return default

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        meta = doc.metadata or {}
        doc.close()
        return {
            "title": (meta.get("title") or "").strip(),
            "author": (meta.get("author") or "").strip(),
            "subject": (meta.get("subject") or "").strip(),
            "keywords": (meta.get("keywords") or "").strip(),
            "creator": (meta.get("creator") or "").strip(),
            "producer": (meta.get("producer") or "").strip(),
        }
    except Exception as e:
        print(f"ERROR extracting metadata from PDF: {e}")
        return default
