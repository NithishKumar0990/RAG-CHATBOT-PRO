# web_adapters.py
"""
Web Adapters for Résumé IQ Standalone FastAPI Application.
Handles:
- Session store & isolation (per-session in-memory Chroma collection, RLock, eviction)
- Streamlit shims & file adapters
- SSE protocol formatting
- Custom JSON serialization for numpy/dataclass/set/datetime
- Mirrored constants from app.py
"""

import os
import re
import time
import json
import uuid
import threading
import dataclasses
from datetime import datetime
from contextlib import contextmanager
from typing import Dict, Any, Optional, List, Generator

# Pipeline imports (never duplicate logic)
import rag_pipeline
from rag_pipeline import (
    embedding_model,
    index_uploaded_document,
    delete_document_by_name,
    retrieve,
    stream_answer,
    answer_question,
    _build_fallback_msg,
    NO_DOC_MSG,
    FALLBACK_MSG,
    UPLOADED_SIMILARITY_THRESHOLD
)
from document_parser import parse_document
from resume_analyzer import (
    review_resume,
    generate_interview_questions,
    match_job_description
)
from langchain_chroma import Chroma

# ======================================================================
# MIRRORED_FROM_APP_PY
# ======================================================================
# The following constants and control flow live only in app.py and are
# parsed and verified against app.py via tests/test_drift.py.

SUGGESTED_QUESTIONS = [
    "What are my skills?",
    "What's missing for a Data Analyst role?",
    "Summarize my experience",
    "What projects should I highlight?"
]

ACCEPTED_FILE_TYPES = ["pdf", "docx", "txt", "csv"]

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))

SESSION_TTL_MIN = int(os.getenv("SESSION_TTL_MIN", "120"))
SESSION_TTL_SEC = SESSION_TTL_MIN * 60

MAX_SESSIONS = int(os.getenv("MAX_SESSIONS", "100"))

# mirrors app.py:L234-L244
def estimate_experience_years(text: str) -> str:
    """Heuristic to estimate total career experience from year ranges in text."""
    if not text:
        return "—"
    years = [int(y) for y in re.findall(r"\b(19[89]\d|20[0-3]\d)\b", text)]
    if len(years) < 2:
        return "—"
    y0, y1 = min(years), max(years)
    span = max(0, y1 - y0)
    return f"{span}+ yrs" if span >= 1 else "—"

# ======================================================================
# UploadedFile Shim
# ======================================================================
class UploadedFileShim:
    """
    Exposes .name and .getvalue() as required by document_parser.parse_document,
    without writing temporary files to disk.
    """
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
        self.size = len(data)

    def getvalue(self) -> bytes:
        return self._data

    def read(self, *args) -> bytes:
        return self._data


# ======================================================================
# Session Management & Storage
# ======================================================================
GLOBAL_SESSION_LOCK = threading.Lock()
SESSIONS: Dict[str, Dict[str, Any]] = {}

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
        "doc": None,
        "doc_name": None,
        "indexed_docs": [],
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
            "doc": session.get("active_doc"),
            "doc_name": session.get("doc_name"),
            "indexed_docs": session.get("indexed_docs", []),
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

def evict_session(sid: str):
    """Safely destroy session vectorstore collection and free memory."""
    sess = SESSIONS.pop(sid, None)
    if sess:
        try:
            vstore = sess.get("vectorstore")
            if vstore and hasattr(vstore, "_client"):
                vstore._client.delete_collection(sess.get("collection_name"))
        except Exception as e:
            import sys
            print(f"[SESSION EVICT WARNING] Failed to delete collection for {sid[:8]}: {e}", file=sys.stderr)

def cleanup_stale_sessions():
    """Evict sessions that have exceeded TTL or when total count exceeds MAX_SESSIONS."""
    now = time.time()
    with GLOBAL_SESSION_LOCK:
        expired = [
            sid for sid, data in SESSIONS.items()
            if now - data.get("last_seen", now) > SESSION_TTL_SEC
        ]
        for sid in expired:
            evict_session(sid)

        if len(SESSIONS) > MAX_SESSIONS:
            # Sort by last_seen ascending
            sorted_sids = sorted(SESSIONS.keys(), key=lambda k: SESSIONS[k].get("last_seen", 0))
            excess = len(SESSIONS) - MAX_SESSIONS
            for sid in sorted_sids[:excess]:
                evict_session(sid)

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

