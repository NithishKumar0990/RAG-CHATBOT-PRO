# test_upload.py
import os
from rag_pipeline import answer_question, index_uploaded_document, clear_uploaded_documents
from langchain_chroma import Chroma

def test_rag_upload():
    print("Starting U1-U5 Tests...")

    # U1: Upload & Retrieval
    print("\n--- Test U1: Upload & Retrieval ---")
    mock_text = "The new policy is that customers get a free gift with every order over 100 dollars."
    num_chunks = index_uploaded_document(mock_text)
    print(f"Indexed {num_chunks} chunks.")
    
    result = answer_question("What do customers get if they order over 100 dollars?")
    ans = result.get("answer", "").lower()
    if "gift" in ans:
        print("[PASS] U1: Uploaded document successfully retrieved and answered.")
    else:
        print("[FAIL] U1: Answer did not match expected upload content. Answer:", ans)
        
    # U2: Original FAQ continuity
    print("\n--- Test U2: Original FAQ continuity ---")
    result_faq = answer_question("How do I request a refund?")
    ans_faq = result_faq.get("answer", "").lower()
    if "refund" in ans_faq:
        print("[PASS] U2: Original FAQ is still active.")
    else:
        print("[FAIL] U2: Original FAQ retrieval failed. Answer:", ans_faq)

    # U3: Fallback / Threshold Gate
    print("\n--- Test U3: Fallback / Threshold Gate ---")
    result_fallback = answer_question("What is the distance to the moon?")
    ans_fallback = result_fallback.get("answer", "")
    if "Sorry, I don't have that information" in ans_fallback:
        print("[PASS] U3: Fallback works correctly.")
    else:
        print("[FAIL] U3: Fallback failed. Answer:", ans_fallback)

    # U4: Clear functionality
    print("\n--- Test U4: Clearing uploaded docs ---")
    clear_uploaded_documents()
    result_clear = answer_question("What do customers get if they order over 100 dollars?")
    ans_clear = result_clear.get("answer", "")
    if "Sorry, I don't have that information" in ans_clear:
        print("[PASS] U4: Cleared docs successfully. Cannot answer secret policy.")
    else:
        print("[FAIL] U4: Clearing failed. Answer:", ans_clear)

    # U5: Original FAQ continuity after clear
    print("\n--- Test U5: Original FAQ continuity after clear ---")
    result_faq2 = answer_question("How do I request a refund?")
    ans_faq2 = result_faq2.get("answer", "").lower()
    if "refund" in ans_faq2:
        print("[PASS] U5: Original FAQ still active after clearing.")
    else:
        print("[FAIL] U5: Original FAQ failed after clear. Answer:", ans_faq2)

if __name__ == "__main__":
    test_rag_upload()
