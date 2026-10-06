# Diagnostic Report: "New Chat" Bug Investigation

**Date:** 2026-10-06  
**Workspace:** `x:/Rag_Chatbot_Pro`  
**Status:** READ-ONLY Diagnostic Completed (No fixes applied)

---

## 1. Tech Stack Confirmation

- **Active Server:** **FastAPI (`server.py`)** running under Uvicorn (`uvicorn server:app --port 8000 --reload`).
- **Active Frontend:** **Vanilla HTML/CSS/JS (`static/index.html`, `static/style.css`, `static/app.js`)** served statically by FastAPI.
- **Streamlit Status:** **NOT RUNNING and NOT PRESENT.** `app.py` does not exist in the project directory; earlier Streamlit references in `verification/nc_REPORT.md` and `tests/test_w8_streamlit_regression.py` relate to legacy prototypes that were fully migrated to the standalone FastAPI architecture.
- **Main Files in Active Use:**
  - `server.py` — Main FastAPI application, routing, middleware, SSE streaming generator.
  - `web_adapters.py` — In-memory session store (`SESSIONS`), session lock management, Chroma vectorstore lifecycle, thread schema.
  - `rag_pipeline.py` — RAG retrieval pipeline, embeddings, query rewriting, LLM streaming wrappers.
  - `document_parser.py` — PDF/DOCX/TXT extraction.
  - `resume_analyzer.py` — ATS 5-axis resume audit, interview question generation, JD matching.
  - `static/index.html` — SPA structure, sidebar navigation (`#new-chat-btn`, `#chatsList`, `#recentList`), chat dock.
  - `static/app.js` — Client state machine (`state.chats`, `state.activeChatId`, `state.messages`), SSE reader, event handlers.
  - `static/style.css` — CSS design system, layout, sidebar and thread styling.

---

## 2. Full File Tree

```
x:/Rag_Chatbot_Pro/
|-- scratch/
|   |-- analyze_persistence_patterns.py
|   |-- audit_chat_input.py
|   |-- capture_baselines.py
|   |-- code_discovery_results.json
|   |-- diagnose_current_work.py
|   |-- diagnose_new_chat.py
|   |-- execute_cleanup.ps1
|   |-- gen_iq.py
|   |-- inspect_cdp.py
|   |-- inspect_dom.py
|   |-- inspect_send_btn.py
|   |-- inspect_session_state.py
|   |-- inspect_stbottom.py
|   |-- patch_meta.py
|   |-- print_tree.py
|   |-- reproduce_bugs.py
|   |-- reproduce_diagnostic.py
|   |-- reproduce_nc.py
|   |-- rescan_cleanup.py
|   |-- run_code_discovery.py
|   |-- run_full_diag_test.py
|   |-- run_full_verification.py
|   |-- save_samples.py
|   |-- scratchpad_chat_ux.md
|   |-- scratchpad_recent_fix.md
|   |-- scratchpad_session_state.md
|   |-- simulate_12_messages.py
|   |-- sweep_filesystem.py
|   |-- test_3_layers.py
|   |-- test_browser_pill.py
|   |-- test_chat_flow.py
|   |-- test_chat_ux.py
|   |-- test_free_text.py
|   |-- test_narrow.py
|   |-- test_new_chat_button.py
|   |-- test_no_doc_session.py
|   |-- test_raw.py
|   |-- test_retrieval_k.py
|   |-- test_s2_indexing.py
|   |-- test_s3_s5.py
|   |-- test_st_html.py
|   |-- test_streaming.py
|   |-- test_svg_inject.py
|   |-- test_u2_u4.py
|   |-- test_ui_fix.py
|   |-- trace_ancestors.py
|   |-- verify_all_scenarios.py
|   |-- verify_all_v1_v5.py
|   |-- verify_c1_to_c4.py
|   |-- verify_chatgpt_input.py
|   |-- verify_cleanup_empty_state.py
|   |-- verify_e3_e4.py
|   |-- verify_layout.py
|   |-- verify_n1_to_n5.py
|   |-- verify_n1_to_n6.py
|   |-- verify_nc_suite.py
|   |-- verify_new_chat.py
|   |-- verify_p1_p5.py
|   |-- verify_sidebar_css.py
|   +-- verify_u1_u3.py
|-- static/
|   |-- app.js
|   |-- index.html
|   +-- style.css
|-- tests/
|   |-- fixtures/
|   |   |-- canary_resume.pdf
|   |   |-- empty_scanned.pdf
|   |   |-- project_atlas_resume.pdf
|   |   +-- unsupported_doc.xyz
|   |-- create_fixtures.py
|   |-- run_all_verifications.py
|   |-- test_drift.py
|   |-- test_part2_criteria.py
|   |-- test_part3_frontend.py
|   |-- test_w1_render_parity.py
|   |-- test_w2_upload_chat.py
|   |-- test_w3_streaming.py
|   |-- test_w4_guards_fallbacks.py
|   |-- test_w5_multiturn_rewrite.py
|   |-- test_w6_isolation_state.py
|   |-- test_w7_analyze.py
|   |-- test_w8_streamlit_regression.py
|   +-- test_w9_no_duplication.py
|-- ui/
|   |-- __init__.py
|   |-- theme.css
|   +-- ui_blocks.py
|-- verification/
|   |-- baseline/
|   |   |-- analyze_audit.png
|   |   |-- analyze_jd.png
|   |   |-- analyze_overview.png
|   |   |-- analyze_questions.png
|   |   |-- chat_with_sources.png
|   |   +-- empty_state.png
|   |-- part2/
|   |   +-- part2_verification_evidence.txt
|   |-- part3/
|   |   |-- analyze_overview.png
|   |   |-- part3_verification_evidence.txt
|   |   |-- w1_chat_with_sources.png
|   |   |-- w1_desktop_1440x900.png
|   |   +-- w1_mobile_390x844.png
|   |-- samples/
|   |   |-- interview_questions.json
|   |   |-- jd_match.json
|   |   +-- resume_audit.json
|   |-- API_CONTRACT.md
|   |-- AUDIT.md
|   |-- cleanup_empty_state.txt
|   |-- cleanup_inventory.md
|   |-- cleanup_log.txt
|   |-- CLEANUP_REPORT.md
|   |-- cleanup_rescan.txt
|   |-- nc_after.png
|   |-- nc_audit.md
|   |-- nc_before.png
|   |-- nc_console.txt
|   |-- nc_console_after.txt
|   |-- nc_docs_diff.txt
|   |-- nc_fixed_after.png
|   |-- nc_REPORT.md
|   |-- nc_repro.md
|   |-- nc_rewrite.txt
|   |-- nc_rootcause.md
|   |-- nc_state_after.json
|   |-- nc_state_before.json
|   |-- nc_threads.png
|   |-- new_chat_verification_evidence.txt
|   |-- protected_manifest.txt
|   |-- w2_upload_chat.txt
|   +-- w9_no_duplication.txt
|-- .env
|-- .gitignore
|-- diagnose.py
|-- diagnose_regression.py
|-- document_parser.py
|-- extract_colors.py
|-- rag_pipeline.py
|-- README.md
|-- requirements-dev.txt
|-- requirements.txt
|-- resume_analyzer.py
|-- sample_resume.txt
|-- server.py
|-- test_analyzer.py
|-- test_memory.py
|-- test_new_chat.py
|-- test_upload.py
|-- verify_improvements.py
|-- verify_platform.py
|-- verify_r1_to_r4.py
|-- verify_rag.py
+-- web_adapters.py
```

