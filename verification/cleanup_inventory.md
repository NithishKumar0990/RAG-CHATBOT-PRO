# Streamlit & Persistence Cleanup Inventory (Prompt 3.5)

## 1. Codebase Persistence Scan Results

| Path or pattern | Source (file:line) | Created by | Classification | Safe to delete? | Notes |
|---|---|---|---|---|---|
| `CHROMA_DIR = BASE_DIR / "chroma_db"` | `rag_pipeline.py:48` | Legacy Streamlit vectorstore | `VECTOR_DISK` | Yes (if found) | Legacy directory path; cleaned on pipeline import. Not present on disk. |
| `Chroma(collection_name=..., embedding_function=...)` | `rag_pipeline.py:211` | Streamlit session vectorstore getter | `PROTECTED` | No (in-memory) | In-memory Chroma vectorstore with no `persist_directory`. |
| `Chroma(collection_name=col_name, ...)` | `web_adapters.py:108` | FastAPI session factory | `PROTECTED` | No (in-memory) | Dedicated in-memory Chroma collection `sess_<sid>`. Zero disk writes. |
| `UploadedFileShim(filename, file_bytes)` | `server.py:205` | FastAPI `/api/upload` | `PROTECTED` | No (in-memory) | In-memory `io.BytesIO` wrapper for document parsing. Zero disk files written. |
| `tests/fixtures/canary_resume.pdf` | `tests/fixtures/` | Test suite fixture | `PROTECTED` | No | Required test fixture for verification suites. |
| `tests/fixtures/project_atlas_resume.pdf` | `tests/fixtures/` | Test suite fixture | `PROTECTED` | No | Required test fixture for verification suites. |
| `tests/fixtures/empty_scanned.pdf` | `tests/fixtures/` | Test suite fixture | `PROTECTED` | No | Required test fixture for verification suites. |
| `tests/fixtures/unsupported_doc.xyz` | `tests/fixtures/` | Test suite fixture | `PROTECTED` | No | Required test fixture for verification suites. |
| `sample_resume.txt` | Project root | Core demo asset | `PROTECTED` | No | Standard sample document used in testing and demo. |

---

## 2. Filesystem Sweep Inventory

### A. Project Tree (`x:/Rag_Chatbot_Pro`)

| Path or pattern | Exists | File Count | Size (Bytes) | Last Write Time | Classification | Safe to delete? | Action |
|---|---|---|---|---|---|---|---|
| `__pycache__/` (root) | Yes | 7 | 163,799 | 2026-10-05 18:49 | `BYTECODE` | Yes | DELETED |
| `tests/__pycache__/` | Yes | 3 | ~15,000 | 2026-10-05 18:44 | `BYTECODE` | Yes | DELETED |
| `ui/__pycache__/` | Yes | 2 | ~12,000 | 2026-10-03 18:10 | `BYTECODE` | Yes | DELETED |
| `.pytest_cache/` | Yes | 4 | 590 | 2026-10-05 16:53 | `BYTECODE` | Yes | DELETED |
| `.mypy_cache/` | No | 0 | 0 | — | `BYTECODE` | N/A | None |
| `.ruff_cache/` | No | 0 | 0 | — | `BYTECODE` | N/A | None |
| `.cache/` (project root) | No | 0 | 0 | — | `STREAMLIT_CACHE` | N/A | None |
| `.streamlit/` (project) | No | 0 | 0 | — | `STREAMLIT_CACHE` | N/A | Decommissioned in Part 5 & archived |
| `chroma_db/`, `.chroma/`, `chromadb/` | No | 0 | 0 | — | `VECTOR_DISK` | N/A | None on disk |
| `faiss_index/`, `faiss/` | No | 0 | 0 | — | `VECTOR_DISK` | N/A | None on disk |
| `vectorstore/`, `vectordb/`, `persist/` | No | 0 | 0 | — | `VECTOR_DISK` | N/A | None on disk |
| `uploads/`, `uploaded/`, `temp/`, `tmp/` | No | 0 | 0 | — | `UPLOAD_DISK` | N/A | None on disk |
| `*.pkl`, `session.json`, `session.pkl` | No | 0 | 0 | — | `STREAMLIT_CACHE` | N/A | None on disk |
| `scratch/edge_*` (CDP test profiles) | Yes | ~1800 | ~880 MB | 2026-10-05 18:55 | `UPLOAD_DISK` / Temp | Yes | DELETED |

### B. User-Level Directories (Windows)

| Path or pattern | Exists | File Count | Size (Bytes) | Classification | Safe to delete? | Action |
|---|---|---|---|---|---|---|
| `%USERPROFILE%\.streamlit\credentials.toml` | Yes | 1 | 49 | `STREAMLIT_CACHE` | Yes | DELETED (Telemetry only, email string) |
| `%USERPROFILE%\.streamlit\machine_id_v4` | Yes | 1 | 36 | `STREAMLIT_CACHE` | Yes | DELETED (Telemetry machine ID) |
| `%USERPROFILE%\.streamlit\cache\` | No | 0 | 0 | `STREAMLIT_CACHE` | N/A | None |
| `%USERPROFILE%\.streamlit\metrics.toml` | No | 0 | 0 | `STREAMLIT_CACHE` | N/A | None |
| `%USERPROFILE%\.streamlit\config.toml` | No | 0 | 0 | `STREAMLIT_CACHE` | N/A | None |
| `%LOCALAPPDATA%\streamlit\` | No | 0 | 0 | `STREAMLIT_CACHE` | N/A | None |
| `%APPDATA%\streamlit\` | No | 0 | 0 | `STREAMLIT_CACHE` | N/A | None |
| `%TEMP%\streamlit\` | No | 0 | 0 | `STREAMLIT_CACHE` | N/A | None |
| `%TEMP%\st_*`, `%TEMP%\*streamlit*` | No | 0 | 0 | `STREAMLIT_CACHE` | N/A | None |
| `%TEMP%\*.pdf` (upload leftovers) | No | 0 | 0 | `UPLOAD_DISK` | N/A | None |

---

## 3. Server Architecture Confirmation

- **Vectorstore Persist Directory**: Confirmed **NONE**. `server.py` and `web_adapters.py` allocate `Chroma(collection_name="sess_<sid>", embedding_function=embedding_model, collection_metadata={"hnsw:space": "cosine"})` in memory.
- **Upload Storage**: Confirmed **NONE**. File uploads are buffered into `io.BytesIO` shims, passed directly to `parse_document()`, and discarded from disk.
- **Session Eviction**: Stored in dictionary `SESSIONS` under a lock; collections destroyed on eviction or shutdown via `destroy_session_vectorstore()`.
