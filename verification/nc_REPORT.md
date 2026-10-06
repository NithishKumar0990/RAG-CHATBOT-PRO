# Verification Report: "New Chat" Threading & Session Isolation

## (a) Root Cause Classification & Analysis

**Primary Root Cause: R6 — No thread model (reset is only behavior - missing feature)**
Prior to this fix, the application maintained only a single flat `chat_history` list per session. Clicking "+New chat" simply wiped `sess["chat_history"] = []` and reset client DOM in-place without generating a distinct thread ID or storing prior conversations.

### Code Before:
- `server.py` (legacy `new_chat`):
```python
@app.post("/api/new_chat")
def new_chat(request: Request):
    """Clear chat conversation history only. Indexed documents remain intact."""
    sess = request.state.session
    with sess["lock"]:
        sess["chat_history"] = []
        return {
            "ok": True,
            "active_doc": sess.get("active_doc"),
            "history_count": 0
        }
```
- `static/app.js` (legacy handler):
```javascript
  btnNewChat.addEventListener('click', async () => {
    state.isStreaming = false;
    ...
    await fetch('/api/new_chat', { method: 'POST' });
    state.messages = [];
    chatMessages.innerHTML = '';
    emptyHero.style.display = 'flex';
  });
```

### Code After:
- `server.py`:
  - Implemented multi-chat thread store `sess["chats"] = {chat_id: {...}}` with `active_chat_id`.
  - Added thread endpoints: `POST /api/new_chat`, `GET /api/chats`, `POST /api/chats/{chat_id}/activate`, `DELETE /api/chats/{chat_id}`.
  - Streaming in `post_chat` checks `await request.is_disconnected()` and `active_chat_id` match to avoid appending partial text on abort.
- `static/app.js`:
  - Added `state.chats` and `state.activeChatId`.
  - Added `renderChats()`, `activateChat(chatId)`, `deleteChat(chatId)`.
  - Added sidebar CHATS list above RECENT docs with truncate ~30 chars and delete 'X'.
  - `+New chat` aborts stream via `AbortController`, calls `POST /api/new_chat`, creates new thread, updates `state.chats`, and resets active view to empty hero without touching indexed documents.

---

## (b) Files Changed Summary

1. `web_adapters.py`:
   - Updated `create_session_data(sid)` to initialize `chats` dict and `active_chat_id`.
   - Added `ensure_session_chats(session)`, `get_active_chat(session)`, `get_chats_list(session)`.
   - Updated `sse_done_event` to emit optional `chat_id` and `title`.
2. `server.py`:
   - Added `uuid` and `time` imports.
   - Updated `GET /api/state` to return `chats`, `active_chat_id`, `history_count`, `messages`.
   - Rewrote `POST /api/new_chat` to instantiate a new thread and set it active without clearing docs/vectorstore.
   - Added `GET /api/chats`, `POST /api/chats/{chat_id}/activate`, `DELETE /api/chats/{chat_id}`.
   - Converted `post_chat` stream generator to `async def` with `await request.is_disconnected()` safety checks and thread title auto-naming.
3. `static/index.html`:
   - Added `chats-header` and `<div class="chats-list" id="chatsList"></div>` in sidebar above RECENT docs.
   - Ensured stable button identifier `id="new-chat-btn"`.
4. `static/style.css`:
   - Added styles for `.chats-header`, `.chats-list`, `.chat-item`, `.chat-item.active`, `.chat-title`, and `.btn-del-chat`.
5. `static/app.js`:
   - Integrated `chats` and `activeChatId` in `state`.
   - Implemented `renderChats()`, `activateChat()`, `deleteChat()`.
   - Updated `btnNewChat` handler per spec.
   - Updated SSE `done` handler to sync thread title and preview.

---

## (c) NC1–NC9 Verification Results

| ID | Test | Status | Evidence Path / Details |
|---|---|---|---|
| **NC1** | Button wired | **PASS** | `verification/nc_console_after.txt` (`POST /api/new_chat` returns HTTP 200, zero console errors) |
| **NC2** | Reset sync | **PASS** | `verification/nc_fixed_after.png`, `verification/nc_state_after.json` (frontend messages 0, backend history_count 0, hero displayed) |
| **NC3** | Docs preserved | **PASS** | `verification/nc_docs_diff.txt` (`indexed_docs` count, active doc `project_atlas_resume.pdf`, and chunk count identical) |
| **NC4** | No context bleed | **PASS** | `verification/nc_rewrite.txt` (isolated thread receives 0 history, rewriter leaves query unchanged; control session resolves context) |
| **NC5** | Threads work | **PASS** | `verification/nc_threads.png` (2 distinct threads visible in sidebar, switching restores conversation turns and sources) |
| **NC6** | Delete thread | **PASS** | Active thread deleted -> next thread auto-activated; non-active thread deleted without affecting active conversation |
| **NC7** | Race safety | **PASS** | Mid-stream `+New chat` triggers abort, disconnect detected on server, zero partial text appended to old or new thread |
| **NC8** | Reload + isolation | **PASS** | Page reload restores chats and docs from `/api/state`; independent session sees 0 documents and receives 404 attempting cross-session chat deletion |
| **NC9** | No regression | **PASS** | `tests/test_w2_upload_chat.py`, `tests/test_w4_guards_fallbacks.py`, `tests/test_w6_isolation_state.py` pass; protected file SHAs intact |

---

## (d) Legacy Streamlit (`app.py`) Comparison

In Streamlit `app.py` (archived/legacy):
```python
# Legacy app.py:
if st.sidebar.button("➕ New Chat"):
    st.session_state.chat_history = []
    st.rerun()
```
### Observation & Proposed Fix (Reference Only — Not Applied):
The legacy Streamlit app suffered from the identical bug: `st.session_state.chat_history = []` wiped the entire conversation history without any thread tracking.
**Proposed fix for Streamlit:**
```python
if st.sidebar.button("➕ New Chat"):
    new_cid = uuid.uuid4().hex[:8]
    if "chats" not in st.session_state:
        st.session_state.chats = {}
    st.session_state.chats[new_cid] = {"title": "New chat", "messages": []}
    st.session_state.active_chat_id = new_cid
    st.session_state.chat_history = st.session_state.chats[new_cid]["messages"]
    st.rerun()
```

---

## (e) Known Limitations

1. **In-Memory Thread Lifecycle:** Chat threads are held in session RAM and bounded by session TTL (60 minutes of inactivity). Threads are destroyed upon session eviction.
2. **Title Heuristic:** Chat thread titles are initialized to "New chat" and automatically set from the first 30 characters of the user's opening prompt.