# ui/ui_blocks.py
"""
Résumé IQ — UI Component Library
Implements the design specification: ChatGPT skeleton + Claude soul + Gemini spark.
"""

from pathlib import Path
import html
import markdown
import streamlit as st

CSS_PATH = Path(__file__).parent / "theme.css"


def inject_css():
    """Inject the Résumé IQ CSS stylesheet into Streamlit."""
    if CSS_PATH.is_file():
        css = CSS_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def gauge_svg(score: int, size: int = 160, stroke: int = 10, is_gradient: bool = True) -> str:
    """
    Renders an inline SVG circular gauge ring.
    Uses exact mathematical stroke-dashoffset float calculation.
    """
    s = max(0, min(100, int(score) if score is not None else 0))
    r = (size / 2) - stroke
    c = 2 * 3.1415926535 * r
    offset = c - (c * s / 100)

    grad_def = """
      <defs>
        <linearGradient id="riqGaugeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#D9784F"/>
          <stop offset="100%" stop-color="#6B4C9A"/>
        </linearGradient>
      </defs>
    """ if is_gradient else ""

    stroke_color = "url(#riqGaugeGrad)" if is_gradient else "#CC6B49"

    return f"""
    <div class="riq-gauge-wrap" style="width:{size}px;height:{size}px;">
      <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
        {grad_def}
        <circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="#E8DFD2" stroke-width="{stroke}"/>
        <circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{stroke_color}"
          stroke-width="{stroke}" stroke-linecap="round"
          stroke-dasharray="{c}" stroke-dashoffset="{offset}"
          transform="rotate(-90 {size/2} {size/2})"
          style="transition: stroke-dashoffset 900ms ease-out;"/>
      </svg>
      <div class="riq-gauge-label">
        <div class="riq-gauge-score" style="font-size:{int(size*0.22)}px;">{s}</div>
        <div class="riq-gauge-max" style="font-size:{int(size*0.085)}px;">/100</div>
      </div>
    </div>
    """


def chat_bubble_user(text: str):
    """Render user message bubble: right-aligned, terracotta background, rounded corners."""
    safe_text = html.escape(text).replace("\n", "<br>")
    st.markdown(f'<div class="riq-msg-user">{safe_text}</div>', unsafe_allow_html=True)


def chat_bubble_bot_html(text: str, timestamp: str = "Just now", sources: list = None) -> str:
    """Generate assistant message bubble HTML."""
    body_html = markdown.markdown(text.strip(), extensions=['extra', 'nl2br'])

    sources_html = ""
    if sources:
        count = len(sources)
        excerpt_rows = []
        for s in sources:
            if isinstance(s, dict):
                src_label = s.get("source", "Document")
                chunk_id = s.get("chunk", 1)
                snippet = html.escape(s.get("content", "").strip())
                score_str = f" · {int(s.get('score', 0)*100)}% match" if s.get("score") is not None else ""
                excerpt_rows.append(
                    f'<div class="riq-citation-row">'
                    f'<strong>{html.escape(src_label)} (Chunk #{chunk_id}{score_str}):</strong><br>'
                    f'"{snippet}"'
                    f'</div>'
                )
            else:
                excerpt_rows.append(
                    f'<div class="riq-citation-row">"{html.escape(str(s).strip())}"</div>'
                )
        joined_excerpts = "".join(excerpt_rows)
        sources_html = (
            f'<details class="riq-citation-details" style="margin-top:12px;">\n'
            f'<summary class="riq-citation-pill">📄 {count} sources ▾</summary>\n'
            f'<div style="margin-top:8px;">{joined_excerpts}</div>\n'
            f'</details>'
        )

    return (
        f'<div class="riq-msg-bot">\n'
        f'<div class="riq-msg-bot-head">\n'
        f'  <span class="riq-avatar">◆</span>\n'
        f'  <span class="riq-micro">Résumé IQ &nbsp;·&nbsp; {timestamp}</span>\n'
        f'</div>\n'
        f'<div class="riq-msg-bot-body">{body_html}</div>\n'
        f'{sources_html}\n'
        f'</div>'
    )


