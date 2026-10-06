# server.py
"""
FastAPI Server for Résumé IQ Standalone Application.
Provides complete session isolation, streaming chat via SSE, document management,
and ATS resume intelligence analysis.
"""

import os
import sys
import logging
import traceback
from pathlib import Path
from typing import Optional, Dict, Any
import uuid
import time
from datetime import datetime
from urllib.parse import urlparse

from fastapi import FastAPI, Request, Response, UploadFile, File, Form, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from starlette.middleware.base import BaseHTTPMiddleware

import web_adapters
from web_adapters import (
    SESSIONS,
    UploadedFileShim,
    get_or_create_session,
    session_scope,
    ensure_session_chats,
    get_active_chat,
    get_chats_list,
    sse_token_event,
    sse_done_event,
    sse_error_event,
    ExtendedJSONEncoder,
    SUGGESTED_QUESTIONS,
    ACCEPTED_FILE_TYPES,
    MAX_UPLOAD_MB,
    SESSION_TTL_MIN,
    estimate_experience_years,
    fallback_review_resume,
    fallback_generate_interview_questions,
    fallback_match_job_description
)
from document_parser import parse_document, parse_tabular
from resume_analyzer import (
    review_resume,
    generate_interview_questions,
    match_job_description,
    generate_resume_summary
)
import rag_pipeline
from rag_pipeline import (
    index_uploaded_document,
    index_tabular_document,
    delete_document_by_name,
    stream_answer,
    _rewrite_question,
    NO_DOC_MSG,
    FALLBACK_MSG
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("resume_iq_server")

BASE_DIR = Path(__file__).parent.resolve()
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"

app = FastAPI(
    title="Résumé IQ API",
    description="Backend API and SSE streaming for Résumé IQ Standalone Web App",
    version="1.0.0"
)

# ======================================================================
# Middleware: Session Handling & Security
# ======================================================================
class SessionSecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. CSRF / Origin Check on Mutating Requests
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")
            if origin:
                origin_host = urlparse(origin).netloc
                req_host = request.headers.get("host")
                if origin_host and req_host and origin_host.lower() != req_host.lower():
                    logger.warning(f"Forbidden Origin: {origin} vs Host: {req_host}")
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Forbidden: cross-site origin rejected"}
                    )

        # 2. Session Cookie Lookup / Minting
        cookie_sid = request.cookies.get("session_id")
        sid, session_data, is_new = get_or_create_session(cookie_sid)
        request.state.session_id = sid
        request.state.session = session_data

        # 3. Call endpoint
        response = await call_next(request)

        # 4. Refresh / set cookie on response
        is_secure = request.url.scheme == "https"
        max_age = SESSION_TTL_MIN * 60
        response.set_cookie(
            key="session_id",
            value=sid,
            max_age=max_age,
            path="/",
            httponly=True,
            samesite="lax",
            secure=is_secure
        )

        # 5. Prevent API response caching
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response

class ProcessTimeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.3f}"
        logger.info(f"{request.method} {request.url.path} completed in {process_time:.3f}s")
        return response

app.add_middleware(ProcessTimeMiddleware)
app.add_middleware(SessionSecurityMiddleware)


# ======================================================================
# Global Exception Handler
# ======================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    
    # Log full traceback on server, return clean error to client
    logger.error(f"Unhandled Exception on {request.method} {request.url.path}: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again."}
    )