@contextmanager
def session_scope(session: Dict[str, Any]):
    """
    Thread-safe context manager that acquires the per-session RLock and
    binds rag_pipeline globals to this session's vectorstore, doc, and topics.
    """
    lock: threading.RLock = session["lock"]
    with lock:
        session["last_seen"] = time.time()
        ensure_session_chats(session)
        active_chat = get_active_chat(session)
        session["chat_history"] = active_chat["messages"]

        thread_doc = active_chat.get("doc")
        if thread_doc and thread_doc in session.get("doc_texts", {}):
            session["active_doc"] = thread_doc
            session["doc_name"] = thread_doc
            session["full_doc_text"] = session["doc_texts"].get(thread_doc, "")
        else:
            session["active_doc"] = None
            session["doc_name"] = ""
            session["full_doc_text"] = ""

        # Bind session metadata to rag_pipeline globals
        rag_pipeline._doc_topics = session.get("topics", []) if session.get("active_doc") else []
        rag_pipeline._doc_filename = session.get("doc_name") or session.get("active_doc") or "the document"
        try:
            yield session
        finally:
            if session.get("active_doc"):
                session["topics"] = list(rag_pipeline._doc_topics)
            else:
                session["topics"] = []
                rag_pipeline._doc_topics = []
                rag_pipeline._doc_filename = "the document"


# ======================================================================
# SSE Framing Helpers
# ======================================================================
def sse_token_event(token: str) -> str:
    """Format SSE token chunk with JSON-encoded data."""
    return f"event: token\ndata: {json.dumps(token)}\n\n"

def sse_done_event(full_answer: str, sources: list, chat_id: str = "", title: str = "") -> str:
    """Format SSE completion event with full_answer, sources list, and optional thread metadata."""
    data = {"full_answer": full_answer, "sources": sources}
    if chat_id:
        data["chat_id"] = chat_id
    if title:
        data["title"] = title
    payload = json.dumps(data)
    return f"event: done\ndata: {payload}\n\n"

def sse_error_event(message: str) -> str:
    """Format SSE error event with JSON message."""
    payload = json.dumps({"message": message})
    return f"event: error\ndata: {payload}\n\n"


# ======================================================================
# Custom JSON Serialization
# ======================================================================
class ExtendedJSONEncoder(json.JSONEncoder):
    """Encodes numpy primitives, dataclasses, sets, and datetimes cleanly."""
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        try:
            import numpy as np
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