---

## 3. Backend New Chat Logic - FULL CODE

### Question: Does backend support MULTIPLE threads/chats per user, or only ONE single `chat_history` array?
**Root Cause Answer:**
The backend data structure (`web_adapters.py`) and API routes (`server.py`) were architected to support **MULTIPLE** threads per session (`sess["chats"] = {chat_id: thread_dict}` with `GET /api/chats`, `POST /api/chats/{chat_id}/activate`, and `DELETE /api/chats/{chat_id}`).

**However, the implementation of `POST /api/new_chat` in `server.py` is broken:**
1. Lines 409–411 in `server.py` explicitly execute:
   ```python
   sess["chats"] = {chat_id: new_thread}
   sess["active_chat_id"] = chat_id
   sess["chat_history"] = new_thread["messages"]
   ```
   Instead of appending the newly created thread into `sess["chats"][chat_id] = new_thread`, it **overwrites the entire dictionary** with a 1-item dictionary containing only the new thread. All prior threads are instantly discarded from memory.
2. Lines 347–395 in `server.py` perform a total document and vectorstore wipe (`vstore.delete(ids=ids)`, `sess["indexed_docs"] = []`, `sess["active_doc"] = None`), clearing the user's active resume and embeddings upon clicking New Chat.
3. Therefore, while multi-threading exists in schema and endpoints, `POST /api/new_chat` treats "New Chat" as a destructive factory reset that obliterates all previous chat threads and all documents.

---

