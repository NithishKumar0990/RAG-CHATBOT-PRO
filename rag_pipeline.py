# rag_pipeline.py
"""
Document RAG Chatbot & Intelligence Pipeline Module

Tech Stack:
- LangChain Text Splitters & Prompts
- ChromaDB (via langchain_chroma)
- Embeddings: HuggingFace (sentence-transformers/all-MiniLM-L6-v2) - 100% local, fast, zero API quota
- LLM: Local Ollama / HuggingFace API / Google Gemini
"""

import os
import re
import sys
import shutil
# Attempt to import Streamlit; if unavailable, create minimal stub.
try:
    import streamlit as st
except ImportError:
    class _DummySessionState(dict):
        def __init__(self):
            super().__init__()
    class _DummyST:
        session_state = _DummySessionState()
    st = _DummyST()
import time
import warnings
from pathlib import Path
from dotenv import load_dotenv

# LangChain components
from langchain_chroma import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_huggingface import HuggingFaceEmbeddings, HuggingFaceEndpoint, ChatHuggingFace
from langchain_text_splitters import RecursiveCharacterTextSplitter

# --------------------------------------------------------------
# 1. Environment & Configuration
# --------------------------------------------------------------
load_dotenv()
hf_token = os.getenv("HF_TOKEN", "").strip()
google_api_key = os.getenv("GOOGLE_API_KEY", "").strip()

# Base paths
BASE_DIR = Path(__file__).parent.resolve()
# Directory previously used for persisted Chroma DB; now unused for session-scoped storage
CHROMA_DIR = BASE_DIR / "chroma_db"  # retained for potential cleanup
# Ensure no persisted data remains to guarantee session‑scoped isolation
if os.path.isdir(CHROMA_DIR):
    try:
        shutil.rmtree(CHROMA_DIR)
        print("[RAG INFO] Removed persisted Chroma DB folder for privacy safety.")
    except Exception as e:
        print(f"[RAG WARNING] Failed to delete persisted Chroma DB folder: {e}", file=sys.stderr)

# Cosine similarity threshold gate:
#   UPLOADED_SIMILARITY_THRESHOLD = 0.12 — garbage filter only; relevance judged by LLM
#   SIMILARITY_THRESHOLD = 0.30 — kept for any FAQ-style collections (future use)
SIMILARITY_THRESHOLD = 0.30
UPLOADED_SIMILARITY_THRESHOLD = 0.12

# Single source-of-truth messages
NO_DOC_MSG = "Please upload a document (PDF, DOCX, TXT, or CSV) above to start chatting."
# FALLBACK_MSG is built dynamically with topics — see _build_fallback_msg()
FALLBACK_MSG = "I couldn't find relevant information for that question in the uploaded document."

# Module-level topic cache: populated by index_uploaded_document()
_doc_topics: list[str] = []
_doc_filename: str = "the document"

def _build_fallback_msg(filename: str = None, topics: list[str] = None) -> str:
    """Build a helpful smart fallback with suggested topics from the indexed document."""
    fname = filename or _doc_filename or "the document"
    topic_list = topics if topics is not None else _doc_topics

    if not topic_list:
        return (
            f"I couldn't find that in **{fname}**. "
            "Try asking a more specific question about the document's contents, "
            "or upload a different document."
        )

    bullets = "\n".join(f"• {t}" for t in topic_list[:5])
    return (
        f"I couldn't find that in **{fname}**. Here's what I **can** answer about this document:\n\n"
        f"{bullets}\n\n"
        "Try one of these, or upload a different document."
    )