# ======================================================================
# API Endpoints
# ======================================================================
@app.get("/")
def get_root():
    """Serve the single-page application index.html."""
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=404, detail="Frontend static/index.html not found")
    content = INDEX_HTML.read_text(encoding="utf-8")
    return HTMLResponse(content=content, headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def get_health():
    """Healthcheck endpoint for verification and monitoring."""
    return {"ok": True}


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

        thread_doc = active_chat.get("doc")
        if thread_doc and thread_doc in sess.get("doc_texts", {}):
            sess["active_doc"] = thread_doc
            sess["doc_name"] = thread_doc
            sess["full_doc_text"] = sess["doc_texts"].get(thread_doc, "")
            active_indexed = active_chat.get("indexed_docs", [])
            if not active_indexed:
                active_indexed = [d for d in sess.get("indexed_docs", []) if d.get("filename") == thread_doc]
        else:
            sess["active_doc"] = None
            sess["doc_name"] = ""
            sess["full_doc_text"] = ""
            active_indexed = []

        return {
            "indexed_docs": active_indexed,
            "active_doc": sess.get("active_doc"),
            "profile": sess.get("doc_profiles", {}).get(sess.get("active_doc")),
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


@app.post("/api/upload")
async def post_upload(request: Request, file: UploadFile = File(...)):
    """
    Ingest and index resume / document into the session-isolated vectorstore.
    Replicates Streamlit handle_uploaded_file behavior cleanly.
    """
    sess = request.state.session
    filename = Path(file.filename).name  # sanitize to basename
    ext = filename.split(".")[-1].lower() if "." in filename else ""

    if ext not in ACCEPTED_FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type .{ext}. Accepted: {', '.join(ACCEPTED_FILE_TYPES)}"
        )

    file_bytes = await file.read()
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload size of {MAX_UPLOAD_MB}MB."
        )

    # Wrap in BytesIO shim for document_parser
    shim = UploadedFileShim(filename, file_bytes)

    with session_scope(sess):
        if ext in ["xlsx", "csv"]:
            try:
                tabular_res = parse_tabular(shim)
            except Exception as parse_err:
                logger.warning(f"Tabular parse error for {filename}: {parse_err}")
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=str(parse_err)
                )

            df = tabular_res["dataframe"]
            sheet_name = tabular_res["sheet_name"]
            row_count = tabular_res["row_count"]
            profile = tabular_res.get("profile")

            num_chunks, total_rows = index_tabular_document(
                df,
                filename=filename,
                sheet_name=sheet_name,
                vectorstore=sess["vectorstore"]
            )

            # Build full text representation for doc_texts session memory
            parsed_text = f"Dataset: {filename} • Sheet: {sheet_name} • {total_rows} rows\n" + df.to_string(index=False, max_rows=50)
            is_tabular = True
        else:
            try:
                parsed_text, pages = parse_document(shim, return_pages=True)
            except Exception as parse_err:
                logger.warning(f"Parse error for {filename}: {parse_err}")
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Failed to parse document: {parse_err}"
                )

            if not parsed_text or len(parsed_text.strip()) < 20:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded document is empty or contains no readable text."
                )

            # Index into session store
            num_chunks = index_uploaded_document(parsed_text, filename=filename, vectorstore=sess["vectorstore"], pages=pages)
            is_tabular = False
            sheet_name = None
            row_count = None

        # Format file size
        if len(file_bytes) >= 1024 * 1024:
            size_str = f"{len(file_bytes) / (1024*1024):.1f} MB"
        else:
            size_str = f"{len(file_bytes) / 1024:.1f} KB"

        upload_time = datetime.now().strftime("%I:%M %p")

        # Update session memory
        sess["doc_texts"][filename] = parsed_text
        sess["active_doc"] = filename
        sess["doc_name"] = filename
        sess["full_doc_text"] = parsed_text

        # Invalidate analysis cache for this session
        sess["analysis_cache"].clear()

        # Update indexed_docs list (replace if already exists)
        existing_idx = None
        for i, item in enumerate(sess["indexed_docs"]):
            if item.get("filename") == filename:
                existing_idx = i
                break

        doc_entry = {
            "filename": filename,
            "chunks": num_chunks,
            "size": size_str,
            "uploaded_at": upload_time
        }
        if is_tabular:
            sess.setdefault("doc_profiles", {})[filename] = profile
            doc_entry["kind"] = "tabular"
            doc_entry["row_count"] = row_count
            doc_entry["sheet_name"] = sheet_name
            doc_entry["profile"] = profile

        if existing_idx is not None:
            sess["indexed_docs"][existing_idx] = doc_entry
        else:
            sess["indexed_docs"].append(doc_entry)

        # Bind to active chat thread
        ensure_session_chats(sess)
        active_chat = get_active_chat(sess)
        active_chat["doc"] = filename
        active_chat["doc_name"] = filename
        active_chat["indexed_docs"] = [doc_entry]

        logger.info(f"Session {sess['sid'][:8]} indexed {filename} ({num_chunks} chunks)")

        res_payload = {
            "filename": filename,
            "chunks": num_chunks,
            "indexed_docs": active_chat["indexed_docs"],
            "active_doc": sess["active_doc"]
        }
        if is_tabular:
            res_payload["kind"] = "tabular"
            res_payload["row_count"] = row_count
            res_payload["sheet_name"] = sheet_name
            res_payload["profile"] = profile

        return res_payload


