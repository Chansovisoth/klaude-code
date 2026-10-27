"use strict";

// Canvas drafts stay in this tab and session. Document previews reuse the passive viewer.
window.ChatCanvas = (() => {
  const drafts = new Map(), mobile = matchMedia('(max-width: 1100px)');
  let panel, editor, documents, name, language, preview, status, editTab, previewTab;
  let current, trigger, restoreContext = false, generation = 0, serial = 0;
  let launch, menuItem;
  function refreshLaunchers() {
    const available = authenticated && currentView === 'chat' && (drafts.size > 0 ||
      !!document.querySelector('#messages [data-canvas-entry]:not([hidden])'));
    if (launch) launch.hidden = !available;
    if (menuItem) menuItem.hidden = !available;
  }
  function openAvailable() {
    if (current || drafts.size) { open(); return; }
    const entries = document.querySelectorAll('#messages [data-canvas-entry]:not([hidden])');
    entries[entries.length - 1]?.click();
  }
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const icon = (shape = 'M4 3h16v18H4zM8 7h8M8 11h8M8 15h5') => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.classList.add('icon');
    for (const [key, value] of Object.entries({viewBox:'0 0 24 24', fill:'none', stroke:'currentColor', 'stroke-width':'1.7', 'aria-hidden':'true'})) svg.setAttribute(key, value);
    const path = document.createElementNS(svg.namespaceURI, 'path');
    path.setAttribute('d', shape); svg.append(path); return svg;
  };
  function button(text, action, className = 'quiet') {
    const node = element('button', text, className); node.type = 'button';
    node.addEventListener('click', action); return node;
  }
  const notice = text => window.KlaudeToast?.show(text, {variant:'info'});
  function persist() {
    if (!current) return;
    current.source = editor.value; current.name = name.value; current.language = language.value;
    status.textContent = `${current.source.split('\n').length} lines · Draft`;
    const selected = documents.selectedOptions[0]; if (selected) selected.textContent = current.name || 'Untitled';
  }
  function select(draft) {
    persist(); generation++; current = draft;
    editor.value = draft.source; name.value = draft.name;
    if (![...language.options].some(option => option.value === draft.language)) language.append(new Option(draft.language, draft.language));
    language.value = draft.language;
    documents.replaceChildren(...[...drafts.values()].map(item => new Option(item.name || 'Untitled', item.id)));
    documents.value = draft.id; showEditor(); persist();
  }
  function showEditor() {
    generation++; preview.replaceChildren(); preview.hidden = true; editor.hidden = false;
    const writing = language.value === 'markdown' || language.value === 'text';
    editor.wrap = writing ? 'soft' : 'off'; editor.spellcheck = writing;
    editor.style.whiteSpace = writing ? 'pre-wrap' : 'pre'; editor.classList.toggle('canvas-writing', writing);
    editTab.setAttribute('aria-selected', 'true'); previewTab.setAttribute('aria-selected', 'false');
    editTab.tabIndex = 0; previewTab.tabIndex = -1;
  }
  async function showPreview() {
    persist(); const version = ++generation, draft = current;
    editor.hidden = true; preview.hidden = false; preview.replaceChildren();
    editTab.setAttribute('aria-selected', 'false'); previewTab.setAttribute('aria-selected', 'true');
    editTab.tabIndex = -1; previewTab.tabIndex = 0;
    if (draft.language === 'markdown') {
      preview.classList.add('markdown-body');
      preview.append(ChatMarkdown.renderDocument(draft.source)); return;
    }
    preview.classList.remove('markdown-body');
    if (['html', 'svg'].includes(draft.language)) {
      const loading = element('p', 'Loading preview…', 'muted'); preview.append(loading);
      try {
        const result = await jsonRequest('/api/v1/chat-previews', 'POST', {source:draft.source});
        if (version !== generation || !panel.open || current !== draft) return;
        if (!/^\/api\/v1\/chat-previews\/[a-f0-9]{32}$/.test(result.url)) throw Error('Invalid preview');
        const frame = element('iframe'); frame.title = `Preview of ${draft.name}`;
        frame.setAttribute('sandbox', ''); frame.referrerPolicy = 'no-referrer'; frame.src = result.url;
        preview.replaceChildren(frame);
      } catch (error) {
        if (version === generation && panel.open) loading.textContent = error.status === 404 ?
          'Restart Web UI to enable document previews.' : 'Preview unavailable. Your draft is still available in the editor.';
      }
    } else {
      const pre = element('pre'), code = element('code');
      ChatMarkdown.highlight(code, draft.source, draft.language); pre.append(code); preview.append(pre);
    }
  }
  function download() {
    persist();
    const safeName = (current.name || 'canvas.txt').replace(/[\\/\u0000-\u001f\u007f]/g, '_').slice(0, 160);
    const url = URL.createObjectURL(new Blob([current.source], {type:'text/plain;charset=utf-8'}));
    const link = element('a'); link.href = url; link.download = safeName;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function ask() {
    persist(); const selected = editor.value.slice(editor.selectionStart, editor.selectionEnd) || current.source;
    if (selected.length > 16000) { notice('Select a smaller section to discuss in chat.'); return; }
    const prompt = document.getElementById('prompt');
    const request = `Please help revise ${current.name || 'this draft'}:\n\n${selected}`;
    if (prompt.value.length + request.length > 32000) { notice('Make room in your chat draft first.'); return; }
    prompt.value += `${prompt.value ? '\n\n' : ''}${request}`;
    prompt.dispatchEvent(new Event('input', {bubbles:true}));
    if (mobile.matches) { trigger = prompt; panel.close(); }
    prompt.focus(); notice('Added to your chat draft. Add instructions, then send.');
  }
  function closed() {
    if (panel.open) return;
    persist(); generation++; preview.replaceChildren();
    if (restoreContext) { restoreContext = false; setContextPanel(true); }
    if (trigger?.isConnected && !trigger.closest('[hidden]')) trigger.focus({preventScroll:true});
  }
  function open(options = {}) {
    if (!authenticated || !latest?.session_id) return;
    initialize();
    if (options.source !== undefined && (typeof options.source !== 'string' || options.source.length > 128000)) {
      notice('This document is too large for Canvas.'); return;
    }
    let draft;
    if (options.source !== undefined) {
      draft = [...drafts.values()].find(item => item.original === options.source && item.originalName === options.name);
      if (!draft) {
        if (drafts.size >= 20) { notice('Close a canvas with Discard before opening another.'); return; }
        const value = options.source;
        draft = {id:String(++serial), source:value, original:value, originalName:options.name,
          name:options.name || 'Untitled.md', language:options.language || 'markdown'};
        drafts.set(draft.id, draft);
      }
    } else draft = current || [...drafts.values()].at(-1);
    if (!draft) {
      draft = {id:String(++serial), source:'', original:'', name:'Untitled.md', language:'markdown'};
      drafts.set(draft.id, draft);
    }
    trigger = options.trigger || document.activeElement;
    if (currentView !== 'chat') showView('chat');
    if (!panel.open) {
      restoreContext = contextPanelOpen; if (restoreContext) setContextPanel(false);
      if (mobile.matches) panel.showModal(); else panel.show();
    }
    select(draft); editor.focus(); refreshLaunchers();
  }
  function reset() {
    generation++; drafts.clear(); current = null; trigger = null;
    if (restoreContext) { restoreContext = false; setContextPanel(true); }
    if (panel?.open) panel.close();
    if (panel) { editor.value = ''; name.value = ''; documents.replaceChildren(); preview.replaceChildren(); }
    if (launch) launch.hidden = true;
    if (menuItem) menuItem.hidden = true;
  }
  function initialize() {
    if (panel) return;
    panel = element('dialog', undefined, 'chat-canvas'); panel.id = 'chat-canvas'; panel.setAttribute('aria-labelledby', 'canvas-title');
    const heading = element('header', undefined, 'canvas-heading'), title = element('h2', 'Canvas'); title.id = 'canvas-title';
    const close = button('×', () => panel.close(), 'icon-button quiet'); close.setAttribute('aria-label', 'Close Canvas');
    close.replaceChildren(icon('m6 6 12 12M6 18 18 6'));
    heading.append(title, close);
    const toolbar = element('div', undefined, 'canvas-toolbar');
    documents = element('select'); documents.setAttribute('aria-label', 'Open canvases');
    documents.addEventListener('change', () => select(drafts.get(documents.value)));
    toolbar.append(documents, button('New', () => open({source:'', name:`Untitled ${serial + 1}.md`, language:'markdown', trigger:document.activeElement})));
    const info = element('div', undefined, 'canvas-document');
    name = element('input'); name.maxLength = 160; name.setAttribute('aria-label', 'Canvas filename');
    language = element('select'); language.setAttribute('aria-label', 'Canvas language');
    for (const [value, label] of [['markdown','Writing'],['text','Plain text'],['python','Python'],['javascript','JavaScript'],['typescript','TypeScript'],['html','HTML'],['css','CSS'],['svg','SVG'],['json','JSON'],['bash','Shell'],['other','Other code']]) language.append(new Option(label, value));
    name.addEventListener('input', persist); language.addEventListener('change', () => { persist(); showEditor(); }); info.append(name, language);
    const tabs = element('div', undefined, 'canvas-tabs segmented'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Canvas view');
    editTab = button('Edit', showEditor); previewTab = button('Preview', showPreview);
    editTab.id = 'canvas-edit-tab'; previewTab.id = 'canvas-preview-tab';
    for (const [tab, controls] of [[editTab,'canvas-editor'],[previewTab,'canvas-preview']]) {
      tab.setAttribute('role', 'tab'); tab.setAttribute('aria-controls', controls); tabs.append(tab);
      tab.addEventListener('keydown', event => {
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault(); const next = event.key === 'Home' ? editTab : event.key === 'End' ? previewTab : tab === editTab ? previewTab : editTab;
        next.click(); next.focus();
      });
    }
    editor = element('textarea'); editor.id = 'canvas-editor'; editor.maxLength = 128000; editor.spellcheck = false;
    editor.setAttribute('aria-label', 'Canvas editor'); editor.setAttribute('aria-labelledby', 'canvas-edit-tab');
    editor.addEventListener('input', persist);
    editor.addEventListener('keydown', event => {
      if (event.key === 'Tab' && !event.shiftKey && !event.ctrlKey && !event.metaKey && !['markdown','text'].includes(language.value)) {
        event.preventDefault();
        if (editor.value.length - (editor.selectionEnd - editor.selectionStart) + 2 <= editor.maxLength) {
          editor.setRangeText('  ', editor.selectionStart, editor.selectionEnd, 'end'); persist();
        }
      }
    });
    preview = element('div', undefined, 'canvas-preview'); preview.id = 'canvas-preview'; preview.tabIndex = 0;
    preview.setAttribute('role', 'tabpanel'); preview.setAttribute('aria-labelledby', 'canvas-preview-tab');
    status = element('small', '', 'muted'); status.id = 'canvas-status';
    const footer = element('footer', undefined, 'canvas-footer');
    footer.append(status, button('Ask Klaude', ask), button('Download', download), button('Discard', () => {
      const id = current.id; current = null; drafts.delete(id);
      const next = [...drafts.values()].at(-1); if (next) select(next); else { panel.close(); editor.value = ''; }
      refreshLaunchers();
    }));
    panel.append(heading, toolbar, info, tabs, editor, preview, footer);
    document.getElementById('main-content').append(panel);
    panel.addEventListener('close', closed);
    panel.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); download(); }
      if (event.key === 'Escape' && !mobile.matches) { event.preventDefault(); panel.close(); }
    });
    launch = button('Canvas', openAvailable, 'quiet canvas-launch'); launch.prepend(icon()); launch.title = 'Open Canvas';
    document.querySelector('.topbar-actions').prepend(launch);
    const menu = document.getElementById('mobile-chat-menu');
    menuItem = button('Canvas', () => { menu.hidePopover?.(); openAvailable(); }, 'message-action');
    const tile = element('span', undefined, 'menu-action-icon'); tile.setAttribute('aria-hidden', 'true'); tile.append(icon());
    menuItem.setAttribute('role', 'menuitem'); menuItem.prepend(tile); menu.prepend(menuItem);
    refreshLaunchers();
  }
  mobile.addEventListener('change', () => {
    if (!panel?.open) return;
    const focused = panel.contains(document.activeElement) ? document.activeElement : editor;
    panel.close(); if (mobile.matches) panel.showModal(); else panel.show();
    focused.focus({preventScroll:true});
  });
  document.addEventListener('klaude-auth-reset', reset);
  document.addEventListener('klaude-chat-session-changed', reset);
  document.addEventListener('klaude-view', () => { if (currentView !== 'chat' && panel?.open) panel.close(); refreshLaunchers(); });
  document.addEventListener('klaude-snapshot', refreshLaunchers);
  document.addEventListener('klaude-canvas-availability', () => queueMicrotask(refreshLaunchers));
  window.addEventListener('pagehide', reset);
  document.addEventListener('DOMContentLoaded', initialize);
  return Object.freeze({open});
})();
