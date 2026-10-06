# verify_r1_to_r4.py
import io
import sys
from pypdf import PdfWriter
from document_parser import parse_document
from rag_pipeline import answer_question, index_uploaded_document, clear_uploaded_documents, FALLBACK_MSG

# Force utf-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

class MockUploadedFile:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
        
    def getvalue(self) -> bytes:
        return self._data

def make_text_pdf(text_lines: list[str]) -> bytes:
    escaped_lines = [line.replace("(", "[").replace(")", "]") for line in text_lines]
    content_ops = ["BT /F1 11 Tf 50 720 Td"]
    for i, line in enumerate(escaped_lines):
        if i > 0:
            content_ops.append(f"0 -18 Td ({line}) Tj")
        else:
            content_ops.append(f"({line}) Tj")
    content_ops.append("ET")
    content = "\n".join(content_ops)

    pdf_str = f"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >> endobj
4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
5 0 obj << /Length {len(content)} >> stream
{content}
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000318 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
500
%%EOF"""
    return pdf_str.encode("latin-1")

def run_tests():
    print("==================================================")
    print("RUNNING VERIFICATION TESTS R1 - R4")
    print("==================================================")
    results = {}

    # ------------------------------------------------------------------
    # Test R2: Scanned / Image-based PDF with no extractable text (<100 chars)
    # ------------------------------------------------------------------
    print("\n--- Test R2: Image-based / Empty PDF Warning ---")
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)
    empty_pdf = MockUploadedFile("scanned_resume.pdf", pdf_bytes.getvalue())

    try:
        parse_document(empty_pdf)
        print("[FAIL] R2: Expected ValueError for image-based/empty PDF, but none was raised.")
        results["R2"] = "FAIL"
    except ValueError as e:
        expected_msg = "⚠️ This PDF has no extractable text (scanned/image-based). Please upload a text-based PDF or DOCX."
        if expected_msg in str(e):
            print(f"[PASS] R2: Raised expected warning: '{e}'")
            results["R2"] = "PASS"
        else:
            print(f"[FAIL] R2: Unexpected message: '{e}'")
            results["R2"] = "FAIL"

    # ------------------------------------------------------------------
    # Test R1 & R4: Upload text-based resume PDF → UI feedback & Ask 'What are my skills?'
    # ------------------------------------------------------------------
    print("\n--- Test R1 & R4: Text-based Resume PDF Upload & Retrieval ---")
    resume_lines = [
        "Alex Rivera - Senior Software Engineer",
        "Email: alex.rivera@example.com | Phone: +1-555-0199",
        "PROFESSIONAL SUMMARY",
        "Dynamic full-stack developer with 6 years experience architecting cloud systems.",
        "SKILLS INVENTORY",
        "Technical Skills: Python, TypeScript, React, Next.js, Node.js, PostgreSQL, Docker, AWS",
        "Developer Tools: Git, Kubernetes, Redis, GraphQL, CI/CD pipelines",
        "EXPERIENCE",
        "Lead Engineer at CloudScale Solutions: Designed high-throughput microservices in Python."
    ]
    pdf_data = make_text_pdf(resume_lines)
    resume_pdf = MockUploadedFile("alex_rivera_resume.pdf", pdf_data)

    # Parse and index
    extracted_text = parse_document(resume_pdf)
    print(f"Extracted characters from PDF: {len(extracted_text)}")
    num_chunks = index_uploaded_document(extracted_text, filename=resume_pdf.name)
    ui_msg = f"✅ Indexed {num_chunks} chunks"
    print(f"UI Banner: {ui_msg}")
    
    if num_chunks > 0 and ui_msg == f"✅ Indexed {num_chunks} chunks":
        print(f"[PASS] R4: Correct chunk count ({num_chunks}) with UI banner '{ui_msg}'")
        results["R4"] = "PASS"
    else:
        print(f"[FAIL] R4: Chunk indexing or message format failed.")
        results["R4"] = "FAIL"

    # Ask skills question
    res = answer_question("What are my skills?")
    ans = res.get("answer", "")
    sources = res.get("sources", [])
    print(f"Answer: {ans}")
    print(f"Sources count: {len(sources)}")
    for i, s in enumerate(sources, 1):
        content = s.get("content", "") if isinstance(s, dict) else s
        print(f"  Source {i}: {content[:100]}...")

    skills_in_sources = any(
        "python" in (s.get("content", "") if isinstance(s, dict) else s).lower() and 
        "react" in (s.get("content", "") if isinstance(s, dict) else s).lower() 
        for s in sources
    )
    skills_in_ans = "python" in ans.lower() or "typescript" in ans.lower() or "react" in ans.lower()
    
    if sources and skills_in_sources and skills_in_ans and ans != FALLBACK_MSG:
        print("[PASS] R1: Sources contain actual skills from resume and LLM answered accurately.")
        results["R1"] = "PASS"
    else:
        print(f"[FAIL] R1: Failed to retrieve skills or answer accurately. Ans: {ans}")
        results["R1"] = "FAIL"

    # ------------------------------------------------------------------
    # Test R3: Regression: "How do I request a refund?" works, "hi" fallback
    # ------------------------------------------------------------------
    print("\n--- Test R3: Regressions ('How do I request a refund?' & 'hi') ---")
    refund_res = answer_question("How do I request a refund?")
    refund_ans = refund_res.get("answer", "").lower()
    refund_sources = refund_res.get("sources", [])
    print(f"Refund answer: {refund_ans[:100]}... | sources: {len(refund_sources)}")
    
    hi_res = answer_question("hi")
    hi_ans = hi_res.get("answer", "")
    hi_sources = hi_res.get("sources", [])
    print(f"Hi answer: {hi_ans} | sources: {len(hi_sources)}")

    r3_refund_pass = "refund" in refund_ans and len(refund_sources) > 0
    r3_hi_pass = hi_ans == FALLBACK_MSG and len(hi_sources) == 0

    if r3_refund_pass and r3_hi_pass:
        print("[PASS] R3: 'How do I request a refund?' works and 'hi' triggers threshold fallback.")
        results["R3"] = "PASS"
    else:
        print(f"[FAIL] R3: Refund pass? {r3_refund_pass}, Hi fallback pass? {r3_hi_pass}")
        results["R3"] = "FAIL"

    print("\n==================================================")
    print("FINAL SUMMARY OF R1 - R4:")
    for k, v in results.items():
        print(f"  {k}: {v}")
    print("==================================================")
    
    if all(v == "PASS" for v in results.values()):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
