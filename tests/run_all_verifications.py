# tests/run_all_verifications.py
import sys
import os
import pathlib
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))
VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)

from tests.test_w1_render_parity import run_w1_test
from tests.test_w2_upload_chat import run_w2_test
from tests.test_w3_streaming import run_w3_test
from tests.test_w4_guards_fallbacks import run_w4_test
from tests.test_w5_multiturn_rewrite import run_w5_test
from tests.test_w6_isolation_state import run_w6_test
from tests.test_w7_analyze import run_w7_test
from tests.test_w8_streamlit_regression import run_w8_test
from tests.test_w9_no_duplication import run_w9_test

SUITE = [
    ("W1", "Render parity (1440x900 & mobile, computed styles, zero console errors)", run_w1_test),
    ("W2", "Upload -> index -> chat (chunk equality, no duplicates, sources chip N>=1)", run_w2_test),
    ("W3", "Streaming protocol (tokens over time, in-place node replacement, single scroll)", run_w3_test),
    ("W4", "Guards & fallbacks ('hi', irrelevant Q smart fallback, no-doc guard)", run_w4_test),
    ("W5", "Multi-turn query rewrite (pronoun resolution, Q2 alone control)", run_w5_test),
    ("W6", "Session isolation & state ops (canary token protection, cross-user privacy)", run_w6_test),
    ("W7", "ATS Resume intelligence & Analyze tabs (caching, JD not indexed)", run_w7_test),
    ("W8", "Streamlit regression & manifest integrity (zero tampering)", run_w8_test),
    ("W9", "Zero logic duplication (AST literal checks, no streamlit in server)", run_w9_test),
]

def main():
    print("=" * 70)
    print("      RÉSUMÉ IQ — COMPLETE VERIFICATION SUITE (W1 - W9)")
    print("=" * 70)

    summary_rows = []
    all_passed = True

    for test_id, name, test_func in SUITE:
        print(f"\n>>> Running [{test_id}] {name}...")
        t0 = time.time()
        try:
            passed = test_func()
            duration = time.time() - t0
            status_str = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            summary_rows.append((test_id, name, status_str, f"{duration:.2f}s", f"verification/{test_id.lower()}_*.txt / .png"))
            print(f">>> [{test_id}] RESULT: {status_str} in {duration:.2f}s")
        except Exception as e:
            duration = time.time() - t0
            all_passed = False
            summary_rows.append((test_id, name, "FAIL", f"{duration:.2f}s", f"Error: {e}"))
            print(f">>> [{test_id}] RESULT: FAIL in {duration:.2f}s")
            traceback.print_exc()

    # Generate Markdown Report
    lines = [
        "# Résumé IQ — W1-W9 Verification Report",
        "",
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Overall Status**: {'ALL PASSED (100%)' if all_passed else 'SOME FAILED'}",
        "",
        "| ID | Test Suite | Status | Duration | Evidence Path |",
        "|---|---|---|---|---|"
    ]

    for row in summary_rows:
        lines.append(f"| **{row[0]}** | {row[1]} | **{row[2]}** | {row[3]} | `{row[4]}` |")

    report_content = "\n".join(lines)
    (VERIF_DIR / "VERIFICATION_REPORT.md").write_text(report_content, encoding="utf-8")
    print("\n" + "=" * 70)
    print(report_content)
    print("=" * 70)

    assert all_passed, "One or more verification tests failed!"

if __name__ == "__main__":
    main()
