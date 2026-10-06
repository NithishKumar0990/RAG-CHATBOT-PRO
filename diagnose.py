# diagnose.py
import os
import sys
import io

# Force utf-8 stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import chromadb
from rag_pipeline import (
    embedding_model,
    uploaded_vectorstore,
    vectorstore,
    answer_question,
    SIMILARITY_THRESHOLD,
    _rewrite_question,
    _invoke_llm_with_retry,
    _format_docs
)

print("=== DIAGNOSIS RUN ===")

# Check uploaded_docs in Chroma
client = chromadb.PersistentClient(path="chroma_db")
try:
    up_col = client.get_collection("uploaded_docs")
    data = up_col.get()
    num_chunks = len(data["documents"])
    print(f"\n[STEP 2: INDEXING EVIDENCE]")
    print(f"Uploaded docs chunk count: {num_chunks}")
    for idx, (doc, meta) in enumerate(zip(data["documents"][:3], data["metadatas"][:3])):
        print(f"\n--- Chunk {idx+1} (meta={meta}) ---")
        print(doc[:300] + ("..." if len(doc) > 300 else ""))
except Exception as e:
    print(f"Error accessing uploaded_docs: {e}")

# Check total text from uploaded chunks (to inspect extraction)
full_text = "\n".join(data["documents"]) if "data" in locals() and data["documents"] else ""
print(f"\n[STEP 1: EXTRACTION EVIDENCE]")
print(f"Total reconstructed characters from chunks: {len(full_text)}")
print("First 800 chars preview:")
print(full_text[:800])

# Classification
if len(full_text.strip()) < 100:
    classification = "EMPTY (<100 chars) -> scanned/image-based PDF"
else:
    # Check if lines seem garbled or clean
    classification = "CLEAN / EXTRACTED"
print(f"Classification: {classification}")

# STEP 3: RETRIEVAL TEST
query = "What are my skills?"
print(f"\n[STEP 3: RETRIEVAL TEST for query: '{query}']")
try:
    # Let's search with no threshold first to see raw scores
    raw_results = uploaded_vectorstore.similarity_search_with_relevance_scores(query, k=5)
    print(f"Raw similarity search with relevance scores on uploaded_docs (threshold=None, k=5):")
    for doc, score in raw_results:
        passed = score >= SIMILARITY_THRESHOLD
        print(f"  Score: {score:.4f} (>= {SIMILARITY_THRESHOLD}? {passed}) | preview: {doc.page_content[:80]!r}")
        
    # Search with threshold 0.30
    scored_030 = uploaded_vectorstore.similarity_search_with_relevance_scores(query, k=3, score_threshold=SIMILARITY_THRESHOLD)
    print(f"Search with threshold {SIMILARITY_THRESHOLD}: returned {len(scored_030)} chunks")

    # Search with threshold 0.20
    scored_020 = uploaded_vectorstore.similarity_search_with_relevance_scores(query, k=3, score_threshold=0.20)
    print(f"Search with threshold 0.20: returned {len(scored_020)} chunks")
except Exception as e:
    print(f"Retrieval error: {e}")

# STEP 4: LLM TEST & PIPELINE RUN
print(f"\n[STEP 4: FULL PIPELINE / LLM TEST]")
result = answer_question(query)
print(f"Full answer_question result:")
print(f"Answer: {result.get('answer')}")
print(f"Sources count: {len(result.get('sources', []))}")
for i, s in enumerate(result.get("sources", [])):
    print(f"  Source {i+1}: {s[:100]!r}")
