# New Chat Reproduction Findings (Phase 0)

## Step 5-7 Actual vs Expected

- **POST /api/new_chat Call**: Returned HTTP 200 OK.
- **Messages in View**: Disappeared immediately.
- **Empty State Hero**: Reappeared as expected.
- **Docs in RECENT / activeDoc**: Remained untouched (`project_atlas_resume.pdf`).
- **Old Messages / Threads**: Completely erased! No sidebar thread list or thread preservation mechanism exists.
- **State Before vs After**:
  - `history_count` before: 2
  - `history_count` after: 0
  - `chats` thread model: Absent (`chats` key not present in `/api/state`).
- **Q2 Context Isolation**:
  - Since history was wiped, Q2 ("How long did it take?") did not bleed into Project Atlas from Q1.
- **Root Symptom Confirmed**:
  - Clicking "+New chat" resets the entire conversation in-place instead of creating a new conversation thread while preserving previous threads in a sidebar thread list.
