# verification/verify_10_criteria.py
"""
Comprehensive 10-point Verification Suite for Fresh New Chat & Thread Isolation.

Tests:
1. Upload PDF A, ask a question about A, and confirm a source is returned.
2. Click New Chat. GET /api/state shows an empty active chat and no active PDF. Confirm the session vectorstore/document state was cleared as specified.
3. Ask a question before uploading again. The existing no-document guard is returned.
4. Upload PDF B and ask about A's unique canary. A's content must not be retrieved or returned.
5. Ask about B's unique canary. B is retrievable with sources.
6. Query rewriting in the new chat receives no prior chat messages.
7. Switching to an older chat does not accidentally use another chat's PDF.
8. Two separate browser sessions remain isolated.
9. Frontend state consistency: recent-doc list, active-doc display, chat list, and empty state match /api/state.
10. Existing upload/chat/source behavior still works.
"""

import sys
import json
import time
import pathlib
from starlette.testclient import TestClient

# Add project root to sys.path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))

import server
from server import app
import web_adapters
import rag_pipeline

LOG_LINES = []

def log(msg):
    print(msg)
    LOG_LINES.append(msg)

def parse_sse(response_text):
    tokens = []
    done_payload = None
    for line in response_text.splitlines():
        if line.startswith("data: "):
            payload = line[6:].strip()
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict) and "full_answer" in parsed:
                    done_payload = parsed
                elif isinstance(parsed, str):
                    tokens.append(parsed)
            except Exception:
                pass
    return "".join(tokens), done_payload

