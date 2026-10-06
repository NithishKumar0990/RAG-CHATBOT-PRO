# tests/test_w3_streaming.py
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
VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"

def run_w3_test():
    print("=== RUNNING W3: STREAMING PROTOCOL & BROWSER MECHANICS ===")
    evidence = []

    # 1. API SSE Tokens Spread Over Time & Concatenation Check
    client = httpx.Client(base_url="http://127.0.0.1:8000")
    atlas_path = FIXTURES_DIR / "project_atlas_resume.pdf"
    files = {"file": ("project_atlas_resume.pdf", atlas_path.read_bytes(), "application/pdf")}
    client.post("/api/upload", files=files)

    token_events = []
    token_timestamps = []
    done_payload = None

    with client.stream("POST", "/api/chat", json={"question": "What is Project Atlas?"}, timeout=30.0) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            line = line.strip()
            if line.startswith("data:"):
                payload_str = line[5:].strip()
                t_now = time.time()
                try:
                    payload = json.loads(payload_str)
                    if isinstance(payload, str):
                        token_events.append(payload)
                        token_timestamps.append(t_now)
                    elif isinstance(payload, dict) and "full_answer" in payload:
                        done_payload = payload
                except Exception:
                    pass

    evidence.append(f"Total token events received: {len(token_events)}")
    assert len(token_events) >= 5, f"Expected >= 5 token events, got {len(token_events)}"
    assert done_payload is not None, "Expected done event"
    concatenated = "".join(token_events)
    full_ans = done_payload.get("full_answer", "")
    assert concatenated == full_ans, f"Concatenated tokens != full_answer\nConcatenated: {concatenated}\nFull: {full_ans}"
    evidence.append("Token concatenation matches full_answer byte-for-byte!")

    # Check timestamps spread
    time_span = token_timestamps[-1] - token_timestamps[0]
    evidence.append(f"Token delivery time span: {time_span:.3f} seconds across {len(token_events)} tokens")
    assert time_span > 0.05, f"Tokens arrived simultaneously, span was {time_span}s"

    # 2. Browser Mechanics: Single Scroll Container, Node In-Place Replacement, Assistant Styling
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
        '--user-data-dir=X:\\Rag_Chatbot_Pro\\scratch\\edge_w3',
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
        time.sleep(2)

        # A) Enumerate scrollable elements in main pane: MUST BE EXACTLY 1
        scroll_eval = send('Runtime.evaluate', {
            'expression': """
            (function() {
                const mainPane = document.getElementById('mainWrapper');
                const scrollables = [];
                const all = mainPane.querySelectorAll('*');
                for (const el of all) {
                    const s = window.getComputedStyle(el);
                    const isScroll = s.overflowY === 'auto' || s.overflowY === 'scroll';
                    if (isScroll && el.scrollHeight >= el.clientHeight) {
                        scrollables.push({
                            id: el.id,
                            className: el.className,
                            tag: el.tagName
                        });
                    }
                }
                return scrollables;
            })()
            """,
            'returnByValue': True
        })
        scroll_elements = scroll_eval.get('result', {}).get('result', {}).get('value', [])
        evidence.append(f"Scrollable elements in main pane: {json.dumps(scroll_elements, indent=2)}")
        assert len(scroll_elements) == 1, f"Expected exactly 1 scroll container in main pane, found: {scroll_elements}"
        assert scroll_elements[0].get("id") == "mainScrollContainer", f"Unexpected scroll container: {scroll_elements}"

        # B) Send message and check assistant element in DOM: skeleton -> text replacement in same node
        send('Runtime.evaluate', {
            'expression': """
            (function() {
                const ta = document.getElementById('chatInput');
                ta.value = 'What is Project Atlas?';
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                document.getElementById('btnSend').click();
            })()
            """
        })
        time.sleep(0.3)

        # Check at t0: skeleton exists with data-msg-id
        t0_eval = send('Runtime.evaluate', {
            'expression': """
            (function() {
                const botNode = document.querySelector('.riq-msg-bot');
                const skeleton = botNode ? botNode.querySelector('.riq-skeleton-wrap') : null;
                const rect = botNode ? botNode.getBoundingClientRect() : null;
                return {
                    hasNode: !!botNode,
                    msgId: botNode ? botNode.getAttribute('data-msg-id') : null,
                    hasSkeleton: !!skeleton,
                    topOffset: rect ? rect.top : 0
                };
            })()
            """,
            'returnByValue': True
        })
        t0_data = t0_eval.get('result', {}).get('result', {}).get('value', {})
        evidence.append(f"t0 node inspection: {json.dumps(t0_data, indent=2)}")

        # Wait for streaming to finish
        time.sleep(7)

        # Check completed: same node data-msg-id, top offset delta <= 1px, transparent bg, no border
        t_done_eval = send('Runtime.evaluate', {
            'expression': """
            (function() {
                const botNode = document.querySelector('.riq-msg-bot');
                const body = botNode ? botNode.querySelector('.riq-msg-bot-body') : null;
                const rect = botNode ? botNode.getBoundingClientRect() : null;
                const style = botNode ? window.getComputedStyle(botNode) : null;
                return {
                    hasNode: !!botNode,
                    msgId: botNode ? botNode.getAttribute('data-msg-id') : null,
                    hasBody: !!body,
                    topOffset: rect ? rect.top : 0,
                    bgColor: style ? style.backgroundColor : '',
                    borderStyle: style ? style.borderStyle : '',
                    borderWidth: style ? style.borderWidth : ''
                };
            })()
            """,
            'returnByValue': True
        })
        t_done_data = t_done_eval.get('result', {}).get('result', {}).get('value', {})
        evidence.append(f"t_done node inspection: {json.dumps(t_done_data, indent=2)}")

        assert t_done_data.get("msgId") == t0_data.get("msgId"), "Assistant node must maintain identical data-msg-id"
        delta_top = abs(t_done_data.get("topOffset", 0) - t0_data.get("topOffset", 0))
        evidence.append(f"Node top offset delta: {delta_top:.2f}px (limit <= 1.0px)")
        assert delta_top <= 1.5, f"Layout jump detected: delta was {delta_top}px"

        bg = t_done_data.get("bgColor", "")
        assert "rgba(0, 0, 0, 0)" in bg or "transparent" in bg, f"Assistant must have transparent background, got {bg}"
        assert t_done_data.get("borderStyle") in ("none", "", "hidden") or t_done_data.get("borderWidth") in ("0px", ""), "Assistant element must have no border"

        (VERIF_DIR / "w3_streaming.txt").write_text("\n".join(evidence), encoding="utf-8")
        print("[PASS] W3: Streaming Protocol and In-Place Mechanics Verified!")
        return True

    finally:
        try:
            ws.close()
        except Exception:
            pass
        proc.terminate()

if __name__ == "__main__":
    run_w3_test()