# --------------------------------------------------------------
# Graduated PROMPT_TEMPLATE — relevance judgment moves to the LLM
# --------------------------------------------------------------
PROMPT_TEMPLATE = """You are a helpful document assistant. Use the context below (extracted from an uploaded document) to answer the user's question.

Context:
{context}

Question: {question}

Rules — follow these in order:
1. If the context FULLY answers the question → answer clearly and concisely using only the context.
2. If the context PARTIALLY answers it → give the best answer possible from the available context; do not make up information.
3. For questions about current/ongoing employment, role, company, education, or activity: identify entries whose date range ends with 'Present' or 'Current' — that entry's company/role/institution IS the current one. Prioritize Present-marked entries over summary statements, relocation notes, or objective lines.
4. If the question is a greeting or small talk (e.g. "hi", "hello", "how are you") → reply EXACTLY: "Hi! I'm your document assistant. Ask me anything about the uploaded document 😊"
5. ONLY if the context has truly nothing related to the question → reply EXACTLY: "<<FALLBACK>>"

Do NOT mention these rules in your answer. Do NOT say "according to the context". Just answer naturally.
Answer:"""

REWRITE_PROMPT_TEMPLATE = """Given the chat history and a follow-up question, rewrite the follow-up question into a standalone question that includes the necessary topic context from the chat history.
If the follow-up question is already independent and does not refer to previous messages, output it unchanged.
If the follow-up asks about 'currently working', 'current company/role', 'working now' — expand the rewritten question with terms: 'Present current employment company role experience' to improve retrieval matching.
Output ONLY the rewritten question.

Chat History:
{history}

Follow-up Question: {question}
Standalone Question:"""

# --------------------------------------------------------------
# 2. Embedding Model (HuggingFace local)
# --------------------------------------------------------------
def _get_embedding_model():
    """
    Initialize embeddings. Uses sentence-transformers/all-MiniLM-L6-v2
    which runs 100% locally with zero external API calls or quota limits.
    Falls back gracefully to Chroma's native ONNX all-MiniLM-L6-v2 when running
    in environments with Windows Smart App Control / WDAC DLL restrictions.
    """
    try:
        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    except Exception as e:
        print(f"[RAG INFO] HuggingFaceEmbeddings unavailable ({e}), using Chroma ONNX MiniLM fallback.", file=sys.stderr)
        from langchain_core.embeddings import Embeddings
        from chromadb.utils import embedding_functions

        class ChromaONNXEmbeddings(Embeddings):
            def __init__(self):
                self.ef = embedding_functions.DefaultEmbeddingFunction()
            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                return self.ef(texts)
            def embed_query(self, text: str) -> list[float]:
                return self.ef([text])[0]

        return ChromaONNXEmbeddings()

embedding_model = _get_embedding_model()

# --------------------------------------------------------------
# 3. LLM Setup
# --------------------------------------------------------------
HF_MODEL_NAME = "meta-llama/Llama-3.1-8B-Instruct"

def _get_llm(model_name: str = HF_MODEL_NAME, max_new_tokens: int = 512, temperature: float = 0.01):
    """
    Initialize LLM with local Ollama, HuggingFace, or Gemini fallback.
    Ollama is tested with an actual invocation before being returned.
    """
    try:
        from langchain_ollama import OllamaLLM
        test_ollama = OllamaLLM(model="mistral", timeout=5)
        # Verify Ollama is actually running before committing to it
        test_ollama.invoke("hi")
        return test_ollama
    except Exception:
        print("[RAG INFO] Ollama not available, trying HuggingFace/Gemini fallback.", file=sys.stderr)

    if hf_token:
        try:
            endpoint = HuggingFaceEndpoint(
                repo_id=model_name,
                huggingfacehub_api_token=hf_token,
                temperature=temperature,
                max_new_tokens=max_new_tokens
            )
            return ChatHuggingFace(llm=endpoint)
        except Exception as e:
            print(f"[RAG WARNING] Failed to initialize HF model {model_name}: {e}", file=sys.stderr)

    if google_api_key and google_api_key not in ("your_google_api_key_here", "placeholder_key"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        print("[RAG INFO] Using Google Gemini as fallback LLM.")
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=google_api_key,
            temperature=temperature,
            max_retries=0
        )

    return None

llm = _get_llm()
llm_rewriter = _get_llm(max_new_tokens=128, temperature=0.0)

# --------------------------------------------------------------
# 4. Document Vector Store
# --------------------------------------------------------------
def _format_docs(docs) -> str:
    """Convert Document list into one clean context block for the prompt."""
    return "\n\n".join(doc.page_content for doc in docs)

