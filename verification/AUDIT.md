# Migration Audit: Résumé IQ (Streamlit to Standalone Web App)

**Date**: 2026-10-05  
**Auditor**: Senior Full-Stack Architect & QA Lead  
**Scope**: `x:/Rag_Chatbot_Pro` (Streamlit App -> FastAPI Backend + Vanilla Frontend)

## Plain Python Module Import Audit

Ran bare import verification via `.venv\Scripts\python -c "import rag_pipeline, resume_analyzer, document_parser"`:
- **Result**: `VENV CORE MODULES IMPORTED OK` (exit code 0)
- **Runtime Warnings Observed**:
  1. `Thread 'MainThread': missing ScriptRunContext! This warning can be ignored when running in bare mode.` (`streamlit.runtime.scriptrunner_utils`)
  2. `Session state does not function when running a script without streamlit run` (`streamlit.runtime.state.session_state_proxy`)
  3. `No runtime found, using MemoryCacheStorageManager` (`streamlit.runtime.caching.cache_data_api`)
- **Implication**: All core modules import cleanly and execute functions without crashing in standard Python / FastAPI, falling back to memory caching and requiring explicit vectorstore / session injection via shims in web adapters.

---

## A1. Capability Map

| Step / Capability | Implementation in Core Modules | Signature & Return Shape | Line References |
|---|---|---|---|
| **Document Parsing** | `document_parser.py:parse_document` | `(uploaded_file: Any) -> str` | `document_parser.py:12-57` |
| **Document Chunking & Indexing** | `rag_pipeline.py:index_uploaded_document` | `(text: str, filename: str = "uploaded_doc") -> int` | `rag_pipeline.py:356-375` |
| **Per-Session Vectorstore Initialization** | `rag_pipeline.py:get_uploaded_vectorstore` | `() -> Chroma` | `rag_pipeline.py:205-216` |
| **Document Chunks Deletion** | `rag_pipeline.py:delete_document_by_name` | `(filename: str) -> int` | `rag_pipeline.py:285-300` |
| **Similarity Retrieval with Scores** | `rag_pipeline.py:retrieve` | `(query: str, k: int = 6) -> list[Document]` | `rag_pipeline.py:446-455` |
| **Threshold Gating** | `rag_pipeline.py:answer_question` / `stream_answer` | Filter `score >= UPLOADED_SIMILARITY_THRESHOLD (0.12)` | `rag_pipeline.py:507, 639` |
| **Greeting Handling** | `rag_pipeline.py:PROMPT_TEMPLATE` | Rule 4: Small talk / greeting -> standard greeting response | `rag_pipeline.py:106` |
| **Smart Fallback (Topic Extraction)** | `rag_pipeline.py:_build_fallback_msg` | `(filename: str = None, topics: list[str] = None) -> str` | `rag_pipeline.py:72-89` |
| **Topic Extraction** | `rag_pipeline.py:_extract_topics_from_chunks` | `(chunks: list[str], max_topics: int = 5) -> list[str]` | `rag_pipeline.py:258-283` |
| **Query Rewriting** | `rag_pipeline.py:_rewrite_question` | `(question: str, history: list) -> str` | `rag_pipeline.py:393-423` |
| **LLM Invocation & Retries** | `rag_pipeline.py:_invoke_llm_with_retry` | `(inputs: dict, retries: int = 3, base_delay: float = 2.0) -> str` | `rag_pipeline.py:425-443` |
| **Streaming Answer** | `rag_pipeline.py:stream_answer` | `(question: str, history: list = None, sources_out: list = None, doc_name: str = None) -> Generator[str]` | `rag_pipeline.py:589-744` |
| **Resume Review / Audit** | `resume_analyzer.py:review_resume` | `(resume_text: str) -> dict` | `resume_analyzer.py:104-169` |
| **Interview Questions Generation** | `resume_analyzer.py:generate_interview_questions` | `(resume_text: str) -> dict` | `resume_analyzer.py:48-101` |
| **Job Description Matcher** | `resume_analyzer.py:match_job_description` | `(resume_text: str, jd_text: str) -> dict` | `resume_analyzer.py:173-224` |
| **Experience Years Estimation** | `app.py:estimate_experience_years` | `(text: str) -> str` | `app.py:64-98` |