@app.post("/api/doc/{filename}/activate")
def activate_doc(filename: str, request: Request):
    """Switch active document in the session."""
    sess = request.state.session
    with sess["lock"]:
        if filename not in sess.get("doc_texts", {}):
            raise HTTPException(status_code=404, detail=f"Document '{filename}' not found in this session.")
        
        sess["active_doc"] = filename
        sess["doc_name"] = filename
        sess["full_doc_text"] = sess["doc_texts"][filename]

        ensure_session_chats(sess)
        active_chat = get_active_chat(sess)
        active_chat["doc"] = filename
        active_chat["doc_name"] = filename
        matching = [d for d in sess.get("indexed_docs", []) if d.get("filename") == filename]
        active_chat["indexed_docs"] = matching

        return {
            "active_doc": filename,
            "indexed_docs": active_chat["indexed_docs"],
            "profile": sess.get("doc_profiles", {}).get(filename)
        }


@app.delete("/api/doc/{filename}")
def delete_doc(filename: str, request: Request):
    """
    Remove document chunks from session vectorstore, memory texts, and indexed list.
    If it was the active document, switch to most recent remaining or clear.
    """
    sess = request.state.session
    with session_scope(sess):
        if filename not in sess.get("doc_texts", {}):
            raise HTTPException(status_code=404, detail=f"Document '{filename}' not found in this session.")

        del_chunks = delete_document_by_name(filename, vectorstore=sess["vectorstore"])
        sess["doc_texts"].pop(filename, None)
        sess.get("doc_profiles", {}).pop(filename, None)
        sess["indexed_docs"] = [d for d in sess["indexed_docs"] if d["filename"] != filename]
        sess["analysis_cache"].clear()

        # If deleted active document, fall back to last remaining doc
        if sess.get("active_doc") == filename:
            if sess["indexed_docs"]:
                new_active = sess["indexed_docs"][-1]["filename"]
                sess["active_doc"] = new_active
                sess["doc_name"] = new_active
                sess["full_doc_text"] = sess["doc_texts"].get(new_active, "")
            else:
                sess["active_doc"] = None
                sess["doc_name"] = ""
                sess["full_doc_text"] = ""

        # Update active chat if it was bound to deleted document
        ensure_session_chats(sess)
        active_chat = get_active_chat(sess)
        if active_chat.get("doc") == filename:
            active_chat["doc"] = sess.get("active_doc")
            active_chat["doc_name"] = sess.get("doc_name")
            active_chat["indexed_docs"] = [d for d in active_chat.get("indexed_docs", []) if d.get("filename") != filename]

        logger.info(f"Session {sess['sid'][:8]} deleted {filename} ({del_chunks} chunks)")

        return {
            "deleted": filename,
            "chunks_removed": del_chunks,
            "active_doc": sess["active_doc"],
            "indexed_docs": active_chat.get("indexed_docs", [])
        }