def get_uploaded_vectorstore() -> Chroma:
    """Create or retrieve an in-memory Chroma vectorstore scoped to the Streamlit session.
    The store is stored in ``st.session_state`` to ensure isolation between user sessions.
    """
    if "uploaded_vectorstore" not in st.session_state:
        # Initialize a new in-memory collection (no persist_directory)
        st.session_state.uploaded_vectorstore = Chroma(
            collection_name="uploaded_docs",
            embedding_function=embedding_model,
            collection_metadata={"hnsw:space": "cosine"}
        )
    return st.session_state.uploaded_vectorstore

# Initialize session-scoped vectorstore lazily via getter
uploaded_vectorstore = get_uploaded_vectorstore()
vectorstore = uploaded_vectorstore  # alias for backwards compatibility

def _rebuild_topic_cache():
    """
    Rebuild _doc_topics and _doc_filename from the existing Chroma collection.
    Called at module load so topics survive app restarts without re-uploading.
    """
    global _doc_topics, _doc_filename
    try:
        data = uploaded_vectorstore.get()
        docs = data.get("documents", [])
        metas = data.get("metadatas", [])
        if not docs:
            return
        # Recover filename from metadata
        for m in metas:
            if m and m.get("source"):
                _doc_filename = m["source"]
                break
        _doc_topics = _extract_topics_from_chunks(docs)
        print(f"[RAG] Topic cache rebuilt from existing collection: {len(_doc_topics)} topics, file='{_doc_filename}'")
    except Exception as e:
        print(f"[RAG WARNING] Could not rebuild topic cache: {e}", file=sys.stderr)

def clear_uploaded_documents():
    """Clear all documents from the session-scoped vectorstore and reset topic cache."""
    global _doc_topics, _doc_filename
    try:
        store = get_uploaded_vectorstore()
        data = store.get()
        ids = data.get("ids", [])
        if ids:
            store.delete(ids=ids)
    except Exception as e:
        print(f"[RAG WARNING] Failed to clear uploaded documents: {e}", file=sys.stderr)
    _doc_topics = []
    _doc_filename = "the document"

def _extract_topics_from_chunks(chunks: list[str], max_topics: int = 5) -> list[str]:
    """
    Extract top meaningful topic hints from raw chunks for smart fallback.
    Skips contact/symbol lines and picks the first clean descriptive line per chunk.
    """
    # Regex: skip lines dominated by unicode symbols, emails, phone numbers, URLs
    _JUNK_RE = re.compile(r'[♂✉|/\\@+]|http|www|gmail|linkedin|github|phone|\+\d{7,}', re.IGNORECASE)
    topics = []
    seen = set()
    for chunk in chunks:
        for line in chunk.splitlines():
            line = line.strip()
            # Skip blank, very short, or symbol/contact-info lines
            if len(line) < 25:
                continue
            if _JUNK_RE.search(line):
                continue
            # Trim to a readable length
            topic = line[:90] + ("..." if len(line) > 90 else "")
            key = topic.lower()
            if key not in seen:
                seen.add(key)
                topics.append(topic)
            if len(topics) >= max_topics:
                return topics
    return topics

def delete_document_by_name(filename: str, vectorstore=None) -> int:
    """Delete all chunks for a specific filename from the session-scoped vectorstore."""
    global _doc_topics, _doc_filename
    deleted_count = 0
    try:
        store = vectorstore or get_uploaded_vectorstore()
        data = store.get(where={"source": filename})
        ids = data.get("ids", [])
        if ids:
            store.delete(ids=ids)
            deleted_count = len(ids)
            print(f"[RAG] Deleted {deleted_count} chunks for '{filename}'")
    except Exception as e:
        print(f"[RAG WARNING] Failed to delete document '{filename}': {e}", file=sys.stderr)
    _rebuild_topic_cache()
    return deleted_count