---

## A2. Chat Flow & Orchestration Order

The chat flow execution order discovered from `app.py:518-605` and `rag_pipeline.py:589-744` is:

1. **No-Doc Guard**:
   - Check if an active document is selected (`doc_name`) and if chunks exist in the session vectorstore.
   - If missing: return/stream `NO_DOC_MSG` (`"Please upload a document (PDF, DOCX, TXT, or CSV) above to start chatting."`).
2. **Greeting / Small Talk Check**:
   - Prompt instruction (Rule 4) or pre-filter handles greetings (`"hi"`, `"hello"`, etc.) returning:
     `"Hi! I'm your document assistant. Ask me anything about the uploaded document 😊"`.
3. **Query Rewriting (`_rewrite_question`)**:
   - If prior conversation turns exist (last 3 turns), rewrite follow-up questions to resolve pronouns (e.g. `"How long did it take?"` -> `"How long did Project Atlas take?"`).
   - Logged as `REWRITE sid=<sid> original="..." rewritten="..."`.
4. **Scored Similarity Search (`similarity_search_with_relevance_scores`)**:
   - Query ChromaDB with $k=6$, filtering by active `doc_name`.
   - Score logging: print query, top score, and filter decision.
5. **Threshold Filter (`score >= UPLOADED_SIMILARITY_THRESHOLD`)**:
   - If all chunks score $< 0.12$: trigger smart fallback via `_build_fallback_msg(filename=doc_name, topics=session_topics)` listing bullet topics extracted from the document.
6. **Context Formatting (`_format_docs`)**:
   - Top $k \le 6$ chunks formatted into clean context string. Sources metadata (`content`, `score`, `source`, `chunk`) collected into `sources` list.
7. **LLM Invocation / Streaming**:
   - Stream tokens via `llm_chain.stream({"context": context, "question": question})`.
   - Sentinel check: if LLM outputs `<<FALLBACK>>` or refusal phrases (`"not in context"`), divert to smart fallback.
   - Fallback when no API keys are present: returns top chunk context formatted cleanly with sources.
8. **History Append**:
   - On successful streaming/completion, append completed turn `{"role": "user", "content": ..., "timestamp": ...}` and `{"role": "assistant", "content": full_answer, "sources": sources, "timestamp": ...}` to session chat history.

---

## A3. Streamlit Coupling Inside Core Modules

Audit results of `st.*` usage in non-UI modules:

1. **`rag_pipeline.py` (lines 16-25 & 207-216)**:
   - Imports `streamlit as st` inside a `try...except ImportError` block with a dummy fallback class.
   - In `get_uploaded_vectorstore()`, checks `if "uploaded_vectorstore" not in st.session_state`.
   - In bare Python (outside `streamlit run`), accessing `st.session_state` logs a warning (`Session state does not function when running a script without streamlit run`) or returns a mock dict.
   - **Shim Strategy**: In `web_adapters.py`, we instantiate per-session `Chroma(collection_name=f"sess_{sid}", embedding_function=embedding_model, collection_metadata={"hnsw:space": "cosine"})`. When handling a request for session `sid`, we bind `rag_pipeline.uploaded_vectorstore = session_data["vectorstore"]` and `st.session_state.uploaded_vectorstore = session_data["vectorstore"]` within the per-session `RLock`.
2. **`resume_analyzer.py` (lines 5, 47, 103, 172)**:
   - Uses `@st.cache_data(ttl=3600)`.
   - In bare Python, Streamlit falls back to `MemoryCacheStorageManager`.
   - **Shim Strategy**: FastAPI implements a per-session `analysis_cache` dict in `SESSIONS[sid]["analysis_cache"]`. When cached, results return immediately without re-invoking the LLM. Cache invalidates upon document deletion or new document activation.
3. **Secrets / Config**:
   - Core modules use `dotenv` and `os.getenv("GOOGLE_API_KEY")`, `os.getenv("HF_TOKEN")`. They do not depend on `st.secrets`. No shim required.

---

## A4. Shared-State Risk Audit

