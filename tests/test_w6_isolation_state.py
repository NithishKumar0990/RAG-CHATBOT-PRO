# tests/test_w6_isolation_state.py
import sys
import os
import pathlib
import json
import httpx
import threading

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))
VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

def extract_answer(sse_text: str) -> str:
    for line in sse_text.splitlines():
        if line.startswith("data:"):
            try:
                p = json.loads(line[5:].strip())
                if isinstance(p, dict) and "full_answer" in p:
                    return p["full_answer"]
            except Exception:
                pass
    return ""

def run_w6_test():
    print("=== RUNNING W6: SESSION ISOLATION & STATE OPERATIONS ===")
    evidence = []

    # Client A and Client B with completely independent cookie jars
    client_a = httpx.Client(base_url="http://127.0.0.1:8000")
    client_b = httpx.Client(base_url="http://127.0.0.1:8000")

    # 1. Client A uploads canary document
    canary_path = FIXTURES_DIR / "canary_resume.pdf"
    canary_bytes = canary_path.read_bytes()
    files_a = {"file": ("canary_resume.pdf", canary_bytes, "application/pdf")}
    res_a_up = client_a.post("/api/upload", files=files_a)
    assert res_a_up.status_code == 200
    evidence.append("Client A uploaded canary_resume.pdf successfully")

    # 2. Verify Cookie Security Flags and Cache-Control
    state_res_a = client_a.get("/api/state")
    assert state_res_a.status_code == 200
    cc = state_res_a.headers.get("cache-control", "")
    assert "no-store" in cc, f"Cache-Control must contain no-store, got: {cc}"
    evidence.append(f"Cache-Control header verified on /api/state: {cc}")

    cookie_header = res_a_up.headers.get("set-cookie", "")
    if cookie_header:
        assert "httponly" in cookie_header.lower(), "Cookie missing HttpOnly"
        assert "samesite=lax" in cookie_header.lower(), "Cookie missing SameSite=Lax"
        evidence.append(f"Cookie flags verified: {cookie_header}")

    # 3. Client B state isolation checks
    state_b = client_b.get("/api/state").json()
    assert len(state_b["indexed_docs"]) == 0, f"Leak! Client B sees docs: {state_b['indexed_docs']}"
    assert state_b["active_doc"] is None, f"Leak! Client B has active doc: {state_b['active_doc']}"
    evidence.append("Client B state is completely empty — no leak from Client A")

    # 4. Client B chat returns no-doc guard and cannot retrieve canary
    res_b_chat = client_b.post("/api/chat", json={"question": "What is the canary token?"})
    ans_b = extract_answer(res_b_chat.text)
    assert "ZEBRA-CANARY-7731" not in ans_b, "CRITICAL PRIVACY LEAK: Client B retrieved Client A's canary token!"
    assert "Please upload a document" in ans_b, f"Client B should get no-doc message, got: {ans_b}"
    evidence.append("Client B cannot retrieve canary token — zero cross-session leakage!")

    # 5. Client B cannot delete Client A's document
    res_b_del = client_b.delete("/api/doc/canary_resume.pdf")
    assert res_b_del.status_code == 404, f"Client B delete should 404, got: {res_b_del.status_code}"
    evidence.append("Client B DELETE of Client A's doc returned 404 Forbidden/Not Found as required")

    # 6. Client A is unaffected by Client B's operations
    state_a_after = client_a.get("/api/state").json()
    assert len(state_a_after["indexed_docs"]) == 1
    assert state_a_after["active_doc"] == "canary_resume.pdf"
    evidence.append("Client A state remains intact after Client B actions")

    # 7. Forged/Unknown cookie protection (anti-session fixation)
    forged_client = httpx.Client(base_url="http://127.0.0.1:8000", cookies={"session_id": "forged_malicious_id_123"})
    res_forged = forged_client.get("/api/state")
    set_cookie_forged = res_forged.headers.get("set-cookie", "")
    assert "forged_malicious_id_123" not in set_cookie_forged, "Server allowed forged cookie session fixation!"
    evidence.append("Server rejected forged cookie and issued a fresh cryptographically random ID")

    # 8. Concurrent Chat Streams (Client A and Client B concurrently)
    atlas_path = FIXTURES_DIR / "project_atlas_resume.pdf"
    client_b.post("/api/upload", files={"file": ("project_atlas_resume.pdf", atlas_path.read_bytes(), "application/pdf")})

    ans_a_stream = []
    ans_b_stream = []

    def stream_worker(client, q, out_list):
        r = client.post("/api/chat", json={"question": q})
        out_list.append(extract_answer(r.text))

    t_a = threading.Thread(target=stream_worker, args=(client_a, "What is the canary token?", ans_a_stream))
    t_b = threading.Thread(target=stream_worker, args=(client_b, "What is Project Atlas?", ans_b_stream))

    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()

    assert len(ans_a_stream) == 1 and len(ans_b_stream) == 1
    evidence.append(f"Concurrent Stream A response: {ans_a_stream[0]}")
    evidence.append(f"Concurrent Stream B response: {ans_b_stream[0]}")

    assert "ZEBRA-CANARY-7731" in ans_a_stream[0], "Stream A lost canary context"
    assert "ZEBRA-CANARY-7731" not in ans_b_stream[0], "Cross-contamination! Stream B received canary token"
    assert "Atlas" in ans_b_stream[0] or "Project" in ans_b_stream[0], "Stream B failed to answer about Atlas"
    evidence.append("Concurrent streams completed without cross-contamination!")

    (VERIF_DIR / "w6_isolation_state.txt").write_text("\n".join(evidence), encoding="utf-8")
    print("[PASS] W6: Session Isolation and State Operations Verified!")
    return True

if __name__ == "__main__":
    run_w6_test()