@app.post("/api/new_chat")
def new_chat(request: Request):
    """
    Create a new chat thread and WIPE document state (vectorstore, indexed_docs, etc.)
    but PRESERVE all existing chat threads.
    """
    sess = request.state.session
    with sess["lock"]:
        # --- Wipe document state (vectorstore, indexed_docs, etc.) ---
        vstore = sess.get("vectorstore")
        if vstore is not None:
            try:
                existing = vstore.get()
                ids = existing.get("ids", []) if existing else []
                if ids:
                    vstore.delete(ids=ids)
                    logger.info(f"new_chat: deleted {len(ids)} chunks from vectorstore")

                # Verify vectorstore is completely cleared
                check = vstore.get()
                rem_ids = check.get("ids", []) if check else []
                if rem_ids:
                    logger.warning(f"new_chat: {len(rem_ids)} chunks remained after delete, recreating collection")
                    new_col_name = f"sess_{sess['sid']}_{uuid.uuid4().hex[:6]}"
                    try:
                        if hasattr(vstore, "_client"):
                            vstore._client.delete_collection(sess.get("collection_name"))
                    except Exception:
                        pass
                    sess["collection_name"] = new_col_name
                    sess["vectorstore"] = Chroma(
                        collection_name=new_col_name,
                        embedding_function=embedding_model,
                        collection_metadata={"hnsw:space": "cosine"}
                    )
                    vstore = sess["vectorstore"]
                    check2 = vstore.get()
                    if check2 and check2.get("ids"):
                        raise RuntimeError(f"Vectorstore still contains {len(check2.get('ids'))} chunks after recreation")
            except Exception as e:
                logger.error(f"new_chat: failed to clear vectorstore: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to clear vectorstore: {e}")

        # Clear document metadata
        sess["indexed_docs"] = []
        sess["doc_texts"] = {}
        sess["doc_profiles"] = {}
        sess["active_doc"] = None
        sess["full_doc_text"] = ""
        sess["doc_name"] = ""
        sess["topics"] = []
        sess["analysis_cache"] = {}

        # Reset mutable pipeline globals
        rag_pipeline._doc_topics = []
        rag_pipeline._doc_filename = "the document"

        # --- Create new chat thread (preserve existing threads) ---
        ensure_session_chats(sess)
        chat_id = uuid.uuid4().hex[:8]
        now = time.time()
        new_thread = {
            "id": chat_id,
            "title": "New chat",
            "messages": [],
            "doc": None,
            "doc_name": None,
            "indexed_docs": [],
            "created_at": now,
            "updated_at": now
        }
        sess["chats"][chat_id] = new_thread  # Append to existing threads
        sess["active_chat_id"] = chat_id
        sess["chat_history"] = new_thread["messages"]

        return {
            "ok": True,
            "chat_id": chat_id,
            "title": "New chat",
            "active_chat_id": chat_id,
            "chats": get_chats_list(sess),  # All threads (including old ones)
            "indexed_docs": [],            # Empty - no docs
            "active_doc": None,            # No active doc
            "history_count": 0,
            "messages": []
        }


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

        thread_doc = active.get("doc")
        if thread_doc and thread_doc in sess.get("doc_texts", {}):
            sess["active_doc"] = thread_doc
            sess["doc_name"] = thread_doc
            sess["full_doc_text"] = sess["doc_texts"].get(thread_doc, "")
            active_indexed = active.get("indexed_docs", [])
            if not active_indexed:
                active_indexed = [d for d in sess.get("indexed_docs", []) if d.get("filename") == thread_doc]
            rag_pipeline._doc_topics = sess.get("topics", [])
            rag_pipeline._doc_filename = thread_doc
        else:
            sess["active_doc"] = None
            sess["doc_name"] = ""
            sess["full_doc_text"] = ""
            active_indexed = []
            rag_pipeline._doc_topics = []
            rag_pipeline._doc_filename = "the document"

        return {
            "ok": True,
            "active_chat_id": chat_id,
            "title": active.get("title", "New chat"),
            "messages": active.get("messages", []),
            "history_count": len(active.get("messages", [])),
            "active_doc": sess.get("active_doc"),
            "indexed_docs": active_indexed
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
                    "doc": None,
                    "doc_name": None,
                    "indexed_docs": [],
                    "created_at": now,
                    "updated_at": now
                }
                sess["active_chat_id"] = new_id
            else:
                sorted_c = sorted(sess["chats"].values(), key=lambda x: x.get("updated_at", 0), reverse=True)
                sess["active_chat_id"] = sorted_c[0]["id"]

        active = sess["chats"][sess["active_chat_id"]]
        sess["chat_history"] = active["messages"]

        thread_doc = active.get("doc")
        if thread_doc and thread_doc in sess.get("doc_texts", {}):
            sess["active_doc"] = thread_doc
            sess["doc_name"] = thread_doc
            sess["full_doc_text"] = sess["doc_texts"].get(thread_doc, "")
            active_indexed = active.get("indexed_docs", [])
            if not active_indexed:
                active_indexed = [d for d in sess.get("indexed_docs", []) if d.get("filename") == thread_doc]
            rag_pipeline._doc_topics = sess.get("topics", [])
            rag_pipeline._doc_filename = thread_doc
        else:
            sess["active_doc"] = None
            sess["doc_name"] = ""
            sess["full_doc_text"] = ""
            active_indexed = []
            rag_pipeline._doc_topics = []
            rag_pipeline._doc_filename = "the document"

        return {
            "ok": True,
            "deleted": chat_id,
            "active_chat_id": sess["active_chat_id"],
            "chats": get_chats_list(sess),
            "active_doc": sess.get("active_doc"),
            "indexed_docs": active_indexed,
            "messages": active.get("messages", []),
            "history_count": len(active.get("messages", []))
        }


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
            ensure_session_chats(sess)
            active_chat = get_active_chat(sess)
            history = list(active_chat.get("messages", []))
            chat_id = active_chat.get("id", "")

            thread_doc = active_chat.get("doc")
            if thread_doc and thread_doc in sess.get("doc_texts", {}):
                active_doc = thread_doc
                sess["active_doc"] = thread_doc
                sess["doc_name"] = thread_doc
                sess["full_doc_text"] = sess["doc_texts"].get(thread_doc, "")
                rag_pipeline._doc_topics = sess.get("topics", [])
                rag_pipeline._doc_filename = thread_doc
            else:
                active_doc = None
                sess["active_doc"] = None
                sess["doc_name"] = ""
                sess["full_doc_text"] = ""
                rag_pipeline._doc_topics = []
                rag_pipeline._doc_filename = "the document"

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

            doc_profile = sess.get("doc_profiles", {}).get(active_doc) if active_doc else None

            # Stream tokens
            for chunk in stream_answer(
                question,
                history=history,
                sources_out=sources,
                doc_name=active_doc,
                vectorstore=sess["vectorstore"],
                doc_profile=doc_profile
            ):
                if await request.is_disconnected():
                    logger.info(f"Client disconnected mid-stream for session {sid[:8]}; saving partial answer ({len(full_answer)} chars)")
                    if full_answer:
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
            if active_doc:
                sess["topics"] = list(rag_pipeline._doc_topics)
            else:
                sess["topics"] = []
                rag_pipeline._doc_topics = []
                rag_pipeline._doc_filename = "the document"
            lock.release()

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive"
    }
    return StreamingResponse(event_stream(), headers=headers)