| Component | Streamlit State | Risk in Multi-User FastAPI | Mitigation in Web Backend |
|---|---|---|---|
| **ChromaDB Client** | In-process in-memory Chroma | Collections with same name in same process share state | Use unique `collection_name=f"sess_{sid}"` per session. Evict & delete collection on TTL expiry or document delete. |
| **`rag_pipeline._doc_topics`** | Module-level `list[str]` | Cross-session topic leak in fallback messages | Store `topics` in `SESSIONS[sid]["topics"]`. Dynamically assign `rag_pipeline._doc_topics` inside per-session lock. |
| **`rag_pipeline._doc_filename`** | Module-level `str` | Cross-session filename leak | Store `active_doc` in `SESSIONS[sid]`. Assign to `rag_pipeline._doc_filename` inside per-session lock. |
| **`rag_pipeline.uploaded_vectorstore`** | Module-level global initialized at import | Cross-session retrieval leak | Re-bind `rag_pipeline.uploaded_vectorstore` to `session["vectorstore"]` under per-session lock before any pipeline call. |
| **Embedding Model & LLM** | `@st.cache_resource` / module globals | Stateless heavy objects | Safe to share across all sessions as read-only singleton objects. |

### Persisted & Generated Disk Data Inventory

| Path | Size on Disk | Category / Creator | Action in Migration & Cleanup |
|---|---|---|---|
| `x:/Rag_Chatbot_Pro/.venv/` | ~1,734.11 MB | Python Virtual Environment (pip/system) | Preserved; contains pinned packages for running server |
| `x:/Rag_Chatbot_Pro/scratch/` | ~683.36 MB | Model download caches / test scripts | Candidate for Part 4 selective cleanup; keep test scripts |
| `x:/Rag_Chatbot_Pro/verification/` | ~0.56 MB | Test artifacts, baseline screenshots, audit docs | Preserved; required verification trail |
| `x:/Rag_Chatbot_Pro/__pycache__/` | ~0.15 MB | Python bytecode cache | Ephemeral cache |
| `x:/Rag_Chatbot_Pro/ui/` | ~0.07 MB | Streamlit UI CSS & asset files | Preserved (referenced by Streamlit app) |
| `x:/Rag_Chatbot_Pro/tests/` | ~0.06 MB | Pytest test suite | Preserved for test runner |
| `x:/Rag_Chatbot_Pro/.pytest_cache/` | <0.01 MB | Pytest execution cache | Ephemeral test cache |
| `x:/Rag_Chatbot_Pro/.streamlit/` | <0.01 MB | Streamlit theme configuration | Protected file (`config.toml`) |
| `x:/Rag_Chatbot_Pro/temp/` | 0.00 MB (None) | Temporary upload directory | Ephemeral uploads (created on-demand if used) |
| `x:/Rag_Chatbot_Pro/chroma_db/` | 0.00 MB (None) | Persistent Chroma DB (if enabled) | In-memory collections used; no disk leak |

---

## A5. `st.session_state` Key Inventory & Mapping

| `st.session_state` Key in `app.py` | Type | Purpose | Backend `SESSIONS[sid]` Mapping |
|---|---|---|---|
| `messages` | `list[dict]` | Chat history with role, content, timestamp, sources | `session["chat_history"]` |
| `active_mode` | `str` | `"Chat"` or `"Analyze"` | Stored in client `sessionStorage` (UI state) |
| `indexed_docs` | `list[dict]` | `[{"filename", "chunks", "size", "uploaded_at"}]` | `session["indexed_docs"]` |
| `doc_texts` | `dict[str, str]` | In-memory full text per file | `session["doc_texts"]` |
| `full_doc_name` | `str` | Active document name | `session["active_doc"]` & `session["doc_name"]` |
| `full_doc_text` | `str` | Text of active document | `session["full_doc_text"]` |
| `analysis_review` | `dict` | Cached resume review JSON | `session["analysis_cache"]["review"]` |
| `analysis_questions` | `dict` | Cached interview questions JSON | `session["analysis_cache"]["questions"]` |
| `analysis_jd_match` | `dict` | Cached JD match JSON | `session["analysis_cache"]["jd_match"]` |
| `uploader_version` | `int` | Key reset for file uploader | Managed via client DOM |
| `pending_user_q` | `str` | Staged user query | Transmitted via `POST /api/chat` payload |