### Full Code: `POST /api/new_chat` (`server.py:337-423`)
```python
@app.post("/api/new_chat")
def new_chat(request: Request):
    """
    Full session reset: wipe ALL document state (vectorstore, indexed_docs, doc_texts,
    active_doc, full_doc_text, doc_name, analysis_cache, topics) AND clear all existing
    chat threads. Returns a pristine new thread — equivalent to a fresh session.
    """
    sess = request.state.session
    with sess["lock"]:
        # --- Wipe vectorstore chunks ---
        try:
            vstore = sess.get("vectorstore")
            if vstore is not None:
                existing = vstore.get()
                ids = existing.get("ids", []) if existing else []
                if ids:
                    vstore.delete(ids=ids)
                    logger.info(f"new_chat: deleted {len(ids)} chunks from vectorstore")
                # Verify deletion
                remaining = vstore.get()
                remaining_ids = remaining.get("ids", []) if remaining else []
                if remaining_ids:
                    logger.error(f"new_chat: vstore.delete() failed, {len(remaining_ids)} chunks remain — collection will be recreated")
                    col_name = sess.get("collection_name", f"sess_{sess.get('sid', uuid.uuid4().hex)}")
                    from langchain_chroma import Chroma
                    from web_adapters import embedding_model
                    sess["vectorstore"] = Chroma(
                        collection_name=col_name + "_reset",
                        embedding_function=embedding_model,
                        collection_metadata={"hnsw:space": "cosine"}
                    )
                    sess["collection_name"] = col_name + "_reset"
                    logger.info(f"new_chat: nuclear fallback recreated collection as {sess['collection_name']}")
                else:
                    logger.info("new_chat: vectorstore confirmed empty (0 chunks remaining)")
        except Exception as e:
            logger.error(f"new_chat: vectorstore wipe error: {e}")
            try:
                col_name = sess.get("collection_name", f"sess_{sess.get('sid', uuid.uuid4().hex)}")
                from langchain_chroma import Chroma
                from web_adapters import embedding_model
                sess["vectorstore"] = Chroma(
                    collection_name=col_name + "_reset",
                    embedding_function=embedding_model,
                    collection_metadata={"hnsw:space": "cosine"}
                )
                sess["collection_name"] = col_name + "_reset"
                logger.info(f"new_chat: nuclear fallback recreated collection as {sess['collection_name']} after exception")
            except Exception as fallback_err:
                logger.critical(f"new_chat: nuclear fallback failed: {fallback_err}")

        # --- Wipe document metadata & cache ---
        sess["indexed_docs"] = []
        sess["doc_texts"] = {}
        sess["active_doc"] = None
        sess["full_doc_text"] = ""
        sess["doc_name"] = ""
        sess["topics"] = []
        sess["analysis_cache"] = {}

        # --- Create a fresh chat thread (replace all old threads) ---
        chat_id = uuid.uuid4().hex[:8]
        now = time.time()
        new_thread = {
            "id": chat_id,
            "title": "New chat",
            "messages": [],
            "doc": None,
            "doc_name": None,
            "created_at": now,
            "updated_at": now
        }
        sess["chats"] = {chat_id: new_thread}
        sess["active_chat_id"] = chat_id
        sess["chat_history"] = new_thread["messages"]
        return {
            "ok": True,
            "chat_id": chat_id,
            "title": "New chat",
            "active_chat_id": chat_id,
            "chats": get_chats_list(sess),
            "indexed_docs": [],
            "active_doc": None,
            "history_count": 0,
            "messages": []
        }
```

---

### Full Code: `GET /api/state` (`server.py:164-187`)
```python
@app.get("/api/state")
def get_state(request: Request):
    """
    Return full session state: indexed documents, active doc, chat threads,
    and app configuration so page reload seamlessly restores conversation.
    """
    sess = request.state.session
    with sess["lock"]:
        ensure_session_chats(sess)
        active_chat = get_active_chat(sess)
        return {
            "indexed_docs": sess.get("indexed_docs", []),
            "active_doc": sess.get("active_doc"),
            "chats": get_chats_list(sess),
            "active_chat_id": sess.get("active_chat_id"),
            "history_count": len(active_chat.get("messages", [])),
            "messages": active_chat.get("messages", []),
            "config": {
                "accepted_types": ACCEPTED_FILE_TYPES,
                "max_upload_mb": MAX_UPLOAD_MB,
                "suggested_questions": SUGGESTED_QUESTIONS
            }
        }
```

---

