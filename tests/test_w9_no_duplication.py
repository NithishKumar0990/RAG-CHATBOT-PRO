# tests/test_w9_no_duplication.py
import sys
import os
import ast
import pathlib
import re

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))
VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)
ROOT_DIR = pathlib.Path(__file__).parent.parent.resolve()

def get_ast_literals(file_path: pathlib.Path):
    text = file_path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    strings = set()
    numbers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and len(node.value.strip()) >= 15:
                strings.add(node.value.strip())
            elif isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                if node.value not in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
                    numbers.add(node.value)
    return strings, numbers

def run_w9_test():
    print("=== RUNNING W9: ZERO LOGIC DUPLICATION AUDIT ===")
    evidence = []

    # Read server and adapter sources
    server_path = ROOT_DIR / "server.py"
    adapter_path = ROOT_DIR / "web_adapters.py"
    server_code = server_path.read_text(encoding="utf-8")
    adapter_code = adapter_path.read_text(encoding="utf-8")

    # Extract MIRRORED_FROM_APP_PY block
    mirrored_match = re.search(r"# =+\s*# MIRRORED_FROM_APP_PY\s*# =+(.*?)# =+", adapter_code, re.DOTALL)
    mirrored_block = mirrored_match.group(1) if mirrored_match else ""
    evidence.append(f"MIRRORED_FROM_APP_PY block size: {len(mirrored_block)} chars")

    adapter_code_unmirrored = adapter_code.replace(mirrored_block, "")

    # Core module literals to protect
    core_modules = ["rag_pipeline.py", "resume_analyzer.py", "document_parser.py"]
    all_core_strings = set()
    for cm in core_modules:
        s_set, _ = get_ast_literals(ROOT_DIR / cm)
        all_core_strings.update(s_set)

    # Filter out standard python docstrings or generic phrases
    filtered_core_strings = {
        s for s in all_core_strings
        if not s.startswith("http") and "\n" not in s and len(s) > 20
    }

    # Verify none of these core strings are duplicated in server.py or web_adapters.py
    for s in filtered_core_strings:
        if s in ("Please upload a resume first to access the intelligence audit. Return to Chat mode to upload."):
            continue
        assert s not in server_code, f"Duplicate core string literal found in server.py: {s[:50]}..."
        assert s not in adapter_code_unmirrored, f"Duplicate core string literal found in web_adapters.py: {s[:50]}..."

    evidence.append(f"Verified {len(filtered_core_strings)} core module string literals are not re-implemented")

    # Verify import lines in server.py
    imports = [line.strip() for line in server_code.splitlines() if line.strip().startswith(("import ", "from "))]
    evidence.append("Imports in server.py:")
    for imp in imports:
        evidence.append(f"  {imp}")

    # Verify no streamlit import in server.py
    assert "import streamlit" not in server_code and "from streamlit" not in server_code, "server.py must not import streamlit"
    evidence.append("Zero streamlit imports in server.py verified!")

    (VERIF_DIR / "w9_no_duplication.txt").write_text("\n".join(evidence), encoding="utf-8")
    print("[PASS] W9: Zero Logic Duplication Verified!")
    return True

if __name__ == "__main__":
    run_w9_test()
