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
    activeTab: 'tabAudit',
    userScrolledUp: false,
    analysisCache: {},
    streamAbortController: null,
    profile: null
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
  const profileChipContainer = document.getElementById('profileChipContainer');
  const profileChipBtn = document.getElementById('profileChipBtn');
  const profileChipText = document.getElementById('profileChipText');
  const profilePopover = document.getElementById('profilePopover');

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
      state.profile = data.profile || null;
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
      chatsList.innerHTML = '<div class="sidebar-empty"><span class="sidebar-empty-icon">💬</span><span>No chats yet</span></div>';
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
      recentList.innerHTML = '<div class="sidebar-empty"><span class="sidebar-empty-icon">📄</span><span>No documents yet</span></div>';
      return;
    }

    state.indexed_docs.forEach(doc => {
      const item = document.createElement('div');
      item.className = 'recent-item' + (doc.filename === state.active_doc ? ' active' : '');
      item.setAttribute('data-filename', doc.filename);

      const infoCol = document.createElement('div');
      infoCol.style.display = 'flex';
      infoCol.style.flexDirection = 'column';
      infoCol.style.overflow = 'hidden';

      const nameSpan = document.createElement('span');
      nameSpan.className = 'recent-name';
      nameSpan.textContent = doc.filename;
      infoCol.appendChild(nameSpan);

      if (doc.profile) {
        const numNumeric = doc.profile.columns ? doc.profile.columns.filter(c => c.dtype === 'numeric').length : Object.keys(doc.profile.numeric_summary || {}).length;
        const chipBtn = document.createElement('button');
        chipBtn.className = 'recent-profile-chip';
        chipBtn.textContent = `📊 ${doc.profile.row_count} rows • ${doc.profile.col_count} cols • ${numNumeric} numeric`;
        chipBtn.title = 'View dataset schema and stats';
        chipBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          activateDocument(doc.filename);
          toggleProfilePopover(doc.profile, doc.filename);
        });
        infoCol.appendChild(chipBtn);
      }

      const delBtn = document.createElement('button');
      delBtn.className = 'btn-del-doc';
      delBtn.textContent = '✕';
      delBtn.title = 'Remove document';
      delBtn.setAttribute('aria-label', `Remove ${doc.filename}`);

      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteDocument(doc.filename);
      });

      item.appendChild(infoCol);
      item.appendChild(delBtn);

      item.addEventListener('click', () => {
        activateDocument(doc.filename);
      });

      recentList.appendChild(item);
    });
  }

  function toggleProfilePopover(prof, fname) {
    if (!profilePopover) return;
    if (profilePopover.style.display === 'block') {
      profilePopover.style.display = 'none';
      return;
    }
    const profile = prof || state.profile;
    const filename = fname || state.active_doc;
    if (!profile || !profile.columns) return;

    let html = `
      <div class="profile-popover-header">
        <span class="profile-popover-title">📊 ${escapeHTML(filename || 'Dataset Profile')}</span>
        <button class="profile-popover-close" id="btnCloseProfilePopover" aria-label="Close">✕</button>
      </div>
      <table class="profile-popover-table">
        <thead>
          <tr>
            <th>Column</th>
            <th>Type</th>
            <th>Null %</th>
          </tr>
        </thead>
        <tbody>
    `;

    profile.columns.forEach(col => {
      html += `
        <tr>
          <td class="col-name">${escapeHTML(col.name)}</td>
          <td class="col-type">${escapeHTML(col.dtype)}</td>
          <td>${col.null_pct}%</td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
    profilePopover.innerHTML = html;
    profilePopover.style.display = 'block';

    const closeBtn = document.getElementById('btnCloseProfilePopover');
    if (closeBtn) {
      closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        profilePopover.style.display = 'none';
      });
    }
  }

  if (profileChipBtn) {
    profileChipBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const activeEntry = (state.indexed_docs || []).find(d => d.filename === state.active_doc);
      const prof = state.profile || (activeEntry && activeEntry.profile);
      toggleProfilePopover(prof, state.active_doc);
    });
  }

  document.addEventListener('click', (e) => {
    if (profilePopover && profilePopover.style.display === 'block') {
      if (!profilePopover.contains(e.target) && !profileChipBtn.contains(e.target)) {
        profilePopover.style.display = 'none';
      }
    }
  });

  function renderActiveDocPill() {
    if (state.active_doc) {
      activeDocPill.style.display = 'inline-flex';
      activeDocName.textContent = state.active_doc;
      const analyzeInfo = document.getElementById('analyzeActiveDoc');
      if (analyzeInfo) analyzeInfo.textContent = state.active_doc;

      const activeEntry = (state.indexed_docs || []).find(d => d.filename === state.active_doc);
      const prof = state.profile || (activeEntry && activeEntry.profile);
      if (prof && (activeEntry?.kind === 'tabular' || prof.columns)) {
        const numNumeric = prof.columns ? prof.columns.filter(c => c.dtype === 'numeric').length : Object.keys(prof.numeric_summary || {}).length;
        if (profileChipContainer && profileChipText) {
          profileChipText.textContent = `📊 ${prof.row_count} rows • ${prof.col_count} cols • ${numNumeric} numeric`;
          profileChipContainer.style.display = 'inline-flex';
        }
      } else {
        if (profileChipContainer) profileChipContainer.style.display = 'none';
        if (profilePopover) profilePopover.style.display = 'none';
      }
    } else {
      activeDocPill.style.display = 'none';
      activeDocName.textContent = '';
      if (profileChipContainer) profileChipContainer.style.display = 'none';
      if (profilePopover) profilePopover.style.display = 'none';
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
      state.profile = data.profile || null;
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
      if (!state.active_doc) state.profile = null;
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

  async function handleFileUpload(file) {
    if (!file) return;

    const allowed = ['.pdf', '.docx', '.txt', '.csv', '.xlsx'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) {
      showToast('Unsupported file type. Please upload a PDF, DOCX, TXT, CSV, or XLSX file.', 'error');
      return;
    }

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
      state.profile = data.profile || null;
      renderRecentDocs();
      renderActiveDocPill();
      if (data.kind === 'tabular' || data.row_count != null) {
        const prof = data.profile;
        const numNumeric = prof && prof.columns ? prof.columns.filter(c => c.dtype === 'numeric').length : 0;
        const chipStr = prof ? `📊 ${prof.row_count} rows • ${prof.col_count} cols • ${numNumeric} numeric` : `📊 ${data.row_count} rows`;
        showToast(`✓ Uploaded ${data.filename} (${chipStr})`, 'success');
      } else {
        showToast(`✓ Indexed ${data.chunks} chunks from ${data.filename}`, 'success');
      }
      if (state.mode === 'Analyze') {
        loadAnalyzeTab(state.activeTab, true);
      }
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      state.isUploading = false;
      updateSendButtonState();
    }
  }

  fileUploadInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    fileUploadInput.value = '';
    if (file) {
      await handleFileUpload(file);
    }
  });

  // ---- Window-level Drag & Drop (overlay, works in any state) ----
  const dragOverlay = document.getElementById('dragOverlay');
  let dragCounter = 0;

  function isFileDrag(e) {
    return e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files');
  }
  function hideDragOverlay() {
    dragCounter = 0;
    if (dragOverlay) dragOverlay.classList.remove('active');
  }

  window.addEventListener('dragenter', (e) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    dragCounter++;
    if (dragCounter === 1 && dragOverlay) dragOverlay.classList.add('active');
  });
  window.addEventListener('dragover', (e) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  });
  window.addEventListener('dragleave', (e) => {
    if (!isFileDrag(e)) return;
    dragCounter--;
    if (dragCounter <= 0) hideDragOverlay();
  });
  window.addEventListener('drop', async (e) => {
    e.preventDefault();
    hideDragOverlay();
    const files = e.dataTransfer ? e.dataTransfer.files : null;
    if (files && files.length > 0) {
      await handleFileUpload(files[0]);
    }
  });
  window.addEventListener('dragend', hideDragOverlay);

  btnNewChat.addEventListener('click', async () => {
    if (btnNewChat.disabled) return;
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
      btnNewChat.innerHTML = '<span>+</span><span>New chat</span>';
      updateSendButtonState();
    }
  });

  // ====================================================================
  // Chat Rendering & SSE Streaming Mechanics
  // ====================================================================
  function updateSendButtonState() {
    if (state.isStreaming) {
      btnSend.disabled = false;
      btnSend.classList.add('btn-stop');
      btnSend.innerHTML = '■';
      btnSend.setAttribute('title', 'Stop generation');
      btnSend.setAttribute('aria-label', 'Stop generation');
      return;
    }
    btnSend.classList.remove('btn-stop');
    btnSend.innerHTML = '↑';
    btnSend.setAttribute('title', 'Send message');
    btnSend.setAttribute('aria-label', 'Send message');
    const val = chatInput.value.trim();
    btnSend.disabled = !val || state.isUploading;
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
        if (state.isStreaming) {
          if (state.streamAbortController) state.streamAbortController.abort();
        } else {
          sendMessage(chatInput.value.trim());
        }
      }
    }
  });

  btnSend.addEventListener('click', () => {
    if (state.isStreaming) {
      if (state.streamAbortController) {
        state.streamAbortController.abort();
      }
      return;
    }
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

    botWrap.appendChild(createMessageToolbar(text));

    row.appendChild(botWrap);
    chatMessages.appendChild(row);
  }

  function createMessageToolbar(text) {
    const bar = document.createElement('div');
    bar.className = 'riq-msg-toolbar';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn-copy-msg';
    copyBtn.setAttribute('title', 'Copy response');
    copyBtn.setAttribute('aria-label', 'Copy response');
    copyBtn.innerHTML = `
      <svg class="copy-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
      </svg>
      <span class="copy-label">Copy</span>
    `;

    copyBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.innerHTML = `
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--success, #10B981);">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          <span class="copy-label" style="color:var(--success, #10B981);">Copied!</span>
        `;
        setTimeout(() => {
          copyBtn.innerHTML = `
            <svg class="copy-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
            <span class="copy-label">Copy</span>
          `;
        }, 2000);
      } catch (err) {
        showToast('Could not copy to clipboard', 'error');
      }
    });

    bar.appendChild(copyBtn);
    return bar;
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
      let headerTitle = label;
      const parts = [];
      if (s.kind === 'tabular' && s.row_start != null && s.row_end != null) {
        headerTitle = `Rows ${s.row_start}-${s.row_end} • ${label}`;
        if (s.sheet) parts.push(`Sheet: ${s.sheet}`);
      } else if (s.kind === 'tabular_profile') {
        headerTitle = `Dataset Overview • ${label}`;
        if (s.row_end) parts.push(`All ${s.row_end} rows`);
      } else {
        if (s.page !== undefined && s.page !== null) parts.push(`Page ${s.page}`);
        if (s.chunk !== undefined && s.chunk !== null) parts.push(`Chunk ${s.chunk}`);
      }
      if (s.score !== undefined && s.score !== null) parts.push(`${Math.round(s.score * 100)}% match`);
      const meta = parts.join(' • ');
      row.innerHTML = `
        <strong>${escapeHTML(headerTitle)}${meta ? ` (${escapeHTML(meta)})` : ''}:</strong><br>
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

            if (!botWrap.querySelector('.riq-msg-toolbar')) {
              botWrap.appendChild(createMessageToolbar(finalAns));
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
        if (!hasReplacedSkeleton) {
          skeletonWrap.remove();
          bodyContainer = document.createElement('div');
          bodyContainer.className = 'riq-msg-bot-body';
          botWrap.appendChild(bodyContainer);
          hasReplacedSkeleton = true;
          bodyContainer.innerHTML = '<span style="color:var(--text-muted); font-style:italic;">Generation stopped.</span>';
        }
        if (fullAnswer && !botWrap.querySelector('.riq-msg-toolbar')) {
          botWrap.appendChild(createMessageToolbar(fullAnswer));
        }
        if (fullAnswer) {
          state.messages.push({ role: 'user', content: question, timestamp: nowTime });
          state.messages.push({
            role: 'assistant',
            content: fullAnswer,
            sources: [],
            timestamp: nowTime
          });
        }
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

    if (tabId === 'tabAudit') {
      if (!state.analysisCache.resume || force) {
        const axisContainer = document.getElementById('auditAxisContainer');
        if (axisContainer) {
          axisContainer.innerHTML = '<div class="riq-skeleton-wrap"><div class="riq-skeleton-line"></div><div class="riq-skeleton-line"></div><div class="riq-skeleton-line"></div></div>';
        }
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

  // 1. Empty State (When no document is uploaded)
  function showAnalyzeEmptyState() {
    const axis = document.getElementById('auditAxisContainer');
    if (axis) axis.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted);">Upload a résumé to view audit.</div>';
    const mistakes = document.getElementById('auditMistakesContainer');
    if (mistakes) mistakes.innerHTML = '';
    const rewrites = document.getElementById('auditRewritesContainer');
    if (rewrites) rewrites.innerHTML = '';
  }

  // --- NEW: Copy to Clipboard Utility ---
  function copyToClipboard(text, btnElement) {
    navigator.clipboard.writeText(text).then(() => {
      const originalText = btnElement.textContent;
      btnElement.textContent = 'Copied!';
      btnElement.classList.add('copied');
      setTimeout(() => {
        btnElement.textContent = originalText;
        btnElement.classList.remove('copied');
      }, 1500);
    }).catch(() => {
      showToast('Could not copy to clipboard', 'error');
    });
  }

  // --- NEW: Download Analysis Report ---
  function downloadAnalysisReport() {
    if (!state.analysisCache.resume) {
      showToast('Run an analysis first to download.', 'error');
      return;
    }
    const data = state.analysisCache.resume;
    let report = `RESUME IQ - PRO ANALYSIS REPORT\n`;
    report += `Generated: ${new Date().toLocaleString()}\n`;
    report += `${'='.repeat(50)}\n\n`;
    report += `OVERALL ATS SCORE: ${data.overall_score}/100\n\n`;
    
    report += `AXIS BREAKDOWN:\n`;
    if (data.axis_scores) {
      for (const [axis, score] of Object.entries(data.axis_scores)) {
        const feedback = data.axis_feedback?.[axis] || 'No specific feedback provided.';
        report += `- ${axis.replace(/_/g, ' ').toUpperCase()}: ${score}/100\n  Reason: ${feedback}\n`;
      }
    }
    
    report += `\nCRITICAL MISTAKES & MISSING ELEMENTS:\n`;
    (data.mistakes_and_missing || []).forEach((m, i) => report += `${i + 1}. ${m}\n`);
    
    report += `\nBULLET POINT REWRITES:\n`;
    (data.bullet_rewrites || []).forEach((rw, i) => {
      report += `\nRewrite ${i + 1}:\n[WEAK] ${rw.weak_original}\n[STRONG] ${rw.strong_version}\n`;
    });

    const blob = new Blob([report], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ResumeIQ_Analysis_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Report downloaded!', 'success');
  }

  // --- UPDATE: Render Audit Data (Adds Copy Buttons & Tooltips) ---
  function renderAuditData(data) {
    if (!data) return;
    const axisContainer = document.getElementById('auditAxisContainer');
    axisContainer.innerHTML = '';

    if (data.axis_scores) {
      for (const [axisName, axisScore] of Object.entries(data.axis_scores)) {
        const feedback = data.axis_feedback?.[axisName] || 'No specific feedback.';
        const formattedName = axisName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        
        const card = document.createElement('div');
        card.className = 'axis-card';
        card.innerHTML = `
          <div class="axis-head">
            <span class="axis-title-wrap">
              ${escapeHTML(formattedName)}
              <span class="info-icon" title="${escapeHTML(feedback)}">ⓘ</span>
            </span>
            <span class="axis-score">${axisScore}/100</span>
          </div>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" style="width:${axisScore}%;"></div>
          </div>
        `;
        axisContainer.appendChild(card);
      }
    }

    // Mistakes
    const mistakesContainer = document.getElementById('auditMistakesContainer');
    mistakesContainer.innerHTML = '';
    if (data.mistakes_and_missing) {
      data.mistakes_and_missing.forEach(m => {
        const item = document.createElement('div');
        item.className = 'weak-box';
        item.textContent = m;
        mistakesContainer.appendChild(item);
      });
    }

    // Rewrites (WITH COPY BUTTON)
    const rewritesContainer = document.getElementById('auditRewritesContainer');
    rewritesContainer.innerHTML = '';
    if (data.bullet_rewrites) {
      data.bullet_rewrites.forEach(rw => {
        const card = document.createElement('div');
        card.className = 'rewrite-card';
        card.innerHTML = `
          <div class="weak-box"><strong>Weak Original:</strong><br>${escapeHTML(rw.weak_original)}</div>
          <div class="strong-box">
            <div class="strong-box-head">
              <strong>Strong Version:</strong>
              <button class="copy-btn" data-copy="${escapeHTML(rw.strong_version)}">Copy</button>
            </div>
            <div>${escapeHTML(rw.strong_version)}</div>
          </div>
        `;
        rewritesContainer.appendChild(card);
      });
    }
    
    // Attach copy listeners
    rewritesContainer.querySelectorAll('.copy-btn').forEach(btn => {
      btn.addEventListener('click', (e) => copyToClipboard(e.target.dataset.copy, e.target));
    });
  }

  // --- UPDATE: Render Questions Data (WITH COPY BUTTON) ---
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
        <div class="q-header">
          <span class="q-category-badge">${escapeHTML(q.category || 'General')}</span>
          <button class="copy-btn" data-copy="${escapeHTML(q.question)}">Copy Question</button>
        </div>
        <div class="q-text">${escapeHTML(q.question)}</div>
        <div class="q-rubric"><strong>Tests:</strong> ${escapeHTML(q.what_is_tested || '—')}</div>
        <div class="q-rubric"><strong>Ideal Answer:</strong> ${escapeHTML(q.ideal_answer_outline || '—')}</div>
      `;
      list.appendChild(card);
    });

    list.querySelectorAll('.copy-btn').forEach(btn => {
      btn.addEventListener('click', (e) => copyToClipboard(e.target.dataset.copy, e.target));
    });
  }

  // --- UPDATE: JD Match Rendering (Handles Categorized Keywords) ---
  function renderJdResults(matchData) {
    document.getElementById('jdGaugeWrap').innerHTML = renderGaugeSVG(matchData.match_percentage || 0, 110, 8);

    // Helper to render categorized chips
    const renderChips = (containerId, categories, type) => {
      const container = document.getElementById(containerId);
      container.innerHTML = '';
      if (!categories) return;
      
      const classMap = { hard_skills: 'kw-chip-hard', soft_skills: 'kw-chip-soft', tools: 'kw-chip-tool' };
      const labelMap = { hard_skills: 'Hard', soft_skills: 'Soft', tools: 'Tool' };

      if (Array.isArray(categories)) {
        categories.forEach(k => {
          const chip = document.createElement('span');
          chip.className = `kw-chip ${type === 'match' ? 'kw-chip-match' : 'kw-chip-missing'}`;
          const icon = type === 'match' ? '✓' : '✗';
          chip.textContent = `${icon} ${k}`;
          container.appendChild(chip);
        });
        return;
      }

      for (const [cat, keywords] of Object.entries(categories)) {
        if (Array.isArray(keywords)) {
          keywords.forEach(k => {
            const chip = document.createElement('span');
            chip.className = `kw-chip ${classMap[cat] || (type === 'match' ? 'kw-chip-match' : 'kw-chip-missing')}`;
            const icon = type === 'match' ? '✓' : '✗';
            const badge = labelMap[cat] ? ` [${labelMap[cat]}]` : '';
            chip.textContent = `${icon} ${k}${badge}`;
            container.appendChild(chip);
          });
        }
      }
    };

    renderChips('jdMatchedChips', matchData.matched_keywords, 'match');
    renderChips('jdMissingChips', matchData.missing_keywords, 'missing');

    const sugList = document.getElementById('jdSuggestionsList');
    sugList.innerHTML = '';
    (matchData.edit_suggestions || []).forEach(s => {
      const card = document.createElement('div');
      card.className = 'axis-card';
      card.style.marginBottom = '8px';
      card.textContent = s;
      sugList.appendChild(card);
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
      renderJdResults(matchData);
      showToast('JD Analysis complete', 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      btnRunJdMatch.disabled = false;
      btnRunJdMatch.textContent = 'Match Against Resume';
    }
  });

  const btnDownloadReport = document.getElementById('btnDownloadReport');
  if (btnDownloadReport) {
    btnDownloadReport.addEventListener('click', downloadAnalysisReport);
  }

  // ====================================================================
  // Theme System: Light / Dark / System
  // ====================================================================
  const btnThemeToggle = document.getElementById('btnThemeToggle');
  const systemDarkQuery = window.matchMedia('(prefers-color-scheme: dark)');

  const THEMES = ['light', 'dark', 'system'];
  const THEME_ICONS = {
    light: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>',
    dark: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>',
    system: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>'
  };
  const THEME_LABELS = { light: 'Light', dark: 'Dark', system: 'System' };

  let currentThemePref = localStorage.getItem('riq-theme') || 'system';

  function applyTheme(pref, animate = true) {
    if (animate) {
      document.documentElement.classList.add('theme-transitioning');
    }

    let effectiveTheme = pref;
    if (pref === 'system') {
      effectiveTheme = systemDarkQuery.matches ? 'dark' : 'light';
    }

    document.documentElement.setAttribute('data-theme', effectiveTheme);

    if (btnThemeToggle) {
      btnThemeToggle.innerHTML = THEME_ICONS[pref] || THEME_ICONS.system;
      btnThemeToggle.title = `Theme: ${THEME_LABELS[pref] || 'System'}`;
      btnThemeToggle.setAttribute('aria-label', `Theme: ${THEME_LABELS[pref] || 'System'}`);
    }

    if (animate) {
      setTimeout(() => {
        document.documentElement.classList.remove('theme-transitioning');
      }, 250);
    }
  }

  function cycleTheme() {
    const nextIdx = (THEMES.indexOf(currentThemePref) + 1) % THEMES.length;
    currentThemePref = THEMES[nextIdx];
    localStorage.setItem('riq-theme', currentThemePref);
    applyTheme(currentThemePref, true);
  }

  if (btnThemeToggle) {
    btnThemeToggle.addEventListener('click', cycleTheme);
  }

  systemDarkQuery.addEventListener('change', () => {
    if (currentThemePref === 'system') {
      applyTheme('system', true);
    }
  });

  // Apply theme immediately without transition flash
  applyTheme(currentThemePref, false);

  // Initial Load
  loadInitialState();
})();