### Full Code: `POST /api/chat` (`server.py:493-642`)
```python
@app.post("/api/chat")
async def post_chat(request: Request):
    """
    Stream answer tokens via Server-Sent Events (SSE).
    Orchestration:
    1. No-doc guard -> returns NO_DOC_MSG
    2. Query rewriting with session history (last 3 turns)
    3. Log: REWRITE sid=<8> original="..." rewritten="..."
    4. Retrieval from session vectorstore + threshold check
    5. Token streaming via LangChain / pipeline
    6. Completed turn appended to chat_history
    """
    body = await request.json()
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="Question is too long (max 2000 characters).")

    sess = request.state.session
    sid = sess["sid"]

    async def event_stream():
        full_answer = ""
        sources = []
        user_ts = datetime.now().strftime("%I:%M %p")
        bot_ts = user_ts

        # Acquire per-session lock for the entire generation
        lock = sess["lock"]
        lock.acquire()
        try:
            # Bind session metadata
            rag_pipeline._doc_topics = sess.get("topics", [])
            rag_pipeline._doc_filename = sess.get("doc_name") or sess.get("active_doc") or "the document"

            active_doc = sess.get("active_doc")
            ensure_session_chats(sess)
            active_chat = get_active_chat(sess)
            history = list(active_chat.get("messages", []))
            chat_id = active_chat.get("id", "")

            # Step 1: No-doc guard
            if not active_doc or not sess.get("doc_texts", {}).get(active_doc):
                for chunk in [NO_DOC_MSG[i:i+4] for i in range(0, len(NO_DOC_MSG), 4)]:
                    full_answer += chunk
                    yield sse_token_event(chunk)
                yield sse_done_event(full_answer, sources, chat_id=chat_id, title=active_chat.get("title", "New chat"))
                return

            # Step 2: Greeting detection (Prompt Rule 4 string)
            q_clean = question.lower().strip()
            greetings = {"hi", "hello", "hey", "how are you", "good morning", "good evening", "good afternoon", "hi there", "hello there", "greetings"}
            if q_clean in greetings:
                import re
                m = re.search(r'reply EXACTLY:\s*"([^"]+)"', rag_pipeline.PROMPT_TEMPLATE)
                greeting_text = m.group(1) if m else "Hi! I'm your document assistant. Ask me anything about the uploaded document 😊"
                for chunk in [greeting_text[i:i+4] for i in range(0, len(greeting_text), 4)]:
                    if await request.is_disconnected():
                        return
                    full_answer += chunk
                    yield sse_token_event(chunk)
                
                if await request.is_disconnected() or sess.get("active_chat_id") != chat_id:
                    return

                title = active_chat.get("title", "New chat")
                if title in ("New chat", ""):
                    title = question[:30] + ("..." if len(question) > 30 else "")
                    active_chat["title"] = title
                active_chat["updated_at"] = time.time()
                active_chat["messages"].append({
                    "role": "user",
                    "content": question,
                    "timestamp": user_ts
                })
                active_chat["messages"].append({
                    "role": "assistant",
                    "content": full_answer,
                    "sources": sources,
                    "timestamp": bot_ts
                })
                sess["chat_history"] = active_chat["messages"]
                yield sse_done_event(full_answer, sources, chat_id=chat_id, title=title)
                return

            # Check rewritten query
            if history:
                rewritten_q = _rewrite_question(question, history)
            else:
                rewritten_q = question

            logger.info(f'REWRITE sid={sid[:8]} original="{question}" rewritten="{rewritten_q}"')

            # Stream tokens
            for chunk in stream_answer(
                question,
                history=history,
                sources_out=sources,
                doc_name=active_doc,
                vectorstore=sess["vectorstore"]
            ):
                if await request.is_disconnected():
                    logger.info(f"Client disconnected mid-stream for session {sid[:8]}")
                    return
                full_answer += chunk
                yield sse_token_event(chunk)

            # Check if disconnected or switched chat thread mid-stream
            if await request.is_disconnected() or sess.get("active_chat_id") != chat_id:
                logger.info(f"Stream aborted or chat thread changed for session {sid[:8]}")
                return

            # Record completed turn to active chat thread
            title = active_chat.get("title", "New chat")
            if title in ("New chat", ""):
                title = question[:30] + ("..." if len(question) > 30 else "")
                active_chat["title"] = title
            active_chat["updated_at"] = time.time()
            active_chat["messages"].append({
                "role": "user",
                "content": question,
                "timestamp": user_ts
            })
            active_chat["messages"].append({
                "role": "assistant",
                "content": full_answer,
                "sources": sources,
                "timestamp": bot_ts
            })
            sess["chat_history"] = active_chat["messages"]

            # Yield done event with chat thread metadata
            yield sse_done_event(full_answer, sources, chat_id=chat_id, title=title)

        except Exception as stream_err:
            logger.error(f"Streaming error in session {sid[:8]}: {stream_err}")
            yield sse_error_event(f"An error occurred while generating response: {stream_err}")
        finally:
            sess["topics"] = list(rag_pipeline._doc_topics)
            lock.release()

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive"
    }
    return StreamingResponse(event_stream(), headers=headers)
```

---

### Full Code: Session Creation Code (`web_adapters.py:105-140` and `224-250`)
```python
def create_session_data(sid: str) -> Dict[str, Any]:
    """Create a pristine session data dictionary with a dedicated Chroma collection."""
    col_name = f"sess_{sid}"
    vstore = Chroma(
        collection_name=col_name,
        embedding_function=embedding_model,
        collection_metadata={"hnsw:space": "cosine"}
    )
    now = time.time()
    init_chat_id = uuid.uuid4().hex[:8]
    initial_chat = {
        "id": init_chat_id,
        "title": "New chat",
        "messages": [],
        "created_at": now,
        "updated_at": now
    }
    return {
        "sid": sid,
        "lock": threading.RLock(),
        "vectorstore": vstore,
        "collection_name": col_name,
        "indexed_docs": [],  # [{filename, chunks, size, uploaded_at}]
        "doc_texts": {},     # filename -> parsed text
        "active_doc": None,
        "full_doc_text": "",
        "doc_name": "",
        "chats": {init_chat_id: initial_chat},
        "active_chat_id": init_chat_id,
        "chat_history": initial_chat["messages"],  # alias to active thread
        "analysis_cache": {},
        "topics": [],
        "created_at": now,
        "last_seen": now
    }
```

```python
def get_or_create_session(sid: Optional[str]) -> tuple[str, Dict[str, Any], bool]:
    """
    Lookup session by sid. If missing or invalid, mint a new one.
    Returns (sid, session_dict, is_new).
    """
    cleanup_stale_sessions()

    # Validate uuid format
    is_valid_uuid = False
    if sid:
        try:
            uuid_obj = uuid.UUID(sid)
            is_valid_uuid = uuid_obj.hex == sid.replace("-", "")
        except Exception:
            is_valid_uuid = False

    with GLOBAL_SESSION_LOCK:
        if is_valid_uuid and sid in SESSIONS:
            sess = SESSIONS[sid]
            sess["last_seen"] = time.time()
            return sid, sess, False

        new_sid = uuid.uuid4().hex
        new_sess = create_session_data(new_sid)
        SESSIONS[new_sid] = new_sess
        return new_sid, new_sess, True
```