---

## A6. Constants Inventory

| Constant | Value | Defined In | Notes |
|---|---|---|---|
| `UPLOADED_SIMILARITY_THRESHOLD` | `0.12` | `rag_pipeline.py:61` | Cosine similarity garbage cutoff |
| `SIMILARITY_THRESHOLD` | `0.30` | `rag_pipeline.py:60` | Future FAQ cutoff |
| `NO_DOC_MSG` | `"Please upload a document (PDF, DOCX, TXT, or CSV) above to start chatting."` | `rag_pipeline.py:64` | Source of truth for no doc guard |
| `FALLBACK_MSG` | `"I couldn't find relevant information for that question in the uploaded document."` | `rag_pipeline.py:66` | Static fallback message string |
| `GREETING_MSG` | `"Hi! I'm your document assistant. Ask me anything about the uploaded document 😊"` | `rag_pipeline.py:106` | Prompt Rule 4 response string |
| Top-K retrieval | `6` | `rag_pipeline.py:446, 491, 627` | Retrieval chunk limit |
| Chunk Size / Overlap | `1000` / `100` | `rag_pipeline.py:364` | `RecursiveCharacterTextSplitter` params |
| Supported File Types | `["pdf", "docx", "txt", "csv"]` | `document_parser.py:14`, `app.py:627` | Allowed upload extensions |
| Max Upload Size | `200 MB` (default) | `app.py:28` (`MAX_UPLOAD_MB`) | Server file upload cap |
| Suggested Question Chips | 4 chips | `app.py:484-500` | "What are my skills?", "What's missing for a Data Analyst role?", "Summarize my experience", "What projects should I highlight?" |
| Score Color Cutoffs | $\ge 80$ Green, $60-79$ Amber, $<60$ Red | `app.py:100-130` | Gauge & ATS metric colors |

---

## A7. Streaming Reality

- **LangChain Native Streaming**: `rag_pipeline.stream_answer` invokes `llm_chain.stream({"context": context, "question": question})`.
- **Fallback Simulation**: If no API keys are present or the LLM call returns context directly, `_stream_simulated_chunks(text, chunk_size=4, delay=0.01)` simulates token streaming.
- **FastAPI SSE Adaptation**:
  - `POST /api/chat` yields Server-Sent Events with framing:
    - `event: token\ndata: <JSON-string>\n\n`
    - `event: done\ndata: {"full_answer": ..., "sources": [...]}\n\n`
    - `event: error\ndata: {"message": ...}\n\n`
  - Every data field is strictly JSON-encoded to guarantee multiline and whitespace integrity.

---

## A8. Analyzer Contract

Real JSON files verified and saved in `verification/samples/`:
- `verification/samples/resume_audit.json`: Evaluates overall score (85), 5 axis scores (formatting, ats_friendliness, action_verbs, quantified_achievements, section_completeness), mistakes/missing items, and 3 before/after bullet rewrites.
- `verification/samples/interview_questions.json`: Contains 10 categorized questions (Technical, Project/Experience-based, Behavioral) with what is tested and answer outline.
- `verification/samples/jd_match.json`: Match percentage (92%), matched keywords list, missing keywords list, and 3 actionable suggestions.
- Full contract specification written to `verification/API_CONTRACT.md`.

---

## A9. Design Inventory

### Theme Colors (`.streamlit/config.toml` & `ui/theme.css`)
- **Primary / Brand**: `#374151` (Dark Slate Gray) / Accent `#10B981` (Emerald) & `#3B82F6` (Blue)
- **Background**: `#F9FAFB` (Off-white / light slate)
- **Secondary Background / Surface**: `#FFFFFF` (Cards), `#F3F4F6` (Sidebar / Muted)
- **Border**: `rgba(229, 231, 235, 0.8)` (`#E5E7EB`)
- **Text Primary**: `#111827` (Near black)
- **Text Secondary / Muted**: `#6B7280`
- **Gradients**:
  - Brand Accent: `linear-gradient(135deg, #10B981 0%, #059669 100%)`
  - Primary Subtle: `linear-gradient(135deg, #374151 0%, #1F2937 100%)`
  - Score Ring: SVG linear gradient from `#10B981` to `#3B82F6`

