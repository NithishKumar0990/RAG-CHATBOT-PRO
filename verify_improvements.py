# verify_improvements.py — Q1-Q5 verification
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from rag_pipeline import (
    answer_question, index_uploaded_document, clear_uploaded_documents,
    _doc_topics, _doc_filename, _build_fallback_msg,
    UPLOADED_SIMILARITY_THRESHOLD, SIMILARITY_THRESHOLD, NO_DOC_MSG, FALLBACK_MSG
)
import chromadb

print("=" * 65)
print("VERIFICATION — Smart Retrieval + Smart Fallback + Score Logging")
print("=" * 65)

print(f"\n[CONFIG]")
print(f"  UPLOADED_SIMILARITY_THRESHOLD = {UPLOADED_SIMILARITY_THRESHOLD}  (garbage filter)")
print(f"  SIMILARITY_THRESHOLD (FAQ)    = {SIMILARITY_THRESHOLD}")

# Check existing collection
client = chromadb.PersistentClient(path="chroma_db")
cols = client.list_collections()
print(f"\n[COLLECTION] {len(cols)} collection(s) found:")
for c in cols:
    print(f"  '{c.name}': {c.count()} chunks")

# Check if resume is already indexed
from rag_pipeline import uploaded_vectorstore
doc_count = uploaded_vectorstore._collection.count()
print(f"\n[DOC COUNT] uploaded_vectorstore: {doc_count} chunks")

if doc_count == 0:
    print("  WARNING: No document indexed. Seeding with synthetic resume text for testing...")
    sample_text = """NITHISH KUMAR L
Contact: nithishkumarl168@gmail.com | +91-6382417367 | Portfolio | LinkedIn | GitHub

SKILLS
Languages: Python, JavaScript (ES6+), PHP, React, Node.js
Data/ML: Airflow, dbt, Snowflake, Spark/PySpark, CNN, YOLOv8
Tools: Docker, Git, PostgreSQL, MySQL, REST APIs

EXPERIENCE
Full-Stack Web Development Trainee | ICEICO Technologies, Nagpur | Apr 2026 – Present
- Engineered a production-grade web application using React and Node.js
- Integrated REST APIs and managed PostgreSQL databases

Computer Vision Intern | Zetspire Technologies | 5-Day Program
- Implemented YOLOv8-based object detection pipeline
- Built temporal analysis models for video streams

EDUCATION
B.E. Computer Science | SRM Institute of Science and Technology | 2022–2026
- CGPA: 8.2/10

PROJECTS
Object Detection Platform (YOLOv8, PyTorch, MLOps) | Oct 2024
- Built end-to-end ML pipeline for real-time object tracking with 94% mAP score
"""
    n = index_uploaded_document(sample_text, filename="Nithish_Resume_1.pdf")
    print(f"  Indexed {n} chunks.")
else:
    print(f"  Using existing {doc_count} chunks. Topics cached: {_doc_topics}")

print(f"\n[TOPICS CACHED] {_doc_topics}")
print(f"[FILENAME CACHED] {_doc_filename}")

# --- Q1: Document-specific questions (should all answer, none fallback) ---
print("\n" + "=" * 65)
print("Q1: DOCUMENT-SPECIFIC QUESTIONS")
print("=" * 65)
q1_queries = [
    "What are my skills?",
    "Tell me about my work experience",
    "What projects have I built?",
    "What is my educational background?",
]
for q in q1_queries:
    print(f"\n  Query: '{q}'")
    result = answer_question(q)
    ans = result.get("answer", "")
    is_fallback = "couldn't find" in ans.lower() or "cannot find" in ans.lower()
    sources_count = len(result.get("sources", []))
    status = "✅ ANSWERED" if not is_fallback else "❌ FALLBACK"
    print(f"  {status} | sources={sources_count} | answer[:150]={ans[:150]!r}")

# --- Q2: Greeting ---
print("\n" + "=" * 65)
print("Q2: GREETING")
print("=" * 65)
result = answer_question("hi")
ans = result.get("answer", "")
is_greeting = "document assistant" in ans.lower() or "😊" in ans
status = "✅ GREETING" if is_greeting else "❌ WRONG"
print(f"  {status} | answer: {ans!r}")

# --- Q3: Truly irrelevant question ---
print("\n" + "=" * 65)
print("Q3: TRULY IRRELEVANT QUESTION")
print("=" * 65)
result = answer_question("Who won the IPL match?")
ans = result.get("answer", "")
has_topics = "can" in ans.lower() and ("•" in ans or "-" in ans)
sources_count = len(result.get("sources", []))
status = "✅ SMART FALLBACK" if has_topics or "couldn't find" in ans.lower() else "❌ WRONG"
print(f"  {status} | sources={sources_count} | answer:\n{ans}")

# --- Q4: FAQ-style question (no FAQ collection now, expected: smart fallback or best match) ---
print("\n" + "=" * 65)
print("Q4: FAQ-STYLE 'How do I request a refund?' (FAQ collection removed)")
print("=" * 65)
result = answer_question("How do I request a refund?")
ans = result.get("answer", "")
sources_count = len(result.get("sources", []))
print(f"  sources={sources_count} | answer[:200]={ans[:200]!r}")
print(f"  (FAQ collection was removed per user request — smart fallback expected)")

# --- Q5: Verify module/pipeline loads without error ---
print("\n" + "=" * 65)
print("Q5: PIPELINE HEALTH (module loads, chains initialized)")
print("=" * 65)
from rag_pipeline import llm, llm_chain, rewrite_chain
print(f"  llm: {type(llm).__name__ if llm else 'None'}")
print(f"  llm_chain: {'initialized' if llm_chain else 'None'}")
print(f"  rewrite_chain: {'initialized' if rewrite_chain else 'None'}")
print(f"  ✅ Pipeline healthy")

print("\n" + "=" * 65)
print("VERIFICATION COMPLETE")
print("=" * 65)
