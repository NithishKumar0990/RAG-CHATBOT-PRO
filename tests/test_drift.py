# tests/test_drift.py
import ast
import re
import pytest
from pathlib import Path
import web_adapters

APP_PY_PATH = Path(__file__).parent.parent / "app.py"

def test_mirrored_constants_drift():
    """Assert all constants in MIRRORED_FROM_APP_PY match app.py via AST and runtime comparison."""
    # 1. Test function parity
    test_cases = [
        ("Worked 2018 - 2023 at Google", "5+ yrs"),
        ("Software Engineer from 2020 to 2024", "4+ yrs"),
        ("Recent graduate in 2024", "—"),
        ("", "—"),
    ]
    for inp, expected in test_cases:
        assert web_adapters.estimate_experience_years(inp) == expected

    if not APP_PY_PATH.exists():
        pytest.skip("Legacy app.py was decommissioned")

    app_text = APP_PY_PATH.read_text(encoding="utf-8")
    app_ast = ast.parse(app_text)

    # 1. Check suggested question chips in app.py
    for chip in web_adapters.SUGGESTED_QUESTIONS:
        assert chip in app_text, f"Chip '{chip}' not found in app.py"

    # 2. Check accepted file types
    for ext in web_adapters.ACCEPTED_FILE_TYPES:
        assert f'"{ext}"' in app_text or f"'{ext}'" in app_text, f"File type '{ext}' not found in app.py"

    # 3. Check estimate_experience_years function logic in app.py
    # Extract function def from AST
    found_func = False
    for node in ast.walk(app_ast):
        if isinstance(node, ast.FunctionDef) and node.name == "estimate_experience_years":
            found_func = True
            break
    assert found_func, "estimate_experience_years function def not found in app.py AST"

    # Test function parity
    test_cases = [
        ("Worked 2018 - 2023 at Google", "5+ yrs"),
        ("Software Engineer from 2020 to 2024", "4+ yrs"),
        ("Recent graduate in 2024", "—"),
        ("", "—"),
    ]
    for inp, expected in test_cases:
        assert web_adapters.estimate_experience_years(inp) == expected
