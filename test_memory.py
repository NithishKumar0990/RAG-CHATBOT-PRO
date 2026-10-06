# test_memory.py
import sys
import json
from rag_pipeline import answer_question, FALLBACK_MSG

def run_tests():
    print("--- V1: Turn 1 ---")
    res1 = answer_question("How do I request a refund?")
    print("Q: How do I request a refund?")
    print("A:", res1['answer'])
    
    history = [
        {"role": "user", "content": "How do I request a refund?"},
        {"role": "assistant", "content": res1['answer']}
    ]
    
    print("\n--- V2: Turn 2 ---")
    res2 = answer_question("How long does it take?", history=history)
    print("Q: How long does it take?")
    print("A:", res2['answer'])
    
    print("\n--- V3: Fresh session 'hi' ---")
    res3 = answer_question("hi", history=[])
    print("Q: hi")
    print("A:", res3['answer'])
    
    print("\n--- V4: Fresh session 'Can I pay with Bitcoin?' ---")
    res4 = answer_question("Can I pay with Bitcoin?", history=[])
    print("Q: Can I pay with Bitcoin?")
    print("A:", res4['answer'])

    print("\n--- V4 (Literal): Fresh session 'Can I pay with PayPal?' ---")
    res5 = answer_question("Can I pay with PayPal?", history=[])
    print("Q: Can I pay with PayPal?")
    print("A:", res5['answer'])

if __name__ == "__main__":
    run_tests()