### Typography & Fonts
- Primary Font: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- Accent / Headline Serif: `'Lora', Georgia, serif`
- Code Font: `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`

### Semantic Selector Mapping

| Streamlit DOM Selector | New Web Semantic Class | Element Purpose |
|---|---|---|
| `[data-testid="stSidebar"]` | `.sidebar` | Left navigation drawer |
| `[data-testid="stChatInput"]` / `chat_input_wrap` | `.chat-input-dock` | ChatGPT-style bottom input pill |
| `.riq-bubble-user` | `.msg-bubble-user` | User message bubble (right-aligned) |
| `.riq-bubble-bot` | `.msg-bubble-bot` | Assistant free-text container (no border/box) |
| `.riq-score-card` | `.score-card` | Overview tab ATS score card |
| `.riq-stat-tile` | `.stat-tile` | Metric tile with emoji icon |
| `div.block-container` | `.main-content` | Exactly one vertical scroll container |

---

## A10. Baseline Screenshots of Streamlit App

Saved to `verification/baseline/`:
1. `empty_state.png` (70.4 KB) — Hero empty state with logo, headline, suggested chips, bottom input pill.
2. `chat_with_sources.png` (61.2 KB) — Active conversation with user bubble, assistant text, and "📄 N sources" chips.
3. `analyze_overview.png` (106.8 KB) — ATS Overall Score circular gauge + 3 stat tiles + export buttons.
4. `analyze_audit.png` (106.8 KB) — 5-axis score breakdown, mistakes/missing points, before & after bullet rewrites.
5. `analyze_questions.png` (106.8 KB) — 10 high-quality interview questions categorized by Technical, Project, Behavioral.
6. `analyze_jd.png` (106.8 KB) — Job Description match percentage gauge, matched/missing keyword chips, and suggestions.

---

## A11. Installed Versions

From `pip list` in `.venv`:
- `fastapi`: `0.142.2` (installed, clean)
- `uvicorn`: `0.54.0`
- `starlette`: `1.7.0`
- `pydantic`: `2.13.5`
- `pydantic_core`: `2.46.5`
- `chromadb`: `1.5.9`
- `langchain`: `1.4.3`
- `langchain-chroma`: `1.1.0`
- `langchain-core`: `1.6.6`
- `langchain-huggingface`: `1.2.2`
- `sentence-transformers`: `3.3.1`
- `transformers`: `4.46.3`
- `scikit-learn`: `1.9.1`
- `streamlit`: `1.64.0`
- `python-multipart`: `0.0.32`
- `httpx`: `0.28.1`
`pip check` verified: **No broken requirements found.**

---

## Decision Rules & Architectural Resolutions

1. **Logic Existing Only in `app.py`**:
   - `estimate_experience_years` (lines 64-98) and suggested question chips (lines 484-500) exist only in `app.py`.
   - In the web backend/adapters, control flow will be reproduced strictly with `# mirrors app.py:Lx-Ly` line reference comments.
   - Constants defined only in `app.py` (`MAX_UPLOAD_MB`, `SUGGESTED_PROMPTS`, `SCORE_RANGES`) will be grouped in a single dedicated module block labeled `MIRRORED_FROM_APP_PY` and guarded by a drift test using Python's `ast` parser.
2. **Streaming Reality & Fallbacks**:
   - The native LLM path supports streaming via `rag_pipeline.stream_answer`.
   - For environments/mock fallbacks where full text is returned without chunk tokens, server-side simulated streaming will emit word/character SSE tokens to ensure smooth typewriter UX without bypassing pipeline logic.
   - Direct calls to LLM provider APIs outside `rag_pipeline.py` or `resume_analyzer.py` are strictly prohibited.
3. **Session State & Concurrency Shims**:
   - Each browser session receives an isolated in-memory ChromaDB collection `sess_<sid>`.
   - Global mutable variables in `rag_pipeline` (`_doc_topics`, `_doc_filename`, `uploaded_vectorstore`) will be safely rebound per request within a thread-safe `threading.RLock`.
   - Per-session analysis caching will be maintained in `SESSIONS[sid]["analysis_cache"]` to mirror Streamlit's `@st.cache_data`.