def chat_bubble_bot(text: str, timestamp: str = "Just now", sources: list = None):
    """
    Render assistant message bubble:
    Left-aligned, speech-bubble tail corner (4px 18px 18px 18px), max-width 85%,
    tightened 8px head gap, 16px 20px padding, no border, subtle shadow.
    Includes inline collapsible citation pill inside the bubble if sources are present.
    """
    st.markdown(chat_bubble_bot_html(text, timestamp, sources), unsafe_allow_html=True)


def chat_bubble_bot_skeleton(timestamp: str = "Just now") -> str:
    """Generate ChatGPT-style skeleton shimmer HTML (3 rounded grey bars)."""
    return (
        f'<div class="riq-msg-bot">\n'
        f'<div class="riq-msg-bot-head">\n'
        f'  <span class="riq-avatar">◆</span>\n'
        f'  <span class="riq-micro">Résumé IQ &nbsp;·&nbsp; {timestamp}</span>\n'
        f'</div>\n'
        f'<div class="riq-msg-bot-body">\n'
        f'  <div class="riq-skeleton-wrap">\n'
        f'    <div class="riq-skeleton-line"></div>\n'
        f'    <div class="riq-skeleton-line"></div>\n'
        f'    <div class="riq-skeleton-line"></div>\n'
        f'  </div>\n'
        f'</div>\n'
        f'</div>'
    )


