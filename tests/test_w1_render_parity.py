# tests/test_w1_render_parity.py
import subprocess
import time
import urllib.request
import json
import base64
import websocket
import sys
import os
import pathlib

sys.stdout.reconfigure(encoding='utf-8')
VERIF_DIR = pathlib.Path(__file__).parent.parent / "verification"
VERIF_DIR.mkdir(parents=True, exist_ok=True)

def run_w1_test():
    print("=== RUNNING W1: RENDER PARITY & COMPUTED STYLES ===")
    
    # Kill any existing msedge debug instances
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
        '--user-data-dir=X:\\Rag_Chatbot_Pro\\scratch\\edge_w1',
        '--window-size=1440,900',
        'http://127.0.0.1:8000'
    ])
    time.sleep(3)

    evidence = []
    try:
        with urllib.request.urlopen('http://localhost:9222/json') as resp:
            tabs = json.loads(resp.read().decode())
        target = [t for t in tabs if '127.0.0.1:8000' in t.get('url', '')][0]
        ws = websocket.create_connection(target['webSocketDebuggerUrl'])
        _id = 0
        def send(cmd, p=None):
            nonlocal _id
            _id += 1
            cur_id = _id
            ws.send(json.dumps({'id': cur_id, 'method': cmd, 'params': p or {}}))
            while True:
                r = json.loads(ws.recv())
                if r.get('id') == cur_id:
                    return r

        send('Page.enable')
        send('Runtime.enable')
        time.sleep(2)

        # 1. Desktop Screenshot 1440x900
        res = send('Page.captureScreenshot', {'format': 'png'})
        desktop_bytes = base64.b64decode(res['result']['data'])
        (VERIF_DIR / "w1_desktop_1440x900.png").write_bytes(desktop_bytes)
        evidence.append(f"Saved desktop screenshot: verification/w1_desktop_1440x900.png ({len(desktop_bytes)} bytes)")

        # 2. Computed Styles Check
        style_eval = send('Runtime.evaluate', {
            'expression': """
            (function() {
                const bodyStyle = window.getComputedStyle(document.body);
                const brand = document.querySelector('.brand-title');
                const brandText = brand ? brand.textContent.trim() : '';
                const btnNewChat = document.getElementById('btnNewChat');
                const btnStyle = btnNewChat ? window.getComputedStyle(btnNewChat) : null;
                const hero = document.getElementById('emptyHero');
                const chips = document.querySelectorAll('#emptyHero .chip-btn');

                return {
                    bodyBg: bodyStyle.backgroundColor,
                    bodyColor: bodyStyle.color,
                    bodyFont: bodyStyle.fontFamily,
                    brandText: brandText,
                    brandHasAccent: brandText.includes('Résumé'),
                    btnBorderRadius: btnStyle ? btnStyle.borderRadius : '',
                    chipsCount: chips.length,
                    heroVisible: !!hero && hero.offsetParent !== null
                };
            })()
            """,
            'returnByValue': True
        })
        styles = style_eval.get('result', {}).get('result', {}).get('value', {})
        print("Computed Styles Result:", styles)
        evidence.append(f"Computed styles: {json.dumps(styles, indent=2)}")

        assert styles.get("brandHasAccent"), "Brand title must include Résumé with correct accent"
        assert styles.get("chipsCount") == 4, f"Expected 4 prompt chips, got {styles.get('chipsCount')}"
        assert styles.get("heroVisible"), "Empty hero state must be visible"

        # 3. Mobile Emulation ~390px
        send('Emulation.setDeviceMetricsOverride', {
            'width': 390,
            'height': 844,
            'deviceScaleFactor': 3,
            'mobile': True
        })
        time.sleep(1)
        res_mobile = send('Page.captureScreenshot', {'format': 'png'})
        mobile_bytes = base64.b64decode(res_mobile['result']['data'])
        (VERIF_DIR / "w1_mobile_390x844.png").write_bytes(mobile_bytes)
        evidence.append(f"Saved mobile screenshot: verification/w1_mobile_390x844.png ({len(mobile_bytes)} bytes)")

        (VERIF_DIR / "w1_render_parity.txt").write_text("\n".join(evidence), encoding="utf-8")
        print("[PASS] W1: Render Parity Verified!")
        return True

    finally:
        try:
            ws.close()
        except Exception:
            pass
        proc.terminate()

if __name__ == "__main__":
    run_w1_test()