def cleanup_chroma_duplicates() -> int:
    """
    Check for duplicate chunk sets in the in-memory Chroma collection from repeated indexing.
    If duplicates are found for a source filename, they are removed and a clean re-index is performed.
    Returns the count of duplicate chunks removed.
    """
    global _doc_topics, _doc_filename
    total_removed = 0
    try:
        store = get_uploaded_vectorstore()
        data = store.get()
        ids = data.get("ids", [])
        metas = data.get("metadatas", [])
        docs = data.get("documents", [])
        if not ids:
            return 0

        # Group by source
        sources_map = {}
        for cid, meta, doc in zip(ids, metas, docs):
            src = meta.get("source", "uploaded_doc") if meta else "uploaded_doc"
            sources_map.setdefault(src, []).append({"id": cid, "meta": meta or {}, "doc": doc})

        for src, items in sources_map.items():
            chunk_indices = [item["meta"].get("chunk") for item in items if "chunk" in item["meta"]]
            has_dup_indices = len(chunk_indices) != len(set(chunk_indices))
            chunk_0_count = sum(1 for item in items if item["meta"].get("chunk") == 0)

            if has_dup_indices or chunk_0_count > 1:
                all_ids = [item["id"] for item in items]
                store.delete(ids=all_ids)

                unique_items = {}
                for item in items:
                    c_idx = item["meta"].get("chunk")
                    if c_idx is not None and c_idx not in unique_items:
                        unique_items[c_idx] = item

                sorted_chunks = [unique_items[k]["doc"] for k in sorted(unique_items.keys())]
                if sorted_chunks:
                    store.add_texts(
                        texts=sorted_chunks,
                        metadatas=[{"source": src, "chunk": i} for i in range(len(sorted_chunks))]
                    )
                dups_removed = len(all_ids) - len(sorted_chunks)
                total_removed += dups_removed
                print(f"[RAG CLEANUP] Deleted {len(all_ids)} chunks for '{src}' and re-indexed {len(sorted_chunks)} cleanly. Removed {dups_removed} duplicate chunks.")

        if total_removed > 0:
            _rebuild_topic_cache()
    except Exception as e:
        print(f"[RAG WARNING] Failed to cleanup chroma duplicates: {e}", file=sys.stderr)
    return total_removed

def index_uploaded_document(text: str, filename: str = "uploaded_doc", vectorstore=None) -> int:
    """Delete any prior chunks for this filename, chunk text, index with chunk metadata, and cache topics in the session-scoped store."""
    global _doc_topics, _doc_filename
    delete_document_by_name(filename, vectorstore=vectorstore)

    if not text.strip():
        return 0

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = splitter.split_text(text)

    if not chunks:
        return 0

    store = vectorstore or get_uploaded_vectorstore()
    store.add_texts(
        texts=chunks,
        metadatas=[{"source": filename, "chunk": i} for i in range(len(chunks))]
    )

    # Cache topics and filename for smart fallback
    _doc_filename = filename
    _doc_topics = _extract_topics_from_chunks(chunks)
    print(f"[RAG] Indexed {len(chunks)} chunks from '{filename}'. Topics cached: {_doc_topics}")
    return len(chunks)
# Rebuild topic cache on module load (survives app restarts)
_rebuild_topic_cache()

# --------------------------------------------------------------
# 5. Query Rewriting & Invocation Chains
# --------------------------------------------------------------
prompt = PromptTemplate.from_template(PROMPT_TEMPLATE)
rewrite_prompt = PromptTemplate.from_template(REWRITE_PROMPT_TEMPLATE)

llm_chain = (prompt | llm | StrOutputParser()) if llm else None
rewrite_chain = (rewrite_prompt | llm_rewriter | StrOutputParser()) if llm_rewriter else None

def _rewrite_question(question: str, history: list) -> str:
    """Rewrite follow-up question into a standalone query using conversation history."""
    q_lower = question.lower()
    is_current_work_q = any(phrase in q_lower for phrase in [
        "currently working", "current company", "current role", "working now",
        "where does he work", "where is he working", "what is his current", "who is his employer"
    ])

    if not history or not rewrite_chain:
        if is_current_work_q:
            return f"{question} Present current employment company role experience"
        return question

    history_text = ""
    for msg in history[-6:]:  # Last 3 turns
        role = "User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role}: {msg['content']}\n"

    try:
        rewritten = rewrite_chain.invoke({"history": history_text.strip(), "question": question})
        clean_rewritten = rewritten.strip().strip('"').strip("'")
        print(f"[RAG] Rewritten query: {clean_rewritten!r}")
        res = clean_rewritten if clean_rewritten else question
        if is_current_work_q and "present" not in res.lower():
            res = f"{res} Present current employment company role experience"
        return res
    except Exception as e:
        print(f"[RAG WARNING] Rewriting failed ({e}). Using original question.", file=sys.stderr)
        if is_current_work_q:
            return f"{question} Present current employment company role experience"
        return question

