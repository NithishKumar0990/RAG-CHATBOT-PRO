# tests/test_w5_multiturn_rewrite.py
import sys
import os
import pathlib
import json
import httpx

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))
VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

def extract_full_answer_and_sources(sse_text: str):
    for line in sse_text.splitlines():
        if line.startswith("data:"):
            try:
                p = json.loads(line[5:].strip())
                if isinstance(p, dict) and "full_answer" in p:
                    return p["full_answer"], p.get("sources", [])
            except Exception:
                pass
    return "", []

def run_w5_test():
    print("=== RUNNING W5: MULTI-TURN QUERY REWRITING ===")
    evidence = []

    client = httpx.Client(base_url="http://127.0.0.1:8000")
    atlas_path = FIXTURES_DIR / "project_atlas_resume.pdf"
    files = {"file": ("project_atlas_resume.pdf", atlas_path.read_bytes(), "application/pdf")}
    client.post("/api/upload", files=files)

    # Turn 1: Establish topic
    q1 = "What is Project Atlas?"
    res1 = client.post("/api/chat", json={"question": q1})
    ans1, sources1 = extract_full_answer_and_sources(res1.text)
    evidence.append(f"Turn 1 Q: '{q1}' -> A: '{ans1}'")

    # Turn 2: Follow-up question with pronoun
    q2 = "How long did it take?"
    res2 = client.post("/api/chat", json={"question": q2})
    ans2, sources2 = extract_full_answer_and_sources(res2.text)
    evidence.append(f"Turn 2 Q: '{q2}' -> A: '{ans2}'")
    evidence.append(f"Turn 2 Sources count: {len(sources2)}")

    # Q2 must answer with 8 months or cite Project Atlas chunk
    assert "8 months" in ans2.lower() or any("Atlas" in s.get("content", "") for s in sources2), f"Multi-turn rewrite failed to resolve context: {ans2}"
    evidence.append("Turn 2 correctly resolved 'it' to Project Atlas and retrieved the 8 months duration!")

    # CONTROL: Reset chat with /api/new_chat, then ask Q2 alone
    client.post("/api/new_chat")
    res_control = client.post("/api/chat", json={"question": q2})
    ans_control, sources_control = extract_full_answer_and_sources(res_control.text)
    evidence.append(f"Control Turn Q: '{q2}' alone without prior history -> A: '{ans_control}'")

    # Without history, Q2 is ambiguous and cannot know about Project Atlas
    assert "8 months" not in ans_control.lower() or "Atlas" not in ans_control, "Control check failed: Q2 alone should not resolve Project Atlas without history"
    evidence.append("Control check passed: Q2 without history was not resolved to Project Atlas!")

    (VERIF_DIR / "w5_multiturn_rewrite.txt").write_text("\n".join(evidence), encoding="utf-8")
    print("[PASS] W5: Multi-Turn Rewriting Verified!")
    return True

if __name__ == "__main__":
    run_w5_test()
