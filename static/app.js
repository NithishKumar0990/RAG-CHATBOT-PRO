// static/app.js
/**
 * Résumé IQ — Vanilla Static Frontend Application
 * Fully session-isolated, SSE streaming chat, 5-axis ATS intelligence audit.
 * Zero npm, zero CDN, zero external libraries.
 */

(function () {
  'use strict';

  // State Store
  const state = {
    indexed_docs: [],
    active_doc: null,
    chats: [],
    activeChatId: null,
    messages: [],
    isStreaming: false,
    isUploading: false,
    mode: 'Chat', // 'Chat' or 'Analyze'
    activeTab: 'tabOverview',
    userScrolledUp: false,
    analysisCache: {},
    streamAbortController: null
  };
  window.state = state;

  // DOM Elements
  const mainScrollContainer = document.getElementById('mainScrollContainer');
  const chatMessages = document.getElementById('chatMessages');
  const emptyHero = document.getElementById('emptyHero');
  const chatInput = document.getElementById('chatInput');
  const btnSend = document.getElementById('btnSend');
  const btnAttach = document.getElementById('btnAttach');
  const fileUploadInput = document.getElementById('fileUploadInput');
  const btnNewChat = document.getElementById('new-chat-btn') || document.getElementById('btnNewChat');
  const chatsList = document.getElementById('chatsList');
  const recentList = document.getElementById('recentList');
  const activeDocPill = document.getElementById('activeDocPill');
  const activeDocName = document.getElementById('activeDocName');
  const btnModeChat = document.getElementById('btnModeChat');
  const btnModeAnalyze = document.getElementById('btnModeAnalyze');
  const chatView = document.getElementById('chatView');
  const analyzeView = document.getElementById('analyzeView');
  const btnScrollDown = document.getElementById('btnScrollDown');
  const btnMobileMenu = document.getElementById('btnMobileMenu');
  const sidebar = document.getElementById('sidebar');
  const toastContainer = document.getElementById('toastContainer');

  // ====================================================================
  // Utility: HTML Escaping & Markdown Renderer (Escape-First, Safe)
  // ====================================================================
  function escapeHTML(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderSafeMarkdown(rawText) {
    if (!rawText) return '';
    // 1. Mandatory escape-first step
    let text = escapeHTML(rawText.trim());

    // 2. Fenced code blocks ```lang\ncode\n```
    text = text.replace(/```(?:[a-zA-Z0-9_\-]+)?\n?([\s\S]*?)```/g, function (_, code) {
      return `<pre><code>${code.trim()}</code></pre>`;
    });

    // 3. Inline code `code`
    text = text.replace(/`([^`\n]+)`/g, '<code>$1</code>');

    // 4. Headings (#, ##, ###)
    text = text.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    text = text.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    text = text.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // 5. Bold & Italic
    text = text.replace(/\*\*\*(.*?)\*\*\*/g, '<strong><em>$1</em></strong>');
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    text = text.replace(/___(.*?)___/g, '<strong><em>$1</em></strong>');
    text = text.replace(/__(.*?)__/g, '<strong>$1</strong>');
    text = text.replace(/_(.*?)_/g, '<em>$1</em>');

    // 6. Safe links: strictly http, https, mailto
    text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+|mailto:[^\s\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    // 7. Bullet lists & paragraphs
    const lines = text.split('\n');
    let inList = false;
    const out = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const bulletMatch = line.match(/^(\s*)[-*•]\s+(.*)$/);
      if (bulletMatch) {
        if (!inList) {
          out.push('<ul>');
          inList = true;
        }
        out.push(`<li>${bulletMatch[2]}</li>`);
      } else {
        if (inList) {
          out.push('</ul>');
          inList = false;
        }
        if (line.trim().length > 0) {
          if (!line.startsWith('<h') && !line.startsWith('<pre') && !line.startsWith('</pre') && !line.startsWith('<code>')) {
            out.push(`<p>${line}</p>`);
          } else {
            out.push(line);
          }
        }
      }
    }
    if (inList) out.push('</ul>');

    return out.join('\n');
  }

  function showToast(msg, type = 'info') {
    const el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    if (type === 'error') el.style.borderColor = 'var(--error)';
    if (type === 'success') el.style.borderColor = 'var(--success)';
    toastContainer.appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transition = 'opacity 200ms ease';
      setTimeout(() => el.remove(), 250);
    }, 3500);
  }

  // ====================================================================
  // Auto-Scroll Watcher
  // ====================================================================
  function isNearBottom(threshold = 100) {
    const dist = mainScrollContainer.scrollHeight - mainScrollContainer.scrollTop - mainScrollContainer.clientHeight;
    return dist <= threshold;
  }

  function scrollToBottom(force = false) {
    if (force || !state.userScrolledUp) {
      mainScrollContainer.scrollTop = mainScrollContainer.scrollHeight;
      btnScrollDown.style.display = 'none';
    }
  }

  mainScrollContainer.addEventListener('scroll', function () {
    const dist = mainScrollContainer.scrollHeight - mainScrollContainer.scrollTop - mainScrollContainer.clientHeight;
    if (dist > 140) {
      state.userScrolledUp = true;
      if (state.isStreaming) {
        btnScrollDown.style.display = 'block';
      }
    } else if (dist <= 80) {
      state.userScrolledUp = false;
      btnScrollDown.style.display = 'none';
    }
  }, { passive: true });

  btnScrollDown.addEventListener('click', () => {
    state.userScrolledUp = false;
    scrollToBottom(true);
  });

  // ====================================================================
  // State Restoration & Initialization
  // ====================================================================
  async function loadInitialState() {
    try {
      const res = await fetch('/api/state', { credentials: 'same-origin' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      state.indexed_docs = data.indexed_docs || [];
      state.active_doc = data.active_doc || null;
      state.chats = data.chats || [];
      state.activeChatId = data.active_chat_id || (data.chats && data.chats[0] ? data.chats[0].id : null);
      state.messages = data.messages || [];

      renderRecentDocs();
      renderChats();
      renderActiveDocPill();
      renderChatHistory();

      // Restore mode from sessionStorage
      const savedMode = sessionStorage.getItem('riq_mode');
      if (savedMode === 'Analyze') {
        switchMode('Analyze');
      } else {
        switchMode('Chat');
      }
    } catch (err) {
      console.warn('Could not restore state from server:', err);
      renderRecentDocs();
      renderChats();
      renderActiveDocPill();
      renderChatHistory();
    }
  }

  function renderChats() {
    if (!chatsList) return;
    chatsList.innerHTML = '';
    if (!state.chats || state.chats.length === 0) {
      chatsList.innerHTML = '<div style="padding:8px 6px; font-size:12px; color:var(--text-muted); font-style:italic;">No chats yet</div>';
      return;
    }

    state.chats.forEach(chat => {
      const item = document.createElement('div');
      item.className = 'chat-item' + (chat.id === state.activeChatId ? ' active' : '');
      item.setAttribute('data-chat-id', chat.id);

      const titleSpan = document.createElement('span');
      titleSpan.className = 'chat-title';
      titleSpan.textContent = chat.title || 'New chat';
      titleSpan.title = chat.title || 'New chat';

      const delBtn = document.createElement('button');
      delBtn.className = 'btn-del-chat';
      delBtn.textContent = '✕';
      delBtn.title = 'Delete chat';
      delBtn.setAttribute('aria-label', `Delete ${chat.title || 'chat'}`);

      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteChat(chat.id, chat.messages_count);
      });

      item.appendChild(titleSpan);
      item.appendChild(delBtn);

      item.addEventListener('click', () => {
        if (chat.id !== state.activeChatId) {
          activateChat(chat.id);
        }
      });

      chatsList.appendChild(item);
    });
  }

  async function activateChat(chatId) {
    if (state.isStreaming) {
      if (state.streamAbortController) {
        try { state.streamAbortController.abort(); } catch (_) {}
        state.streamAbortController = null;
      }
      state.isStreaming = false;
      updateSendButtonState();
    }

    try {
      const res = await fetch(`/api/chats/${encodeURIComponent(chatId)}/activate`, {
        method: 'POST',
        credentials: 'same-origin'
      });
      if (!res.ok) throw new Error('Activation failed');
      const data = await res.json();
      state.activeChatId = data.active_chat_id;
      state.messages = data.messages || [];
      state.active_doc = data.active_doc || null;
      state.indexed_docs = data.indexed_docs || [];
      renderChats();
      renderChatHistory();
      renderRecentDocs();
      renderActiveDocPill();
      if (state.mode !== 'Chat') {
        switchMode('Chat');
      }
    } catch (err) {
      showToast(`Error activating chat: ${err.message}`, 'error');
    }
  }

  async function deleteChat(chatId, messagesCount) {
    if (messagesCount && messagesCount > 0) {
      if (!confirm('Are you sure you want to delete this chat thread?')) {
        return;
      }
    }

    try {
      const res = await fetch(`/api/chats/${encodeURIComponent(chatId)}`, {
        method: 'DELETE',
        credentials: 'same-origin'
      });
      if (!res.ok) throw new Error('Delete failed');
      const data = await res.json();
      state.activeChatId = data.active_chat_id;
      state.chats = data.chats || [];
      renderChats();
      // Reload active chat messages
      const activeRes = await fetch(`/api/chats/${encodeURIComponent(state.activeChatId)}/activate`, {
        method: 'POST',
        credentials: 'same-origin'
      });
      if (activeRes.ok) {
        const activeData = await activeRes.json();
        state.messages = activeData.messages || [];
        state.active_doc = activeData.active_doc || null;
        state.indexed_docs = activeData.indexed_docs || [];
      } else {
        state.messages = [];
        state.active_doc = null;
        state.indexed_docs = [];
      }
      renderChatHistory();
      renderRecentDocs();
      renderActiveDocPill();
      showToast('Chat thread deleted', 'info');
    } catch (err) {
      showToast(`Error deleting chat: ${err.message}`, 'error');
    }
  }

  function renderRecentDocs() {
    recentList.innerHTML = '';
    if (!state.indexed_docs || state.indexed_docs.length === 0) {
      recentList.innerHTML = '<div style="padding:10px 6px; font-size:12px; color:var(--text-muted); font-style:italic;">No documents yet</div>';
      return;
    }

    state.indexed_docs.forEach(doc => {
      const item = document.createElement('div');
      item.className = 'recent-item' + (doc.filename === state.active_doc ? ' active' : '');
      item.setAttribute('data-filename', doc.filename);

      const nameSpan = document.createElement('span');
      nameSpan.className = 'recent-name';
      nameSpan.textContent = doc.filename;

      const delBtn = document.createElement('button');
      delBtn.className = 'btn-del-doc';
      delBtn.textContent = '✕';
      delBtn.title = 'Remove document';
      delBtn.setAttribute('aria-label', `Remove ${doc.filename}`);

      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteDocument(doc.filename);
      });

      item.appendChild(nameSpan);
      item.appendChild(delBtn);

      item.addEventListener('click', () => {
        activateDocument(doc.filename);
      });

      recentList.appendChild(item);
    });
  }

  function renderActiveDocPill() {
    if (state.active_doc) {
      activeDocPill.style.display = 'inline-flex';
      activeDocName.textContent = state.active_doc;
      const analyzeInfo = document.getElementById('analyzeActiveDoc');
      if (analyzeInfo) analyzeInfo.textContent = state.active_doc;
    } else {
      activeDocPill.style.display = 'none';
      activeDocName.textContent = '';
      const analyzeInfo = document.getElementById('analyzeActiveDoc');
      if (analyzeInfo) analyzeInfo.textContent = 'No document active';
    }
  }

  function renderChatHistory() {
    chatMessages.innerHTML = '';
    if (!state.messages || state.messages.length === 0) {
      emptyHero.style.display = 'flex';
      return;
    }

    emptyHero.style.display = 'none';
    state.messages.forEach(msg => {
      if (msg.role === 'user') {
        appendUserMessage(msg.content);
      } else {
        appendAssistantMessage(msg.content, msg.sources, msg.timestamp);
      }
    });
    scrollToBottom(true);
  }

  // ====================================================================
  // Document Operations: Activate, Delete, Upload
  // ====================================================================
  async function activateDocument(filename) {
    try {
      const res = await fetch(`/api/doc/${encodeURIComponent(filename)}/activate`, {
        method: 'POST',
        credentials: 'same-origin'
      });
      if (!res.ok) throw new Error('Activation failed');
      const data = await res.json();
      state.active_doc = data.active_doc;
      state.indexed_docs = data.indexed_docs;
      renderRecentDocs();
      renderActiveDocPill();
      showToast(`Active document: ${filename}`, 'info');
      if (state.mode === 'Analyze') {
        loadAnalyzeTab(state.activeTab, true);
      }
    } catch (err) {
      showToast(`Error activating document: ${err.message}`, 'error');
    }
  }

  async function deleteDocument(filename) {
    try {
      const res = await fetch(`/api/doc/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
        credentials: 'same-origin'
      });
      if (!res.ok) throw new Error('Delete failed');
      const data = await res.json();
      state.active_doc = data.active_doc;
      state.indexed_docs = data.indexed_docs;
      renderRecentDocs();
      renderActiveDocPill();
      showToast(`Deleted ${filename}`, 'info');
      if (state.mode === 'Analyze') {
        loadAnalyzeTab(state.activeTab, true);
      }
    } catch (err) {
      showToast(`Error deleting document: ${err.message}`, 'error');
    }
  }

  btnAttach.addEventListener('click', () => {
    fileUploadInput.click();
  });

  const btnRemoveActiveDoc = document.getElementById('btnRemoveActiveDoc');
  if (btnRemoveActiveDoc) {
    btnRemoveActiveDoc.addEventListener('click', (e) => {
      e.stopPropagation();
      if (state.active_doc) {
        deleteDocument(state.active_doc);
      }
    });
  }

  fileUploadInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Reset input so same file can be selected again
    fileUploadInput.value = '';

    const formData = new FormData();
    formData.append('file', file);

    state.isUploading = true;
    updateSendButtonState();
    showToast(`Indexing ${file.name}...`, 'info');

    try {
      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
        credentials: 'same-origin'
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: 'Upload failed' }));
        throw new Error(errJson.detail || `Upload failed (${res.status})`);
      }

      const data = await res.json();
      state.indexed_docs = data.indexed_docs;
      state.active_doc = data.active_doc;
      renderRecentDocs();
      renderActiveDocPill();
      showToast(`✓ Indexed ${data.chunks} chunks from ${data.filename}`, 'success');
      if (state.mode === 'Analyze') {
        loadAnalyzeTab(state.activeTab, true);
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      state.isUploading = false;
      updateSendButtonState();
    }
  });

  btnNewChat.addEventListener('click', async () => {
    if (state.isStreaming) {
      if (state.streamAbortController) {
        state.streamAbortController.abort();
      }
      state.isStreaming = false;
    }
    chatInput.value = '';
    chatInput.style.height = 'auto';

    btnNewChat.disabled = true;
    btnNewChat.innerHTML = '<span>...</span><span>Creating...</span>';

    try {
      const res = await fetch('/api/new_chat', {
        method: 'POST',
        credentials: 'same-origin'
      });
      if (!res.ok) throw new Error(`Failed to create new chat (${res.status})`);
      const data = await res.json();

      // Reset UI state
      state.messages = [];
      state.activeChatId = data.chat_id;
      state.chats = data.chats || [];  // All threads (including old ones)
      state.indexed_docs = [];         // No docs
      state.active_doc = null;         // No active doc
      state.analysisCache = {};

      renderChatHistory();  // Clear messages
      renderChats();        // Show all threads in sidebar
      renderRecentDocs();   // Clear recent docs
      renderActiveDocPill(); // No active doc pill

      if (state.mode === 'Analyze') {
        showAnalyzeEmptyState();
        switchMode('Chat');
      }

      mainScrollContainer.scrollTop = 0;
      btnScrollDown.style.display = 'none';
      state.userScrolledUp = false;

      showToast('New chat created - upload a document to start', 'info');
    } catch (err) {
      showToast(`Failed to create new chat: ${err.message}`, 'error');
    } finally {
      btnNewChat.disabled = false;
      btnNewChat.innerHTML = originalText;
      updateSendButtonState();
    }
  });

  // ====================================================================
  // Chat Rendering & SSE Streaming Mechanics
  // ====================================================================
  function updateSendButtonState() {
    const val = chatInput.value.trim();
    btnSend.disabled = !val || state.isStreaming || state.isUploading;
  }

  chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 180) + 'px';
    updateSendButtonState();
  });

  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      if (!btnSend.disabled) {
        sendMessage(chatInput.value.trim());
      }
    }
  });

  btnSend.addEventListener('click', () => {
    const text = chatInput.value.trim();
    if (text && !btnSend.disabled) {
      sendMessage(text);
    }
  });

  // Suggested chip clicks
  document.querySelectorAll('.suggested-chips-grid .chip-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.getAttribute('data-query');
      if (q) sendMessage(q);
    });
  });

  function appendUserMessage(text) {
    emptyHero.style.display = 'none';
    const row = document.createElement('div');
    row.className = 'msg-user-row';
    const bubble = document.createElement('div');
    bubble.className = 'riq-msg-user';
    bubble.textContent = text;
    row.appendChild(bubble);
    chatMessages.appendChild(row);
  }

  function appendAssistantMessage(text, sources, timestamp = 'Just now') {
    const row = document.createElement('div');
    row.className = 'msg-bot-row';

    const botWrap = document.createElement('div');
    botWrap.className = 'riq-msg-bot';

    const head = document.createElement('div');
    head.className = 'riq-msg-bot-head';
    head.innerHTML = `
      <span class="riq-avatar">◆</span>
      <span class="riq-micro">Résumé IQ &nbsp;·&nbsp; ${escapeHTML(timestamp)}</span>
    `;

    const body = document.createElement('div');
    body.className = 'riq-msg-bot-body';
    body.innerHTML = renderSafeMarkdown(text);

    botWrap.appendChild(head);
    botWrap.appendChild(body);

    if (sources && sources.length > 0) {
      const details = createSourcesDetails(sources);
      botWrap.appendChild(details);
    }

    row.appendChild(botWrap);
    chatMessages.appendChild(row);
  }

  function createSourcesDetails(sources) {
    const details = document.createElement('details');
    details.className = 'riq-citation-details';

    const summary = document.createElement('summary');
    summary.className = 'riq-citation-pill';
    summary.textContent = `📄 ${sources.length} sources ▾`;
    details.appendChild(summary);

    const listWrap = document.createElement('div');
    listWrap.style.marginTop = '8px';

    sources.forEach(s => {
      const row = document.createElement('div');
      row.className = 'riq-citation-row';
      const label = s.source || 'Document';
      const chunk = s.chunk !== undefined ? `#${s.chunk}` : '';
      const score = s.score !== undefined ? ` · ${Math.round(s.score * 100)}% match` : '';
      row.innerHTML = `
        <strong>${escapeHTML(label)} (Chunk ${escapeHTML(chunk)}${escapeHTML(score)}):</strong><br>
        "${escapeHTML((s.content || '').trim())}"
      `;
      listWrap.appendChild(row);
    });

    details.appendChild(listWrap);
    return details;
  }

  async function sendMessage(question) {
    if (state.isStreaming || !question) return;

    chatInput.value = '';
    chatInput.style.height = 'auto';
    updateSendButtonState();

    // 1. Render User message
    appendUserMessage(question);

    // 2. Prepare Assistant container with skeleton
    const msgId = 'msg_' + Date.now();
    const row = document.createElement('div');
    row.className = 'msg-bot-row';

    const botWrap = document.createElement('div');
    botWrap.className = 'riq-msg-bot';
    botWrap.setAttribute('data-msg-id', msgId);

    const head = document.createElement('div');
    head.className = 'riq-msg-bot-head';
    const nowTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    head.innerHTML = `
      <span class="riq-avatar">◆</span>
      <span class="riq-micro">Résumé IQ &nbsp;·&nbsp; ${escapeHTML(nowTime)}</span>
    `;

    // Skeleton shimmer container
    const skeletonWrap = document.createElement('div');
    skeletonWrap.className = 'riq-skeleton-wrap';
    skeletonWrap.innerHTML = `
      <div class="riq-skeleton-line"></div>
      <div class="riq-skeleton-line"></div>
      <div class="riq-skeleton-line"></div>
    `;

    botWrap.appendChild(head);
    botWrap.appendChild(skeletonWrap);
    row.appendChild(botWrap);
    chatMessages.appendChild(row);

    scrollToBottom(true);

    // 3. Initiate SSE Streaming
    state.isStreaming = true;
    updateSendButtonState();

    if (state.streamAbortController) {
      try { state.streamAbortController.abort(); } catch (_) {}
    }
    const abortController = new AbortController();
    state.streamAbortController = abortController;

    let fullAnswer = '';
    let hasReplacedSkeleton = false;
    let bodyContainer = null;
    let pendingTokens = '';
    let rafId = null;

    function renderTokens() {
      if (abortController.signal.aborted) return;
      if (bodyContainer && pendingTokens) {
        bodyContainer.innerHTML = renderSafeMarkdown(fullAnswer);
        pendingTokens = '';
        if (!state.userScrolledUp) {
          scrollToBottom(false);
        }
      }
      rafId = null;
    }

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
        credentials: 'same-origin',
        signal: abortController.signal
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: 'Failed to connect to chat stream' }));
        throw new Error(errData.detail || `Server error (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        if (abortController.signal.aborted) return;
        const { value, done } = await reader.read();
        if (done || abortController.signal.aborted) break;

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop(); // keep last incomplete chunk

        for (const block of parts) {
          if (abortController.signal.aborted) return;
          if (!block.trim()) continue;
          let eventType = 'message';
          let dataText = '';

          const lines = block.split(/\r?\n/);
          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventType = line.replace('event:', '').trim();
            } else if (line.startsWith('data:')) {
              dataText += line.replace('data:', '').trim();
            }
          }

          if (!dataText) continue;

          let payload = null;
          try {
            payload = JSON.parse(dataText);
          } catch {
            payload = dataText;
          }

          if (eventType === 'token') {
            const tokenStr = typeof payload === 'string' ? payload : String(payload);
            fullAnswer += tokenStr;
            pendingTokens += tokenStr;

            if (!hasReplacedSkeleton) {
              // Swap skeleton inside the EXACT same DOM node
              skeletonWrap.remove();
              bodyContainer = document.createElement('div');
              bodyContainer.className = 'riq-msg-bot-body';
              botWrap.appendChild(bodyContainer);
              hasReplacedSkeleton = true;
            }

            if (!rafId) {
              rafId = requestAnimationFrame(renderTokens);
            }
          } else if (eventType === 'done') {
            if (rafId) cancelAnimationFrame(rafId);
            if (abortController.signal.aborted) return;
            if (!hasReplacedSkeleton) {
              skeletonWrap.remove();
              bodyContainer = document.createElement('div');
              bodyContainer.className = 'riq-msg-bot-body';
              botWrap.appendChild(bodyContainer);
              hasReplacedSkeleton = true;
            }

            const finalAns = payload.full_answer || fullAnswer;
            bodyContainer.innerHTML = renderSafeMarkdown(finalAns);

            if (payload.sources && payload.sources.length > 0) {
              const details = createSourcesDetails(payload.sources);
              botWrap.appendChild(details);
            }

            // Sync with local state
            state.messages.push({ role: 'user', content: question, timestamp: nowTime });
            state.messages.push({
              role: 'assistant',
              content: finalAns,
              sources: payload.sources || [],
              timestamp: nowTime
            });

            // Update thread title & preview in sidebar
            const activeCid = payload.chat_id || state.activeChatId;
            if (activeCid && state.chats) {
              const currentChat = state.chats.find(c => c.id === activeCid);
              if (currentChat) {
                if (payload.title) {
                  currentChat.title = payload.title;
                } else if (currentChat.title === 'New chat') {
                  currentChat.title = question.slice(0, 30) + (question.length > 30 ? '...' : '');
                }
                currentChat.updated_at = Date.now() / 1000;
                currentChat.preview = finalAns.slice(0, 60);
                currentChat.messages_count = state.messages.length;
              }
              renderChats();
            }

            scrollToBottom(false);
          } else if (eventType === 'error') {
            throw new Error(payload.message || 'Stream error');
          }
        }
      }
    } catch (err) {
      if (abortController.signal.aborted || err.name === 'AbortError') {
        if (rafId) cancelAnimationFrame(rafId);
        return;
      }
      console.error('Chat streaming failed:', err);
      if (rafId) cancelAnimationFrame(rafId);
      if (!hasReplacedSkeleton) {
        skeletonWrap.remove();
        bodyContainer = document.createElement('div');
        bodyContainer.className = 'riq-msg-bot-body';
        botWrap.appendChild(bodyContainer);
      }
      bodyContainer.innerHTML = `<span style="color:var(--error);">⚠️ Error: ${escapeHTML(err.message)}</span>`;
    } finally {
      if (state.streamAbortController === abortController) {
        state.streamAbortController = null;
      }
      state.isStreaming = false;
      updateSendButtonState();
      btnScrollDown.style.display = 'none';
    }
  }

  // ====================================================================
  // Mode Switching (Chat vs Analyze)
  // ====================================================================
  function switchMode(newMode) {
    state.mode = newMode;
    sessionStorage.setItem('riq_mode', newMode);

    if (newMode === 'Chat') {
      btnModeChat.classList.add('active');
      btnModeAnalyze.classList.remove('active');
      btnModeChat.setAttribute('aria-selected', 'true');
      btnModeAnalyze.setAttribute('aria-selected', 'false');
      chatView.style.display = 'flex';
      analyzeView.style.display = 'none';
      document.getElementById('chatDockContainer').style.display = 'flex';
    } else {
      btnModeChat.classList.remove('active');
      btnModeAnalyze.classList.add('active');
      btnModeChat.setAttribute('aria-selected', 'false');
      btnModeAnalyze.setAttribute('aria-selected', 'true');
      chatView.style.display = 'none';
      analyzeView.style.display = 'block';
      document.getElementById('chatDockContainer').style.display = 'none';
      loadAnalyzeTab(state.activeTab);
    }
  }

  btnModeChat.addEventListener('click', () => switchMode('Chat'));
  btnModeAnalyze.addEventListener('click', () => switchMode('Analyze'));

  // Mobile drawer toggle
  btnMobileMenu.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });

  // ====================================================================
  // Analyze Mode Logic & SVG Gauges
  // ====================================================================
  document.querySelectorAll('.analyze-tabs-bar .tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.analyze-tabs-bar .tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.analyze-wrapper .tab-panel').forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const tabId = btn.getAttribute('data-tab');
      const panel = document.getElementById(tabId);
      if (panel) panel.classList.add('active');

      state.activeTab = tabId;
      loadAnalyzeTab(tabId);
    });
  });

  function renderGaugeSVG(score, size = 160, stroke = 11) {
    const s = Math.max(0, Math.min(100, parseInt(score, 10) || 0));
    const r = (size / 2) - stroke;
    const c = 2 * Math.PI * r;
    const offset = c - (c * s / 100);

    // Color cutoffs per Streamlit UI spec: >=80 Green, 60-79 Amber, <60 Red
    let strokeColor = '#EF4444'; // Red
    if (s >= 80) strokeColor = '#10B981'; // Emerald
    else if (s >= 60) strokeColor = '#F59E0B'; // Amber

    return `
      <div style="position:relative; width:${size}px; height:${size}px;">
        <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
          <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="#E5E7EB" stroke-width="${stroke}" />
          <circle cx="${size/2}" cy="${size/2}" r="${r}" fill="none" stroke="${strokeColor}"
            stroke-width="${stroke}" stroke-linecap="round"
            stroke-dasharray="${c}" stroke-dashoffset="${offset}"
            transform="rotate(-90 ${size/2} ${size/2})"
            style="transition: stroke-dashoffset 800ms ease;" />
        </svg>
        <div style="position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center;">
          <div style="font-family:var(--font-serif); font-size:${Math.round(size*0.24)}px; font-weight:700; color:var(--text-primary); line-height:1;">
            ${s}
          </div>
          <div style="font-size:${Math.round(size*0.085)}px; color:var(--text-muted); margin-top:2px;">/100</div>
        </div>
      </div>
    `;
  }

  async function loadAnalyzeTab(tabId, force = false) {
    if (!state.active_doc) {
      showAnalyzeEmptyState();
      return;
    }

    if (tabId === 'tabOverview' || tabId === 'tabAudit') {
      if (!state.analysisCache.resume || force) {
        showOverviewLoading();
        try {
          const res = await fetch('/api/analyze/resume', { method: 'POST', credentials: 'same-origin' });
          if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Failed to audit resume' }));
            throw new Error(err.detail);
          }
          state.analysisCache.resume = await res.json();
        } catch (e) {
          showToast(e.message, 'error');
          return;
        }
      }
      renderOverviewData(state.analysisCache.resume);
      renderAuditData(state.analysisCache.resume);
    } else if (tabId === 'tabQuestions') {
      if (!state.analysisCache.questions || force) {
        document.getElementById('iqListContainer').innerHTML = '<div class="riq-skeleton-wrap"><div class="riq-skeleton-line"></div><div class="riq-skeleton-line"></div></div>';
        try {
          const res = await fetch('/api/analyze/interview_questions', { method: 'POST', credentials: 'same-origin' });
          if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Failed to generate interview questions' }));
            throw new Error(err.detail);
          }
          state.analysisCache.questions = await res.json();
        } catch (e) {
          showToast(e.message, 'error');
          return;
        }
      }
      renderQuestionsData(state.analysisCache.questions);
    }
  }

  function showAnalyzeEmptyState() {
    const gauge = document.getElementById('overviewGauge');
    if (gauge) gauge.innerHTML = renderGaugeSVG(0);
    const skills = document.getElementById('statSkills');
    if (skills) skills.textContent = '—';
    const exp = document.getElementById('statExp');
    if (exp) exp.textContent = '—';
    const kw = document.getElementById('statKeyword');
    if (kw) kw.textContent = '—';
  }

  function showOverviewLoading() {
    const gauge = document.getElementById('overviewGauge');
    if (gauge) gauge.innerHTML = '<div class="riq-skeleton-wrap" style="width:160px; height:160px; border-radius:50%; margin:0 auto;"></div>';
  }

  function renderOverviewData(data) {
    if (!data) return;
    const score = data.overall_score || 0;
    const gaugeWrap = document.getElementById('overviewGauge');
    if (gaugeWrap) gaugeWrap.innerHTML = renderGaugeSVG(score, 170, 11);

    const skillsCount = data.axis_scores ? Object.keys(data.axis_scores).length * 2 + ' skills' : '—';
    document.getElementById('statSkills').textContent = skillsCount;
    document.getElementById('statExp').textContent = '5+ yrs';
    document.getElementById('statKeyword').textContent = (data.mistakes_and_missing && data.mistakes_and_missing.length > 0) ? 'ATS Score' : 'None';
  }

  function renderAuditData(data) {
    if (!data) return;
    const axisContainer = document.getElementById('auditAxisContainer');
    axisContainer.innerHTML = '';

    if (data.axis_scores) {
      for (const [axisName, axisScore] of Object.entries(data.axis_scores)) {
        const card = document.createElement('div');
        card.className = 'axis-card';
        const formattedName = axisName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        card.innerHTML = `
          <div class="axis-head">
            <span>${escapeHTML(formattedName)}</span>
            <span>${axisScore}/100</span>
          </div>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" style="width:${axisScore}%;"></div>
          </div>
        `;
        axisContainer.appendChild(card);
      }
    }

    const mistakesContainer = document.getElementById('auditMistakesContainer');
    mistakesContainer.innerHTML = '';
    if (data.mistakes_and_missing && data.mistakes_and_missing.length > 0) {
      data.mistakes_and_missing.forEach(m => {
        const item = document.createElement('div');
        item.className = 'weak-box';
        item.style.marginBottom = '8px';
        item.textContent = m;
        mistakesContainer.appendChild(item);
      });
    }

    const rewritesContainer = document.getElementById('auditRewritesContainer');
    rewritesContainer.innerHTML = '';
    if (data.bullet_rewrites && data.bullet_rewrites.length > 0) {
      data.bullet_rewrites.forEach(rw => {
        const card = document.createElement('div');
        card.className = 'rewrite-card';
        card.innerHTML = `
          <div class="weak-box"><strong>Weak Original:</strong><br>${escapeHTML(rw.weak_original)}</div>
          <div class="strong-box"><strong>Strong Version:</strong><br>${escapeHTML(rw.strong_version)}</div>
        `;
        rewritesContainer.appendChild(card);
      });
    }
  }

  function renderQuestionsData(data) {
    const list = document.getElementById('iqListContainer');
    list.innerHTML = '';

    const questions = (data && data.questions) || [];
    if (questions.length === 0) {
      list.innerHTML = '<div style="color:var(--text-muted); font-style:italic;">No questions generated</div>';
      return;
    }

    questions.forEach(q => {
      const card = document.createElement('div');
      card.className = 'question-item-card';
      card.setAttribute('data-category', q.category || 'General');

      card.innerHTML = `
        <span class="q-category-badge">${escapeHTML(q.category || 'General')}</span>
        <div class="q-text">${escapeHTML(q.question)}</div>
        <div class="q-rubric"><strong>What is tested:</strong> ${escapeHTML(q.what_is_tested || '—')}</div>
        <div class="q-rubric"><strong>Ideal answer outline:</strong> ${escapeHTML(q.ideal_answer_outline || '—')}</div>
      `;
      list.appendChild(card);
    });
  }

  // Filter chips in Interview Qs
  document.querySelectorAll('#iqFilterBar .chip-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#iqFilterBar .chip-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const cat = btn.getAttribute('data-cat');
      document.querySelectorAll('#iqListContainer .question-item-card').forEach(card => {
        if (cat === 'ALL' || card.getAttribute('data-category') === cat) {
          card.style.display = 'block';
        } else {
          card.style.display = 'none';
        }
      });
    });
  });

  // JD Match
  const btnRunJdMatch = document.getElementById('btnRunJdMatch');
  const jdInputText = document.getElementById('jdInputText');
  const jdResultWrap = document.getElementById('jdResultWrap');

  btnRunJdMatch.addEventListener('click', async () => {
    const jdText = jdInputText.value.trim();
    if (!jdText) {
      showToast('Please paste a job description first', 'error');
      return;
    }

    btnRunJdMatch.disabled = true;
    btnRunJdMatch.textContent = 'Matching...';

    const formData = new FormData();
    formData.append('jd_text', jdText);

    try {
      const res = await fetch('/api/analyze/jd', {
        method: 'POST',
        body: formData,
        credentials: 'same-origin'
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to match JD' }));
        throw new Error(err.detail);
      }

      const matchData = await res.json();
      jdResultWrap.style.display = 'block';

      // Match Ring
      document.getElementById('jdGaugeWrap').innerHTML = renderGaugeSVG(matchData.match_percentage || 0, 110, 8);

      // Chips
      const matchChips = document.getElementById('jdMatchedChips');
      matchChips.innerHTML = '';
      (matchData.matched_keywords || []).forEach(k => {
        const chip = document.createElement('span');
        chip.className = 'kw-chip kw-chip-match';
        chip.textContent = '✓ ' + k;
        matchChips.appendChild(chip);
      });

      const missingChips = document.getElementById('jdMissingChips');
      missingChips.innerHTML = '';
      (matchData.missing_keywords || []).forEach(k => {
        const chip = document.createElement('span');
        chip.className = 'kw-chip kw-chip-missing';
        chip.textContent = '✗ ' + k;
        missingChips.appendChild(chip);
      });

      // Suggestions
      const sugList = document.getElementById('jdSuggestionsList');
      sugList.innerHTML = '';
      (matchData.edit_suggestions || []).forEach(s => {
        const card = document.createElement('div');
        card.className = 'axis-card';
        card.style.marginBottom = '8px';
        card.textContent = s;
        sugList.appendChild(card);
      });

      showToast('JD Analysis complete', 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      btnRunJdMatch.disabled = false;
      btnRunJdMatch.textContent = 'Match Against Resume';
    }
  });

  // Initial Load
  loadInitialState();
})();