# ======================================================================
# Analyze Endpoints
# ======================================================================
@app.post("/api/analyze/resume")
def analyze_resume(request: Request):
    """Perform 5-axis ATS resume audit with caching."""
    sess = request.state.session
    with session_scope(sess):
        doc_text = sess.get("full_doc_text")
        if not doc_text or len(doc_text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Please upload a resume first to access the intelligence audit. Return to Chat mode to upload."
            )

        if "resume_audit" in sess["analysis_cache"]:
            return JSONResponse(content=sess["analysis_cache"]["resume_audit"])

        try:
            rev = review_resume(doc_text)
            encoded = jsonable_encoder(rev, custom_encoder={set: list})
            sess["analysis_cache"]["resume_audit"] = encoded
            return JSONResponse(content=encoded)
        except Exception as e:
            logger.warning(f"review_resume LLM call failed ({e}), using resilient heuristic fallback")
            rev = fallback_review_resume(doc_text)
            encoded = jsonable_encoder(rev, custom_encoder={set: list})
            sess["analysis_cache"]["resume_audit"] = encoded
            return JSONResponse(content=encoded)


@app.post("/api/analyze/interview_questions")
def analyze_interview_questions(request: Request):
    """Generate 10 categorized interview questions with caching."""
    sess = request.state.session
    with session_scope(sess):
        doc_text = sess.get("full_doc_text")
        if not doc_text or len(doc_text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Please upload a resume first to generate interview questions."
            )

        if "interview_questions" in sess["analysis_cache"]:
            return JSONResponse(content=sess["analysis_cache"]["interview_questions"])

        try:
            iq = generate_interview_questions(doc_text)
            encoded = jsonable_encoder(iq, custom_encoder={set: list})
            sess["analysis_cache"]["interview_questions"] = encoded
            return JSONResponse(content=encoded)
        except Exception as e:
            logger.warning(f"generate_interview_questions LLM call failed ({e}), using resilient heuristic fallback")
            iq = fallback_generate_interview_questions(doc_text)
            encoded = jsonable_encoder(iq, custom_encoder={set: list})
            sess["analysis_cache"]["interview_questions"] = encoded
            return JSONResponse(content=encoded)


