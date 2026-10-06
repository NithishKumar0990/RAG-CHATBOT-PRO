# Root Cause Classification (Phase 2)

## Selected Root Cause: R6 — No Thread Model (Reset is Only Behavior)

### Evidence & Analysis

1. **Code Evidence**:
   - `server.py:333`: `sess["chat_history"] = []`
   - `web_adapters.py:124`: `"chat_history": []`
   - `static/app.js:380`: `state.messages = []`
2. **Diagnosis**:
   - The user expectation is ChatGPT-style thread behavior: creating a new conversation thread while preserving older conversations in a sidebar list.
   - The application currently lacks a multi-thread data model. Each session maintains only a single global `chat_history` list.
   - When the user clicks "+New chat", the only available action is wiping `chat_history` to start over in-place.
3. **Classification**:
   - **R6 (Primary)**: No thread model implemented.
   - Secondary consideration: Query rewriting must be evaluated against the active thread only to prevent cross-thread bleed while allowing multi-turn context within a thread.