def _invoke_llm_with_retry(inputs: dict, retries: int = 3, base_delay: float = 2.0) -> str:
    """Invoke llm_chain with automatic retry on transient errors."""
    if not llm_chain:
        raise RuntimeError("No LLM chain initialized.")

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return str(llm_chain.invoke(inputs))
        except Exception as e:
            last_exc = e
            wait = base_delay * attempt
            print(f"[RAG RETRY] LLM error on attempt {attempt}/{retries} ({e}). Waiting {wait}s...", file=sys.stderr)
            time.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM invocation failed: retries exhausted.")

# --------------------------------------------------------------
# 6. Public Helpers: Retrieve & Answer Question
# --------------------------------------------------------------
def retrieve(query: str, k: int = 6) -> list:
    """Retrieve document chunks matching query that pass UPLOADED_SIMILARITY_THRESHOLD using the session-scoped store."""
    try:
        store = get_uploaded_vectorstore()
        scored_docs = store.similarity_search_with_relevance_scores(
            query, k=k, score_threshold=UPLOADED_SIMILARITY_THRESHOLD
        )
        return [doc for doc, _score in scored_docs]
    except Exception:
        return []

def answer_question(question: str, history: list = None, doc_name: str = None, vectorstore = None) -> dict:
    """
    Retrieve top chunks from uploaded document scored by cosine similarity,
    then generate an answer with graduated LLM judgment and structured citations.

    Args:
        question (str): User question.
        history (list): Optional chat history list of {"role": "user"|"assistant", "content": str}.
        doc_name (str): Optional active document name to isolate search to that specific document.
        vectorstore: Optional session-specific vectorstore. Defaults to uploaded_vectorstore.

    Returns:
        dict: {"answer": str, "sources": List[dict]}
    """
    try:
        # Check if active document is specified or any document is uploaded
        if not doc_name:
            return {"answer": NO_DOC_MSG, "sources": []}

        store = vectorstore or uploaded_vectorstore
        try:
            doc_count = store._collection.count()
        except Exception:
            doc_count = 0

        if doc_count == 0:
            return {"answer": NO_DOC_MSG, "sources": []}

        # Step 1: Rewrite question if history exists
        search_query = _rewrite_question(question, history)

        # Step 2: Scored similarity search (garbage filter at 0.12) isolated to active document
        search_filter = {"source": doc_name} if doc_name else None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            raw_scored = store.similarity_search_with_relevance_scores(
                search_query, k=6, filter=search_filter
            )
        all_scored = [(doc, max(0.0, min(1.0, float(sc)))) for doc, sc in raw_scored]

        # --- TASK 3: Score Logging ---
        if all_scored:
            top_score = all_scored[0][1]
            decision = "PASS" if top_score >= UPLOADED_SIMILARITY_THRESHOLD else "FILTERED"
            print(f"[RAG SCORES] query={search_query!r} | top_score={top_score:.4f} | threshold={UPLOADED_SIMILARITY_THRESHOLD} | decision={decision}")
            for i, (doc, sc) in enumerate(all_scored):
                passed = sc >= UPLOADED_SIMILARITY_THRESHOLD
                print(f"  [{i+1}] score={sc:.4f} ({'PASS' if passed else 'skip'}) | preview={doc.page_content[:70]!r}")
        else:
            print(f"[RAG SCORES] query={search_query!r} | no results returned from vectorstore")

        # Apply threshold filter
        scored_docs = [(doc, sc) for doc, sc in all_scored if sc >= UPLOADED_SIMILARITY_THRESHOLD]

        # Step 3: Threshold guard — if no chunk passes, return smart fallback
        if not scored_docs:
            fallback = _build_fallback_msg(filename=doc_name)
            return {"answer": fallback, "sources": []}

        scored_docs.sort(key=lambda x: x[1], reverse=True)
        top = scored_docs[:6]

        docs = [doc for doc, _score in top]
        context = _format_docs(docs)

        # Build structured citations
        source_items = []
        for doc, score in top:
            md = doc.metadata or {}
            source_items.append({
                "origin": "uploaded",
                "content": doc.page_content,
                "score": float(score),
                "source": md.get("source", "Uploaded Document"),
                "chunk": md.get("chunk")
            })

        # If no valid LLM token, return best chunk directly
        if not hf_token and (not google_api_key or google_api_key in ("your_google_api_key_here", "placeholder_key")):
            print("[RAG WARNING] No API token is set — returning best-match context directly.")
            best = source_items[0]
            return {
                "answer": f"Relevant information from {best.get('source', 'document')}:\n\n{best['content']}",
                "sources": source_items
            }

        # Step 4: Call LLM — if it fails, return best-match context with sources intact
        try:
            answer = _invoke_llm_with_retry({"context": context, "question": question})
            answer = (answer or "").strip()
        except Exception as llm_err:
            print(f"[RAG WARNING] LLM call failed ({llm_err}). Returning best-match context.", file=sys.stderr)
            best = source_items[0]
            return {
                "answer": f"Relevant information from {best.get('source', 'document')}:\n\n{best['content']}",
                "sources": source_items
            }

        # Step 5: Handle <<FALLBACK>> sentinel OR LLM refusal phrases
        # The LLM may say "no mention" / "not in context" instead of <<FALLBACK>>
        # — detect these and redirect to the smart fallback with topic bullets
        _REFUSAL_PHRASES = (
            "<<fallback>>",
            "no mention",
            "not mentioned",
            "not in the context",
            "not in the provided",
            "cannot find",
            "does not contain",
            "not found in",
            "no information",
            "not available in",
        )
        answer_lower = answer.lower()
        if not answer or any(p in answer_lower for p in _REFUSAL_PHRASES):
            print(f"[RAG] LLM returned refusal/fallback for query={search_query!r}. Using smart fallback.")
            fallback = _build_fallback_msg(filename=doc_name)
            return {"answer": fallback, "sources": []}

        return {"answer": answer, "sources": source_items}

    except Exception as e:
        err_str = str(e)
        print(f"[RAG ERROR] {err_str[:200]}", file=sys.stderr)
        return {"answer": _build_fallback_msg(filename=doc_name), "sources": []}