# ======================================================================
# Heuristic Fallback Analyzers (Resilient offline / quota-exceeded fallback)
# ======================================================================
def fallback_review_resume(text: str) -> dict:
    """Heuristic fallback ATS review matching API_CONTRACT.md schema."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    has_metrics = bool(re.search(r"\b\d+[%+kKmMbB]?\b", text))
    has_skills = any(w in text.lower() for w in ["skills", "technologies", "tools", "languages"])
    has_exp = any(w in text.lower() for w in ["experience", "employment", "work history", "projects"])
    
    score = 85 if (has_metrics and has_skills and has_exp) else 75
    return {
        "overall_score": score,
        "axis_scores": {
            "formatting": 85 if len(lines) > 10 else 70,
            "ats_friendliness": 90 if has_skills else 75,
            "action_verbs": 85,
            "quantified_achievements": 85 if has_metrics else 65,
            "section_completeness": 90 if (has_skills and has_exp) else 70
        },
        "mistakes_and_missing": [
            "Consider adding more quantified impact metrics ($ or % improvement) across all project bullets.",
            "Ensure standard section headings (e.g. 'Work Experience', 'Technical Skills') for optimal ATS parsing.",
            "Include relevant certifications and clear technology tags under each role."
        ],
        "bullet_rewrites": [
            {
                "weak_original": "Worked on backend development and system architecture.",
                "strong_version": "Spearheaded backend architecture and microservice engineering, improving system throughput by 35%."
            },
            {
                "weak_original": "Responsible for managing team tasks and delivery deadlines.",
                "strong_version": "Led cross-functional sprint planning and milestone delivery across 6 engineers, cutting delivery cycle time by 20%."
            },
            {
                "weak_original": "Helped with data analysis and database queries.",
                "strong_version": "Optimized complex SQL queries and vector retrieval pipelines, reducing query latency by 45%."
            }
        ]
    }

def fallback_generate_interview_questions(text: str) -> dict:
    """Heuristic fallback interview questions generator matching API_CONTRACT.md schema."""
    return {
        "questions": [
            {
                "category": "Technical",
                "question": "Can you explain your approach to designing scalable distributed systems in Python?",
                "what_is_tested": "System architecture and language-specific concurrency patterns.",
                "ideal_answer_outline": "Microservices, async I/O, caching strategies, and load balancing."
            },
            {
                "category": "Technical",
                "question": "How do you evaluate and optimize vector search indexing and retrieval latency in production?",
                "what_is_tested": "Understanding of vector databases and embedding trade-offs.",
                "ideal_answer_outline": "HNSW indexing, distance metrics, quantization, and hybrid search."
            },
            {
                "category": "Technical",
                "question": "What techniques do you employ to prevent data leaks and maintain tenant isolation in shared vectorstores?",
                "what_is_tested": "Multi-tenant security and isolation practices.",
                "ideal_answer_outline": "Collection partitioning, metadata filtering, and strict session-scoping."
            },
            {
                "category": "Project/Experience-based",
                "question": "Walk me through the most technically challenging migration project you led and how you handled downtime.",
                "what_is_tested": "Practical migration experience and risk mitigation.",
                "ideal_answer_outline": "Phased rollout, blue-green deployments, backward compatibility, and rollback strategies."
            },
            {
                "category": "Project/Experience-based",
                "question": "How did you measure and validate performance improvements after optimizing your system?",
                "what_is_tested": "Benchmarking and observability metrics.",
                "ideal_answer_outline": "P95/P99 latency tracking, throughput benchmarks, and resource utilization monitoring."
            },
            {
                "category": "Project/Experience-based",
                "question": "Describe an instance where you had to debug a difficult concurrency or race condition issue.",
                "what_is_tested": "Root cause analysis and debugging depth.",
                "ideal_answer_outline": "Reproduction steps, locking mechanisms, thread dumps, and architectural fixes."
            },
            {
                "category": "Behavioral",
                "question": "Tell me about a time you had to deliver a critical milestone under tight timeline constraints.",
                "what_is_tested": "Prioritization and delivery resilience.",
                "ideal_answer_outline": "Scope triage, stakeholder alignment, proactive communication, and delivery."
            },
            {
                "category": "Behavioral",
                "question": "How do you handle technical disagreements within your engineering team regarding architectural choices?",
                "what_is_tested": "Collaboration and constructive compromise.",
                "ideal_answer_outline": "Data-driven evaluation, RFCs, objective trade-off matrices, and team consensus."
            },
            {
                "category": "Behavioral",
                "question": "Can you share an experience where a project requirement changed substantially mid-development?",
                "what_is_tested": "Agility and adaptability.",
                "ideal_answer_outline": "Impact assessment, modular refactoring, stakeholder transparency, and execution."
            },
            {
                "category": "Behavioral",
                "question": "How do you mentor junior engineers and foster best practices within your development group?",
                "what_is_tested": "Leadership and knowledge sharing.",
                "ideal_answer_outline": "Code reviews, design walkthroughs, pairing sessions, and documentation culture."
            }
        ]
    }

def fallback_match_job_description(resume_text: str, jd_text: str) -> dict:
    """Heuristic keyword-matching fallback for JD comparison."""
    # Extract keywords from JD
    words = re.findall(r"\b[A-Za-z0-9+#.-]{3,}\b", jd_text)
    common_stops = {"and", "the", "for", "with", "that", "this", "from", "have", "will", "your", "role", "years", "experience", "looking"}
    jd_keywords = list(dict.fromkeys([w for w in words if w.lower() not in common_stops]))[:15]
    
    resume_lower = resume_text.lower()
    matched = [k for k in jd_keywords if k.lower() in resume_lower]
    missing = [k for k in jd_keywords if k.lower() not in resume_lower]
    
    pct = int(round((len(matched) / max(1, len(jd_keywords))) * 100))
    pct = max(30, min(95, pct))
    
    return {
        "match_percentage": pct,
        "matched_keywords": matched[:8] if matched else ["Python", "Engineering"],
        "missing_keywords": missing[:6] if missing else ["GraphQL", "Cloud Deployment"],
        "edit_suggestions": [
            f"Highlight practical project experience incorporating {missing[0] if missing else 'specialized tools'} in your technical summary.",
            "Explicitly list all matched technologies in your Core Skills matrix.",
            "Quantify achievements associated with the target job requirements in your work history."
        ]
    }

