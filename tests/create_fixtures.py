import os
import sys
import pathlib
import io

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))
from pypdf import PdfReader
from document_parser import parse_document
from web_adapters import UploadedFileShim

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

def make_pdf_bytes(content: str) -> bytes:
    escaped = content.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    stream = f'BT /F1 12 Tf 50 700 Td ({escaped}) Tj ET'
    stream_bytes = stream.encode('latin1')
    stream_len = len(stream_bytes)
    
    pdf = f'''%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length {stream_len} >>
stream
{stream}
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000300 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
370
%%EOF
'''
    return pdf.encode('latin1')

def generate_fixtures():
    # 1. Project Atlas Resume
    atlas_text = (
        "John Doe - Senior Software Engineer. "
        "Led Project Atlas, a data-platform migration that took 8 months to complete successfully. "
        "Skills: Python, Distributed Systems, Vector Search, Cloud Infrastructure, Docker, Kubernetes. "
        "Experience: 2018 - Present leading backend migrations and improving system reliability."
    )
    atlas_pdf = make_pdf_bytes(atlas_text)
    atlas_path = FIXTURES_DIR / "project_atlas_resume.pdf"
    atlas_path.write_bytes(atlas_pdf)
    print(f"Created {atlas_path} ({len(atlas_pdf)} bytes)")

    # 2. Canary Resume
    canary_text = (
        "Alice Smith - Security Architect and Confidential Systems Specialist. "
        "Canary identifier token: ZEBRA-CANARY-7731. "
        "Skills: Cryptography, Identity Access Management, Zero-Trust Architecture, Python, Linux. "
        "Led confidential security audits across multiple enterprise clients from 2019 to Present."
    )
    canary_pdf = make_pdf_bytes(canary_text)
    canary_path = FIXTURES_DIR / "canary_resume.pdf"
    canary_path.write_bytes(canary_pdf)
    print(f"Created {canary_path} ({len(canary_pdf)} bytes)")

    # 3. Scanned / Empty PDF (length < 100 characters)
    empty_pdf = make_pdf_bytes("Scanned Image")
    empty_path = FIXTURES_DIR / "empty_scanned.pdf"
    empty_path.write_bytes(empty_pdf)
    print(f"Created {empty_path} ({len(empty_pdf)} bytes)")

    # 4. Unsupported extension
    unsupported_path = FIXTURES_DIR / "unsupported_doc.xyz"
    unsupported_path.write_text("Unsupported format content", encoding="utf-8")
    print(f"Created {unsupported_path}")

    # Verify parser behaviors
    txt_atlas = parse_document(UploadedFileShim("project_atlas_resume.pdf", atlas_pdf))
    assert "Project Atlas" in txt_atlas and "8 months" in txt_atlas
    
    txt_canary = parse_document(UploadedFileShim("canary_resume.pdf", canary_pdf))
    assert "ZEBRA-CANARY-7731" in txt_canary

    try:
        parse_document(UploadedFileShim("empty_scanned.pdf", empty_pdf))
        assert False, "empty_scanned.pdf should fail with ValueError"
    except ValueError as ve:
        assert "no extractable text" in str(ve)

    try:
        parse_document(UploadedFileShim("unsupported_doc.xyz", b"abc"))
        assert False, "unsupported_doc.xyz should fail with ValueError"
    except ValueError as ve:
        assert "Unsupported file format" in str(ve)

    print("ALL FIXTURES GENERATED AND VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    generate_fixtures()
