# verify_rag.py
import os
import sys
import shutil
from pathlib import Path

# Ensure UTF-8 output
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Step 1: Delete chroma_db directory to ensure fresh rebuild
CHROMA_DIR = Path(__file__).parent / "chroma_db"
if CHROMA_DIR.exists():
    print(f"Removing existing {CHROMA_DIR}...")
    shutil.rmtree(CHROMA_DIR, ignore_errors=True)

# Step 2: Import rag_pipeline (this triggers fresh vectorstore creation)
print("Importing rag_pipeline and building vectorstore...")
from rag_pipeline import answer_question

# Step 3: Run the test query
query = "How do I request a refund?"
print(f"\n--- Testing Query: '{query}' ---")
result = answer_question(query)

answer = result.get("answer", "")
sources = result.get("sources", [])

print(f"\n[ANSWER]:\n{answer}\n")
print(f"[SOURCES RETURNED]: {len(sources)} chunks\n")
for i, src in enumerate(sources, start=1):
    print(f"--- Chunk {i} ---")
    print(src.get("content", src) if isinstance(src, dict) else src)
    print()

# Step 4: Verify PASS CONDITION
pass_condition = (
    len(answer) > 0
    and "refund" in answer.lower()
    and len(sources) == 3
)

if pass_condition:
    print("=========================================")
    print(">>> VERIFICATION TEST: PASSED! <<<")
    print("=========================================")
    sys.exit(0)
else:
    print("=========================================")
    print(">>> VERIFICATION TEST: FAILED! <<<")
    print("=========================================")
    sys.exit(1)