def _stream_simulated_chunks(text: str, chunk_size: int = 4, delay: float = 0.01):
    """Yield text in small simulated chunks with a tiny delay for typing animation."""
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]
        time.sleep(delay)


def stream_answer(question: str, history: list = None, sources_out: list = None, doc_name: str = None, vectorstore = None):
    """
    Generator function that yields answer tokens as they arrive via LangChain streaming.
    
    Reuses the exact same retrieval, thresholding, query rewriting, garbage filter,
    and smart fallback logic as answer_question().
    
    If sources_out (a list) is passed, it is populated with structured source dicts
    when retrieval succeeds.
    """
    if sources_out is not None:
        sources_out.clear()

    try:
        # Check if active document is specified or any document is uploaded
        if not doc_name:
            for chunk in _stream_simulated_chunks(NO_DOC_MSG):
                yield chunk
            return

        store = vectorstore or uploaded_vectorstore
        try:
            doc_count = store._collection.count()
        except Exception:
            doc_count = 0

        if doc_count == 0:
            for chunk in _stream_simulated_chunks(NO_DOC_MSG):
                yield chunk
            return

        # Step 1: Rewrite question if history exists
        search_query = _rewrite_question(question, history)

        # Step 2: Scored similarity search (garbage filter at 0.12) isolated to active document
        search_filter = {"source": doc_name} if doc_name else None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            raw_scored = store.similarity_search_with_relevance_scores(
                search_query, k=6, filter=search_filter
            )
        all_scored = [(doc, max(0.0, min(1.0, float(sc)))) for doc, sc in raw_scored]

        # Score logging
        if all_scored:
            top_score = all_scored[0][1]
            decision = "PASS" if top_score >= UPLOADED_SIMILARITY_THRESHOLD else "FILTERED"
            print(f"[RAG SCORES STREAM] query={search_query!r} | top_score={top_score:.4f} | decision={decision}")
        else:
            print(f"[RAG SCORES STREAM] query={search_query!r} | no results returned from vectorstore")

        scored_docs = [(doc, sc) for doc, sc in all_scored if sc >= UPLOADED_SIMILARITY_THRESHOLD]

        # Step 3: Threshold guard — if no chunk passes threshold, return smart fallback
        if not scored_docs:
            fallback = _build_fallback_msg(filename=doc_name)
            for chunk in _stream_simulated_chunks(fallback):
                yield chunk
            return

        scored_docs.sort(key=lambda x: x[1], reverse=True)
        top = scored_docs[:6]
        docs = [doc for doc, _score in top]
        context = _format_docs(docs)

        # Build structured citations
        source_items = []
        for doc, score in top:
            md = doc.metadata or {}
            source_items.append({
                "origin": "uploaded",
                "content": doc.page_content,
                "score": float(score),
                "source": md.get("source", "Uploaded Document"),
                "chunk": md.get("chunk")
            })

        if sources_out is not None:
            sources_out.extend(source_items)

        # If no LLM API key / token available
        if not hf_token and (not google_api_key or google_api_key in ("your_google_api_key_here", "placeholder_key")):
            print("[RAG WARNING STREAM] No API token set — returning best-match context directly.")
            best = source_items[0]
            text = f"Relevant information from {best.get('source', 'document')}:\n\n{best['content']}"
            for chunk in _stream_simulated_chunks(text):
                yield chunk
            return

        if not llm_chain:
            best = source_items[0]
            text = f"Relevant information from {best.get('source', 'document')}:\n\n{best['content']}"
            for chunk in _stream_simulated_chunks(text):
                yield chunk
            return

        # Step 4: Stream tokens via llm_chain
        _REFUSAL_PHRASES = (
            "<<fallback>>",
            "no mention",
            "not mentioned",
            "not in the context",
            "not in the provided",
            "cannot find",
            "does not contain",
            "not found in",
            "no information",
            "not available in",
        )

        try:
            stream_iter = iter(llm_chain.stream({"context": context, "question": question}))
            buffer = ""
            refusal_detected = False

            # Buffer initial tokens to detect sentinel / refusal
            for chunk in stream_iter:
                text_chunk = str(chunk)
                buffer += text_chunk
                buf_lower = buffer.strip().lower()
                if buf_lower.startswith("<<") or any(p in buf_lower for p in _REFUSAL_PHRASES):
                    refusal_detected = True
                    break
                if len(buffer) >= 25:
                    break

            if refusal_detected or any(p in buffer.lower() for p in _REFUSAL_PHRASES):
                print(f"[RAG STREAM] LLM refusal detected for query={search_query!r}. Switching to fallback.")
                if sources_out is not None:
                    sources_out.clear()
                fallback = _build_fallback_msg()
                for chunk in _stream_simulated_chunks(fallback):
                    yield chunk
                return

            if buffer:
                yield buffer

            for chunk in stream_iter:
                yield str(chunk)

        except Exception as llm_err:
            print(f"[RAG WARNING STREAM] LLM stream failed ({llm_err}). Returning best-match context.", file=sys.stderr)
            best = source_items[0]
            text = f"Relevant information from {best.get('source', 'document')}:\n\n{best['content']}"
            for chunk in _stream_simulated_chunks(text):
                yield chunk

    except Exception as e:
        print(f"[RAG ERROR STREAM] {e}", file=sys.stderr)
        if sources_out is not None:
            sources_out.clear()
        fallback = _build_fallback_msg()
        for chunk in _stream_simulated_chunks(fallback):
            yield chunk

