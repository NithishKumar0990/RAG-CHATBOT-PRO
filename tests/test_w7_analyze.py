# tests/test_w7_analyze.py
import sys
import os
import pathlib
import json
import time
import httpx
import subprocess
import urllib.request
import websocket
import base64

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.resolve()))
from resume_analyzer import review_resume, generate_interview_questions, match_job_description
from document_parser import parse_document
from web_adapters import UploadedFileShim

VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

def run_w7_test():
    print("=== RUNNING W7: ATS RESUME INTELLIGENCE & ANALYZE SUITE ===")
    evidence = []

    client = httpx.Client(base_url="http://127.0.0.1:8000")

    # 1. Analyze with NO document uploaded
    res_no_doc = client.post("/api/analyze/resume")
    assert res_no_doc.status_code == 400
    err_msg = res_no_doc.json().get("detail", "")
    assert "upload a resume first" in err_msg.lower()
    evidence.append(f"No-doc analyze response: {err_msg}")

    # 2. Upload sample resume
    sample_text = pathlib.Path("sample_resume.txt").read_text(encoding="utf-8")
    files = {"file": ("sample_resume.txt", sample_text.encode("utf-8"), "text/plain")}
    client.post("/api/upload", files=files)

    # 3. Call /api/analyze/resume
    t0 = time.time()
    res_audit_1 = client.post("/api/analyze/resume")
    t_first = time.time() - t0
    assert res_audit_1.status_code == 200
    data_audit_1 = res_audit_1.json()
    evidence.append(f"First analyze/resume latency: {t_first:.3f}s")
    evidence.append(f"Audit keys: {list(data_audit_1.keys())}")

    # Assert top-level keys from API_CONTRACT.md
    assert "overall_score" in data_audit_1
    assert "axis_scores" in data_audit_1
    assert "mistakes_and_missing" in data_audit_1
    assert "bullet_rewrites" in data_audit_1

    # 4. Second call hits cache (very fast < 0.1s)
    t1 = time.time()
    res_audit_2 = client.post("/api/analyze/resume")
    t_second = time.time() - t1
    assert res_audit_2.status_code == 200
    data_audit_2 = res_audit_2.json()
    evidence.append(f"Second analyze/resume latency (cached): {t_second:.4f}s")
    assert data_audit_1 == data_audit_2, "Cached output must match identical data"
    assert t_second < 0.5, f"Cache lookup took too long: {t_second}s"

    # 5. Call /api/analyze/jd and verify JD is NOT indexed into vectorstore
    state_before_jd = client.get("/api/state").json()
    chunks_before = state_before_jd["indexed_docs"][0]["chunks"]

    jd_text = (
        "Role: Senior AI Engineer\n"
        "Requirements:\n"
        "- 5+ years experience in Python, AI/ML, and RAG architectures\n"
        "- Experience with LangChain, Vector databases, ChromaDB, FastAPI\n"
        "- Familiarity with cloud technologies: Docker, AWS, Kubernetes\n"
    )
    res_jd = client.post("/api/analyze/jd", data={"jd_text": jd_text})
    assert res_jd.status_code == 200
    jd_data = res_jd.json()
    evidence.append(f"JD Match percentage: {jd_data.get('match_percentage')}%")
    evidence.append(f"JD Matched keywords: {jd_data.get('matched_keywords')}")
    evidence.append(f"JD Missing keywords: {jd_data.get('missing_keywords')}")

    # Assert JD keys
    assert "match_percentage" in jd_data
    assert "matched_keywords" in jd_data
    assert "missing_keywords" in jd_data
    assert "edit_suggestions" in jd_data

    state_after_jd = client.get("/api/state").json()
    chunks_after = state_after_jd["indexed_docs"][0]["chunks"]
    assert chunks_before == chunks_after, "SECURITY/PRIVACY VIOLATION: JD was indexed into session vectorstore!"
    evidence.append(f"Vectorstore chunk count preserved: {chunks_before} == {chunks_after} (JD not indexed)")

    # 6. Browser UI checks on Analyze tabs & Screenshots
    subprocess.run(["powershell", "-Command", "Get-Process -Name msedge -ErrorAction SilentlyContinue | Stop-Process -Force"], capture_output=True)
    time.sleep(1)

    proc = subprocess.Popen([
        r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        '--remote-debugging-port=9222',
        '--remote-allow-origins=*',
        '--headless=new',
        '--disable-gpu',
        '--no-first-run',
        '--no-default-browser-check',
        '--user-data-dir=X:\\Rag_Chatbot_Pro\\scratch\\edge_w7',
        '--window-size=1440,900',
        'http://127.0.0.1:8000'
    ])
    time.sleep(3)

    try:
        with urllib.request.urlopen('http://localhost:9222/json') as resp:
            tabs = json.loads(resp.read().decode())
        target = [t for t in tabs if '127.0.0.1:8000' in t.get('url', '')][0]
        ws = websocket.create_connection(target['webSocketDebuggerUrl'])
        _id = 0
        def send(cmd, p=None):
            global _id
            _id += 1
            cur_id = _id
            ws.send(json.dumps({'id': cur_id, 'method': cmd, 'params': p or {}}))
            while True:
                r = json.loads(ws.recv())
                if r.get('id') == cur_id:
                    return r

        send('Runtime.enable')
        send('Page.enable')
        send('DOM.enable')
        time.sleep(2)

        # Upload sample resume via CDP
        doc_res = send('DOM.getDocument')
        root_id = doc_res['result']['root']['nodeId']
        node_res = send('DOM.querySelector', {'nodeId': root_id, 'selector': '#fileUploadInput'})
        file_node_id = node_res['result']['nodeId']
        send('DOM.setFileInputFiles', {'nodeId': file_node_id, 'files': [os.path.abspath("sample_resume.txt")]})
        time.sleep(4)

        # Switch to Analyze mode
        send('Runtime.evaluate', {
            'expression': "document.getElementById('btnModeAnalyze').click()"
        })
        time.sleep(4)

        # Capture Overview Tab
        res_ov = send('Page.captureScreenshot', {'format': 'png'})
        (VERIF_DIR / "w7_web_analyze_overview.png").write_bytes(base64.b64decode(res_ov['result']['data']))

        # Click Tab Resume Audit
        send('Runtime.evaluate', {
            'expression': "document.querySelector('[data-tab=\"tabAudit\"]').click()"
        })
        time.sleep(2)
        res_aud = send('Page.captureScreenshot', {'format': 'png'})
        (VERIF_DIR / "w7_web_analyze_audit.png").write_bytes(base64.b64decode(res_aud['result']['data']))

        # Click Tab Interview Qs
        send('Runtime.evaluate', {
            'expression': "document.querySelector('[data-tab=\"tabQuestions\"]').click()"
        })
        time.sleep(6)
        res_qs = send('Page.captureScreenshot', {'format': 'png'})
        (VERIF_DIR / "w7_web_analyze_questions.png").write_bytes(base64.b64decode(res_qs['result']['data']))

        # Click Tab JD Match & Run Match
        send('Runtime.evaluate', {
            'expression': f"""
            document.querySelector('[data-tab="tabJd"]').click();
            document.getElementById('jdInputText').value = {json.dumps(jd_text)};
            document.getElementById('btnRunJdMatch').click();
            """
        })
        time.sleep(5)
        res_jdm = send('Page.captureScreenshot', {'format': 'png'})
        (VERIF_DIR / "w7_web_analyze_jd.png").write_bytes(base64.b64decode(res_jdm['result']['data']))

        evidence.append("All Analyze tabs rendered and screenshots captured!")
        (VERIF_DIR / "w7_analyze.txt").write_text("\n".join(evidence), encoding="utf-8")
        print("[PASS] W7: ATS Resume Intelligence Verified!")
        return True

    finally:
        try:
            ws.close()
        except Exception:
            pass
        proc.terminate()

if __name__ == "__main__":
    run_w7_test()
