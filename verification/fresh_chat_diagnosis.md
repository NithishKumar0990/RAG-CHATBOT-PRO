# Fresh Chat Diagnosis: Root Cause of Inherited Context

**Date:** 2026-10-06  
**Target:** `x:/Rag_Chatbot_Pro`  
**Focus:** Context inheritance across New Chat and thread switching

---

## 1. Trace of Current Paths

### Path A: Frontend New Chat Handler & State Reset (`static/app.js:485-548`)
- **Current Behavior:**
  When clicking `btnNewChat`, `app.js` aborts in-flight streams, calls `POST /api/new_chat`, and resets `state.messages = []`, `state.activeChatId = data.chat_id`, `state.indexed_docs = []`, `state.active_doc = null`, `state.analysisCache = {}`.
- **Defect / Leak:**
  In `activateChat(chatId)` (`static/app.js:249-276`), when the user clicks an older chat in the sidebar, `app.js` only updates `state.activeChatId` and `state.messages`. It does **not** update `state.active_doc` or `state.indexed_docs` from the server response. As a result, whatever document was active in the most recent chat remains displayed in the top pill and recent-doc list when switching between chats.

---

### Path B: `POST /api/new_chat` (`server.py:337-385`)
- **Current Behavior:**
  Creates a new thread `new_thread = {"id": chat_id, "title": "New chat", "messages": [], ...}`, appends it to `sess["chats"]`, and sets `sess["active_chat_id"] = chat_id`.
  Wipes session document fields: `sess["indexed_docs"] = []`, `sess["doc_texts"] = {}`, `sess["active_doc"] = None`, `sess["topics"] = []`, `sess["analysis_cache"] = {}`.
  Calls `vstore.delete(ids=ids)` if existing IDs are found in Chroma.
- **Defects / Leaks:**
  1. **Silent Failure on Incomplete Wipe:** If `vstore.delete()` fails or leaves chunks behind, it logs an error but does not verify remaining count and returns `ok: True`. The requirement states: *"If clearing the vectorstore fails, do not report a successful fresh chat while old chunks remain. Log the failure and return an appropriate error."*
  2. **Pipeline Globals Not Reset:** It clears `sess["topics"]`, but does **not** clear the module-level globals `rag_pipeline._doc_topics` or `rag_pipeline._doc_filename`.
  3. **No Thread Document Association:** When new chat creates a thread, it does not clean up or isolate document pointers per thread.

---

### Path C: `POST /api/chat` History Selection & Query Rewriting (`server.py:480-600`)
- **Current Behavior:**
  `history = list(active_chat.get("messages", []))`.
  In a fresh chat, `history` is empty, so `_rewrite_question` is bypassed.
- **Defects / Leaks:**
  1. **Global Session Active Doc Lookup:** `active_doc = sess.get("active_doc")` reads from the session root rather than checking whether the active thread is bound to that document.
  2. **Topic Contamination via `finally` Block:** In line 600:
     ```python
     finally:
         sess["topics"] = list(rag_pipeline._doc_topics)
         lock.release()
     ```
     When a new chat receives a query without a document, it hits the no-doc guard and jumps to `finally`. If `rag_pipeline._doc_topics` still holds topics from a previous document, line 600 re-populates `sess["topics"]` with the prior document's topics.
  3. **Fallback Message Leak:** If `rag_pipeline._doc_topics` is non-empty, `_build_fallback_msg()` builds bullets from the previous document's contents.

---

### Path D: Vectorstore Lifecycle & Document Metadata (`web_adapters.py:105-140`, `server.py:189-280`)
- **Current Behavior:**
  A single Chroma collection (`sess_<sid>`) is shared across all threads in the session.
- **Defects / Leaks:**
  Chunks in the vectorstore have metadata `{"source": filename, "chunk": i}`. While `stream_answer` filters by `{"source": doc_name}`, if `doc_name` is inherited by an older chat from a newly uploaded document, the search retrieves chunks from the wrong thread's document.

---

### Path E: Chat Switching / Activation & Upload Behavior (`server.py:405-423`, `189-280`)
- **Current Behavior:**
  - In `post_upload`: Document is parsed and indexed. It sets `sess["active_doc"] = filename`, `sess["doc_texts"][filename] = text`, but does **not** bind `active_chat["doc"] = filename`.
  - In `activate_chat(chat_id)`:
    ```python
    sess["active_chat_id"] = chat_id
    active = sess["chats"][chat_id]
    sess["chat_history"] = active["messages"]
    ```
    It does **not** update `sess["active_doc"]` or `sess["indexed_docs"]`.
