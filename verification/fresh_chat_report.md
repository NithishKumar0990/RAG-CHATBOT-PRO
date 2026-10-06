# Verification Report: Fresh New Chat & Thread Context Isolation

**Date:** 2026-10-06  
**Project:** `x:/Rag_Chatbot_Pro`  
**Status:** ALL 10 TESTS PASSED (100%)

---

## 1. Root Cause & Relevant File/Function Locations

Prior to this fix, clicking "+ New Chat" created a new conversation thread, but context was still leaked across chats and document boundaries due to four key root causes:

1. **Session-Level vs. Thread-Level Document Binding (`server.py:post_upload`, `server.py:activate_chat`)**:
   - `sess["active_doc"]` was tracked globally per session rather than scoped to the active thread.
   - When Chat 2 uploaded a PDF (e.g. PDF B), switching back to Chat 1 (`/api/chats/{id}/activate`) left `sess["active_doc"]` pointing to PDF B. Chat 1 then mistakenly queried and answered using PDF B instead of returning the no-doc guard.
2. **Global Pipeline Topics Bleed (`rag_pipeline.py:69`, `server.py:post_chat`, `server.py:new_chat`)**:
   - `rag_pipeline._doc_topics` is a module-level global list.
   - `server.py:new_chat` wiped `sess["topics"] = []`, but failed to clear `rag_pipeline._doc_topics`.
   - In `server.py:post_chat`, the `finally` block unconditionally executed `sess["topics"] = list(rag_pipeline._doc_topics)`, re-populating `sess["topics"]` from the prior document and causing smart fallbacks to leak topics from previous documents into fresh chats.
3. **Unverified Vectorstore Wipe (`server.py:new_chat`)**:
   - `new_chat` invoked `vstore.delete(ids=ids)` in a try-catch block, but did not verify that the chunk count reached 0 before reporting success, nor did it handle recreating collections if deletion failed.
4. **Frontend UI Desynchronization on Chat Switch (`static/app.js:activateChat`, `deleteChat`)**:
   - `activateChat` and `deleteChat` updated `state.messages` but never updated `state.active_doc` or `state.indexed_docs`, leaving stale document pills and recent document items displayed in the UI when toggling between threads.

---

## 2. Files Changed

All edits were strictly confined to the web layer without modifying `rag_pipeline.py`, `document_parser.py`, or `resume_analyzer.py`:

| File | Changes Made |
|---|---|
| [`web_adapters.py`](file:///x:/Rag_Chatbot_Pro/web_adapters.py) | • Initialized `"doc": None`, `"doc_name": None`, `"indexed_docs": []` on newly created threads in `create_session_data` and `ensure_session_chats`.<br>• Enhanced `session_scope` to dynamically resolve `session["active_doc"]` from `active_chat.get("doc")`, safely resetting `rag_pipeline._doc_topics = []` and `_doc_filename = "the document"` if no document is active on the current thread. |
| [`server.py`](file:///x:/Rag_Chatbot_Pro/server.py) | • `get_state`: Resolves `active_doc` and `indexed_docs` strictly from the currently active thread.<br>• `post_upload`: Explicitly binds `active_chat["doc"] = filename`, `active_chat["doc_name"] = filename`, `active_chat["indexed_docs"] = [doc_entry]`.<br>• `new_chat`: Wipes Chroma vectorstore with post-deletion count verification and atomic collection re-creation fallback; raises HTTP 500 if chunks remain; resets session doc memory, caches, and pipeline globals (`rag_pipeline._doc_topics = []`, `rag_pipeline._doc_filename = "the document"`); creates pristine thread with empty messages and no doc pointers.<br>• `activate_chat` & `delete_chat`: Synchronizes `sess["active_doc"]` and pipeline globals with the newly activated thread's document state and returns authoritative `active_doc` and `indexed_docs`.<br>• `post_chat`: Scopes retrieval and no-doc guard to `active_chat.get("doc")`; safely cleans up topics in `finally` without topic bleed. |
| [`static/app.js`](file:///x:/Rag_Chatbot_Pro/static/app.js) | • `activateChat`: Synchronizes `state.active_doc = data.active_doc \|\| null` and `state.indexed_docs = data.indexed_docs \|\| []` from the server response; calls `renderRecentDocs()` and `renderActiveDocPill()`.<br>• `deleteChat`: Synchronizes `state.active_doc` and `state.indexed_docs` and re-renders document state upon thread deletion. |

---

## 3. Test Results & Evidence (10 Criteria)

Automated test execution script: [`verification/verify_10_criteria.py`](file:///x:/Rag_Chatbot_Pro/verification/verify_10_criteria.py)  
Browser automation script: [`scratch/capture_browser_evidence.py`](file:///x:/Rag_Chatbot_Pro/scratch/capture_browser_evidence.py)  
Execution Log: [`verification/fresh_chat_test_evidence.txt`](file:///x:/Rag_Chatbot_Pro/verification/fresh_chat_test_evidence.txt)  
UI Screenshot: [`verification/fresh_chat_ui.png`](file:///x:/Rag_Chatbot_Pro/verification/fresh_chat_ui.png)

| # | Test Requirement | Result | Evidence Details |
|---|---|---|---|
| **1** | Upload PDF A (`canary_resume.pdf`), ask question about A, confirm source returned | **PASS** | Status 200, chunk indexed, answer contains canary token `ZEBRA-CANARY-7731`, sources include `canary_resume.pdf` (score: 0.4649). |
| **2** | Click New Chat; `GET /api/state` shows empty active chat & no active PDF; session vectorstore/doc state cleared | **PASS** | `active_chat_id` updated to new thread, `active_doc=None`, `indexed_docs=[]`, `history_count=0`, Chroma chunk count = `0`, `rag_pipeline._doc_topics=[]`. |
| **3** | Ask question in new thread before upload -> returns existing no-document guard | **PASS** | Status 200, answer is exact guard: `"Please upload a document (PDF, DOCX, TXT, or CSV) above to start chatting."`, sources: `[]`. |
| **4** | Upload PDF B (`project_atlas_resume.pdf`) and ask about A's unique canary -> A not retrievable | **PASS** | Similarity score 0.1190 (`FILTERED`), answer is smart fallback: `"I couldn't find that in project_atlas_resume.pdf..."`, zero leakage of Canary A or `canary_resume.pdf`. |
| **5** | Ask about B's unique canary (`Project Atlas`) -> B is retrievable with sources | **PASS** | Similarity score 0.7767 (`PASS`), answer accurately details Project Atlas migration, sources include `project_atlas_resume.pdf`. |
| **6** | Query rewriting in new chat receives no prior chat messages | **PASS** | Chat 1 messages (2 items) isolated from Chat 2 messages (4 items); no cross-thread history supplied to rewrite chain. |
| **7** | Switching to older chat does not accidentally use another chat's PDF | **PASS** | Activating Chat 1 returns `active_doc=None`, `indexed_docs=[]`. Asking about Project Atlas in Chat 1 triggers no-doc guard instead of retrieving Chat 2's PDF. |
| **8** | Two separate browser sessions remain isolated | **PASS** | Session 2 has independent UUID, empty docs (`active_doc=None`, `indexed_docs=[]`), 1 initial chat, and asking questions triggers no-doc guard. |
| **9** | Frontend recent-doc list, active-doc display, chat list, and empty state match `/api/state` | **PASS** | Verified via Chrome DevTools Protocol in Edge: `activeDocPill` is `none`, `recentList` displays `"No documents yet"`, `emptyHero` is `flex`, chat items match server list. |
| **10** | Existing upload/chat/source behavior still works | **PASS** | Follow-up query in Chat 2 (*"Who led the migration?"*) rewrites correctly, achieves similarity score 0.6431 (`PASS`), returns *"John Doe"*, and cites `project_atlas_resume.pdf`. |

---

## 4. Confirmation of Zero Inherited Context

- **Messages:** Verified that when `POST /api/new_chat` is called, a new thread UUID is minted with `messages: []` and `history_count: 0`. Query rewriting in the new chat receives only `[]`.
- **PDF & Embeddings:** Verified that `new_chat` deletes all chunk IDs from the Chroma vectorstore and verifies chunk count is 0.
- **Metadata & Cache:** Verified that `active_doc`, `doc_name`, `full_doc_text`, `topics`, and `analysis_cache` are wiped on `new_chat`.
- **Pipeline Globals:** Verified that module globals `rag_pipeline._doc_topics` and `rag_pipeline._doc_filename` are reset on `new_chat` and whenever `not active_doc`.
- **Thread Scoping:** When a document is subsequently uploaded in Chat 2, Chat 1 does not inherit Chat 2's document context upon activation.

---

## 5. Design Decisions & Limitations

1. **In-Memory Collection Management**:
   - Each session maintains its dedicated in-memory Chroma collection. On `new_chat`, the collection's IDs are deleted and verified. If delete leaves residual chunks, the collection is automatically recreated under a new random sub-name (`sess_{sid}_{hex}`). If chunks remain after recreation, an HTTP 500 error is returned rather than reporting a false success.
2. **Transcript Preservation Without Re-indexing**:
   - Old chat threads retain their conversation messages for reading in the sidebar. Because a session possesses a single active vectorstore and the previous document chunks were cleared upon New Chat, older threads whose documents were cleared cleanly return the no-document guard response if a user asks a new document question without uploading a new file in that thread.
3. **No Database Dependencies**:
   - Implemented entirely using the existing session storage and RLock mechanisms without external databases or modifying pipeline core modules.