---

### Supporting Thread Endpoints & Helpers
#### `web_adapters.py:141-193`
```python
def ensure_session_chats(session: Dict[str, Any]) -> None:
    """Ensure session has 'chats' and 'active_chat_id', migrating old 'chat_history' if needed."""
    if "chats" not in session or not isinstance(session["chats"], dict):
        session["chats"] = {}

    if not session["chats"]:
        init_id = uuid.uuid4().hex[:8]
        now = time.time()
        old_history = session.get("chat_history", [])
        title = "New chat"
        if old_history and len(old_history) > 0:
            first_user = next((m.get("content", "") for m in old_history if m.get("role") == "user"), "")
            if first_user:
                title = first_user[:30] + ("..." if len(first_user) > 30 else "")
        session["chats"][init_id] = {
            "id": init_id,
            "title": title,
            "messages": list(old_history),
            "created_at": now,
            "updated_at": now
        }
        session["active_chat_id"] = init_id

    if "active_chat_id" not in session or session["active_chat_id"] not in session["chats"]:
        session["active_chat_id"] = next(iter(session["chats"]))

    session["chat_history"] = session["chats"][session["active_chat_id"]]["messages"]

def get_active_chat(session: Dict[str, Any]) -> Dict[str, Any]:
    """Return active chat dict, creating a default one if none exists."""
    ensure_session_chats(session)
    return session["chats"][session["active_chat_id"]]

def get_chats_list(session: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return list of chats sorted by updated_at descending."""
    ensure_session_chats(session)
    chat_list = []
    for cid, c in session["chats"].items():
        msgs = c.get("messages", [])
        preview = ""
        if msgs:
            preview = msgs[-1].get("content", "")[:60]
        chat_list.append({
            "id": cid,
            "title": c.get("title", "New chat"),
            "created_at": c.get("created_at", 0),
            "updated_at": c.get("updated_at", 0),
            "preview": preview,
            "messages_count": len(msgs)
        })
    chat_list.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    return chat_list
```

#### `server.py:425-490`
```python
@app.get("/api/chats")
def get_chats(request: Request):
    """Return all chat threads for the current session, sorted newest first."""
    sess = request.state.session
    with sess["lock"]:
        ensure_session_chats(sess)
        return {
            "chats": get_chats_list(sess),
            "active_chat_id": sess.get("active_chat_id")
        }


@app.post("/api/chats/{chat_id}/activate")
def activate_chat(chat_id: str, request: Request):
    """Switch active chat thread in the session."""
    sess = request.state.session
    with sess["lock"]:
        ensure_session_chats(sess)
        if chat_id not in sess["chats"]:
            raise HTTPException(status_code=404, detail=f"Chat thread '{chat_id}' not found in this session.")
        sess["active_chat_id"] = chat_id
        active = sess["chats"][chat_id]
        sess["chat_history"] = active["messages"]
        return {
            "ok": True,
            "active_chat_id": chat_id,
            "title": active.get("title", "New chat"),
            "messages": active.get("messages", []),
            "history_count": len(active.get("messages", []))
        }


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    """
    Delete a chat thread. If active thread is deleted, auto-activate the newest remaining
    or auto-create a fresh empty thread so zero chats never happens.
    """
    sess = request.state.session
    with sess["lock"]:
        ensure_session_chats(sess)
        if chat_id not in sess["chats"]:
            raise HTTPException(status_code=404, detail=f"Chat thread '{chat_id}' not found in this session.")
        del sess["chats"][chat_id]
        if not sess["chats"] or sess.get("active_chat_id") == chat_id:
            if not sess["chats"]:
                new_id = uuid.uuid4().hex[:8]
                now = time.time()
                sess["chats"][new_id] = {
                    "id": new_id,
                    "title": "New chat",
                    "messages": [],
                    "created_at": now,
                    "updated_at": now
                }
                sess["active_chat_id"] = new_id
            else:
                sorted_c = sorted(sess["chats"].values(), key=lambda x: x.get("updated_at", 0), reverse=True)
                sess["active_chat_id"] = sorted_c[0]["id"]
        sess["chat_history"] = sess["chats"][sess["active_chat_id"]]["messages"]
        return {
            "ok": True,
            "deleted": chat_id,
            "active_chat_id": sess["active_chat_id"],
            "chats": get_chats_list(sess)
        }
```

---

## 4. Session Schema

The in-memory session dictionary stored at `SESSIONS[session_id]` in `web_adapters.py`:

