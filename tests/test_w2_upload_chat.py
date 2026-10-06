# tests/test_w2_upload_chat.py
import sys
import os
import pathlib
import json
import httpx

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))
from rag_pipeline import index_uploaded_document, delete_document_by_name
from document_parser import parse_document
from web_adapters import UploadedFileShim

VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

def run_w2_test():
    print("=== RUNNING W2: UPLOAD -> INDEX -> CHAT CITATIONS ===")
    evidence = []

    atlas_path = FIXTURES_DIR / "project_atlas_resume.pdf"
    atlas_bytes = atlas_path.read_bytes()
    atlas_text = parse_document(UploadedFileShim("project_atlas_resume.pdf", atlas_bytes))

    # 1. Compare direct pipeline index chunk count with API response
    direct_chunks = index_uploaded_document(atlas_text, "direct_ref.pdf")
    delete_document_by_name("direct_ref.pdf")
    evidence.append(f"Direct pipeline chunk count: {direct_chunks}")

    client = httpx.Client(base_url="http://127.0.0.1:8000")
    
    # 2. Upload to API
    files = {"file": ("project_atlas_resume.pdf", atlas_bytes, "application/pdf")}
    res_up = client.post("/api/upload", files=files)
    assert res_up.status_code == 200, f"Upload failed: {res_up.status_code} {res_up.text}"
    up_data = res_up.json()
    evidence.append(f"API upload response: {json.dumps(up_data, indent=2)}")
    assert up_data["chunks"] == direct_chunks, f"Expected {direct_chunks} chunks, got {up_data['chunks']}"
    assert len(up_data["indexed_docs"]) == 1
    assert up_data["active_doc"] == "project_atlas_resume.pdf"

    # 3. Same-name re-upload: no duplicate doc, no duplicate chunks
    files_re = {"file": ("project_atlas_resume.pdf", atlas_bytes, "application/pdf")}
    res_re = client.post("/api/upload", files=files_re)
    assert res_re.status_code == 200
    re_data = res_re.json()
    evidence.append(f"Re-upload response: {json.dumps(re_data, indent=2)}")
    assert len(re_data["indexed_docs"]) == 1, f"Expected exactly 1 doc in indexed_docs, got {len(re_data['indexed_docs'])}"
    assert re_data["chunks"] == direct_chunks, f"Chunks changed on re-upload: {re_data['chunks']}"

    # 4. Chat question expecting citations
    chat_res = client.post("/api/chat", json={"question": "What is Project Atlas?"})
    assert chat_res.status_code == 200
    lines = [line.strip() for line in chat_res.text.splitlines() if line.startswith("data:")]
    
    done_payload = None
    for line in lines:
        if line.startswith("data:"):
            try:
                p = json.loads(line[5:].strip())
                if isinstance(p, dict) and "full_answer" in p:
                    done_payload = p
                    break
            except Exception:
                pass

    assert done_payload is not None, f"No done event found in SSE stream: {lines}"
    sources = done_payload.get("sources", [])
    evidence.append(f"Chat answer: {done_payload.get('full_answer')}")
    evidence.append(f"Sources count: {len(sources)}")
    evidence.append(f"Sources detail: {json.dumps(sources, indent=2)}")

    assert len(sources) >= 1, f"Expected at least 1 source, got {len(sources)}"
    assert "Atlas" in done_payload.get("full_answer") or "Project" in done_payload.get("full_answer")

    (VERIF_DIR / "w2_upload_chat.txt").write_text("\n".join(evidence), encoding="utf-8")
    print("[PASS] W2: Upload -> Index -> Chat Citations Verified!")
    return True

if __name__ == "__main__":
    run_w2_test()
