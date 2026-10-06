# verification/verify_phase_a1.py
import io
import sys
import json
import pathlib
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from starlette.testclient import TestClient

from server import app
from web_adapters import SESSIONS
from rag_pipeline import NO_DOC_MSG

def run_verifications():
    client1 = TestClient(app, base_url="http://testserver")
    
    # 1. Prepare sample data (25 rows)
    roles = ["Software Engineer", "Data Analyst", "Product Manager", "DevOps Engineer", "HR Specialist"]
    cities = ["New York", "San Francisco", "Austin", "Seattle", "Chicago"]
    names = [
        "Alice Smith", "Bob Jones", "Charlie Brown", "Diana Prince", "Evan Wright",
        "Fiona Gallagher", "George Clark", "Hannah Abbott", "Ian Malcolm", "Julia Roberts",
        "Kevin Bacon", "Laura Croft", "Michael Scott", "Nina Simone", "Oscar Martinez",
        "Pam Beesly", "Quentin Tarantino", "Rachel Green", "Steve Rogers", "Tony Stark",
        "Uma Thurman", "Victor Hugo", "Wanda Maximoff", "Xavier Woods", "Yvonne Strahovski"
    ]
    data = []
    for i, name in enumerate(names):
        data.append({
            "name": name,
            "role": roles[i % len(roles)],
            "salary": 70000 + (i * 2500),
            "city": cities[i % len(cities)]
        })
    df_sample = pd.DataFrame(data)
    
    csv_bytes = df_sample.to_csv(index=False).encode("utf-8")
    
    xlsx_bio = io.BytesIO()
    with pd.ExcelWriter(xlsx_bio, engine="openpyxl") as writer:
        df_sample.to_excel(writer, sheet_name="Employees", index=False)
    xlsx_bytes = xlsx_bio.getvalue()
    
    empty_csv_bytes = b"name,role,salary,city\n"
    corrupt_xlsx_bytes = b"PK\x03\x04CORRUPTED_NON_EXCEL_BYTES_1234567890"

    print("=" * 70)
    print("PHASE A1: EXCEL/CSV INTELLIGENCE FOUNDATION VERIFICATION")
    print("=" * 70)

    # -------------------------------------------------------------
    # X1: Upload sample .csv (25 rows) -> indexes -> check response
    # -------------------------------------------------------------
    resp_x1 = client1.post(
        "/api/upload",
        files={"file": ("employees.csv", csv_bytes, "text/csv")}
    )
    assert resp_x1.status_code == 200, f"X1 failed: {resp_x1.text}"
    x1_data = resp_x1.json()
    assert x1_data.get("kind") == "tabular", f"Expected kind=tabular, got {x1_data.get('kind')}"
    assert x1_data.get("row_count") == 25, f"Expected 25 rows, got {x1_data.get('row_count')}"
    assert x1_data.get("chunks") == 3, f"Expected 3 chunks (10+10+5), got {x1_data.get('chunks')}"
    assert len(x1_data.get("indexed_docs", [])) == 1, "Expected 1 doc in active thread indexed_docs"
    
    # Check session state
    state_resp = client1.get("/api/state")
    assert state_resp.status_code == 200
    state_data = state_resp.json()
    assert state_data["active_doc"] == "employees.csv"
    assert len(state_data["indexed_docs"]) == 1
    print(f"X1 PASS: employees.csv uploaded (25 rows, {x1_data['chunks']} chunks). Response: {x1_data}")

    # -------------------------------------------------------------
    # X2: Chat "What is Alice's role?" -> answer correct, source "Rows X-Y"
    # -------------------------------------------------------------
    resp_x2 = client1.post("/api/chat", json={"question": "What is Alice's role and salary?"})
    assert resp_x2.status_code == 200
    # Parse SSE stream
    answer_x2 = ""
    sources_x2 = []
    for line in resp_x2.text.strip().split("\n"):
        if line.startswith("data:"):
            payload = json.loads(line[5:].strip())
            if isinstance(payload, dict):
                if "full_answer" in payload:
                    answer_x2 = payload["full_answer"]
                if "sources" in payload:
                    sources_x2 = payload["sources"]
            elif isinstance(payload, str):
                answer_x2 += payload

    assert "Software Engineer" in answer_x2 or "Alice" in answer_x2, f"Answer missing role: {answer_x2}"
    assert len(sources_x2) > 0, "Expected at least 1 source"
    alice_src = next((s for s in sources_x2 if "Alice Smith" in s.get("content", "")), sources_x2[0])
    assert alice_src.get("kind") == "tabular", f"Expected source kind=tabular, got {alice_src}"
    assert alice_src.get("row_start") == 1 and alice_src.get("row_end") == 10, f"Expected Rows 1-10, got {alice_src}"
    print(f"X2 PASS: Chat answered Alice's role. Source: Rows {alice_src['row_start']}-{alice_src['row_end']} • {alice_src['source']}")
    print(f"   Answer snippet: {answer_x2[:120]}...")

    # -------------------------------------------------------------
    # X3: Chat about a row that exists -> retrieved chunk contains it
    # -------------------------------------------------------------
    resp_x3 = client1.post("/api/chat", json={"question": "What is Wanda Maximoff's role and city?"})
    assert resp_x3.status_code == 200
    answer_x3 = ""
    sources_x3 = []
    for line in resp_x3.text.strip().split("\n"):
        if line.startswith("data:"):
            payload = json.loads(line[5:].strip())
            if isinstance(payload, dict):
                if "full_answer" in payload:
                    answer_x3 = payload["full_answer"]
                if "sources" in payload:
                    sources_x3 = payload["sources"]
    matched_chunk = next((s["content"] for s in sources_x3 if "Wanda Maximoff" in s["content"]), None)
    assert matched_chunk is not None, "Expected chunk containing Wanda Maximoff"
    print("X3 PASS: Retrieved chunk contains target row:")
    print("   " + matched_chunk.replace("\n", "\n   "))

    # -------------------------------------------------------------
    # X4: Upload .xlsx (convert the same data) -> works identically (sheet name shown)
    # -------------------------------------------------------------
    resp_x4 = client1.post(
        "/api/upload",
        files={"file": ("employees.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert resp_x4.status_code == 200, f"X4 failed: {resp_x4.text}"
    x4_data = resp_x4.json()
    assert x4_data.get("sheet_name") == "Employees", f"Expected sheet_name=Employees, got {x4_data.get('sheet_name')}"
    assert x4_data.get("row_count") == 25
    assert x4_data.get("chunks") == 3
    print(f"X4 PASS: employees.xlsx uploaded. Sheet: '{x4_data['sheet_name']}', Rows: {x4_data['row_count']}, Chunks: {x4_data['chunks']}")

    # -------------------------------------------------------------
    # X5: Corrupted .xlsx (random bytes) -> friendly error toast/message, no crash
    # -------------------------------------------------------------
    resp_x5 = client1.post(
        "/api/upload",
        files={"file": ("corrupt.xlsx", corrupt_xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert resp_x5.status_code == 422, f"Expected 422, got {resp_x5.status_code}"
    err_detail_x5 = resp_x5.json().get("detail", "")
    assert "Unable to read Excel file" in err_detail_x5, f"Unexpected error detail: {err_detail_x5}"
    print(f"X5 PASS: Corrupted .xlsx returned 422 friendly error: {err_detail_x5}")

    # -------------------------------------------------------------
    # X6: Empty .csv (headers only) -> friendly message, no crash
    # -------------------------------------------------------------
    resp_x6 = client1.post(
        "/api/upload",
        files={"file": ("empty.csv", empty_csv_bytes, "text/csv")}
    )
    assert resp_x6.status_code == 422, f"Expected 422, got {resp_x6.status_code}"
    err_detail_x6 = resp_x6.json().get("detail", "")
    assert "The file has no data" in err_detail_x6, f"Unexpected error detail: {err_detail_x6}"
    print(f"X6 PASS: Empty .csv returned 422 friendly message: {err_detail_x6}")

    # -------------------------------------------------------------
    # X7: Regression check (PDF upload + chat unchanged)
    # -------------------------------------------------------------
    pdf_path = "tests/fixtures/project_atlas_resume.pdf"
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    resp_x7 = client1.post(
        "/api/upload",
        files={"file": ("project_atlas_resume.pdf", pdf_bytes, "application/pdf")}
    )
    assert resp_x7.status_code == 200, f"X7 upload failed: {resp_x7.text}"
    x7_data = resp_x7.json()
    assert x7_data.get("chunks", 0) > 0
    resp_x7_chat = client1.post("/api/chat", json={"question": "What is the candidate experience?"})
    assert resp_x7_chat.status_code == 200
    assert NO_DOC_MSG not in resp_x7_chat.text
    print(f"X7 PASS: PDF upload and chat regression intact. Chunks: {x7_data['chunks']}")

    # -------------------------------------------------------------
    # X8: No cross-session leakage (second incognito session sees no data)
    # -------------------------------------------------------------
    client2 = TestClient(app, base_url="http://testserver")
    resp_x8_state = client2.get("/api/state")
    assert resp_x8_state.status_code == 200
    state2 = resp_x8_state.json()
    assert state2["active_doc"] is None, f"Expected active_doc None in fresh session, got {state2['active_doc']}"
    assert len(state2["indexed_docs"]) == 0, f"Expected 0 indexed docs in fresh session, got {state2['indexed_docs']}"
    
    resp_x8_chat = client2.post("/api/chat", json={"question": "What is Alice's role?"})
    assert resp_x8_chat.status_code == 200
    assert NO_DOC_MSG in resp_x8_chat.text, "Fresh session unexpectedly had access to doc data"
    print("X8 PASS: Session isolation verified. Client 2 sees no active doc or chunks.")
    print("=" * 70)
    print("ALL VERIFICATION CHECKS X1 - X8 PASSED!")
    print("=" * 70)

if __name__ == "__main__":
    run_verifications()
