/* Mobile presentation over the existing chat catalog, runtime actions and menus.
 * Bundled into app.js; no additional route or provider discovery path. */
window.MobileChatUI = (() => {
  let initialized = false, sheet, title, menu, more;
  let page = 1, error = '', reading = false, listKey = '', connectionKey = '';
  let viewportFrame = 0;
  const viewportHeights = new Map();
  const text = (tag, value, className = '') => {
    const node = document.createElement(tag); node.textContent = value; node.className = className; return node;
  };
  const infoTrigger = () => narrowScreen.matches ? more : byId('chat-info-toggle');
  function render() {
    if (!initialized) return;
    const model = latest?.requires_model_selection ? 'Choose a model' : latest?.model || 'Choose a model';
    const modes = [latest?.mode === 'thinking' ? 'Thinking' : '', latest?.plan_mode ? 'Plan' : ''].filter(Boolean);
    const label = [model, ...modes].join(' · ');
    const chat = currentView === 'chat';
    byId('chat-create-image').hidden = !chat || !latest?.profile_management;
    byId('attach-create-image').disabled = !latest?.profile_management;
    byId('mobile-chat-subtitle').textContent = label;
    byId('mobile-chat-subtitle').setAttribute('aria-hidden', String(!chat));
    title.tabIndex = chat ? 0 : -1;
    title.setAttribute('aria-disabled', String(!chat));
    title.setAttribute('aria-label', chat ? `Choose chat model · ${label}` : 'Klaude');
    if (chat) title.title = label; else title.removeAttribute('title');
    if (!sheet.open || !latest) return;
    const connection = byId('model-connection-choice'), mobileConnection = byId('mobile-model-connection');
    const options = [...connection.options];
    const nextConnectionKey = JSON.stringify(options.map(option => [option.value, option.textContent, option.disabled, option.dataset.backend, option.dataset.source]));
    if (nextConnectionKey !== connectionKey) {
      connectionKey = nextConnectionKey;
      mobileConnection.replaceChildren(...options.map(option => option.cloneNode(true)));
    }
    mobileConnection.value = connection.value; mobileConnection.disabled = connection.disabled || reading;
    byId('mobile-model-connection-label').hidden = !latest.model_providers || options.length < 2;
    const selected = connection.selectedOptions[0];
    const source = latest.model_providers ? selected?.dataset.source : 'Local';
    const backend = latest.model_providers ? selected?.dataset.backend : 'ollama';
    byId('mobile-model-group').textContent = source === 'Local' ? 'Local models' : source === 'Cloud' ? 'Cloud models' : 'Models';
    const current = latest.model_providers ? latest.model_ref : latest.model;
    const sameConnection = !latest.model_providers || connection.value === latest.model_connection;
    const choices = [...localModels];
    if (sameConnection && !latest.requires_model_selection && !choices.some(item => item.id === current)) choices.unshift({id: current, name: latest.model});
    choices.sort((a, b) => Number(b.id === current) - Number(a.id === current));
    const query = byId('mobile-model-search').value.trim().toLocaleLowerCase();
    const filtered = choices.filter(item => `${item.name} ${item.id}`.toLocaleLowerCase().includes(query));
    page = Math.max(1, Math.min(page, Math.ceil(filtered.length / 20) || 1));
    const offset = (page - 1) * 20, items = filtered.slice(offset, offset + 20);
    const deferred = latest.chat_deferred_model_selection === true;
    const locked = runtimeChoiceInFlight || !deferred && (Boolean(latest.active_turn_id) || Boolean(latest.queue?.length));
    const status = error || (reading ? 'Loading models…' : locked ?
      'Finish the current reply and queued messages before changing models.' : !filtered.length ?
        query ? 'No matching models.' : byId('model-status').textContent || 'No models available.' : deferred && (latest.active_turn_id || latest.queue?.length) ? 'Your selection applies to the next prompt, including queued messages.' : '');
    byId('mobile-model-status').textContent = status;
    byId('mobile-model-status').dataset.error = String(Boolean(error));
    byId('mobile-model-refresh').disabled = reading;
    byId('mobile-model-list').setAttribute('aria-busy', String(reading));
    const nextListKey = JSON.stringify([items, filtered.length, current, locked, backend, source, page]);
    if (nextListKey === listKey) return;
    listKey = nextListKey;
    const list = byId('mobile-model-list');
    const focused = list.contains(document.activeElement) ? document.activeElement.dataset.modelId : null;
    list.replaceChildren(...items.map(item => {
      const row = text('div', '', 'collection-row library-card');
      const button = text('button', '', 'collection-open mobile-model-row'); button.type = 'button';
      button.dataset.modelId = item.id; button.disabled = locked;
      if (item.id === current && !latest.requires_model_selection) button.setAttribute('aria-current', 'true');
      const icon = text('span', '', 'model-brand-icon'); icon.setAttribute('aria-hidden', 'true');
      setModelBrandIcon(icon, item.id, backend || '');
      const copy = text('span', '', 'mobile-model-copy'), name = text('strong', item.name);
      const identity = window.AIIcons?.resolveModel(item.id, {provider: backend || ''});
      const platform = identity?.runtime?.name || identity?.apiProvider?.name || selected?.textContent?.replace(/ · (Local|Cloud)$/, '') || 'Model';
      const active = item.id === current && !latest.requires_model_selection;
      const state = active ? latest.model_selection_pending ? 'Next prompt' : 'Active' : source === 'Local' && backend === 'ollama' ? 'Installed' : 'Available';
      const caption = text('small', '');
      caption.append(text('span', platform, 'mobile-model-platform'), text('span', `· ${state}`, 'mobile-model-state'));
      copy.append(name, caption); button.append(icon, copy); row.append(button);
      button.addEventListener('click', async () => {
        if (active) { closeModels(); return; }
        const epoch = authEpoch, session = latest.session_id;
        error = '';
        const applied = await chooseRuntime('model', item.id, {onError: failure => {
          if (epoch === authEpoch && latest?.session_id === session && sheet.open) error = failure.message;
        }});
        if (epoch !== authEpoch || latest?.session_id !== session || !sheet.open) return;
        if (applied) closeModels();
        else {
          render();
          const status = byId('mobile-model-status'); status.tabIndex = -1;
          status.focus({preventScroll: true}); status.scrollIntoView({block: 'nearest'});
        }
      });
      return row;
    }));
    if (focused) focusModel(focused);
    if (typeof updateDomainPager === 'function') updateDomainPager('mobile-model', offset, {
      items, total: filtered.length, page_size: 20, more: offset + items.length < filtered.length,
    });
    byId('mobile-model-pages').hidden = filtered.length <= 20;
  }
  function focusModel(id) {
    [...byId('mobile-model-list').querySelectorAll('button')].find(node => node.dataset.modelId === id)?.focus({preventScroll: true});
  }
  function positionModels() {
    if (!sheet.open) return;
    const view = window.visualViewport, height = view?.height || innerHeight;
    sheet.style.maxHeight = `${Math.max(80, Math.min(narrowScreen.matches ? height * .85 : 720, height - (narrowScreen.matches ? 16 : 32)))}px`;
    sheet.style.bottom = narrowScreen.matches ? `${Math.max(0, innerHeight - height - (view?.offsetTop || 0))}px` : '';
  }
  function closeModels() { if (sheet.open) sheet.close(); }
  function closeMenu() { if (menu.matches(':popover-open')) menu.hidePopover(); }
  function openModels() {
    if (!initialized || !authenticated || !latest || currentView !== 'chat') return;
    for (const id of ['model-menu', 'thinking-menu']) byId(id).open = false;
    closeChatInfo(); closeMenu();
    error = ''; page = 1; byId('mobile-model-search').value = '';
    if (!sheet.open) sheet.showModal();
    byId('model-picker').setAttribute('aria-expanded', 'true');
    byId('model-menu').querySelector('summary').setAttribute('aria-expanded', 'true');
    positionModels(); render();
    // Phones inspect models first; desktop can focus search without a soft keyboard.
    byId(narrowScreen.matches ? 'mobile-model-close' : 'mobile-model-search').focus({preventScroll: true});
    const connection = byId('model-connection-choice');
    if (latest.model_providers && latest.model_connection && connection.value !== latest.model_connection &&
        [...connection.options].some(option => option.value === latest.model_connection)) {
      connection.value = latest.model_connection; connection.dispatchEvent(new Event('change'));
    }
    if (!localModels.length && !reading) refreshModels();
  }
  function positionMenu() {
    if (!menu.matches(':popover-open')) return;
    const anchor = more.getBoundingClientRect(), view = window.visualViewport;
    const left = (view?.offsetLeft || 0) + 8, top = (view?.offsetTop || 0) + 8;
    const right = left + (view?.width || innerWidth) - 16, bottom = top + (view?.height || innerHeight) - 16;
    menu.style.maxHeight = `${bottom - top}px`;
    const bounds = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(left, Math.min(anchor.right - bounds.width, right - bounds.width))}px`;
    menu.style.top = `${Math.max(top, Math.min(anchor.bottom + 4, bottom - bounds.height))}px`;
  }
  function viewport() {
    viewportFrame = 0;
    const view = window.visualViewport, root = document.documentElement;
    const width = Math.round(innerWidth), height = view?.height || innerHeight;
    const field = document.activeElement;
    const editable = field?.matches('textarea, input:not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="button"]):not([type="submit"]), [contenteditable="true"]');
    const baseline = !editable && root.dataset.chatKeyboard !== 'true' ?
      Math.max(innerHeight, height) : Math.max(viewportHeights.get(width) || 0, innerHeight, height);
    viewportHeights.set(width, baseline);
    if (viewportHeights.size > 8) viewportHeights.delete(viewportHeights.keys().next().value);
    const shrunk = baseline - height > 120;
    const keyboard = authenticated && currentView === 'chat' && width <= 560 &&
      (!view || Math.abs(view.scale - 1) < .05) && shrunk &&
      (editable || root.dataset.chatKeyboard === 'true');
    root.dataset.chatKeyboard = String(Boolean(keyboard));
    root.style.setProperty('--chat-viewport-height', `${height}px`);
    root.style.setProperty('--chat-viewport-top', `${view?.offsetTop || 0}px`);
    positionModels(); positionMenu();
  }
  function scheduleViewport() { if (!viewportFrame) viewportFrame = requestAnimationFrame(viewport); }
  function reset() {
    closeModels(); closeMenu(); error = ''; reading = false; page = 1; listKey = connectionKey = '';
    byId('mobile-model-search').value = ''; byId('mobile-model-list').replaceChildren();
    byId('mobile-model-connection').replaceChildren(); byId('mobile-model-status').textContent = '';
    byId('mobile-chat-subtitle').textContent = 'Choose a model';
    title.setAttribute('aria-label', 'Choose chat model'); title.removeAttribute('title');
    scheduleViewport();
  }
  function init() {
    if (initialized) return;
    initialized = true;
    sheet = byId('mobile-model-sheet'); title = byId('mobile-chat-title');
    menu = byId('mobile-chat-menu'); more = byId('mobile-chat-more');
    title.addEventListener('click', openModels);
    byId('mobile-model-close').addEventListener('click', closeModels);
    sheet.addEventListener('close', () => {
      byId('model-picker').setAttribute('aria-expanded', 'false');
      byId('model-menu').querySelector('summary').setAttribute('aria-expanded', 'false');
      if (authenticated && currentView === 'chat') {
        const trigger = narrowScreen.matches ? title : byId('model-picker');
        (trigger.disabled ? byId('messages') : trigger).focus({preventScroll: true});
      }
    });
    byId('mobile-model-search').addEventListener('input', () => {
      page = 1; error = ''; render(); sheet.querySelector('.mobile-model-body').scrollTop = 0;
    });
    byId('mobile-model-connection').addEventListener('change', () => {
      page = 1; error = ''; byId('model-connection-choice').value = byId('mobile-model-connection').value;
      byId('model-connection-choice').dispatchEvent(new Event('change'));
    });
    byId('mobile-model-refresh').addEventListener('click', () => { error = ''; refreshModels(); });
    byId('mobile-model-previous').addEventListener('click', () => { page--; render(); });
    byId('mobile-model-next').addEventListener('click', () => { page++; render(); });
    byId('mobile-model-numbers').addEventListener('click', event => {
      const target = event.target.closest('button[data-page]'); if (target) { page = Number(target.dataset.page); render(); }
    });
    byId('mobile-model-store').addEventListener('click', () => { closeModels(); showView('store'); });
    menu.addEventListener('toggle', () => {
      const open = menu.matches(':popover-open'); more.setAttribute('aria-expanded', String(open));
      if (open) { positionMenu(); menu.querySelector('button').focus({preventScroll: true}); }
    });
    menu.addEventListener('keydown', event => {
      const buttons = [...menu.querySelectorAll('button:not([hidden])')], index = buttons.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
        event.key === 'ArrowDown' ? (index + 1) % buttons.length : event.key === 'ArrowUp' ? (index - 1 + buttons.length) % buttons.length : null;
      if (next !== null) { event.preventDefault(); buttons[next].focus(); }
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeMenu(); more.focus(); }
    });
    menu.addEventListener('click', event => {
      const action = event.target.closest('button[data-mobile-chat-action]')?.dataset.mobileChatAction;
      if (!action) return;
      closeMenu();
      if (action === 'details') byId('chat-info-panel').showPopover();
      else if (action === 'context') byId('inspector-toggle').click();
      else if (action === 'search') { more.focus({preventScroll: true}); byId('command-open')?.click(); }
      else if (action === 'account') byId('account-shortcut').click();
    });
    byId('account-sign-out').addEventListener('click', () => byId('logout').click());
    document.addEventListener('klaude-view', () => { closeMenu(); if (currentView !== 'chat') closeModels(); render(); scheduleViewport(); });
    for (const name of ['klaude-chat-session-changed', 'klaude-auth-reset']) document.addEventListener(name, reset);
    narrowScreen.addEventListener('change', () => { closeMenu(); scheduleViewport(); });
    for (const name of ['resize', 'orientationchange']) window.addEventListener(name, scheduleViewport);
    for (const name of ['resize', 'scroll']) window.visualViewport?.addEventListener(name, scheduleViewport);
    for (const name of ['focusin', 'focusout']) document.addEventListener(name, scheduleViewport);
    render(); scheduleViewport();
  }
  return Object.freeze({init, render, openModels, infoTrigger,
    loading: value => { reading = value; if (value) error = ''; render(); },
    catalogError: message => { error = message; render(); }});
})();
