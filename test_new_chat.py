# test_new_chat.py
"""
Integration test suite for New Chat stabilization (AC-1 to AC-7).
Verifies real session cookie flow, vectorstore chunk deletion verification,
SSE no-doc guard, state endpoint, re-upload, session isolation, and doc deletion history preservation.
"""

import json
import pathlib
import pytest
from starlette.testclient import TestClient

from server import app
from web_adapters import SESSIONS
from rag_pipeline import NO_DOC_MSG

FIXTURES_DIR = pathlib.Path(__file__).parent / "tests" / "fixtures"
PDF_PATH = FIXTURES_DIR / "project_atlas_resume.pdf"


def _extract_sse_answer(resp) -> str:
    """Parse SSE event stream from /api/chat response and return full answer."""
    tokens = []
    done_answer = None
    for line in resp.text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            data_str = line.split(":", 1)[1].strip()
            try:
                payload = json.loads(data_str)
                if isinstance(payload, str):
                    tokens.append(payload)
                elif isinstance(payload, dict) and "full_answer" in payload:
                    done_answer = payload["full_answer"]
            except Exception:
                pass
    return done_answer if done_answer is not None else "".join(tokens)


def test_new_chat_ac1_to_ac7():
    print("\n" + "=" * 75)
    print("      INTEGRATION TESTS: NEW CHAT STABILIZATION (AC-1 to AC-7)")
    print("=" * 75)

    assert PDF_PATH.exists(), f"Missing fixture: {PDF_PATH}"
    pdf_bytes = PDF_PATH.read_bytes()

    client1 = TestClient(app, base_url="http://testserver")

    # Establish session
    resp_init = client1.get("/api/health")
    assert resp_init.status_code == 200
    sid1 = client1.cookies.get("session_id")
    assert sid1 and sid1 in SESSIONS, f"Session {sid1} not found in SESSIONS"

    # Step 1: Upload PDF to Client 1
    files = {"file": ("project_atlas_resume.pdf", pdf_bytes, "application/pdf")}
    resp_up = client1.post("/api/upload", files=files)
    assert resp_up.status_code == 200, f"Upload failed: {resp_up.text}"
    vstore1 = SESSIONS[sid1]["vectorstore"]
    count_before = vstore1._collection.count()
    print(f"\n[SETUP] Client 1 uploaded project_atlas_resume.pdf -> {count_before} chunks indexed.")
    assert count_before > 0, "Expected vectorstore chunk count > 0 after upload"

    # Also send a chat message to build history for later tests
    resp_chat0 = client1.post("/api/chat", json={"question": "What is the candidate experience?"})
    assert resp_chat0.status_code == 200
    ans0 = _extract_sse_answer(resp_chat0)
    assert NO_DOC_MSG not in ans0, f"Chat unexpectedly returned NO_DOC_MSG on uploaded doc: {ans0}"
    chat_hist_before = list(SESSIONS[sid1]["chats"][SESSIONS[sid1]["active_chat_id"]]["messages"])
    assert len(chat_hist_before) >= 2, "Expected user + assistant messages in chat history"

    # ------------------------------------------------------------------
    # AC-5 (Part 1): Record cookie before new_chat
    # ------------------------------------------------------------------
    cookie_before = client1.cookies.get("session_id")

    # ------------------------------------------------------------------
    # Trigger POST /api/new_chat
    # ------------------------------------------------------------------
    resp_nc = client1.post("/api/new_chat")
    assert resp_nc.status_code == 200, f"new_chat failed: {resp_nc.text}"
    nc_data = resp_nc.json()
    assert nc_data.get("ok") is True

    # ------------------------------------------------------------------
    # AC-1: After new_chat, vstore._collection.count() == 0 (Direct inspection)
    # ------------------------------------------------------------------
    vstore1_after = SESSIONS[sid1]["vectorstore"]
    count_after_nc = vstore1_after._collection.count()
    print(f"[AC-1] SESSIONS['{sid1[:8]}']['vectorstore']._collection.count() == {count_after_nc} (was {count_before})")
    assert count_after_nc == 0, f"AC-1 FAIL: Vectorstore still contains {count_after_nc} chunks after new_chat!"
    print("  --> PASS: AC-1 verified (direct SESSIONS vectorstore count == 0)")

    # ------------------------------------------------------------------
    # AC-2: After new_chat, next chat question returns NO_DOC_MSG
    # ------------------------------------------------------------------
    resp_chat1 = client1.post("/api/chat", json={"question": "What was the previous document about?"})
    assert resp_chat1.status_code == 200
    ans1 = _extract_sse_answer(resp_chat1)
    print(f"[AC-2] Chat response after new_chat: {ans1!r}")
    assert NO_DOC_MSG in ans1, f"AC-2 FAIL: Expected NO_DOC_MSG, got: {ans1}"
    print("  --> PASS: AC-2 verified (chat returns NO_DOC_MSG)")

    # ------------------------------------------------------------------
    # AC-3: After new_chat, /api/state returns indexed_docs: [], active_doc: null
    # ------------------------------------------------------------------
    resp_state = client1.get("/api/state")
    assert resp_state.status_code == 200
    state_data = resp_state.json()
    print(f"[AC-3] /api/state: indexed_docs={state_data.get('indexed_docs')}, active_doc={state_data.get('active_doc')}")
    assert state_data.get("indexed_docs") == [], f"AC-3 FAIL: indexed_docs not empty: {state_data.get('indexed_docs')}"
    assert state_data.get("active_doc") is None, f"AC-3 FAIL: active_doc is not null: {state_data.get('active_doc')}"
    print("  --> PASS: AC-3 verified (/api/state clean)")

    # ------------------------------------------------------------------
    # AC-4: After new_chat + new upload, vstore._collection.count() > 0
    # ------------------------------------------------------------------
    files_reup = {"file": ("project_atlas_resume.pdf", pdf_bytes, "application/pdf")}
    resp_reup = client1.post("/api/upload", files=files_reup)
    assert resp_reup.status_code == 200, f"Re-upload failed: {resp_reup.text}"
    count_reup = SESSIONS[sid1]["vectorstore"]._collection.count()
    print(f"[AC-4] After re-upload: count == {count_reup}")
    assert count_reup > 0, f"AC-4 FAIL: Re-upload chunk count is {count_reup} <= 0"
    print("  --> PASS: AC-4 verified (re-upload succeeds with chunks > 0)")

    # ------------------------------------------------------------------
    # AC-5 (Part 2): Session ID cookie unchanged across new_chat
    # ------------------------------------------------------------------
    cookie_after = client1.cookies.get("session_id")
    print(f"[AC-5] Cookie before: {cookie_before}, Cookie after: {cookie_after}")
    assert cookie_before == cookie_after == sid1, f"AC-5 FAIL: Cookie changed! {cookie_before} != {cookie_after}"
    print("  --> PASS: AC-5 verified (session ID cookie strictly preserved)")

    # ------------------------------------------------------------------
    # AC-6: Second session (different cookie) sees its own isolated store
    # ------------------------------------------------------------------
    client2 = TestClient(app, base_url="http://testserver")
    resp_c2_init = client2.get("/api/health")
    assert resp_c2_init.status_code == 200
    sid2 = client2.cookies.get("session_id")
    assert sid2 and sid2 != sid1, f"AC-6 FAIL: Client 2 got duplicate session ID: {sid2}"
    c2_count = SESSIONS[sid2]["vectorstore"]._collection.count()
    c1_count = SESSIONS[sid1]["vectorstore"]._collection.count()
    print(f"[AC-6] Client 1 count: {c1_count}, Client 2 count: {c2_count}")
    assert c2_count == 0, f"AC-6 FAIL: Client 2 vectorstore not empty: {c2_count}"
    assert c1_count > 0, f"AC-6 FAIL: Client 1 vectorstore was contaminated or cleared: {c1_count}"
    print("  --> PASS: AC-6 verified (cross-session vectorstore isolation)")

    # ------------------------------------------------------------------
    # AC-7: X-button (DELETE /api/doc/...) does NOT clear chat history
    # ------------------------------------------------------------------
    # Send a message in client 1 on the re-uploaded doc
    resp_chat2 = client1.post("/api/chat", json={"question": "hi"})
    assert resp_chat2.status_code == 200
    active_cid = SESSIONS[sid1]["active_chat_id"]
    msgs_before_x = list(SESSIONS[sid1]["chats"][active_cid]["messages"])
    msgs_count_before_x = len(msgs_before_x)
    assert msgs_count_before_x > 0, "No messages present before X-button delete"

    # Delete doc via X-button endpoint
    resp_del = client1.delete("/api/doc/project_atlas_resume.pdf")
    assert resp_del.status_code == 200, f"DELETE /api/doc failed: {resp_del.text}"
    del_json = resp_del.json()
    assert del_json.get("deleted") == "project_atlas_resume.pdf"

    # Verify document is removed
    assert SESSIONS[sid1]["indexed_docs"] == []
    assert SESSIONS[sid1]["active_doc"] is None

    # Inspect messages list — must be unchanged
    msgs_after_x = list(SESSIONS[sid1]["chats"][active_cid]["messages"])
    msgs_count_after_x = len(msgs_after_x)
    print(f"[AC-7] Messages before X-button: {msgs_count_before_x}, Messages after X-button: {msgs_count_after_x}")
    assert msgs_count_after_x == msgs_count_before_x, (
        f"AC-7 FAIL: Chat history altered! Before: {msgs_count_before_x}, After: {msgs_count_after_x}"
    )
    assert [m["content"] for m in msgs_after_x] == [m["content"] for m in msgs_before_x], (
        "AC-7 FAIL: Chat message contents changed after document delete"
    )
    print("  --> PASS: AC-7 verified (X-button removes doc but preserves chat history)")

    print("\n" + "=" * 75)
    print("  ALL ACCEPTANCE CRITERIA (AC-1 to AC-7) PASSED WITH LIVE EVIDENCE!")
    print("=" * 75)


if __name__ == "__main__":
    test_new_chat_ac1_to_ac7()
