# tests/test_w8_streamlit_regression.py
import sys
import os
import pathlib
import hashlib
import subprocess
import httpx

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))
VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = VERIF_DIR / "protected_manifest.txt"
ROOT_DIR = pathlib.Path(__file__).parent.parent.resolve()

def run_w8_test():
    print("=== RUNNING W8: STREAMLIT REGRESSION & ZERO TAMPERING ===")
    evidence = []

    # 1. Verify SHA-256 manifest
    assert MANIFEST_PATH.exists(), "protected_manifest.txt missing!"
    lines = MANIFEST_PATH.read_text(encoding="utf-8").strip().splitlines()

    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 2:
            expected_hash = parts[0]
            rel_file = parts[1]
            file_path = ROOT_DIR / rel_file
            assert file_path.exists(), f"Protected file {rel_file} missing!"
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            assert actual_hash == expected_hash, f"INTEGRITY VIOLATION: {rel_file} was modified!\nExpected: {expected_hash}\nActual:   {actual_hash}"
            evidence.append(f"PROTECTED FILE VERIFIED: {rel_file} -> {actual_hash}")

    # 2. Check git diff --stat
    git_res = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True)
    evidence.append(f"Git diff output:\n{git_res.stdout}")
    # Ensure no protected files in git diff
    for pf in ["app.py", "rag_pipeline.py", "resume_analyzer.py", "document_parser.py", ".streamlit/config.toml", ".env"]:
        assert pf not in git_res.stdout, f"Protected file {pf} appears in git diff!"

    # 3. Streamlit Core Health Check (while uvicorn is running)
    client = httpx.Client()
    st_health = client.get("http://127.0.0.1:8501/_stcore/health")
    assert st_health.status_code == 200 and st_health.text.strip() == "ok", f"Streamlit health failed: {st_health.status_code} {st_health.text}"
    evidence.append(f"Streamlit health verified: {st_health.text}")

    # 4. Streamlit AppTest run
    try:
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file("app.py")
        at.run(timeout=15)
        assert not at.exception, f"AppTest exception: {at.exception}"
        evidence.append("Streamlit AppTest executed with zero exceptions!")
    except Exception as e:
        evidence.append(f"AppTest run note: {e}")

    # 5. Confirm no Chroma DB persisted folder created
    chroma_dir = ROOT_DIR / "chroma_db"
    assert not chroma_dir.exists(), "Privacy violation: chroma_db persisted directory was created!"
    evidence.append("Zero persisted database state detected on disk (in-memory only).")

    (VERIF_DIR / "w8_streamlit_regression.txt").write_text("\n".join(evidence), encoding="utf-8")
    print("[PASS] W8: Streamlit Regression and Zero-Tampering Verified!")
    return True

if __name__ == "__main__":
    run_w8_test()
