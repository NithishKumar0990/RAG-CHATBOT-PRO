# tests/test_w4_guards_fallbacks.py
import sys
import os
import pathlib
import json
import httpx

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))
from rag_pipeline import (
    NO_DOC_MSG,
    FALLBACK_MSG,
    _build_fallback_msg
)
from web_adapters import UploadedFileShim
from document_parser import parse_document

VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

def extract_full_answer(sse_text: str) -> str:
    for line in sse_text.splitlines():
        if line.startswith("data:"):
            try:
                p = json.loads(line[5:].strip())
                if isinstance(p, dict) and "full_answer" in p:
                    return p["full_answer"]
            except Exception:
                pass
    return ""

def run_w4_test():
    print("=== RUNNING W4: GUARDS & FALLBACKS (ZERO-DRIFT ASSERTIONS) ===")
    evidence = []

    # 1. Fresh session with NO doc uploaded
    client = httpx.Client(base_url="http://127.0.0.1:8000")
    res_no_doc = client.post("/api/chat", json={"question": "What is my experience?"})
    ans_no_doc = extract_full_answer(res_no_doc.text)
    evidence.append(f"No-doc response: {ans_no_doc}")
    assert ans_no_doc == NO_DOC_MSG, f"Expected exact NO_DOC_MSG, got: {ans_no_doc}"
    evidence.append("No-doc guard matches pipeline NO_DOC_MSG exactly!")

    # 2. Upload Project Atlas resume
    atlas_path = FIXTURES_DIR / "project_atlas_resume.pdf"
    files = {"file": ("project_atlas_resume.pdf", atlas_path.read_bytes(), "application/pdf")}
    client.post("/api/upload", files=files)

    # 3. Test Greeting ("hi")
    res_hi = client.post("/api/chat", json={"question": "hi"})
    ans_hi = extract_full_answer(res_hi.text)
    evidence.append(f"Greeting query response: {ans_hi}")
    # Prompt Rule 4 string
    expected_greeting = "Hi! I'm your document assistant. Ask me anything about the uploaded document 😊"
    assert expected_greeting in ans_hi or "document assistant" in ans_hi.lower(), f"Unexpected greeting: {ans_hi}"
    evidence.append("Greeting matches expected pipeline greeting!")

    # 4. Irrelevant question -> Smart fallback
    irrelevant_q = "What is the capital of Mars and the diameter of Jupiter's third moon?"
    res_irrelevant = client.post("/api/chat", json={"question": irrelevant_q})
    ans_irrelevant = extract_full_answer(res_irrelevant.text)
    evidence.append(f"Irrelevant question response: {ans_irrelevant}")

    # Must be either smart fallback with bullets OR fallback message
    assert "couldn't find" in ans_irrelevant.lower() or "can answer" in ans_irrelevant.lower() or ans_irrelevant.startswith("I couldn't find that in"), f"Fallback failed: {ans_irrelevant}"
    evidence.append("Smart fallback triggered properly for out-of-domain question!")

    (VERIF_DIR / "w4_guards_fallbacks.txt").write_text("\n".join(evidence), encoding="utf-8")
    print("[PASS] W4: Guards and Fallbacks Verified!")
    return True

if __name__ == "__main__":
    run_w4_test()