```python
{
    "sid": "39f061a9...",                    # str: Unique 32-hex session UUID
    "lock": <threading.RLock object>,        # RLock: Thread-safe per-session re-entrant lock
    "vectorstore": <langchain_chroma.Chroma>,# Chroma: In-memory vectorstore collection
    "collection_name": "sess_39f061a9...",   # str: Name of isolated collection
    "indexed_docs": [                        # list of dicts: Registered uploaded documents
        {
            "filename": "project_atlas_resume.pdf",
            "chunks": 1,
            "size": "14.2 KB",
            "uploaded_at": "11:17 AM"
        }
    ],
    "doc_texts": {                           # dict: filename -> raw text content
        "project_atlas_resume.pdf": "John Doe - Senior Software Engineer..."
    },
    "active_doc": "project_atlas_resume.pdf",# Optional[str]: Currently active filename
    "full_doc_text": "...",                  # str: Text of active doc for ATS analyzer
    "doc_name": "project_atlas_resume.pdf",  # str: Duplicate tracker for rag_pipeline global
    "chats": {                               # dict: chat_id (str) -> thread dictionary
        "1d7724bd": {
            "id": "1d7724bd",
            "title": "What is Project Atlas?",
            "messages": [
                {
                    "role": "user",
                    "content": "What is Project Atlas?",
                    "timestamp": "11:17 AM"
                },
                {
                    "role": "assistant",
                    "content": "Project Atlas is a data-platform migration...",
                    "sources": [
                        {
                            "source": "project_atlas_resume.pdf",
                            "chunk": 0,
                            "score": 0.6385,
                            "content": "..."
                        }
                    ],
                    "timestamp": "11:17 AM"
                }
            ],
            "doc": None,
            "doc_name": None,
            "created_at": 1791265611.819,
            "updated_at": 1791265613.822
        }
    },
    "active_chat_id": "1d7724bd",            # str: Pointer to current active thread key
    "chat_history": [ ... ],                 # list: Alias reference to active thread's messages
    "analysis_cache": {                      # dict: Cached ATS review results
        "resume_audit": { ... },
        "interview_questions": { ... }
    },
    "topics": [ ... ],                       # list: Summary topic strings extracted from doc
    "created_at": 1791265600.0,              # float: Unix timestamp
    "last_seen": 1791265620.0                # float: Unix timestamp for TTL eviction
}
```

---

## 5. Frontend New Chat Button - FULL CODE

### HTML for "+ New Chat" Button (`static/index.html:21-26`)
```html
      <div class="sidebar-actions">
        <button class="btn-new-chat" id="new-chat-btn" aria-label="Start New Chat">
          <span>+</span>
          <span>New chat</span>
        </button>
      </div>
```

### HTML for Sidebar Chats List (`static/index.html:34-38`)
```html
      <!-- CHATS Section -->
      <div class="chats-header">Chats</div>
      <div class="chats-list" id="chatsList" role="list">
        <!-- Dynamically rendered chat threads -->
      </div>
```

---

### Full JS Click Handler for New Chat (`static/app.js:485-550`)
```javascript
  btnNewChat.addEventListener('click', async () => {
    // 1. If isStreaming, call abortController.abort(), set isStreaming=false
    if (state.isStreaming) {
      if (state.streamAbortController) {
        try { state.streamAbortController.abort(); } catch (_) {}
        state.streamAbortController = null;
      }
      state.isStreaming = false;
      updateSendButtonState();
    }
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // 2. Disable button, show spinner state
    const originalText = btnNewChat.innerHTML;
    btnNewChat.disabled = true;
    btnNewChat.innerHTML = '<span>...</span><span>Creating...</span>';

    try {
      // 3. await fetch('/api/new_chat', {method:'POST', credentials:'same-origin'})
      const res = await fetch('/api/new_chat', {
        method: 'POST',
        credentials: 'same-origin'
      });
      if (!res.ok) {
        throw new Error(`Failed to create new chat (${res.status})`);
      }
      const data = await res.json();

      // Full reset: chat + documents + analysis cache
      state.messages = [];
      state.activeChatId = data.chat_id;
      state.chats = data.chats || [{
        id: data.chat_id,
        title: data.title || 'New chat',
        created_at: Date.now() / 1000,
        updated_at: Date.now() / 1000,
        preview: '',
        messages_count: 0
      }];
      state.indexed_docs = data.indexed_docs || [];
      state.active_doc = data.active_doc || null;
      state.analysisCache = {};

      renderChatHistory();
      renderChats();
      renderRecentDocs();
      renderActiveDocPill();

      if (state.mode === 'Analyze') {
        showAnalyzeEmptyState();
        switchMode('Chat');
      }
      mainScrollContainer.scrollTop = 0;
      btnScrollDown.style.display = 'none';
      state.userScrolledUp = false;

      showToast('New chat created', 'info');
    } catch (err) {
      showToast(`Failed to create new chat: ${err.message}`, 'error');
    } finally {
      btnNewChat.disabled = false;
      btnNewChat.innerHTML = originalText;
      updateSendButtonState();
    }
  });
```

---

### Full JS `renderChatHistory()` and Message Append Functions (`static/app.js:365-381` and `590-630`)
```javascript
  function renderChatHistory() {
    chatMessages.innerHTML = '';
    if (!state.messages || state.messages.length === 0) {
      emptyHero.style.display = 'flex';
      return;
    }

    emptyHero.style.display = 'none';
    state.messages.forEach(msg => {
      if (msg.role === 'user') {
        appendUserMessage(msg.content);
      } else {
        appendAssistantMessage(msg.content, msg.sources, msg.timestamp);
      }
    });
    scrollToBottom(true);
  }
```