@app.post("/api/analyze/jd")
async def analyze_jd(
    request: Request,
    jd_file: Optional[UploadFile] = File(None),
    jd_text: Optional[str] = Form(None)
):
    """
    Match active resume against job description.
    Job description is parsed via parse_document but NEVER indexed or added to chat state.
    """
    sess = request.state.session
    with session_scope(sess):
        resume_text = sess.get("full_doc_text")
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Please upload a resume first to match against a job description."
            )

        target_jd_text = ""
        if jd_file and jd_file.filename:
            fb = await jd_file.read()
            shim = UploadedFileShim(jd_file.filename, fb)
            target_jd_text = parse_document(shim)
        elif jd_text:
            target_jd_text = jd_text.strip()

        if not target_jd_text or len(target_jd_text.strip()) < 20:
            raise HTTPException(
                status_code=400,
                detail="Please provide a valid Job Description text or upload a JD document."
            )

        cache_key = f"jd_{hash(target_jd_text)}"
        if cache_key in sess["analysis_cache"]:
            return JSONResponse(content=sess["analysis_cache"][cache_key])

        try:
            match_res = match_job_description(resume_text, target_jd_text)
            encoded = jsonable_encoder(match_res, custom_encoder={set: list})
            sess["analysis_cache"][cache_key] = encoded
            return JSONResponse(content=encoded)
        except Exception as e:
            logger.warning(f"match_job_description LLM call failed ({e}), using resilient heuristic fallback")
            match_res = fallback_match_job_description(resume_text, target_jd_text)
            encoded = jsonable_encoder(match_res, custom_encoder={set: list})
            sess["analysis_cache"][cache_key] = encoded
            return JSONResponse(content=encoded)


@app.post("/api/analyze/summary")
def analyze_summary(request: Request, jd_text: Optional[str] = Form(None)):
    """Generate a tailored professional summary."""
    sess = request.state.session
    with session_scope(sess):
        resume_text = sess.get("full_doc_text")
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(status_code=400, detail="Please upload a resume first.")

        try:
            summary_data = generate_resume_summary(resume_text, jd_text or "")
            return JSONResponse(content=jsonable_encoder(summary_data))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Summary generation failed: {str(e)}")


# ======================================================================
# Mount Static Files (AFTER API routes)
# ======================================================================
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