- **Defects / Leaks (Primary Leak on Thread Switching):**
  When a user:
  1. Uploads PDF A in Chat 1.
  2. Clicks New Chat -> Chat 2 is created (docs wiped).
  3. Uploads PDF B in Chat 2 (`sess["active_doc"]` becomes PDF B).
  4. Switches back to Chat 1:
     `activate_chat` leaves `sess["active_doc"] = PDF B`!
     When the user asks a question in Chat 1, `post_chat` retrieves from `sess["active_doc"]` (PDF B)!
     Chat 1 accidentally answers using Chat 2's PDF.

---

### Path F: Mutable Pipeline Globals (`rag_pipeline.py:69-70, 222-257`)
- **Current Behavior:**
  `rag_pipeline._doc_topics` and `rag_pipeline._doc_filename` are module-level globals.
  `index_uploaded_document` populates them.
  `delete_document_by_name` calls `_rebuild_topic_cache()`, which reads from `uploaded_vectorstore` (the module-level default store), not the session's vectorstore.
- **Defects / Leaks:**
  `rag_pipeline._doc_topics` survives `new_chat` unless explicitly cleared.

---

## 2. Root Cause Summary

1. **Session-Level vs. Thread-Level Document Binding:** Document identity (`active_doc`, `indexed_docs`) was tracked only at the session level (`sess["active_doc"]`) rather than being bound to the active thread (`active_chat["doc"]`). When switching back to an older chat after uploading a new PDF, the older chat inherited the new PDF.
2. **Missing Vectorstore Verification & Atomic Re-creation on Failure:** `new_chat` did not verify that chunk count dropped to 0 after `vstore.delete(ids=ids)`, nor did it recreate the collection if deletion failed.
3. **Module-Level Topic Global Bleed:** `rag_pipeline._doc_topics` and `rag_pipeline._doc_filename` were not cleared on `new_chat`, and `post_chat`'s `finally` block re-saved stale global topics back into `sess["topics"]`.
4. **Frontend `activateChat` Desynchronization:** `activateChat` in `static/app.js` did not update `state.active_doc` or `state.indexed_docs` from the server, causing the UI to display stale document state when switching threads.

---

## 3. Required Fix Architecture

1. **`server.py:post_upload`**:
   Bind uploaded document to the currently active chat thread: `active_chat["doc"] = filename`, `active_chat["doc_name"] = filename`, `active_chat["indexed_docs"] = [doc_entry]`.
2. **`server.py:new_chat`**:
   - Verify Chroma chunk count drops to 0; if chunks remain or an error occurs, recreate a fresh Chroma collection. If clearing still fails, raise `HTTPException(status_code=500, detail="Failed to clear vectorstore chunks")`.
   - Clear session document metadata and analysis cache.
   - Explicitly clear mutable pipeline globals: `rag_pipeline._doc_topics = []` and `rag_pipeline._doc_filename = "the document"`.
   - Initialize new thread with `"doc": None`, `"doc_name": None`, `"indexed_docs": []`.
   - Return full authoritative state (`chats`, `active_chat_id`, `active_doc: None`, `indexed_docs: []`).
3. **`server.py:activate_chat` & `GET /api/state`**:
   - Synchronize `sess["active_doc"]` with `active_chat.get("doc")`.
   - If `active_chat.get("doc")` is `None` or not in `sess["doc_texts"]`, ensure `sess["active_doc"] = None` and `indexed_docs = []`.
   - Return `active_doc` and `indexed_docs` in the response so the client stays in exact sync.
4. **`server.py:post_chat`**:
   - Read `active_doc = active_chat.get("doc")` rather than trusting un-scoped session globals.
   - If `not active_doc` or `active_doc not in sess["doc_texts"]`, enforce the no-doc guard immediately and ensure `rag_pipeline._doc_topics = []` in finally block.
5. **`static/app.js`**:
   - In `activateChat(chatId)`, update `state.active_doc = data.active_doc || null` and `state.indexed_docs = data.indexed_docs || []`, then call `renderRecentDocs()` and `renderActiveDocPill()`.
   - In `deleteChat(chatId)`, sync `state.active_doc` and `state.indexed_docs` similarly.
