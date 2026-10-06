# New Chat Click Path & Audit (Phase 1)

## A. Frontend (`static/app.js` + `static/index.html`)

1. **Button Binding & Selector**:
   - `static/index.html:22`: `<button class="btn-new-chat" id="btnNewChat" aria-label="Start New Chat">`
   - `static/app.js:32`: `const btnNewChat = document.getElementById('btnNewChat');`
   - Bound once on DOM initialization.
2. **Handler Implementation** (`static/app.js:359-399`):
   - Aborts in-flight stream via `state.streamAbortController.abort()`.
   - Dispatches `POST /api/new_chat` with `credentials: 'same-origin'`.
   - Awaits response. On HTTP 200, sets `state.messages = []`, `chatMessages.innerHTML = ''`, and `emptyHero.style.display = 'flex'`.
   - Resets input pill and scroll position.
3. **Parity Gap**:
   - The frontend has NO data structure for `state.chats` or `state.activeChatId`.
   - There is no sidebar container for listing chat threads.
   - Clicking New Chat simply empties the current chat pane without archiving or creating a selectable thread.

---

## B. Backend (`server.py` + `web_adapters.py`)

1. **Route Definition** (`server.py:328-338`):
   ```python
   @app.post("/api/new_chat")
   def new_chat(request: Request):
       sess = request.state.session
       with sess["lock"]:
           sess["chat_history"] = []
           return {
               "ok": True,
               "active_doc": sess.get("active_doc"),
               "history_count": 0
           }
   ```
2. **Session Storage** (`web_adapters.py:114-129`):
   - Allocates `"chat_history": []`.
   - Missing `"chats": {}` and `"active_chat_id": str`.
3. **Parity Gap**:
   - The backend only resets `sess["chat_history"] = []`. Previous conversation history is overwritten and lost rather than stored in a thread record.

---

## C. Streamlit Reference (`app.py` Legacy)

In legacy Streamlit `app.py`:
```python
if st.sidebar.button("+ New Chat"):
    st.session_state.messages = []
    st.rerun()
```
The legacy Streamlit implementation was also a destructive in-place reset. It lacked a ChatGPT-style thread model where previous conversations remain accessible in the sidebar.
