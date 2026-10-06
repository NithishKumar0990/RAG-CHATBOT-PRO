# diagnose_regression.py — Full regression diagnostic
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import chromadb

print("=" * 60)
print("REGRESSION DIAGNOSIS — RAG Chatbot Pro")
print("=" * 60)

# ------------------------------------------------------------------
# 1. DIFF AUDIT: Find the new fallback string
# ------------------------------------------------------------------
print("\n[1] DIFF AUDIT — Fallback string location")
import rag_pipeline
print(f"  FALLBACK_MSG = {rag_pipeline.FALLBACK_MSG!r}")
print(f"  NO_DOC_MSG   = {rag_pipeline.NO_DOC_MSG!r}")
print(f"  SIMILARITY_THRESHOLD = {rag_pipeline.SIMILARITY_THRESHOLD}")
print(f"  UPLOADED_SIMILARITY_THRESHOLD = {rag_pipeline.UPLOADED_SIMILARITY_THRESHOLD}")

# Check if there's a 'base' FAQ vectorstore or only uploaded
has_faq_vectorstore = hasattr(rag_pipeline, 'faq_vectorstore')
has_base_vectorstore = hasattr(rag_pipeline, 'base_vectorstore')
has_uploaded_vectorstore = hasattr(rag_pipeline, 'uploaded_vectorstore')
has_vectorstore = hasattr(rag_pipeline, 'vectorstore')

print(f"\n  Module attributes:")
print(f"    faq_vectorstore:      {has_faq_vectorstore}")
print(f"    base_vectorstore:     {has_base_vectorstore}")
print(f"    uploaded_vectorstore:  {has_uploaded_vectorstore}")
print(f"    vectorstore:          {has_vectorstore}")

if has_vectorstore:
    print(f"    vectorstore is uploaded_vectorstore: {rag_pipeline.vectorstore is rag_pipeline.uploaded_vectorstore}")

# ------------------------------------------------------------------
# 2. COLLECTION CHECK: Both Chroma collections
# ------------------------------------------------------------------
print("\n[2] COLLECTION CHECK — All Chroma collections")
client = chromadb.PersistentClient(path="chroma_db")
collections = client.list_collections()
print(f"  Total collections found: {len(collections)}")
for col in collections:
    count = col.count()
    print(f"    Collection '{col.name}': {count} chunks")
    if count > 0:
        data = col.peek(3)
        for i, (doc, meta) in enumerate(zip(data["documents"], data["metadatas"])):
            print(f"      Chunk {i}: meta={meta}, preview={doc[:100]!r}")

# ------------------------------------------------------------------
# 3. RETRIEVAL CHECK: similarity_search on uploaded_docs
# ------------------------------------------------------------------
print("\n[3] RETRIEVAL CHECK — similarity_search_with_relevance_scores")
from rag_pipeline import uploaded_vectorstore, SIMILARITY_THRESHOLD

# Check chunk count
try:
    doc_count = uploaded_vectorstore._collection.count()
    print(f"  uploaded_vectorstore chunk count: {doc_count}")
except Exception as e:
    print(f"  ERROR counting uploaded_vectorstore: {e}")
    doc_count = 0

if doc_count > 0:
    for query in ["skills", "name", "school", "experience"]:
        print(f"\n  Query: '{query}'")
        try:
            results = uploaded_vectorstore.similarity_search_with_relevance_scores(query, k=3)
            print(f"    Raw results (no threshold): {len(results)} chunks")
            for doc, score in results:
                passed = score >= SIMILARITY_THRESHOLD
                print(f"      score={score:.4f} (>= {SIMILARITY_THRESHOLD}? {passed}) | preview={doc.page_content[:80]!r}")
            
            # With threshold
            thresholded = uploaded_vectorstore.similarity_search_with_relevance_scores(query, k=3, score_threshold=SIMILARITY_THRESHOLD)
            print(f"    With threshold {SIMILARITY_THRESHOLD}: {len(thresholded)} chunks pass")
        except Exception as e:
            print(f"    ERROR: {e}")
else:
    print("  CRITICAL: uploaded_vectorstore is EMPTY! No document indexed.")
    print("  This is likely the ROOT CAUSE — the app requires a document upload first.")

# ------------------------------------------------------------------
# 4. SEARCH PATH CHECK: Does answer_question search uploaded_docs?
# ------------------------------------------------------------------
print("\n[4] SEARCH PATH CHECK")
print("  answer_question() searches: uploaded_vectorstore only (FAQ removed per user request)")
print(f"  Pipeline checks doc_count first — if 0, returns NO_DOC_MSG")
print(f"  If doc_count > 0, searches with threshold {SIMILARITY_THRESHOLD}")

# ------------------------------------------------------------------
# 5. LLM HEALTH CHECK
# ------------------------------------------------------------------
print("\n[5] LLM HEALTH CHECK")
from rag_pipeline import llm, llm_chain, hf_token, google_api_key
print(f"  hf_token set: {bool(hf_token)}")
print(f"  google_api_key set: {bool(google_api_key and google_api_key not in ('your_google_api_key_here', 'placeholder_key'))}")
print(f"  llm object: {type(llm).__name__ if llm else 'None'}")
print(f"  llm_chain: {'initialized' if llm_chain else 'None'}")

if llm:
    try:
        test_response = llm.invoke("Say 'hello' in one word.")
        print(f"  LLM test response: {str(test_response)[:100]!r}")
        print("  LLM STATUS: HEALTHY")
    except Exception as e:
        print(f"  LLM test FAILED: {e}")
else:
    print("  WARNING: No LLM initialized — will return raw context chunks")

# ------------------------------------------------------------------
# 6. FULL PIPELINE TEST (if docs exist)
# ------------------------------------------------------------------
print("\n[6] FULL PIPELINE TEST")
if doc_count > 0:
    result = rag_pipeline.answer_question("What are my skills?")
    print(f"  answer: {result.get('answer', '')[:200]!r}")
    print(f"  sources: {len(result.get('sources', []))} items")
    is_fallback = result.get("answer") == rag_pipeline.FALLBACK_MSG
    print(f"  IS FALLBACK? {is_fallback}")
else:
    result = rag_pipeline.answer_question("What are my skills?")
    print(f"  answer: {result.get('answer', '')[:200]!r}")
    expected_no_doc = result.get("answer") == rag_pipeline.NO_DOC_MSG
    print(f"  Returns NO_DOC_MSG (expected when empty)? {expected_no_doc}")

print("\n" + "=" * 60)
print("DIAGNOSIS COMPLETE")
print("=" * 60)