def typing_indicator():
    """Render bouncing 3-dot typing indicator."""
    st.markdown("""
    <div class="riq-msg-bot" style="padding:14px 20px; display:inline-block; margin-bottom:16px;">
      <div style="display:flex; align-items:center; gap:8px;">
        <span class="riq-avatar" style="width:20px; height:20px; font-size:9px;">◆</span>
        <div class="riq-typing">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def stat_tile(icon: str, num: str, label: str):
    """Render a clean metric stat tile card."""
    html_content = f"""
    <div class="riq-stat-tile">
      <div class="icon">{icon}</div>
      <div class="num">{num}</div>
      <div class="label">{label}</div>
    </div>
    """
    st.markdown(html_content, unsafe_allow_html=True)


def alert_card(title: str, desc: str, alert_type: str = "warning", line_ref: str = None):
    """Render an alert card for issues and missing items."""
    ref_badge = f'<span class="riq-micro" style="color:var(--text-muted);">{line_ref}</span>' if line_ref else ""
    icon = "⚠" if alert_type == "warning" else "⛔"
    html_content = f"""
    <div class="riq-alert {alert_type}">
      <div class="head">
        <div class="title">{icon} {html.escape(title)}</div>
        {ref_badge}
      </div>
      <div class="desc">{html.escape(desc)}</div>
    </div>
    """
    st.markdown(html_content, unsafe_allow_html=True)


def before_after_pair(weak_text: str, strong_text: str, index: int = 1):
    """Render side-by-side weak vs strong bullet rewrite cards."""
    col_w, col_s = st.columns(2)
    with col_w:
        st.markdown(f"""
        <div class="riq-ba-card weak">
          <div class="riq-ba-badge weak">✕ WEAK #{index}</div>
          <div style="font-size:13.5px; color:var(--text-primary); line-height:1.5;">{html.escape(weak_text)}</div>
        </div>
        """, unsafe_allow_html=True)

    with col_s:
        st.markdown(f"""
        <div class="riq-ba-card strong">
          <div class="riq-ba-badge strong">✓ STRONG #{index}</div>
          <div style="font-size:13.5px; color:var(--text-primary); line-height:1.5;">{html.escape(strong_text)}</div>
        </div>
        """, unsafe_allow_html=True)


def question_card(category: str, question: str, competency: str, outline: str, difficulty: str = "Medium", index: int = 1):
    """Render an interview question card with difficulty badge and ideal outline expander."""
    diff_class = difficulty.lower() if difficulty.lower() in ["easy", "medium", "hard"] else "medium"
    cat_badge = f'<span class="riq-badge primary" style="margin-right:6px;">{category}</span>'
    diff_badge = f'<span class="riq-badge {diff_class}">{difficulty}</span>'

    st.markdown(f"""
    <div class="riq-q-card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div>{cat_badge}</div>
        <div>{diff_badge}</div>
      </div>
      <div style="font-size:16px; font-weight:600; color:var(--text-primary); margin-bottom:8px; line-height:1.45;">
        Q{index}: {html.escape(question)}
      </div>
      <div class="riq-caption" style="margin-bottom:10px;">
        <strong>Competency Tested:</strong> {html.escape(competency)}
      </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander(f"▸ View ideal answer outline for Q{index}"):
        st.markdown(outline)


def kw_chip(text: str, matched: bool = True) -> str:
    """Generate HTML string for matched/missing keyword chip."""
    klass = "matched" if matched else "missing"
    prefix = "✓" if matched else "✕"
    return f'<span class="riq-kw-chip {klass}">{prefix} {html.escape(text)}</span>'


def action_card(num: int, text: str):
    """Render a numbered suggestion action card."""
    html_content = f"""
    <div class="riq-action-card">
      <div class="riq-action-num">{num}</div>
      <div style="font-size:14px; color:var(--text-primary); line-height:1.5;">{html.escape(text)}</div>
    </div>
    """
    st.markdown(html_content, unsafe_allow_html=True)


def review_to_markdown(review: dict) -> str:
    """Format review dict into clean Markdown report for download."""
    if not review:
        return "# Resume Audit Report\n\nNo review data available.\n"

    overall = review.get("overall_score", "—")
    axis = review.get("axis_scores", {}) or {}
    mistakes = review.get("mistakes_and_missing", []) or []
    rewrites = review.get("bullet_rewrites", []) or []

    md = [
        "# Résumé IQ — Audit Report",
        f"**ATS Readiness Score:** {overall}/100\n",
        "## Evaluation Axes Breakdown"
    ]
    for k, v in axis.items():
        md.append(f"- **{k.replace('_', ' ').title()}:** {v}/100")

    md.append("\n## Issues & Missing Elements")
    for m in mistakes:
        md.append(f"- {m}")

    md.append("\n## Bullet Point Transformations")
    for i, r in enumerate(rewrites, 1):
        md.append(f"\n### Transformation #{i}")
        md.append(f"**Weak Original:** {r.get('weak_original', '')}")
        md.append(f"**Strong Rewrite:** {r.get('strong_version', '')}")

    return "\n".join(md) + "\n"


def chat_scroll_js():
    """Inject lightweight JS auto-scroll: follows streaming tokens, pauses if user scrolled up (>120px)."""
    js = """
    <img src="x" style="display:none;" onerror="
    (function() {
      const container = document.querySelector('div[class*=\\'st-key-riq_chat_scroll_area\\']');
      if (!container) return;

      function scrollToBottom(force) {
        const threshold = 120;
        const dist = container.scrollHeight - container.scrollTop - container.clientHeight;
        if (force || dist <= threshold) {
          container.scrollTop = container.scrollHeight;
        }
      }

      // Initial scroll to bottom on new message / page render
      scrollToBottom(true);
      setTimeout(function() { scrollToBottom(true); }, 50);

      // Attach MutationObserver to follow streaming tokens as they arrive
      if (!container.dataset.riqObserverAttached) {
        container.dataset.riqObserverAttached = 'true';
        let lastTime = 0;
        const observer = new MutationObserver(function() {
          const now = Date.now();
          if (now - lastTime > 25) {
            lastTime = now;
            scrollToBottom(false);
          }
        });
        observer.observe(container, { childList: true, subtree: true, characterData: true });
      }
    })();
    " />
    """
    st.markdown(js, unsafe_allow_html=True)