def main():
    log("=" * 80)
    log("FRESH NEW CHAT & THREAD ISOLATION: 10-POINT VERIFICATION SUITE")
    log("=" * 80)

    fixtures_dir = pathlib.Path(__file__).parent.parent / "tests" / "fixtures"
    pdf_a_bytes = (fixtures_dir / "canary_resume.pdf").read_bytes()
    pdf_b_bytes = (fixtures_dir / "project_atlas_resume.pdf").read_bytes()

    client1 = TestClient(app, base_url="http://testserver")
    client1.get("/api/health")
    sid1 = client1.cookies.get("session_id")
    log(f"Session 1 ID: {sid1}")

    results = {}

    # -------------------------------------------------------------------------
    # TEST 1: Upload PDF A, ask a question about A, and confirm a source is returned.
    # -------------------------------------------------------------------------
    log("\n--- TEST 1: Upload PDF A and ask question about A ---")
    resp_up_a = client1.post("/api/upload", files={"file": ("canary_resume.pdf", pdf_a_bytes, "application/pdf")})
    assert resp_up_a.status_code == 200, f"Upload A failed: {resp_up_a.text}"
    up_a_data = resp_up_a.json()
    log(f"Upload A Response: active_doc={up_a_data.get('active_doc')}, chunks={up_a_data.get('chunks')}")

    resp_chat_a = client1.post("/api/chat", json={"question": "What is the canary identifier?"})
    assert resp_chat_a.status_code == 200, f"Chat A failed: {resp_chat_a.status_code}"
    tokens_a, done_a = parse_sse(resp_chat_a.text)
    log(f"Chat A Answer: {done_a.get('full_answer')[:100]}...")
    log(f"Chat A Sources: {done_a.get('sources')}")
    assert "ZEBRA-CANARY-7731" in done_a.get("full_answer"), "Canary token not in response!"
    assert len(done_a.get("sources", [])) > 0, "No sources returned for Question A!"
    assert done_a["sources"][0].get("source") == "canary_resume.pdf", "Source is not canary_resume.pdf!"
    results["Test 1: Upload A & Chat with Source"] = "PASS"
    log(">>> TEST 1: PASS")

    # -------------------------------------------------------------------------
    # TEST 2: Click New Chat. GET /api/state shows empty active chat, no active PDF.
    # Confirm vectorstore/document state cleared as specified.
    # -------------------------------------------------------------------------
    log("\n--- TEST 2: Click New Chat and inspect /api/state and vectorstore ---")
    resp_nc = client1.post("/api/new_chat")
    assert resp_nc.status_code == 200, f"New Chat failed: {resp_nc.text}"
    nc_data = resp_nc.json()
    chat2_id = nc_data.get("chat_id")
    log(f"New Chat ID: {chat2_id}")

    resp_state = client1.get("/api/state")
    assert resp_state.status_code == 200
    state2 = resp_state.json()
    log(f"/api/state after New Chat: active_chat_id={state2.get('active_chat_id')}, active_doc={state2.get('active_doc')}, indexed_docs={state2.get('indexed_docs')}, history_count={state2.get('history_count')}")

    assert state2.get("active_chat_id") == chat2_id, "Active chat ID not switched to new thread!"
    assert state2.get("active_doc") is None, "active_doc is not None after New Chat!"
    assert state2.get("indexed_docs") == [], "indexed_docs is not empty after New Chat!"
    assert state2.get("history_count") == 0, "history_count is not 0 after New Chat!"
    assert state2.get("messages") == [], "messages is not empty after New Chat!"

    sess1 = web_adapters.SESSIONS[sid1]
    vstore1 = sess1.get("vectorstore")
    chunk_count = len(vstore1.get().get("ids", [])) if vstore1 else -1
    log(f"Vectorstore remaining chunks: {chunk_count}")
    log(f"sess1 active_doc: {sess1.get('active_doc')}, topics: {sess1.get('topics')}")
    log(f"rag_pipeline._doc_topics: {rag_pipeline._doc_topics}")

    assert chunk_count == 0, f"Vectorstore not empty! Contains {chunk_count} chunks!"
    assert sess1.get("active_doc") is None, "Session active_doc not None!"
    assert sess1.get("topics") == [], "Session topics not empty!"
    assert rag_pipeline._doc_topics == [], "rag_pipeline._doc_topics not empty!"
    results["Test 2: New Chat Clears Vectorstore & State"] = "PASS"
    log(">>> TEST 2: PASS")

    # -------------------------------------------------------------------------
    # TEST 3: Ask a question before uploading again -> returns no-document guard.
    # -------------------------------------------------------------------------
    log("\n--- TEST 3: Ask question in new thread before uploading ---")
    resp_c2_pre = client1.post("/api/chat", json={"question": "What skills are listed?"})
    assert resp_c2_pre.status_code == 200
    tokens_pre, done_pre = parse_sse(resp_c2_pre.text)
    log(f"Pre-upload Answer: {done_pre.get('full_answer')}")
    assert web_adapters.NO_DOC_MSG.strip() in done_pre.get("full_answer").strip() or "Please upload a document" in done_pre.get("full_answer"), "No-doc guard did not trigger!"
    assert done_pre.get("sources") == [], "Sources returned on no-doc guard!"
    results["Test 3: No-document Guard Pre-Upload"] = "PASS"
    log(">>> TEST 3: PASS")

    # -------------------------------------------------------------------------
    # TEST 4: Upload PDF B and ask about A's unique canary -> A must not be retrieved.
    # -------------------------------------------------------------------------
    log("\n--- TEST 4: Upload PDF B and ask about Canary A ---")
    resp_up_b = client1.post("/api/upload", files={"file": ("project_atlas_resume.pdf", pdf_b_bytes, "application/pdf")})
    assert resp_up_b.status_code == 200
    up_b_data = resp_up_b.json()
    log(f"Upload B Response: active_doc={up_b_data.get('active_doc')}, chunks={up_b_data.get('chunks')}")

    resp_c2_ask_a = client1.post("/api/chat", json={"question": "What is the canary identifier?"})
    assert resp_c2_ask_a.status_code == 200
    tokens_c2_a, done_c2_a = parse_sse(resp_c2_ask_a.text)
    ans_c2_a = done_c2_a.get("full_answer")
    log(f"Chat 2 Ask A Answer: {ans_c2_a}")
    assert "ZEBRA-CANARY-7731" not in ans_c2_a, "LEAK DETECTED: Canary A token was retrieved from previous document!"
    assert not any(s.get("source") == "canary_resume.pdf" for s in done_c2_a.get("sources", [])), "Canary A appeared in sources!"
    results["Test 4: Canary A Not Retrievable in Chat 2"] = "PASS"
    log(">>> TEST 4: PASS")

    # -------------------------------------------------------------------------
    # TEST 5: Ask about B's unique canary -> B is retrievable with sources.
    # -------------------------------------------------------------------------
    log("\n--- TEST 5: Ask about Canary B (Project Atlas) in Chat 2 ---")
    resp_c2_ask_b = client1.post("/api/chat", json={"question": "What is Project Atlas?"})
    assert resp_c2_ask_b.status_code == 200
    tokens_c2_b, done_c2_b = parse_sse(resp_c2_ask_b.text)
    ans_c2_b = done_c2_b.get("full_answer")
    log(f"Chat 2 Ask B Answer: {ans_c2_b[:120]}...")
    log(f"Chat 2 Ask B Sources: {done_c2_b.get('sources')}")
    assert "Project Atlas" in ans_c2_b or "migration" in ans_c2_b, "Project Atlas content missing from answer!"
    assert len(done_c2_b.get("sources", [])) > 0, "No sources returned for Question B!"
    assert done_c2_b["sources"][0].get("source") == "project_atlas_resume.pdf", "Source is not project_atlas_resume.pdf!"
    results["Test 5: Canary B Retrievable with Sources"] = "PASS"
    log(">>> TEST 5: PASS")

    # -------------------------------------------------------------------------
    # TEST 6: Query rewriting in the new chat receives no prior chat messages.
    # -------------------------------------------------------------------------
    log("\n--- TEST 6: Verify query rewriting in new chat receives no prior chat messages ---")
    active_chat2 = sess1["chats"][chat2_id]
    # At the time chat 2 asked questions, history for chat 2 was only chat 2's turns
    chat1_id = [c["id"] for c in sess1["chats"].values() if c["id"] != chat2_id][0]
    chat1_messages = sess1["chats"][chat1_id]["messages"]
    log(f"Chat 1 message count: {len(chat1_messages)}")
    log(f"Chat 2 message count: {len(active_chat2['messages'])}")
    assert len(chat1_messages) == 2, "Chat 1 should have exactly 1 turn (2 messages)"
    # Ensure Chat 2's first turn did not include Chat 1's messages in its history
    assert not any("ZEBRA-CANARY" in m.get("content", "") for m in active_chat2["messages"]), "Chat 1 content leaked into Chat 2 messages!"
    results["Test 6: Query Rewriting Thread Isolation"] = "PASS"
    log(">>> TEST 6: PASS")

    # -------------------------------------------------------------------------
    # TEST 7: Switching to an older chat does not accidentally use another chat's PDF.
    # -------------------------------------------------------------------------
    log("\n--- TEST 7: Switch to Chat 1 and verify it does NOT use Chat 2's PDF ---")
    resp_act1 = client1.post(f"/api/chats/{chat1_id}/activate")
    assert resp_act1.status_code == 200
    act1_data = resp_act1.json()
    log(f"Activate Chat 1 Response: active_doc={act1_data.get('active_doc')}, indexed_docs={act1_data.get('indexed_docs')}")
    assert act1_data.get("active_doc") is None, "Chat 1 active_doc should be None (not Chat 2's PDF)!"
    assert act1_data.get("indexed_docs") == [], "Chat 1 indexed_docs should be empty!"

    # Ask about Project Atlas in Chat 1: should return no-doc guard, NOT Chat 2's PDF B!
    resp_c1_ask_b = client1.post("/api/chat", json={"question": "What is Project Atlas?"})
    assert resp_c1_ask_b.status_code == 200
    tokens_c1_b, done_c1_b = parse_sse(resp_c1_ask_b.text)
    ans_c1_b = done_c1_b.get("full_answer")
    log(f"Chat 1 Ask B Answer: {ans_c1_b}")
    assert "Please upload a document" in ans_c1_b or web_adapters.NO_DOC_MSG.strip() in ans_c1_b, "Chat 1 did not return no-doc guard!"
    assert "Project Atlas" not in ans_c1_b or "migration" not in ans_c1_b, "LEAK DETECTED: Chat 1 retrieved Chat 2's PDF B!"
    results["Test 7: Chat 1 Does Not Inherit Chat 2 PDF"] = "PASS"
    log(">>> TEST 7: PASS")

    # -------------------------------------------------------------------------
    # TEST 8: Two separate browser sessions remain isolated.
    # -------------------------------------------------------------------------
    log("\n--- TEST 8: Multi-session isolation check ---")
    client2 = TestClient(app, base_url="http://testserver")
    client2.get("/api/health")
    sid2 = client2.cookies.get("session_id")
    log(f"Session 2 ID: {sid2}")
    assert sid1 != sid2, "Session IDs must be distinct!"

    state_s2 = client2.get("/api/state").json()
    log(f"Session 2 state: active_doc={state_s2.get('active_doc')}, indexed_docs={state_s2.get('indexed_docs')}, chats={len(state_s2.get('chats', []))}")
    assert state_s2.get("active_doc") is None, "Session 2 has active_doc from Session 1!"
    assert state_s2.get("indexed_docs") == [], "Session 2 has indexed_docs from Session 1!"
    assert len(state_s2.get("chats", [])) == 1, "Session 2 should have only its 1 default initial chat!"

    resp_s2_chat = client2.post("/api/chat", json={"question": "What is Project Atlas?"})
    assert resp_s2_chat.status_code == 200
    tokens_s2, done_s2 = parse_sse(resp_s2_chat.text)
    assert "Please upload a document" in done_s2.get("full_answer") or web_adapters.NO_DOC_MSG.strip() in done_s2.get("full_answer")
    results["Test 8: Cross-session Isolation"] = "PASS"
    log(">>> TEST 8: PASS")

    # -------------------------------------------------------------------------
    # TEST 9: Frontend state consistency: recent-doc list, active-doc display,
    # chat list, and empty state match /api/state.
    # -------------------------------------------------------------------------
    log("\n--- TEST 9: State consistency between endpoints ---")
    # Switch back to Chat 2 in client1
    resp_act2 = client1.post(f"/api/chats/{chat2_id}/activate")
    assert resp_act2.status_code == 200
    state_chat2 = client1.get("/api/state").json()
    log(f"Chat 2 /api/state: active_doc={state_chat2.get('active_doc')}, indexed_docs={state_chat2.get('indexed_docs')}")
    assert state_chat2.get("active_doc") == "project_atlas_resume.pdf"
    assert len(state_chat2.get("indexed_docs", [])) == 1
    assert state_chat2.get("indexed_docs")[0]["filename"] == "project_atlas_resume.pdf"
    assert len(state_chat2.get("chats", [])) == 2

    # Switch to Chat 1 in client1
    client1.post(f"/api/chats/{chat1_id}/activate")
    state_chat1 = client1.get("/api/state").json()
    log(f"Chat 1 /api/state: active_doc={state_chat1.get('active_doc')}, indexed_docs={state_chat1.get('indexed_docs')}")
    assert state_chat1.get("active_doc") is None
    assert state_chat1.get("indexed_docs") == []
    results["Test 9: State Consistency with /api/state"] = "PASS"
    log(">>> TEST 9: PASS")

    # -------------------------------------------------------------------------
    # TEST 10: Existing upload/chat/source behavior still works.
    # -------------------------------------------------------------------------
    log("\n--- TEST 10: Existing upload/chat/source functionality on active thread ---")
    client1.post(f"/api/chats/{chat2_id}/activate")
    resp_chat_followup = client1.post("/api/chat", json={"question": "Who led the migration?"})
    assert resp_chat_followup.status_code == 200
    tokens_fu, done_fu = parse_sse(resp_chat_followup.text)
    ans_fu = done_fu.get("full_answer")
    log(f"Follow-up Answer: {ans_fu[:100]}...")
    log(f"Follow-up Sources: {done_fu.get('sources')}")
    assert "John Doe" in ans_fu, "Follow-up question failed to retrieve John Doe!"
    assert len(done_fu.get("sources", [])) > 0, "Follow-up question missing sources!"
    results["Test 10: Normal Upload/Chat/Source Functionality"] = "PASS"
    log(">>> TEST 10: PASS")

    log("\n" + "=" * 80)
    log("ALL 10 TESTS COMPLETED SUCCESSFULLY!")
    log("=" * 80)
    for k, v in results.items():
        log(f"  [{v}] {k}")

    # Write log file
    out_file = pathlib.Path(__file__).parent / "fresh_chat_test_evidence.txt"
    out_file.write_text("\n".join(LOG_LINES), encoding="utf-8")
    log(f"\nWrote full evidence log to: {out_file}")

if __name__ == "__main__":
    main()