```javascript
  function appendUserMessage(text) {
    emptyHero.style.display = 'none';
    const row = document.createElement('div');
    row.className = 'msg-user-row';
    const bubble = document.createElement('div');
    bubble.className = 'riq-msg-user';
    bubble.textContent = text;
    row.appendChild(bubble);
    chatMessages.appendChild(row);
  }

  function appendAssistantMessage(text, sources, timestamp = 'Just now') {
    const row = document.createElement('div');
    row.className = 'msg-bot-row';

    const botWrap = document.createElement('div');
    botWrap.className = 'riq-msg-bot';

    const head = document.createElement('div');
    head.className = 'riq-msg-bot-head';
    head.innerHTML = `
      <span class="riq-avatar">◆</span>
      <span class="riq-micro">Résumé IQ &nbsp;·&nbsp; ${escapeHTML(timestamp)}</span>
    `;

    const body = document.createElement('div');
    body.className = 'riq-msg-bot-body';
    body.innerHTML = renderSafeMarkdown(text);

    botWrap.appendChild(head);
    botWrap.appendChild(body);

    if (sources && sources.length > 0) {
      const details = createSourcesDetails(sources);
      botWrap.appendChild(details);
    }

    row.appendChild(botWrap);
    chatMessages.appendChild(row);
  }
```

---

### Full JS Sidebar Chat List Rendering Functions (`static/app.js:207-311`)
```javascript
  function renderChats() {
    if (!chatsList) return;
    chatsList.innerHTML = '';
    if (!state.chats || state.chats.length === 0) {
      chatsList.innerHTML = '<div style="padding:8px 6px; font-size:12px; color:var(--text-muted); font-style:italic;">No chats yet</div>';
      return;
    }

    state.chats.forEach(chat => {
      const item = document.createElement('div');
      item.className = 'chat-item' + (chat.id === state.activeChatId ? ' active' : '');
      item.setAttribute('data-chat-id', chat.id);

      const titleSpan = document.createElement('span');
      titleSpan.className = 'chat-title';
      titleSpan.textContent = chat.title || 'New chat';
      titleSpan.title = chat.title || 'New chat';

      const delBtn = document.createElement('button');
      delBtn.className = 'btn-del-chat';
      delBtn.textContent = '✕';
      delBtn.title = 'Delete chat';
      delBtn.setAttribute('aria-label', `Delete ${chat.title || 'chat'}`);

      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteChat(chat.id, chat.messages_count);
      });

      item.appendChild(titleSpan);
      item.appendChild(delBtn);

      item.addEventListener('click', () => {
        if (chat.id !== state.activeChatId) {
          activateChat(chat.id);
        }
      });

      chatsList.appendChild(item);
    });
  }

  async function activateChat(chatId) {
    if (state.isStreaming) {
      if (state.streamAbortController) {
        try { state.streamAbortController.abort(); } catch (_) {}
        state.streamAbortController = null;
      }
      state.isStreaming = false;
      updateSendButtonState();
    }

    try {
      const res = await fetch(`/api/chats/${encodeURIComponent(chatId)}/activate`, {
        method: 'POST',
        credentials: 'same-origin'
      });
      if (!res.ok) throw new Error('Activation failed');
      const data = await res.json();
      state.activeChatId = data.active_chat_id;
      state.messages = data.messages || [];
      renderChats();
      renderChatHistory();
      if (state.mode !== 'Chat') {
        switchMode('Chat');
      }
    } catch (err) {
      showToast(`Error activating chat: ${err.message}`, 'error');
    }
  }

  async function deleteChat(chatId, messagesCount) {
    if (messagesCount && messagesCount > 0) {
      if (!confirm('Are you sure you want to delete this chat thread?')) {
        return;
      }
    }

    try {
      const res = await fetch(`/api/chats/${encodeURIComponent(chatId)}`, {
        method: 'DELETE',
        credentials: 'same-origin'
      });
      if (!res.ok) throw new Error('Delete failed');
      const data = await res.json();
      state.activeChatId = data.active_chat_id;
      state.chats = data.chats || [];
      renderChats();
      // Reload active chat messages
      const activeRes = await fetch(`/api/chats/${encodeURIComponent(state.activeChatId)}/activate`, {
        method: 'POST',
        credentials: 'same-origin'
      });
      if (activeRes.ok) {
        const activeData = await activeRes.json();
        state.messages = activeData.messages || [];
      } else {
        state.messages = [];
      }
      renderChatHistory();
      showToast('Chat thread deleted', 'info');
    } catch (err) {
      showToast(`Error deleting chat: ${err.message}`, 'error');
    }
  }
```

---

## 6. Reproduce + Logs

Reproduction executed via Microsoft Edge DevTools Protocol against `http://127.0.0.1:8000` with active fixture `tests/fixtures/project_atlas_resume.pdf`.

### Sequence of Actions:
1. Document `project_atlas_resume.pdf` uploaded and indexed (1 chunk).
2. **Action 1:** Send message `"What is Project Atlas?"`.
3. **Action 2:** Click `+ New Chat` (`#new-chat-btn`).
4. **Action 3:** Send message `"What skills do I have?"`.

---

### Step-by-Step Screen Behavior & Network Details:

#### Action 1: Send Message 1
- **Network Request:**
  - **URL:** `http://127.0.0.1:8000/api/chat`
  - **Method:** `POST`
  - **Payload:** `{"question":"What is Project Atlas?"}`
  - **Response Status:** `200 OK`
  - **MIME Type:** `text/event-stream`
  - **SSE Events:**
    - `event: token` -> `Project Atlas is a data-platform migration that John Doe led...`
    - `event: done` -> `{"full_answer":"...","sources":[{"source":"project_atlas_resume.pdf",...}],"chat_id":"1d7724bd","title":"What is Project Atlas?"}`
- **Console Logs / Errors:** None.
- **On Screen:**
  - Empty hero disappears.
  - User bubble appears: `"What is Project Atlas?"`.
  - Assistant bubble streams full answer with citations dropdown (1 source).
  - Sidebar "Chats" section updates title to: `"What is Project Atlas?"` with delete `✕` button.

#### Action 2: Click "+ New Chat" Button
- **Network Request:**
  - **URL:** `http://127.0.0.1:8000/api/new_chat`
  - **Method:** `POST`
  - **Payload:** None (empty body)
  - **Response Status:** `200 OK`
  - **Response Body:**
    ```json
    {
      "ok": true,
      "chat_id": "8c41f92e",
      "title": "New chat",
      "active_chat_id": "8c41f92e",
      "chats": [
        {
          "id": "8c41f92e",
          "title": "New chat",
          "created_at": 1791265611.819,
          "updated_at": 1791265611.819,
          "preview": "",
          "messages_count": 0
        }
      ],
      "indexed_docs": [],
      "active_doc": null,
      "history_count": 0,
      "messages": []
    }
    ```
- **Console Logs / Errors:** None.
- **On Screen:**
  - Current chat conversation is cleared immediately (`messagesCount = 0`).
  - Empty hero reappears (`display: flex`).
  - **CRITICAL FAILURE:** In the sidebar under "Chats", the previous thread `"What is Project Atlas?"` **VANISHES**. It is replaced by a single entry: `"New chat"`.
  - **CRITICAL FAILURE:** Active document pill disappears (`activeDoc = null`). The uploaded document is deleted from the session.
  - The user has **NO way** to click on or navigate back to the previous conversation thread.

#### Action 3: Send Message 2
- **Network Request:**
  - **URL:** `http://127.0.0.1:8000/api/chat`
  - **Method:** `POST`
  - **Payload:** `{"question":"What skills do I have?"}`
  - **Response Status:** `200 OK`
  - **MIME Type:** `text/event-stream`
  - **SSE Events:**
    - `event: token` -> `Please upload a document (PDF, DOCX, TXT, or CSV) above to start chatting.`
    - `event: done` -> `{"full_answer":"Please upload a document...","sources":[],"chat_id":"8c41f92e","title":"New chat"}`
- **Console Logs / Errors:** None.
- **On Screen:**
  - User message bubble appears: `"What skills do I have?"`.
  - Assistant responds with `NO_DOC_MSG` because `new_chat` wiped `indexed_docs` and `vectorstore`.
  - Sidebar shows only the current `"New chat"` thread. Previous chat thread remains permanently lost.

---

### Backend Terminal Logs for the 3 Actions:

```text
=== ACTION 1: POST /api/chat ===
2026-10-06 11:17:27,016 [INFO] resume_iq_server: REWRITE sid=39f061a9 original="What is Project Atlas?" rewritten="What is Project Atlas?"
[RAG SCORES STREAM] query='What is Project Atlas?' | top_score=0.6385 | decision=PASS
2026-10-06 11:17:28,743 [INFO] uvicorn.access: 127.0.0.1:54321 - "POST /api/chat HTTP/1.1" 200 OK

=== ACTION 2: POST /api/new_chat ===
2026-10-06 11:17:28,748 [INFO] resume_iq_server: new_chat: deleted 1 chunks from vectorstore
2026-10-06 11:17:28,748 [INFO] resume_iq_server: new_chat: vectorstore confirmed empty (0 chunks remaining)
2026-10-06 11:17:28,750 [INFO] uvicorn.access: 127.0.0.1:54321 - "POST /api/new_chat HTTP/1.1" 200 OK

=== ACTION 3: POST /api/chat ===
2026-10-06 11:17:28,753 [INFO] uvicorn.access: 127.0.0.1:54321 - "POST /api/chat HTTP/1.1" 200 OK
```

---

## 7. Current vs Expected Summary

### Current Behavior (3 lines):
1. In `server.py:347-395`, `new_chat` purges all vectorstore embeddings, clears `indexed_docs = []`, and unsets `active_doc = None`.
2. In `server.py:409-411`, it executes `sess["chats"] = {chat_id: new_thread}`, completely replacing the multi-thread dictionary and deleting all prior threads from memory.
3. In `static/app.js:516-533`, it resets `state.messages = []`, replaces `state.chats` with only the new thread, and leaves the user unable to access or restore previous conversations.

### Expected Behavior (3 lines):
1. `new_chat` should preserve existing threads in `sess["chats"]`, appending a new thread (`sess["chats"][new_id] = new_thread`) and setting `sess["active_chat_id"] = new_id`.
2. Previously created threads should remain visible and selectable in the sidebar (`#chatsList`) so the user can switch between them using `activateChat()`.
3. Uploaded documents (`indexed_docs`, `vectorstore`, `active_doc`) should remain intact across threads in the same session without being wiped.
