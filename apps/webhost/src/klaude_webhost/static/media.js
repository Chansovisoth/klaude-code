"use strict";

window.ChatImageResults = (() => {
  const rendered = new WeakMap();
  let selected = null, menu = null, menuTrigger = null;
  const hint = domainText('div', '', 'chat-image-selection'); hint.hidden = true;
  byId('composer').prepend(hint);
  function clear() { closeMenu(); selected = null; hint.hidden = true; hint.replaceChildren(); }
  function imageButton(icon, label, action, className = 'icon-button') {
    const button = domainButton('', action, `quiet ${className}`);
    button.setAttribute('aria-label', label); button.title = label;
    button.append(libraryIcon(icon));
    return button;
  }
  function closeMenu(focus = false) {
    const trigger = menuTrigger; menuTrigger = null;
    if (menu?.matches(':popover-open')) menu.hidePopover();
    else if (menu && !menu.hasAttribute('popover')) menu.hidden = true;
    menu?.replaceChildren();
    trigger?.setAttribute('aria-expanded', 'false');
    if (focus && trigger?.isConnected) trigger.focus({preventScroll:true});
  }
  function positionMenu() {
    if (!menuTrigger?.isConnected) { closeMenu(); return; }
    const viewport = window.visualViewport, anchor = menuTrigger.getBoundingClientRect();
    const left = (viewport?.offsetLeft || 0) + 12, top = (viewport?.offsetTop || 0) + 12;
    const right = left + (viewport?.width || innerWidth) - 24;
    const bottom = top + (viewport?.height || innerHeight) - 24;
    const bounds = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(left, Math.min(anchor.right - bounds.width, right - bounds.width))}px`;
    menu.style.top = `${Math.max(top, Math.min(anchor.bottom + 4, bottom - bounds.height))}px`;
  }
  function showMenu(asset, trigger) {
    if (menuTrigger === trigger) { closeMenu(true); return; }
    closeMenu();
    if (!menu) {
      menu = domainText('div', '', 'message-menu chat-image-menu');
      menu.id = 'chat-image-options'; menu.setAttribute('role', 'menu');
      menu.setAttribute('aria-label', 'Image options');
      if (typeof menu.showPopover === 'function') menu.setAttribute('popover', 'auto');
      menu.addEventListener('toggle', () => {
        if (menuTrigger && !menu.matches(':popover-open')) closeMenu();
      });
      menu.addEventListener('keydown', event => {
        const items = [...menu.querySelectorAll('[role="menuitem"]')];
        const current = items.indexOf(document.activeElement);
        let next;
        if (event.key === 'ArrowDown') next = (current + 1) % items.length;
        if (event.key === 'ArrowUp') next = (current - 1 + items.length) % items.length;
        if (event.key === 'Home') next = 0;
        if (event.key === 'End') next = items.length - 1;
        if (next !== undefined) { event.preventDefault(); items[next]?.focus(); }
        if (event.key === 'Escape') { event.preventDefault(); closeMenu(true); }
        if (event.key === 'Tab') closeMenu();
        event.stopPropagation();
      });
      document.body.append(menu);
    }
    const details = imageButton('info', 'Image details', async () => {
      closeMenu();
      const epoch = authEpoch, session = latest?.session_id;
      try {
        await openArtifact(asset.id, {origin:trigger});
        if (epoch === authEpoch && session === latest?.session_id && artifactDialog.open &&
            artifactDialog.dataset.details === 'closed') byId('image-details').click();
      } catch (error) { if (epoch === authEpoch) showError(error); }
    }, 'message-action');
    details.append(domainText('span', 'Image details')); details.setAttribute('role', 'menuitem');
    menu.replaceChildren(details);
    const regenerate = trigger.closest('.chat-image-asset').querySelector('.chat-image-regenerate');
    if (getComputedStyle(regenerate).display === 'none') {
      const variation = imageButton('refresh', 'Regenerate', () => {
        closeMenu(); regenerate.click();
      }, 'message-action');
      variation.append(domainText('span', 'Regenerate')); variation.setAttribute('role', 'menuitem');
      menu.prepend(variation);
    }
    menuTrigger = trigger;
    if (menu.hasAttribute('popover')) menu.showPopover(); else menu.hidden = false;
    trigger.setAttribute('aria-expanded', 'true'); positionMenu();
    menu.querySelector('[role="menuitem"]').focus({preventScroll:true});
  }
  function imageFrame(output, index, title) {
    const figure = domainText('figure', '', 'chat-image-asset');
    figure.dataset.imageIndex = String(index); figure.tabIndex = -1;
    figure.setAttribute('aria-label', `${title} ${index + 1}`);
    const setRatio = (width, height) => {
      if (width > 0 && height > 0) figure.style.setProperty('--chat-image-ratio', width / height);
    };
    setRatio(output?.width, output?.height);
    const header = domainText('header', '', 'chat-image-toolbar');
    const identity = domainText('div', '', 'chat-image-identity');
    const copy = domainText('div', '', 'chat-image-heading-copy');
    const status = domainText('span', title, 'chat-image-title chat-image-job-status');
    status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    status.setAttribute('aria-atomic', 'true'); copy.append(status);
    if (output?.width > 0 && output?.height > 0)
      copy.append(domainText('span', `${output.width} × ${output.height}`, 'chat-image-dimensions'));
    identity.append(libraryIcon('image'), copy);
    const tools = domainText('div', '', 'chat-image-tools');
    tools.setAttribute('role', 'group'); tools.setAttribute('aria-label', `Image ${index + 1} actions`);
    header.append(identity, tools);
    const content = domainText('div', '', 'chat-image-content'); content.append(header);
    const footer = domainText('figcaption', '', 'chat-image-footer');
    figure.append(content, footer);
    return {figure, content, footer, tools, setRatio};
  }
  function assetCard(asset, index, multiple) {
    const {figure, content, footer, tools, setRatio} = imageFrame(asset, index,
      multiple ? `Image ${index + 1}` : 'Generated image');
    figure.dataset.asset = asset.id;
    const download = domainText('a', '', 'icon-button quiet chat-image-download');
    download.setAttribute('aria-label', `Download generated image ${index + 1}`);
    download.title = 'Download'; download.href = artifactUrl(asset);
    download.download = `generated-${index + 1}.png`; download.append(libraryIcon('download'));
    const expand = imageButton('expand', `Expand generated image ${index + 1}`,
      () => openArtifact(asset.id, {origin:expand}).catch(showError));
    expand.dataset.imageControl = 'expand';
    const more = imageButton('more', `More options for image ${index + 1}`, () => showMenu(asset, more));
    more.dataset.imageControl = 'more'; more.setAttribute('aria-haspopup', 'menu');
    more.setAttribute('aria-controls', 'chat-image-options'); more.setAttribute('aria-expanded', 'false');
    download.dataset.imageControl = 'download';
    tools.append(download, expand, more);
    const open = domainButton('', () => openArtifact(asset.id, {origin:open}).catch(showError),
      'quiet chat-image-open');
    open.setAttribute('aria-label', `Open generated image ${index + 1}`);
    open.dataset.imageControl = 'preview';
    const thumbnail = artifactImage({...asset, name:`Generated image ${index + 1}`}, true);
    if (asset.width > 0 && asset.height > 0) {
      thumbnail.width = asset.width; thumbnail.height = asset.height;
    }
    thumbnail.addEventListener('load', () => setRatio(thumbnail.naturalWidth, thumbnail.naturalHeight), {once:true});
    open.append(thumbnail);
    const edit = imageButton('options', 'Edit', () => select(asset.id), 'chat-image-edit');
    edit.append(domainText('span', 'Edit')); edit.dataset.imageControl = 'edit';
    const regenerate = imageButton('refresh', 'Regenerate', () => {
      select(asset.id, 'variation'); byId('prompt').value = 'Generate another variation';
    }, 'chat-image-regenerate');
    regenerate.append(domainText('span', 'Regenerate')); regenerate.dataset.imageControl = 'regenerate';
    content.append(open); footer.append(edit, regenerate);
    return figure;
  }
  function jobCard(action, message, index, state) {
    const labels = {queued:'Waiting for image', starting:'Preparing image', running:'Creating image',
      cancelling:'Cancelling image', completed:'Generated image', failed:'Image generation failed',
      cancelled:'Image cancelled', unknown:'Outcome unconfirmed'};
    const {figure, content, footer, tools} = imageFrame(action.outputs?.[index], index,
      labels[state] || 'Image job');
    const active = ['queued', 'starting', 'running', 'cancelling'].includes(state);
    figure.dataset.imageState = state;
    tools.classList.add('chat-image-job-tools');
    if (active) {
      const placeholder = domainText('div', '', 'chat-image-placeholder');
      placeholder.dataset.animating = String(['starting', 'running'].includes(state));
      placeholder.setAttribute('role', 'img'); placeholder.setAttribute('aria-busy', 'true');
      placeholder.setAttribute('aria-label', 'Image preview pending'); content.append(placeholder);
      if (index === (action.position ?? action.assets?.length ?? 0) &&
          (action.cancellable || state === 'cancelling')) {
        const cancel = imageButton('close', 'Cancel image', () => control(action.id, 'cancel', cancel),
          'chat-image-cancel');
        cancel.append(domainText('span', 'Cancel')); cancel.dataset.imageControl = 'cancel';
        cancel.disabled = !action.cancellable || state === 'cancelling'; tools.append(cancel);
      }
    } else {
      const explanation = action.error || (state === 'unknown' ?
        'Check the saved outcome before trying again.' : state === 'cancelled' ?
        'Image creation was cancelled.' : state === 'completed' ?
        'The saved output is no longer available in Library.' : 'The image could not be created.');
      content.append(domainText('p', explanation, 'chat-image-error'));
    }
    const runtime = domainText('span', 'Local generation', 'chat-image-runtime');
    runtime.title = 'Configured Stable Diffusion service'; footer.append(runtime);
    if (state === 'unknown' && action.recoverable) {
      const check = imageButton('refresh', 'Check original output',
        () => control(action.id, 'recover', check), 'chat-image-recover');
      check.append(domainText('span', 'Check original output'));
      check.dataset.imageControl = 'recover'; footer.append(check);
    }
    if (['failed', 'cancelled'].includes(state)) {
      const position = latest.messages.findIndex(item => item.id === message.id);
      const request = latest.messages.slice(0, position).reverse().find(item => item.role === 'user');
      if (request) {
        const retry = imageButton('refresh', 'Retry image request', () => {
          clear(); byId('prompt').value = request.content; resizePrompt(); byId('prompt').focus();
        }, 'chat-image-retry');
        retry.append(domainText('span', 'Retry')); retry.title = 'Review the request and send again';
        retry.dataset.imageControl = 'retry'; footer.append(retry);
      }
    }
    return figure;
  }
  function select(id, operation = 'edit') {
    selected = {id, operation, session:latest.session_id};
    hint.replaceChildren(domainText('span', operation === 'edit' ? 'Editing selected image' : 'New variation'));
    const close = domainButton('', clear, 'quiet icon-button');
    close.setAttribute('aria-label', 'Clear image selection'); close.append(libraryIcon('close'));
    hint.append(close); hint.hidden = false; byId('prompt').focus();
  }
  function submission(text) {
    if (!selected || selected.session !== latest?.session_id) return text;
    return `${selected.operation === 'edit' ? 'Edit' : 'Regenerate'} image ${selected.id}: ${text}`;
  }
  async function control(id, operation, button) {
    const epoch = authEpoch, session = latest?.session_id;
    if (document.activeElement === button)
      button.closest('.chat-image-asset')?.focus({preventScroll:true});
    button.disabled = true;
    try {
      await jsonRequest('/api/v1/chat/images/control', 'POST', {id, operation, request_id:requestId()});
      if (epoch === authEpoch && session === latest?.session_id) await snapshot();
    } catch (error) {
      if (epoch === authEpoch && session === latest?.session_id) showError(error);
    } finally { if (button.isConnected) button.disabled = false; }
  }
  function captureFocus(article) {
    const body = article.querySelector('.message-body');
    const active = menuTrigger && menu?.contains(document.activeElement) ? menuTrigger : document.activeElement;
    if (!body?.contains(active)) return null;
    const figure = active.closest('[data-image-index]');
    return figure ? {asset:figure.dataset.asset, index:figure.dataset.imageIndex,
      control:active.dataset.imageControl} : null;
  }
  function renderMessage(article, message, session, previousFocus = null) {
    const action = message.image_action, body = article.querySelector('.message-body');
    if (body && message.role === 'user') {
      const selectedRequest = /^(Edit|Regenerate) image media:[a-f0-9]{32}:\s*([\s\S]*)$/i.exec(message.content);
      if (selectedRequest) body.textContent = `${selectedRequest[1] === 'Edit' ? 'Refine selected image' : 'New image variation'}: ${selectedRequest[2]}`;
    }
    if (!action || !body) return;
    const key = JSON.stringify([session, action]);
    if (rendered.get(article) === key && body.querySelector('.chat-image-result')) return;
    const card = domainText('section', '', 'chat-image-result');
    card.dataset.imageAction = action.id;
    card.setAttribute('aria-label', 'Image generation');
    const gallery = domainText('div', '', 'chat-image-gallery');
    const multiple = Math.max(action.count || 0, action.assets?.length || 0) > 1;
    gallery.dataset.multiple = String(multiple);
    if (multiple) {
      const heading = domainText('div', '', 'chat-image-gallery-heading');
      const ready = action.assets?.length || 0, total = action.count || ready;
      heading.append(libraryIcon('image'),
        domainText('span', action.state === 'completed' ? 'Generated images' : 'Images'),
        domainText('span', action.state === 'completed' ? String(ready) : `${ready} / ${total}`, 'muted'));
      card.append(heading);
    }
    for (const [index, asset] of (action.assets || []).entries()) {
      gallery.append(assetCard(asset, index, multiple));
    }
    if (['queued', 'starting', 'running', 'cancelling'].includes(action.state)) {
      const count = Math.min(3, Number(action.count) || 1);
      const first = Math.max(action.position ?? 0, action.assets?.length || 0);
      for (let index = first; index < count; index++)
        gallery.append(jobCard(action, message, index,
          index === (action.position ?? action.assets?.length ?? 0) ? action.state : 'queued'));
    } else if (action.state !== 'completed' || !action.assets?.length) {
      gallery.append(jobCard(action, message, action.position || 0, action.state));
    }
    card.append(gallery);
    const focus = previousFocus || captureFocus(article);
    if (menuTrigger && body.contains(menuTrigger)) closeMenu();
    body.replaceChildren(card); rendered.set(article, key);
    if (focus) {
      const target = [...card.querySelectorAll('[data-image-control]')].find(button =>
        (focus.asset ? button.closest('[data-asset]')?.dataset.asset === focus.asset :
          button.closest('[data-image-index]')?.dataset.imageIndex === focus.index) &&
        button.dataset.imageControl === focus.control);
      if (target && !target.disabled) target.focus({preventScroll:true});
      else [...card.querySelectorAll('[data-image-index]')].find(figure =>
        figure.dataset.imageIndex === focus.index)?.focus({preventScroll:true});
    }
  }
  document.addEventListener('klaude-auth-reset', clear);
  document.addEventListener('klaude-chat-session-changed', clear);
  document.addEventListener('klaude-view', () => closeMenu());
  document.addEventListener('click', event => {
    if (menuTrigger && !menu.contains(event.target) && !menuTrigger.contains(event.target)) closeMenu();
  });
  window.addEventListener('resize', () => { if (menuTrigger) positionMenu(); });
  document.addEventListener('scroll', () => { if (menuTrigger) positionMenu(); }, {capture:true, passive:true});
  return {renderMessage, captureFocus, submission, clear};
})();
window.ModelsSettingsNavigation = (() => {
  let screen = 'overview';
  const screens = ['overview', 'connections', 'catalog', 'image'];
  const panels = {overview: 'model-default-settings', connections: 'model-connections-settings', catalog: 'models-configured', image: 'image-service-settings'};
  const links = byId('models-overview-links'), imageLink = byId('models-image-link');
  links.hidden = false; imageLink.hidden = false;
  links.innerHTML = `<section class="settings-section"><h3>Connections</h3><p id="models-connections-summary" class="muted">Loading connection status…</p><div class="settings-row-group"><button type="button" data-model-screen="connections" class="quiet settings-navigation-row">Manage connections <span aria-hidden="true">›</span></button></div></section>`;
  imageLink.innerHTML = `<section class="settings-section"><h3>Image generation</h3><p id="models-image-summary" class="muted">Loading service status…</p><div class="settings-row-group"><button type="button" data-model-screen="image" class="quiet settings-navigation-row">Configure service <span aria-hidden="true">›</span></button></div></section>`;
  function show(next, {restore = false, focus = false} = {}) {
    if (!screens.includes(next)) next = 'overview';
    if (!restore && next !== screen && !canLeave()) return;
    screen = next;
    for (const [name, id] of Object.entries(panels)) byId(id).hidden = name !== screen;
    links.hidden = screen !== 'overview';
    imageLink.hidden = screen !== 'overview';
    byId('models-overview-description').hidden = screen !== 'overview';
    byId('models-heading-label').hidden = screen !== 'overview';
    byId('models-settings-back').hidden = screen === 'overview';
    byId('models-breadcrumb-separator').hidden = screen === 'overview';
    byId('models-screen-title').hidden = screen === 'overview';
    byId('media-settings-refresh').hidden = screen !== 'overview';
    byId('models-screen-title').textContent = {overview:'', connections:'Connections', catalog:'Connected models', image:'Image generation'}[screen];
    if (!restore) {
      const url = new URL(location.href); url.searchParams.set('models-screen', screen);
      history.pushState(history.state, '', url.pathname + url.search + url.hash);
      document.dispatchEvent(new CustomEvent('klaude-view', {detail: currentView}));
    }
    if (focus) { byId('settings-view').scrollTop = 0; byId(screen === 'overview' ? 'model-default-heading' : 'models-screen-title').focus(); }
    window.SettingsActions?.refresh();
  }
  function canLeave() {
    const id = screen === 'image' ? 'image-service' : 'models';
    const state = window.SettingsDrafts?.category(id);
    return !state || (!state.drafts.changed().length && !state.saving) || window.confirm('You have pending changes. Leave this screen and keep your draft?');
  }
  links.addEventListener('click', event => { const button = event.target.closest('[data-model-screen]'); if (button) show(button.dataset.modelScreen, {focus:true}); });
  imageLink.addEventListener('click', event => { const button = event.target.closest('[data-model-screen]'); if (button) show(button.dataset.modelScreen, {focus:true}); });
  byId('models-settings-back').addEventListener('click', () => show('overview', {focus:true}));
  document.addEventListener('klaude-view', () => {
    if (currentView === 'settings' && settingsSection === 'models') show(new URLSearchParams(location.search).get('models-screen') || 'overview', {restore:true});
  });
  window.addEventListener('popstate', event => {
    if (!authenticated || currentView !== 'settings' || settingsSection !== 'models') return;
    const url = new URL(location.href), target = url.searchParams;
    const leaving = target.get('view') !== 'settings' || target.get('settings') !== 'models' || (target.get('models-screen') || 'overview') !== screen;
    if (leaving && !canLeave()) {
      event.stopImmediatePropagation();
      target.set('view', 'settings'); target.set('settings', 'models'); target.set('models-screen', screen);
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    }
  }, {capture:true});
  window.addEventListener('popstate', () => { if (authenticated && currentView === 'settings' && settingsSection === 'models') document.dispatchEvent(new CustomEvent('klaude-view', {detail:currentView})); });
  document.addEventListener('klaude-auth-reset', () => { show('overview', {restore:true}); byId('models-connections-summary').textContent = ''; byId('models-image-summary').textContent = ''; });
  show('overview', {restore:true});
  return {show, canLeave};
})();

// Browse models from configured providers. Runtime selection belongs to Chat.
window.BrowserModelsUI = (() => {
  let connections = [], catalog = [], selected = "", catalogConnection = "";
  let reading = null, generation = 0, loading = false, page = 1;
  let ready;
  const pageSize = 20;
  const active = () => authenticated && currentView === "settings" && settingsSection === "models" && !byId("models-configured").hidden;
  const backendLabel = value => ({ ollama: "Ollama", openai_compatible: "OpenAI compatible", openai_codex: "OpenAI Codex", openai_api: "OpenAI", openrouter: "OpenRouter", gemini_api: "Google", deepseek: "DeepSeek", anthropic: "Anthropic" }[value] || value);
  function render() {
    if (!active() || !latest) return;
    byId("configured-models-refresh").disabled = loading;
    const source = byId('models-source');
    source.replaceChildren(new Option('All connections', '*'), ...connections.map(item => { const option = new Option(`${item.name}${item.enabled ? '' : ' · Disabled'}`, item.id); option.disabled = !item.enabled; return option; }));
    source.value = selected;
    const connection = connections.find(item => item.id === selected);
    byId("models-catalog-title").textContent = connection?.name || "Available models";
    const query = byId("models-query").value.trim().toLocaleLowerCase();
    const items = catalogConnection === selected ? catalog.filter(item => `${item.name} ${item.id}`.toLocaleLowerCase().includes(query)) : [];
    const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
    page = Math.min(page, totalPages);
    byId("models-count").textContent = catalogConnection === selected ? `${items.length.toLocaleString()} shown` : "";
    byId("models-query").disabled = !catalogConnection;
    const rows = items.slice((page - 1) * pageSize, page * pageSize).map(item => {
      const node = domainText("article", "", "models-model library-card collection-row");
      node.dataset.rowKey = item.id;
      node.dataset.rowSignature = JSON.stringify(item);
      const content = domainText("div", "", "models-model-content");
      const artwork = domainText("span", "", "collection-icon");
      const brandIcon = domainText("span", "", "model-brand-icon");
      brandIcon.setAttribute("aria-hidden", "true"); setModelBrandIcon(brandIcon, item.id, item.backend, { appearance: "color" });
      artwork.append(brandIcon);
      const name = domainText("h3", item.name); name.title = item.name;
      const reference = domainText("p", item.id, "muted models-model-ref"); reference.title = item.id;
      content.append(name, reference, modelPlatformIndicator(item.id, item.backend));
      const efforts = (item.effort_levels || []).filter(level => level !== "off");
      if (efforts.length) {
        const capabilities = domainText("div", "", "model-capabilities");
        capabilities.setAttribute("aria-label", "Available Thinking efforts");
        capabilities.append(domainText("span", "Thinking", "muted"));
        for (const effort of efforts) capabilities.append(domainText("span", effort, "model-capability"));
        content.append(capabilities);
      }
      node.append(artwork, content);
      return node;
    });
    const target = byId("models-items");
    // Keep delayed skeletons owned by beginLoading until a catalog is available.
    if (rows.length) reconcileRows(target, rows);
    else if (!loading) collectionEmpty(target, query ? "No matching models" : "No models available",
      query ? "Try another model name." : selected ? "Refresh this connection to check its available models." : "Add or enable a connection in Manage connections.", "models");
    updateDomainPager("models", (page - 1) * pageSize, { items: rows, total: items.length, page_size: pageSize, more: page < totalPages });
    byId("models-pages").hidden = items.length <= pageSize;
  }
  async function load(refreshInventory = true) {
    if (!active() || !latest) return;
    const loadId = ++generation, epoch = authEpoch;
    reading?.abort(); reading = new AbortController();
    loading = true;
    // Changing connections must never show the previous connection's catalog.
    if (selected !== catalogConnection) { catalog = []; catalogConnection = ""; byId("models-items").replaceChildren(); }
    render();
    const finish = beginLoading(byId("models-items"), { kind: "rows", count: 3, preserve: Boolean(catalog.length), label: "Loading models…" });
    const current = () => active() && epoch === authEpoch && loadId === generation;
    try {
      if (refreshInventory) {
        const inventory = latest.model_settings ? (await domainRequest("/api/v1/settings/models", "GET", undefined, { signal: reading.signal })).connections : latest.model_providers ? (await domainRequest("/api/v1/models/connections", "GET", undefined, { signal: reading.signal })).connections :
          [{ id: "legacy-local", name: "Local models", source: "Local", backend: "ollama", enabled: true }];
        if (!current()) return;
        connections = inventory;
        if (selected !== "*" && !connections.some(item => item.id === selected && item.enabled)) selected = connections.find(item => item.id === latest.model_connection && item.enabled)?.id || connections.find(item => item.enabled)?.id || "";
      }
      if (!selected) { catalog = []; catalogConnection = ""; byId("models-status").textContent = "No enabled model connection."; return; }
      const connectionId = selected, models = [], errors = [];
      for (const connection of connections.filter(item => item.enabled && (selected === '*' || item.id === selected))) {
        try {
          const result = await domainRequest(latest.model_settings ? `/api/v1/models/catalog?connection=${encodeURIComponent(connection.id)}&purpose=defaults` : latest.model_providers ? `/api/v1/models/catalog?connection=${encodeURIComponent(connection.id)}` : '/api/v1/models/local', 'GET', undefined, {signal:reading.signal});
          if (!current()) return;
          models.push(...result.models);
          catalog = [...models]; catalogConnection = connectionId; render();
        } catch (error) {
          if (!current() || error.name === 'AbortError') return;
          errors.push(`${connection.name}: ${error.message}`);
        }
      }
      catalog = models; catalogConnection = connectionId;
      byId("models-status").textContent = errors.join(' · ');
    } catch (error) { if (current()) byId("models-status").textContent = `${error.message}${catalog.length ? " Previously loaded models remain visible." : ""}`; }
    finally {
      finish();
      if (loadId === generation) { loading = false; render(); }
    }
  }
  byId('models-source').addEventListener('change', () => { selected = byId('models-source').value; page = 1; load(false); });
  byId("models-previous").append(libraryIcon("previous"));
  byId("models-next").append(libraryIcon("next"));
  byId("configured-models-refresh").addEventListener("click", () => load());
  byId("models-query").addEventListener("input", () => { page = 1; render(); });
  byId("models-previous").addEventListener("click", () => { page = Math.max(1, page - 1); render(); });
  byId("models-next").addEventListener("click", () => { page += 1; render(); });
  byId("models-numbers").addEventListener("click", event => {
    const button = event.target.closest("button[data-page]");
    if (button) { page = Number(button.dataset.page); render(); }
  });
  document.addEventListener("klaude-view", () => {
    if (active()) load();
    else { generation += 1; reading?.abort(); loading = false; cancelLoading(byId("models-items")); }
  });
  document.addEventListener("klaude-auth-reset", () => {
    generation += 1; reading?.abort(); loading = false;
    connections = []; catalog = []; selected = ""; catalogConnection = ""; ready = undefined; page = 1;
    byId("models-query").value = "";
    for (const id of ["models-source", "models-items", "models-status", "models-count", "models-numbers"]) byId(id).replaceChildren();
    byId("models-pages").hidden = true;
  });
  function capabilitiesChanged() {
    const now = Boolean(latest?.model_providers);
    if (ready !== now) { ready = now; if (active()) load(); }
    render();
  }
  return { render, capabilitiesChanged };
})();

window.BrowserMedia = (() => {
  let settings = null, models = [], reading = null, catalogReading = null, generation = 0, catalogGeneration = 0;
  let catalogConnection = "", catalogLoaded = false;
  let ready, loadingCatalog = false;
  let fallbacksOpen = false;
  const active = () => authenticated && currentView === "settings";
  const manager = () => window.BrowserManagement;
  const busy = kind => !settings || settings.management_allowed === false || SettingsDrafts.locked(kind === "image_service" ? "image-service" : "models") || Boolean(settings.pending[kind]) || manager().busy(`media-${kind}`);
  const labels = { chat: "Startup chat", utility: "Utility", research: "Research", vision: "Vision",
    fallbacks: "Utility fallbacks", vision_fallbacks: "Vision fallbacks", output_tokens: "Utility output tokens", vision_enabled: "Vision image input", image_service: "Image generation service" };
  const settingsAdapter = {
    panel: "model-default-settings", status: "media-settings-status", render: renderSettings, changed: renderBusy,
    refresh: () => load(false, true), blocked: () => !settings || settings.management_allowed === false || Object.keys(settings.pending).length > 0,
    operation: entry => entry.base.id === "image_service" ?
      { operation: "image-settings-save", ...entry.value, revision: entry.base.version } :
      { operation: "defaults-save", field: entry.base.id, value: entry.value, expected: entry.base.value },
    order: entry => entry.base.id === "vision_enabled" ? entry.value ? 2 : -2 : entry.base.id === "image_service" ? 3 : 0,
    count: entry => entry.base.id === "image_service" ? ["endpoint", "enabled", "provider", "model"].filter(key => entry.value[key] !== entry.base.value[key]).length : 1,
    normalized: normalizedDraft,
    reviewed: (entry, prepared) => entry.base.id === "image_service" ? prepared.image_settings : undefined,
    validate: entries => entries.every(entry => {
      const inputs = entry.base.id === "image_service" ? [byId("image-service-url")] :
        [...byId("default-model-fields").querySelectorAll(`[data-draft-field="${entry.base.id}"]`)];
      return inputs.every(SettingsDrafts.validateInput);
    }),
    warning: entry => entry.base.id === "vision_enabled" && entry.value && !entry.base.value ?
      "Enable Vision image input: images can be sent to your configured Vision model and fallbacks when you request analysis." :
      entry.base.id === "image_service" && entry.value.enabled && (!entry.base.value.enabled || entry.value.endpoint !== entry.base.value.endpoint) ?
        `Image generation: enable requests to ${entry.value.endpoint}. Generation prompts will be sent to this server.` : null,
  };
  SettingsDrafts.register("models", {...settingsAdapter,
    blocked: () => !settings || settings.management_allowed === false || Boolean(settings.pending.defaults)});
  SettingsDrafts.register("image-service", {...settingsAdapter, panel: "image-service-settings", status: "image-settings-status",
    blocked: () => !settings || settings.management_allowed === false || Boolean(settings.pending.image_service)});
  function normalizedDraft(entry) {
    if (entry.base.id !== "image_service") return entry.value;
    let endpoint = SettingsDrafts.normalizedEndpoint(entry.value.endpoint);
    const sdcpp = endpoint.endsWith("/sdcpp/v1");
    endpoint = endpoint.replace(/\/(?:api|v1)$/, "");
    if (sdcpp) endpoint = endpoint.slice(0, -"/sdcpp".length);
    return { ...entry.value, endpoint };
  }
  function option(value, label) { const node = domainText("option", label); node.value = value; return node; }
  function modelSelect(id, value, role) {
    const select = document.createElement("select"); select.id = id;
    const choices = catalogConnection === byId("default-model-connection").value ?
      models.filter(item => item.roles[role] !== false) : [];
    select.append(option("", loadingCatalog ? "Loading models…" : catalogLoaded && !choices.length ? "No compatible models · Unset" : "Unset"),
      ...choices.map(item => option(item.id, `${item.name}${item.roles[role] === null ? " · Capability unknown" : ""}`)));
    if (value && !choices.some(item => item.id === value)) select.append(option(value, `Saved · ${value}`));
    select.value = value || "";
    const describe = () => { select.title = select.selectedOptions[0]?.textContent || ""; };
    select.addEventListener("change", describe); describe();
    return select;
  }
  const stage = (field, value) => SettingsDrafts.set(field === "image_service" ? "image-service" : "models", field, value);
  function recovery(kind) {
    const container = byId(kind === "defaults" ? "defaults-recovery" : "image-settings-recovery");
    const pending = settings.pending[kind];
    container.replaceChildren();
    if (!pending) return;
    container.append(domainText("p", pending.state === "unknown" ? "The last save is unconfirmed. Check its saved state before making another change." : "A shared save is in progress.", "muted"));
    if (pending.state === "unknown") {
      const button = domainButton("Check saved state", () => SettingsDrafts.recover(kind === "defaults" ? "models" : "image-service", {
        operation: kind === "defaults" ? "defaults-recover" : "image-settings-recover", target: pending.request_id,
      }));
      const state = SettingsDrafts.category(kind === "defaults" ? "models" : "image-service");
      button.disabled = state.saving || Boolean(state.drafts.entries.get("recovery")?.pending); container.append(button);
    }
  }
  function renderBusy() {
    for (const input of byId("default-model-fields").querySelectorAll("input, select, button")) input.disabled = busy("defaults");
    for (const input of byId("image-service-save").querySelectorAll("input, select, button")) input.disabled = busy("image_service");
    byId("default-model-catalog").querySelector("button").disabled = !settings || loadingCatalog;
    byId('image-service-test').disabled = imageTestBusy || busy('image_service') || !latest?.model_settings;
  }
  function renderSettings() {
    if (!settings) return;
    // A catalog/settings read can finish before the native toggle event fires.
    // Capture the live disclosure before replacing its DOM, including fast tabs.
    const currentFallbacks = byId("model-fallbacks");
    if (currentFallbacks) fallbacksOpen = currentFallbacks.open;
    const defaults = Object.fromEntries(Object.keys(settings.defaults).map(key => [key, SettingsDrafts.value("models", key)])), fields = [];
    const section = (id, title) => {
      const group = domainText("section", "", "settings-section");
      const heading = domainText("h3", title); heading.id = id;
      group.setAttribute("aria-labelledby", id); group.append(heading); return group;
    };
    const roles = section("model-roles-heading", "Model roles");
    const roleFields = domainText("div", "", "settings-form-grid settings-role-grid"); roles.append(roleFields);
    for (const [field, label, icon] of [["chat", "Startup chat", "chat"], ["utility", "Utility", "tools"], ["research", "Research", "search"], ["vision", "Vision", "vision"]]) {
      const form = domainText("form", "", "setting-row");
      const title = domainText("label", "", "model-role-label"); title.htmlFor = `default-value-${field}`;
      title.append(libraryIcon(icon), domainText("span", label));
      const select = modelSelect(title.htmlFor, defaults[field], field);
      select.dataset.draftField = field;
      const controls = domainText("div", "", "settings-controls");
      controls.append(select, RoleModelPicker.decorate(select, label, field, settings.connections));
      select.addEventListener("change", () => stage(field, select.value || null));
      const picker = controls.querySelector('button');
      picker.classList.add('settings-role-row'); picker.prepend(title); title.removeAttribute('for');
      form.append(controls); form.classList.add('settings-role-container'); form.addEventListener("submit", event => { event.preventDefault(); stage(field, select.value || null); });
      roleFields.append(form);
    }
    fields.push(roles);
    const fallbacks = domainText("details", "", "settings-disclosure settings-fallbacks");
    fallbacks.id = "model-fallbacks"; fallbacks.open = fallbacksOpen;
    fallbacks.addEventListener("toggle", () => { if (fallbacks.isConnected) fallbacksOpen = fallbacks.open; });
    fallbacks.append(decorateDisclosure(domainText("summary", "Advanced defaults")));
    for (const [field, label, icon] of [["fallbacks", "Utility fallbacks", "tools"], ["vision_fallbacks", "Vision fallbacks", "vision"]]) {
      const form = domainText("form", "", "settings-fallback-form");
      const heading = domainText("h3", "", "model-role-label");
      heading.append(libraryIcon(icon), domainText("span", label));
      form.append(heading, domainText("p", "Optional models, tried in this order only when the primary cannot complete the request.", "muted"));
      const selects = [0, 1, 2].map(index => {
        const row = domainText("div", "", "setting-row");
        const label = domainText("span", `Fallback ${index + 1}`, "model-role-label");
        const select = modelSelect(`default-value-${field}-${index}`, defaults[field][index], field === "fallbacks" ? "utility" : "vision");
        select.dataset.draftField = field;
        const controls = domainText("div", "", "settings-controls");
        controls.append(select, RoleModelPicker.decorate(select, `${field === "fallbacks" ? "Utility" : "Vision"} fallback ${index + 1}`, field === "fallbacks" ? "utility" : "vision", settings.connections));
        const picker = controls.querySelector("button");
        picker.classList.add("settings-role-row"); picker.prepend(label);
        row.classList.add("settings-role-container"); row.append(controls); form.append(row); return select;
      });
      const changed = () => stage(field, selects.map(select => select.value).filter(Boolean));
      selects.forEach(select => select.addEventListener("change", changed));
      form.addEventListener("submit", event => { event.preventDefault(); changed(); });
      fallbacks.append(form);
    }
    const output = domainText("form", "", "setting-row");
    const outputLabel = domainText("label", "Utility output tokens"); outputLabel.htmlFor = "default-output-tokens";
    const number = document.createElement("input"); number.type = "number"; number.min = 128; number.max = 2048; number.required = true;
    number.id = outputLabel.htmlFor; number.value = defaults.output_tokens;
    number.dataset.draftField = "output_tokens";
    const controls = domainText("div", "", "settings-controls settings-number");
    controls.append(number); output.append(outputLabel, controls);
    const changeOutput = () => stage("output_tokens", number.value === "" ? "" : Number(number.value));
    number.addEventListener("input", changeOutput);
    output.addEventListener("submit", event => { event.preventDefault(); changeOutput(); });
    const options = section("model-options-heading", "Utility and Vision options");
    const optionFields = domainText("div", "", "settings-form-grid");
    optionFields.append(output); options.append(optionFields);
    const enabled = domainText("div", "", "setting-row settings-toggle-row");
    const enabledLabel = domainText("label", "Enable Vision for image input and analysis"); enabledLabel.htmlFor = "default-vision-enabled";
    const enabledControls = domainText("div", "", "settings-controls");
    const toggleLabel = domainText("label", "", "switch");
    const toggle = document.createElement("input"); toggle.type = "checkbox"; toggle.id = "default-vision-enabled"; toggle.checked = defaults.vision_enabled;
    toggle.setAttribute("role", "switch");
    toggle.dataset.draftField = "vision_enabled";
    toggle.addEventListener("change", () => stage("vision_enabled", toggle.checked));
    const track = domainText("span", ""); track.setAttribute("aria-hidden", "true");
    toggleLabel.append(toggle, track); enabledControls.append(toggleLabel);
    enabled.append(enabledLabel, enabledControls); optionFields.append(enabled);
    fallbacks.append(options); fields.push(fallbacks);
    byId("default-model-fields").replaceChildren(...fields);
    const image = SettingsDrafts.value("image-service", "image_service");
    byId("image-service-url").value = image.endpoint;
    byId("image-service-provider").value = image.provider;
    byId("image-service-model-name").value = image.model;
    renderImageChoice();
    byId("image-service-enabled").checked = image.enabled;
    byId("image-service-model").textContent = settings.image_service.model ? `Saved model: ${settings.image_service.model}` : "No image model configured.";
    recovery("defaults"); recovery("image_service"); renderBusy();
  }
  async function load(refreshCatalog = false, force = false) {
    if (!force && !active()) return;
    if (!latest?.media_management) {
      byId("media-settings-status").textContent = "Restart the Web UI host and reload to configure model defaults and image services.";
      byId("image-settings-status").textContent = byId("media-settings-status").textContent;
      renderBusy();
      if (force) throw new Error(byId("media-settings-status").textContent);
      return;
    }
    const current = ++generation, epoch = authEpoch;
    reading?.abort(); reading = new AbortController();
    try {
      const result = await domainRequest("/api/v1/settings/models", "GET", undefined, { signal: reading.signal });
      if ((!force && !active()) || epoch !== authEpoch || current !== generation) {
        if (force) throw new Error("Saved values are refreshing. Check save status to confirm them.");
        return;
      }
      settings = result;
      byId('models-connections-summary').textContent = `${settings.connections.length} configured · ${settings.connections.filter(item => item.enabled).length} enabled`;
      byId('models-image-summary').textContent = `${settings.image_service.enabled ? 'Enabled' : 'Disabled'} · ${settings.image_service.provider === 'ollama' ? 'Ollama' : 'stable-diffusion.cpp'}${settings.image_service.model ? ' · ' + settings.image_service.model : ''}`;
      SettingsDrafts.ingest("models", [
        ...Object.entries(settings.defaults).map(([id, value]) => ({ id, value, version: value, label: labels[id] })),
      ]);
      SettingsDrafts.ingest("image-service", [
        { id: "image_service", value: { endpoint: settings.image_service.endpoint, enabled: settings.image_service.enabled, provider: settings.image_service.provider || "sdcpp", model: settings.image_service.model },
          version: settings.image_service.revision, label: labels.image_service },
      ]);
      const selected = byId("default-model-connection").value;
      byId("default-model-connection").replaceChildren(...settings.connections.filter(item => item.enabled).map(item => option(item.id, `${item.name} · ${item.backend}`)));
      if (settings.connections.some(item => item.id === selected && item.enabled)) byId("default-model-connection").value = selected;
      renderSettings();
      byId("media-settings-status").textContent = settings.management_allowed === false ? "Changing model defaults and image-service settings requires an admin account." : "";
      byId("image-settings-status").textContent = imageTestResult?.endpoint === byId("image-service-url").value.trim() ? imageTestResult.message : "";
      if (active() && (refreshCatalog || !loadingCatalog && !catalogLoaded || catalogConnection !== byId("default-model-connection").value)) loadCatalog();
    } catch (error) {
      if (active() && current === generation) {
        domainError(error, "media-settings-status");
        byId("image-settings-status").textContent = byId("media-settings-status").textContent;
      }
      if (force) throw error;
    }
  }
  async function loadCatalog() {
    const connection = byId("default-model-connection").value, epoch = authEpoch, current = ++catalogGeneration;
    catalogReading?.abort(); catalogReading = new AbortController();
    if (connection !== catalogConnection) { models = []; catalogConnection = connection; catalogLoaded = false; }
    if (!connection) {
      loadingCatalog = false; renderSettings();
      byId("media-settings-status").textContent = "No enabled model connection. Configure one in Klaude’s terminal Model settings.";
      return;
    }
    loadingCatalog = true; renderSettings();
    byId("media-settings-status").textContent = "Loading models and checking capabilities…";
    try {
      const result = await domainRequest(`/api/v1/models/catalog?connection=${encodeURIComponent(connection)}&purpose=defaults`, "GET", undefined, { signal: catalogReading.signal });
      if (!active() || epoch !== authEpoch || current !== catalogGeneration) return;
      if (!result.models.every(item => item.roles && ["chat", "utility", "research", "vision"].every(role => [true, false, null].includes(item.roles[role]))))
        throw new Error("Restart the Web UI host and reload to check model capabilities.");
      catalogLoaded = true; loadingCatalog = false;
      models = result.models; renderSettings();
      byId("media-settings-status").textContent = models.length ? "" : "This connection returned no models.";
    } catch (error) {
      if (active() && epoch === authEpoch && current === catalogGeneration && error.name !== "AbortError") {
        domainError(error, "media-settings-status");
        if (catalogLoaded) byId("media-settings-status").textContent += " Previously loaded models remain available.";
      }
    }
    finally {
      if (current === catalogGeneration) {
        const wasLoading = loadingCatalog;
        loadingCatalog = false;
        if (wasLoading && active() && settings) renderSettings();
        else renderBusy();
      }
    }
  }
  byId("media-settings-refresh").addEventListener("click", () => load(true));
  byId("default-model-connection").addEventListener("change", () => { renderSettings(); loadCatalog(); });
  byId("default-model-catalog").addEventListener("submit", event => {
    event.preventDefault(); loadCatalog();
  });
  let imageTestResult = null, imageTestBusy = false;
  const changeImage = () => {
    renderImageChoice();
    imageTestResult = null;
    if (settings) stage("image_service", { endpoint: byId("image-service-url").value.trim(), enabled: byId("image-service-enabled").checked, provider: byId("image-service-provider").value, model: byId("image-service-model-name").value.trim() });
  };
  function renderImageChoice() {
    const native=byId('image-service-provider').value==='sdcpp';
    byId('image-service-model-row').hidden=false;
    byId('image-service-model-name').hidden=native;
    const button=byId('image-service-model-name-picker');
    button.classList.toggle('model-choice-button',native);
    button.classList.toggle('settings-role-row',native);
    byId('image-service-model-row').classList.toggle('settings-role-container',native);
    button.replaceChildren(domainText('span',native ? byId('image-service-model-name').value || 'Choose model' : 'Choose model','model-role-value'));
    if(native){button.prepend(domainText('span','Image model','model-role-label'));const arrow=domainText('span','›','model-role-chevron');arrow.setAttribute('aria-hidden','true');button.append(arrow);}
    button.setAttribute('aria-label','Choose image generation model');
    const label=byId('image-service-model-row').querySelector('label');
    label.hidden=native;label.htmlFor=native?button.id:'image-service-model-name';
  }
  byId('image-service-test').addEventListener('click', async () => {
    const endpoint = byId('image-service-url').value.trim(), epoch = authEpoch;
    const provider = byId('image-service-provider').value, model = byId('image-service-model-name').value.trim();
    imageTestBusy = true; renderBusy();
    imageTestResult = {endpoint, message: 'Testing image service…'};
    byId('image-settings-status').textContent = imageTestResult.message;
    try {
      const result = await domainRequest('/api/v1/settings/models/image-test', 'POST', {endpoint, provider, model});
      if (epoch !== authEpoch || !active() || byId('image-service-url').value.trim() !== endpoint || byId('image-service-provider').value !== provider || byId('image-service-model-name').value.trim() !== model) return;
      imageTestResult = {endpoint, message: `Service reached. Model: ${result.model}. Width ${result.limits.min_width}–${result.limits.max_width}, height ${result.limits.min_height}–${result.limits.max_height}. No image was generated.`};
      byId('image-settings-status').textContent = imageTestResult.message;
    } catch (error) { if (epoch === authEpoch && active()) { imageTestResult = {endpoint, message: error.message}; byId('image-settings-status').textContent = error.message; } }
    finally { if (epoch === authEpoch) { imageTestBusy = false; renderBusy(); } }
  });
  byId("image-service-url").addEventListener("input", changeImage);
  byId("image-service-model-name").addEventListener("input", changeImage);
  byId("image-service-provider").addEventListener("change", () => {
    if (byId("image-service-provider").value === "ollama" && !byId("image-service-url").value.trim()) {
      byId("image-service-url").value = "http://localhost:11434";
    }
    changeImage();
  });
  byId("image-service-enabled").addEventListener("change", changeImage);
  byId("image-service-save").addEventListener("submit", event => { event.preventDefault(); changeImage(); });
  document.addEventListener("klaude-view", () => {
    if (active()) load();
    else { generation += 1; reading?.abort(); catalogReading?.abort(); catalogGeneration += 1; loadingCatalog = false; }
  });
  document.addEventListener("klaude-operations", event => {
    if (SettingsDrafts.category("models").saving || SettingsDrafts.category("image-service").saving) return;
    if (active() && event.detail.some(item => ["defaults-save", "image-settings-save", "defaults-recover", "image-settings-recover"].includes(item.kind) && ["completed", "failed", "unknown"].includes(item.state))) {
      // Reload only when an operation changes, preserving unsaved form edits.
      const revision = JSON.stringify(event.detail.filter(item => item.kind.startsWith("defaults-") || item.kind.startsWith("image-settings-")).map(item => [item.request_id, item.state]));
      if (revision !== lastOperations) { lastOperations = revision; load(); }
    }
  });
  let lastOperations = "";
  document.addEventListener("klaude-auth-reset", () => {
    generation += 1; catalogGeneration += 1; reading?.abort(); catalogReading?.abort(); loadingCatalog = false;
    settings = null; models = []; ready = undefined; lastOperations = ""; imageTestResult = null; imageTestBusy = false;
    catalogConnection = ""; catalogLoaded = false;
    for (const id of ["default-model-fields", "default-model-connection", "defaults-recovery", "image-settings-recovery", "media-settings-status", "image-service-model", "image-settings-status"]) byId(id).replaceChildren();
    fallbacksOpen = false; byId("image-service-save").reset(); renderBusy();
  });
  function capabilitiesChanged() {
    const value = Boolean(latest?.media_management);
    if (value !== ready) { ready = value; if (active()) load(); }
  }
  return { renderBusy, capabilitiesChanged, load };
})();

window.BrowserVision = (() => {
  let image = null, data = null, reading = null, generation = 0, saving = null;
  let loadingReview = false;
  let cached = null, expiryTimer = null, tracked = null, outcome = null, fullResult = null, publishedSuggestions = "";
  let tagSelection = null, modelLoad = 0, modelReading = null;
  const sessionModels = new Map();
  const sessionChoice = () => sessionModels.get(latest?.session_id);
  const modelName = reference => String(reference || "").replace(/^([^@/]+)@[^/]+\//, "$1 · ");
  function renderSelectedSettings() {
    const choice = sessionChoice(), reference = choice ? choice.reference : data?.settings?.reference;
    byId("vision-selected-model").textContent = `Model: ${modelName(reference) || (choice ? "Choose a model" : "Unavailable")}`;
    byId("vision-selected-model").title = reference || "";
    byId("vision-selected-context").textContent = `Context: ${byId("vision-context").value} tokens`;
    byId("vision-selected-output").textContent = `Output: ${byId("vision-output").value} tokens`;
    byId("vision-model-mode").options[0].textContent = `Vision setting — ${modelName(data?.settings?.reference) || "Unavailable"}`;
    byId("vision-model-mode").value = choice ? "session" : "default";
    byId("vision-model-mode").disabled = data?.settings?.session_model !== true;
    byId("vision-session-model-controls").hidden = !choice;
    byId("vision-session-model").required = Boolean(choice);
  }
  async function loadSessionModels() {
    const connection = byId("vision-model-connection").value;
    const epoch = authEpoch, session = latest?.session_id, sequence = ++modelLoad;
    modelReading?.abort(); modelReading = new AbortController();
    const select = byId("vision-session-model"), info = byId("vision-model-status");
    select.replaceChildren(domainText("option", "Choose a model")); select.firstChild.value = "";
    select.disabled = true;
    if (!connection) { info.textContent = "No enabled image model connection is configured."; return; }
    info.textContent = "Loading models…";
    try {
      const result = await domainRequest(`/api/v1/models/catalog?connection=${encodeURIComponent(connection)}&purpose=defaults`, "GET", undefined, { signal: modelReading.signal });
      if (epoch !== authEpoch || session !== latest?.session_id || sequence !== modelLoad || !byId("vision-settings").open) return;
      const choices = result.models.filter(model => model.roles && model.roles.vision !== false);
      for (const model of choices) {
        const option = domainText("option", model.name + (model.roles.vision === true ? "" : " (capabilities unverified)"));
        option.value = model.id; select.append(option);
      }
      select.disabled = false;
      select.value = sessionChoice()?.reference || "";
      info.textContent = choices.length ? "" : "No compatible image models are listed for this connection.";
    } catch (error) {
      if (epoch === authEpoch && sequence === modelLoad && error.name !== "AbortError") info.textContent = error.message;
    }
  }
  async function loadModelConnections() {
    if (!sessionChoice()) return;
    const epoch = authEpoch, session = latest?.session_id, sequence = ++modelLoad;
    modelReading?.abort(); modelReading = new AbortController();
    byId("vision-model-status").textContent = "Loading connections…";
    try {
      const result = await domainRequest("/api/v1/models/connections", "GET", undefined, { signal: modelReading.signal });
      if (epoch !== authEpoch || session !== latest?.session_id || sequence !== modelLoad || !byId("vision-settings").open) return;
      const connections = result.connections.filter(item => item.enabled && ["ollama", "openai_compatible", "anthropic", "openrouter", "openai_api", "gemini_api"].includes(item.backend));
      const select = byId("vision-model-connection"); select.replaceChildren();
      for (const item of connections) { const option = domainText("option", item.name); option.value = item.id; select.append(option); }
      const previous = sessionChoice()?.connection;
      if (previous && connections.some(item => item.id === previous)) select.value = previous;
      await loadSessionModels();
    } catch (error) {
      if (epoch === authEpoch && sequence === modelLoad && error.name !== "AbortError") byId("vision-model-status").textContent = error.message;
    }
  }
  const tagKey = value => value.trim().replace(/\s+/gu, " ").toLocaleLowerCase();
  const fullDialog = byId("vision-full-review");
  const manager = () => window.BrowserManagement;
  const active = () => authenticated && currentView === "library" && artifactDialog.open && image;
  const running = () => Boolean(image && tracked?.artifact === image.id && ["accepted", "running", "cancelling"].includes(tracked.state));
  const reviewing = () => Boolean(
    (data?.pending && data.pending.state !== "unknown" &&
      (data.pending.kind || tracked?.kind || "vision-analyze") === "vision-analyze") ||
    (running() && tracked.kind === "vision-analyze"));
  const generatingTags = () => Boolean(
    (data?.pending && data.pending.state !== "unknown" &&
      (data.pending.kind || tracked?.kind) === "vision-tags") ||
    (running() && tracked.kind === "vision-tags"));
  function requestOutcome() {
    if (!image || tracked?.artifact !== image.id || !["failed", "cancelled", "unknown"].includes(tracked.state)) return null;
    return {
      text: tracked.state === "failed" ? "The new image request failed. Your previous review is kept until it expires. Check Activity for details." :
        tracked.state === "cancelled" ? "Image request stopped. Your previous review is kept until it expires." :
          "Image request unconfirmed. Check Activity before trying again.",
      state: tracked.state === "failed" || tracked.state === "unknown" ? "error" : "",
    };
  }
  const expires = item => Number.isFinite(item.created) ? (item.created + (data?.available_hours || 24) * 3600) * 1000 : null;
  const latestResult = kind => data?.items.filter(item => item.kind === kind && (!expires(item) || expires(item) > Date.now()))
    .sort((a, b) => b.created - a.created)[0];
  function status(text = "", state = "") {
    const target = byId("vision-status");
    if (target.textContent === text && target.dataset.state === state) return;
    target.replaceChildren(); target.dataset.state = state;
    if (state === "loading" && window.MaterialLoadingCircle)
      target.append(MaterialLoadingCircle.create({ size: "small" }));
    target.append(document.createTextNode(text));
    renderPresentation();
  }
  function renderPresentation() {
    const analysis = latestResult("analysis"), state = byId("vision-status").dataset.state;
    const working = loadingReview || running() || Boolean(data?.pending && data.pending.state !== "unknown") || state === "loading";
    byId("artifact-vision").dataset.state = working ? "loading" : ["error", "expired"].includes(state) ? state : analysis ? "complete" : "empty";
    byId("artifact-vision").dataset.hasReview = String(Boolean(analysis));
    const tagging = generatingTags(), generating = reviewing() || tagging;
    const loading = loadingReview && !generating;
    byId("vision-latest").hidden = !analysis || generating || loading;
    byId("vision-empty").hidden = !generating && !loading && (Boolean(analysis) || working);
    byId("vision-empty").querySelector("h3").textContent = generating ? tagging ? "Generating tag suggestions" : "Generating review" : loading ? "Loading AI Review…" : state === "expired" ? "Review expired" : "Understand this image";
    byId("vision-empty").setAttribute("role", "status");
    const icon = byId("vision-empty-icon");
    const indicatorKind = generating ? "generating" : loading ? "loading" : "empty";
    if (icon.dataset.indicator !== indicatorKind) {
      icon.dataset.indicator = indicatorKind;
      const indicator = generating && window.MaterialLoading ? MaterialLoading.create({ size: "large" }) :
        loading && window.MaterialLoadingCircle ? MaterialLoadingCircle.create({ size: "large" }) : libraryIcon("sparkles");
      icon.replaceChildren(...(indicator ? [indicator] : []));
    }
    for (const id of ["vision-copy", "vision-expand", "vision-clear"])
      byId(id).hidden = !analysis || generating || loading;
    const description = byId("vision-empty").querySelector("p");
    if (description) description.textContent = state === "expired" ? "Ask again for a new review of this image." :
      "Ask Klaude to describe this image or explain its visible details.";
    renderSelectedSettings();
    byId("vision-question-label").textContent = analysis ? "Ask another question" : "Ask about this image";
    byId("vision-results").hidden = tagging;
    byId("vision-suggest-label").textContent = tagging ? "Cancel tag suggestions" : latestResult("tags") ? "Generate new tag suggestions" : "Generate tag suggestions";
  }
  function renderStatus() {
    if (reviewing() || generatingTags()) { status(); return; }
    if (data?.pending) {
      status(data.pending.state === "unknown" ? "This image request is unconfirmed. Check Activity before trying again." :
        data.pending.state === "cancelling" ? "Stopping the image request…" :
          `${tracked?.kind === "vision-tags" ? "Generating tag suggestions…" : "Reviewing image…"}${latestResult("analysis") ? " Your previous review remains available." : ""}`,
      data.pending.state === "unknown" ? "error" : "loading");
    } else if (running()) {
      status(`${tracked?.kind === "vision-tags" ? "Generating tag suggestions…" : "Reviewing image…"}${latestResult("analysis") ? " Your previous review remains available." : ""}`, "loading");
    } else {
      const message = outcome?.state === "expired" ? outcome : requestOutcome() || outcome;
      status(message?.text || "", message?.state || "");
    }
  }
  function renderBusy() {
    const blocked = !image || loadingReview || !latest?.media_management || Boolean(data?.pending) ||
      manager().busy(`vision:${image?.id}`) || manager().busy(`vision-save:${image?.id}`);
    for (const input of [...byId("vision-analyze").elements, byId("vision-settings-done"), byId("vision-settings-reset")]) input.disabled = blocked;
    const results = byId("vision-results"), count = tagSelection?.selected.size || 0;
    for (const button of results.querySelectorAll("button")) button.disabled = blocked;
    const save = results.querySelector(".vision-tags-save"), clear = results.querySelector(".vision-tags-clear");
    if (save) {
      save.disabled = blocked || !count;
      if (clear) clear.disabled = blocked || !count;
      save.setAttribute("aria-label", `Save ${count} selected ${count === 1 ? "tag" : "tags"}`);
      save.textContent = saving?.artifact === image?.id ? saving.state === "unknown" ? "Save unconfirmed" : "Saving…" : "Save";
      save.setAttribute("aria-busy", String(Boolean(saving && saving.artifact === image?.id)));
      for (const chip of results.querySelectorAll(".tag-filter-chip")) {
        const selected = Boolean(tagSelection?.selected.has(chip.dataset.tag));
        chip.setAttribute("aria-pressed", String(selected));
        chip.querySelector(".icon").toggleAttribute("hidden", !selected);
      }
    }
    const generating = reviewing(), cancelling = (data?.pending?.state || tracked?.state) === "cancelling";
    const canCancel = data?.pending ? data.pending.cancellable : running();
    byId("vision-submit").textContent = generating ? "Cancel review" : "Review image";
    if (generating) byId("vision-submit").disabled = !canCancel || cancelling;
    byId("vision-cancel").hidden = generating || generatingTags() || !data?.pending?.cancellable;
    byId("vision-cancel").disabled = data?.pending?.state === "cancelling";
    byId("vision-suggest").disabled = generatingTags() ? !canCancel || cancelling : blocked;
    byId("vision-analyze").setAttribute("aria-busy", String(loadingReview || Boolean(data?.pending) || running()));
    renderPresentation();
  }
  function review(draft) {
    if (!image) return;
    const target = image, epoch = authEpoch;
    const applying = draft.operation === "vision-tags-apply";
    const direct = ["vision-tags", "vision-analyze"].includes(draft.operation);
    const inspectorOpen = artifactDialog.dataset.details !== "closed";
    async function reopen() {
      if (!authenticated || epoch !== authEpoch || currentView !== "library") return;
      await openArtifact(target.id);
      if (authenticated && epoch === authEpoch && selectedArtifact?.id === target.id && inspectorOpen && artifactDialog.dataset.details === "closed")
        byId("image-details").click();
    }
    manager().review(draft, `${applying ? "vision-save" : "vision"}:${image.id}`, "image", {
      filename: target.name,
      current: () => image === target && artifactDialog.open,
      statusId: "vision-status",
      onError: error => {
        tracked = null;
        outcome = { text: error.message || "Could not prepare this image request.", state: "error" };
        status(outcome.text, outcome.state); remember();
      },
      beforeOpen: () => artifactDialog.close(),
      onAccepted: operation => {
        if (applying) saving = { request_id: operation.request_id, artifact: target.id };
        else tracked = { request_id: operation.request_id, artifact: target.id, kind: draft.operation, state: operation.state };
        outcome = null;
        if (direct) { if (image === target && artifactDialog.open) load(); }
        else reopen().catch(domainError);
      },
      onDiscard: result => {
        outcome = result.uncertain ? { text: "Image request unconfirmed. Check Activity before trying again.", state: "error" } : null;
        if (direct) { renderStatus(); renderBusy(); }
        else reopen().catch(domainError);
      },
    });
  }
  function metadata(item) {
    const metadata = domainText("div", "", "vision-review-metadata");
    const model = domainText("details", "", "vision-model");
    const reference = String(item.model || ""), match = /^([^@/]+)@[^/]+\/(.+)$/.exec(reference);
    const provider = match ? ({ ollama: "Ollama", openai: "OpenAI", openrouter: "OpenRouter" }[match[1]] || match[1]) : "";
    const summary = domainText("summary", match ? `${provider} · ${match[2]}` : reference || "Model unavailable");
    summary.title = reference;
    const logo = domainText("span", "", "model-brand-icon");
    logo.setAttribute("aria-hidden", "true");
    setModelBrandIcon(logo, reference, match?.[1] || reference.split("/")[0]);
    summary.prepend(logo);
    model.append(decorateDisclosure(summary), domainText("p", `${match ? `Provider: ${match[1]} · ` : ""}${reference}`, "muted"));
    metadata.append(model);
    if (Number.isFinite(item.created)) {
      const time = domainText("time", new Date(item.created * 1000).toLocaleString());
      time.dateTime = new Date(item.created * 1000).toISOString();
      const created = domainText("p", "Reviewed "); created.append(time); metadata.append(created);
    }
    if (expires(item)) metadata.append(domainText("p", `Available until ${new Date(expires(item)).toLocaleString()}`));
    return metadata;
  }
  function markdown(text) {
    return window.ChatMarkdown?.renderDocument ? ChatMarkdown.renderDocument(text) : domainText("div", text, "message-plain");
  }
  function remember() {
    if (image && data) cached = { id: image.id, revision: image.revision, data, outcome };
  }
  function scheduleExpiry() {
    clearTimeout(expiryTimer);
    const deadlines = (data?.items || []).map(expires).filter(value => value && value > Date.now());
    if (!active() || !deadlines.length) return;
    expiryTimer = setTimeout(() => {
      if (!active()) return;
      const analysis = data.items.find(item => item.kind === "analysis");
      data.items = data.items.filter(item => !expires(item) || expires(item) > Date.now());
      if (analysis && !latestResult("analysis")) outcome = { text: "The previous review expired. Ask again for a new review.", state: "expired" };
      if (fullResult && expires(fullResult) <= Date.now()) fullDialog.close();
      remember(); renderResults(); renderStatus(); scheduleExpiry();
    }, Math.max(1, Math.min(...deadlines) - Date.now() + 20));
  }
  function renderResults() {
    const analysis = latestResult("analysis");
    for (const id of ["vision-answer", "vision-review-metadata", "vision-copy", "vision-expand", "vision-clear"]) byId(id).hidden = !analysis;
    if (byId("vision-answer").dataset.result !== analysis?.id) {
      byId("vision-answer").replaceChildren(...(analysis ? [markdown(analysis.text)] : []));
      byId("vision-review-metadata").replaceChildren(...(analysis ? [metadata(analysis)] : []));
      byId("vision-answer").dataset.result = analysis?.id || "";
      if (fullDialog.open) fullDialog.close();
    }
    const item = latestResult("tags"), results = byId("vision-results");
    if (item && (tagSelection?.result !== item.id || tagSelection.artifact !== image.id || tagSelection.revision !== image.revision))
      tagSelection = { result: item.id, artifact: image.id, revision: image.revision, selected: new Set() };
    if (results.dataset.result !== (item?.id || "")) {
      results.replaceChildren(); results.dataset.result = item?.id || "";
      if (item) {
        const node = domainText("section", "", "vision-result");
        const form = document.createElement("form"); form.className = "vision-tag-selector";
        const group = domainText("div", "", "tag-chip-list preview-tags");
        group.setAttribute("role", "group"); group.setAttribute("aria-label", "Suggested tags");
        const seen = new Set([...(image.tags || []), ...(image.ai_tags || [])].map(tagKey));
        for (const tag of item.tags) {
          if (seen.has(tagKey(tag))) continue;
          seen.add(tagKey(tag));
          const chip = domainButton("", () => {
            if (tagSelection.selected.has(tag)) tagSelection.selected.delete(tag);
            else tagSelection.selected.add(tag);
            renderBusy();
          }, "tag-filter-chip filter-chip ai-tag-chip");
          chip.dataset.tag = tag; chip.setAttribute("aria-pressed", "false");
          const face = domainText("span", "", "filter-chip-face");
          const check = libraryIcon("check"); check.classList.add("filter-chip-check");
          face.append(check, domainText("span", tag, "filter-chip-label")); chip.append(face);
          group.append(chip);
        }
        const save = domainButton("Save", () => form.requestSubmit(), "vision-tags-save");
        const clear = domainButton("Clear", () => { tagSelection.selected.clear(); renderBusy(); }, "quiet vision-tags-clear");
        clear.setAttribute("aria-label", "Clear selected tags");
        const actions = domainText("div", "", "preview-edit-actions");
        actions.append(clear, save);
        if (!group.childElementCount) form.append(domainText("p", "These suggestions are already on this file.", "muted"));
        form.append(group, actions);
        form.addEventListener("submit", event => {
          event.preventDefault();
          if (!save.disabled && tagSelection.selected.size)
            review({ operation: "vision-tags-apply", result: item.id, selected: [...tagSelection.selected] });
        });
        node.append(form, metadata(item));
        results.append(node);
      }
    }
    const suggestions = image && item ? { artifact: image.id, revision: image.revision, tags: item.tags } : null;
    const signature = JSON.stringify(suggestions);
    if (signature !== publishedSuggestions) {
      publishedSuggestions = signature;
      document.dispatchEvent(new CustomEvent("klaude-vision-suggestions", { detail: suggestions }));
    }
    renderBusy();
  }
  async function load() {
    if (!active()) return;
    const target = image, current = ++generation, epoch = authEpoch;
    reading?.abort(); reading = new AbortController();
    try {
      const result = await domainRequest(`/api/v1/library/vision?artifact=${encodeURIComponent(target.id)}&revision=${target.revision}`, "GET", undefined, { signal: reading.signal });
      if (!active() || image !== target || current !== generation || epoch !== authEpoch) return;
      const previous = latestResult("analysis");
      loadingReview = false;
      data = result;
      if (previous && !latestResult("analysis")) outcome = { text: expires(previous) <= Date.now() ? "The previous review expired. Ask again for a new review." : "The previous review is no longer available. Ask again for a new review.", state: "expired" };
      if (tracked?.artifact === image.id && result.items.some(item => item.id === tracked.request_id)) {
        outcome = { text: tracked.kind === "vision-tags" ? "Tag suggestions ready. Select tags, then review before saving." : "Image review ready.", state: "success" };
        tracked = null;
      }
      remember(); renderResults(); renderStatus(); scheduleExpiry();
    } catch (error) {
      if (current === generation && active() && error.name !== "AbortError") {
        loadingReview = false;
        outcome = { text: `Could not refresh AI Review. ${error.message} Existing review content is kept until it expires.`, state: "error" };
        status(outcome.text, outcome.state); remember(); renderBusy();
      }
    }
  }
  function select(value) {
    remember(); clearTimeout(expiryTimer); fullDialog.close();
    image = value; data = null; generation += 1; reading?.abort();
    byId("artifact-vision").hidden = !value;
    const same = value && cached?.id === value.id && cached.revision === value.revision;
    if (value && (tagSelection?.artifact !== value.id || tagSelection.revision !== value.revision)) tagSelection = null;
    data = same ? cached.data : null; outcome = same ? cached.outcome : null;
    loadingReview = Boolean(value && !data && latest?.media_management);
    if (value && !same) cached = null;
    if (data?.items.some(item => item.kind === "analysis") && !latestResult("analysis"))
      outcome = { text: "The previous review expired. Ask again for a new review.", state: "expired" };
    byId("vision-copy").disabled = byId("vision-full-copy").disabled = false;
    renderResults(); status();
    byId("vision-cancel").hidden = true;
    if (value && !latest?.media_management) status("Restart the Web UI host and reload to use image analysis.", "error");
    else if (value) {
      renderStatus(); scheduleExpiry();
      setTimeout(() => { if (image === value) load(); }, 0);
    }
    renderBusy();
  }
  function start(operation) {
    if (!image || byId("vision-submit").disabled) return;
    for (const id of ["vision-context", "vision-output"]) {
      if (!byId(id).checkValidity()) { openReviewSettings(); byId(id).reportValidity(); return; }
    }
    if (operation === "vision-analyze" && !byId("vision-question").reportValidity()) return;
    const choice = sessionChoice();
    if (choice && !choice.reference) { openReviewSettings(); return; }
    review({ operation, target: image.id, revision: image.revision, ...(choice ? { reference: choice.reference } : {}), context: Number(byId("vision-context").value),
      output_tokens: Number(byId("vision-output").value), ...(operation === "vision-analyze" ? { question: byId("vision-question").value || "Describe this image." } : {}) });
  }
  const settingsDialog = byId("vision-settings");
  function openReviewSettings() {
    if (!active() || byId("vision-options").disabled) return;
    renderSelectedSettings();
    if (!settingsDialog.open) settingsDialog.showModal();
    loadModelConnections();
  }
  byId("vision-options").append(libraryIcon("more"));
  byId("vision-settings-close").append(libraryIcon("close"));
  byId("vision-options").addEventListener("click", openReviewSettings);
  byId("vision-settings-close").addEventListener("click", () => settingsDialog.close());
  byId("vision-model-mode").addEventListener("change", event => {
    if (event.target.value === "default") { sessionModels.delete(latest.session_id); modelReading?.abort(); modelLoad++; }
    else sessionModels.set(latest.session_id, { reference: "", connection: "" });
    renderSelectedSettings(); loadModelConnections();
  });
  byId("vision-model-connection").addEventListener("change", () => loadSessionModels());
  byId("vision-session-model").addEventListener("change", event => {
    sessionModels.set(latest.session_id, { reference: event.target.value, connection: byId("vision-model-connection").value });
    renderSelectedSettings();
  });
  for (const id of ["vision-context", "vision-output"]) byId(id).addEventListener("input", renderSelectedSettings);
  byId("vision-settings-reset").addEventListener("click", () => {
    sessionModels.delete(latest?.session_id);
    modelReading?.abort(); modelLoad++;
    for (const id of ["vision-context", "vision-output"]) {
      const input = byId(id); input.value = input.defaultValue; input.setCustomValidity("");
    }
    byId("vision-model-status").textContent = "";
    renderSelectedSettings();
  });
  byId("vision-settings-done").addEventListener("click", () => {
    if (sessionChoice() && (!sessionChoice().reference || !byId("vision-session-model").value)) {
      byId("vision-session-model").reportValidity(); return;
    }
    for (const id of ["vision-context", "vision-output"]) {
      if (!byId(id).reportValidity()) return;
    }
    settingsDialog.close();
  });
  settingsDialog.addEventListener("keydown", event => {
    if (event.key === "Enter" && event.target.matches("input")) {
      event.preventDefault(); byId("vision-settings-done").click();
    }
  });
  settingsDialog.addEventListener("close", () => {
    modelReading?.abort(); modelLoad++;
    if (active() && !byId("vision-options").disabled) byId("vision-options").focus({ preventScroll: true });
  });
  artifactDialog.addEventListener("close", () => settingsDialog.close());
  byId("vision-analyze").addEventListener("submit", event => {
    event.preventDefault();
    if (reviewing()) cancelReview();
    else start("vision-analyze");
  });
  byId("vision-suggest").addEventListener("click", () => {
    if (generatingTags()) cancelReview();
    else start("vision-tags");
  });
  byId("vision-empty-icon").append(libraryIcon("sparkles"));
  byId("vision-suggest-icon").append(libraryIcon("tags"));
  byId("vision-retention-icon").append(libraryIcon("info"));
  async function copyReview(button, item, container) {
    if (!item || !active()) return;
    if (expires(item) && expires(item) <= Date.now()) {
      fullDialog.close(); renderResults(); status("This review expired. Ask again for a new review.", "expired"); return;
    }
    const epoch = authEpoch;
    button.disabled = true;
    const copied = await ChatMarkdown.copyText(item.text, container);
    if (epoch !== authEpoch || !active()) return;
    button.disabled = false;
    if (container === fullDialog) byId("vision-full-status").textContent = copied ? "Review copied." : "Copy unavailable. Select the review text and copy it.";
    else status(copied ? "Review copied." : "Copy unavailable. Select the review text and copy it.", copied ? "success" : "error");
  }
  byId("vision-copy").addEventListener("click", () => copyReview(byId("vision-copy"), latestResult("analysis"), artifactDialog));
  byId("vision-clear").addEventListener("click", async () => {
    const review = latestResult("analysis"), target = image, epoch = authEpoch;
    if (!review || !active() || byId("vision-clear").disabled) return;
    byId("vision-clear").disabled = true;
    try {
      await domainRequest("/api/v1/library/vision/clear", "POST", {
        artifact: target.id, revision: target.revision, result: review.id,
      });
      if (epoch !== authEpoch || image !== target || !active()) return;
      generation++; reading?.abort();
      // Remove only the captured review and older reviews; keep new results and tags.
      data.items = data.items.filter(item => item.kind !== "analysis" || item.created > review.created);
      outcome = null;
      remember(); renderResults(); renderStatus(); scheduleExpiry();
      byId("vision-question").focus({ preventScroll: true });
    } catch (error) {
      if (epoch === authEpoch && image === target && active()) domainError(error, "vision-status");
    } finally {
      if (epoch === authEpoch && image === target) byId("vision-clear").disabled = false;
    }
  });
  byId("vision-full-copy").addEventListener("click", () => copyReview(byId("vision-full-copy"), fullResult, fullDialog));
  byId("vision-expand").addEventListener("click", () => {
    fullResult = latestResult("analysis");
    if (!fullResult) return;
    byId("vision-full-content").replaceChildren(metadata(fullResult), markdown(fullResult.text));
    byId("vision-full-status").textContent = "";
    byId("vision-full-copy").disabled = false;
    fullDialog.showModal(); byId("vision-full-content").scrollTop = 0;
  });
  byId("vision-full-close").append(libraryIcon("close"));
  byId("vision-full-close").addEventListener("click", () => fullDialog.close());
  fullDialog.addEventListener("close", () => {
    if (fullDialog.open) return;
    fullResult = null; byId("vision-full-content").replaceChildren(); byId("vision-full-status").textContent = "";
  });
  async function cancelReview() {
    const request = data?.pending || (running() ? tracked : null);
    if (!request || request.state === "cancelling" || request.state === "unknown") return;
    byId("vision-cancel").disabled = byId("vision-submit").disabled = byId("vision-suggest").disabled = true;
    try { await domainRequest("/api/v1/library/cancel", "POST", { request_id: request.request_id }); await load(); }
    catch (error) { domainError(error, "vision-status"); renderBusy(); }
  }
  byId("vision-cancel").addEventListener("click", cancelReview);
  document.addEventListener("klaude-operations", event => {
    const operation = event.detail.find(item => item.request_id === tracked?.request_id);
    if (operation) {
      tracked.state = operation.state;
      if (requestOutcome()) outcome = requestOutcome();
    }
    const saved = event.detail.find(item => item.request_id === saving?.request_id);
    if (saved?.state === "unknown") {
      saving.state = "unknown";
      if (active() && image.id === saving.artifact) {
        outcome = { text: "Tag save unconfirmed. Your selection is kept. Check Activity before trying again.", state: "error" };
        renderStatus(); remember(); renderBusy();
      }
    } else if (saved && ["completed", "failed", "cancelled"].includes(saved.state)) {
      const target = saving.artifact, epoch = authEpoch; saving = null;
      if (saved.state === "completed") {
        artifactDetails.delete(target);
        if (tagSelection?.artifact === target) tagSelection = null;
        if (active() && image.id === target) openArtifact(target).then(() => {
          if (active() && image.id === target && epoch === authEpoch) {
            outcome = { text: "Tags saved.", state: "success" }; renderStatus(); remember();
          }
        }).catch(domainError);
      } else if (active() && image.id === target) {
        outcome = { text: saved.state === "failed" ? "Could not save tags. Your selection is kept. Check Activity for details." : "Tag save cancelled. Your selection is kept.", state: saved.state === "failed" ? "error" : "" };
        renderStatus(); remember(); renderBusy();
      }
    } else if (active()) { renderStatus(); load(); }
  });
  document.addEventListener("klaude-auth-reset", () => {
    sessionModels.clear(); modelReading?.abort(); modelLoad++;
    saving = tracked = tagSelection = null; select(null); cached = data = outcome = null;
    byId("vision-analyze").reset(); byId("vision-settings").close();
  });
  return { select, renderBusy };
})();

// The store owns discovery/navigation only. Effects use the shared reviewed
// operation owner, and activation stays in chooseRuntime.
// Integration discovery shares Store surfaces; installs retain the reviewed domain owner.
window.IntegrationStoreUI = (() => {
  const names = {mcps:'MCPs', skills:'Skills'};
  const descriptions = {mcps:'Connect Klaude to your tools and services.', skills:'Give Klaude reusable instructions for the way you work.'};
  const defaults = {mcps:'search', skills:'coding'};
  const view = byId('store-view'), page = domainText('section', '', 'integration-store-page');
  page.id = 'integration-store-page'; page.hidden = true; view.append(page);
  const previews = domainText('section', '', 'store-integrations'); previews.id = 'store-integrations';
  const previewData = new Map(), details = new Map(), previewReads = new Map(), work = new Map();
  let kind = '', selected = '', query = '', provider = 'skillsmp', order = 'stars', number = 1;
  let data = null, read = null, generation = 0, searchTimer, poll, pending = false, browseScroll = 0;
  let previewEpoch = -1, returnFocus = '', detailRead = null, detailSerial = 0;
  const active = () => authenticated && currentView === 'store';
  const supported = () => latest?.integration_store === true;
  const capabilities = () => `${supported()}:${latest?.integration_store_sort === true}`;
  const address = (target, params={}) => '/api/v1/store/integrations' + (target ? '/' + target : '') + '?' + new URLSearchParams(params);
  const stars = new Map(), starQueue = new Set(), starReads = new Map();
  let starGeneration = 0;
  const starObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.target.isConnected) { starObserver.unobserve(entry.target); continue; }
      if (!entry.isIntersecting) continue;
      starObserver.unobserve(entry.target);
      const id = entry.target.dataset.starItem;
      if (active() && latest?.integration_store_stars && !stars.has(id)) starQueue.add(id);
    }
    pumpStars();
  }, {root:view, rootMargin:'80px'});
  function paintStars(id) {
    const result = stars.get(id);
    for (const node of view.querySelectorAll('[data-integration-stars]')) {
      if (node.dataset.integrationStars !== id) continue;
      const known = Number.isSafeInteger(result?.stars) && result.stars >= 0;
      node.hidden = !known;
      if (node.parentElement?.tagName === 'DD') {
        node.parentElement.hidden = !known; node.parentElement.previousElementSibling.hidden = !known;
      }
      if (!known) continue;
      const exact = result.stars.toLocaleString();
      node.lastElementChild.textContent = new Intl.NumberFormat(undefined,
        {notation:'compact', maximumFractionDigits:1}).format(result.stars);
      const label = `${exact} GitHub stars · ${result.repository}${result.stale ? ' · Cached' : ''}`;
      node.setAttribute('aria-label',label); node.title = label;
    }
  }
  function starBadge(item, target) {
    if (!item.github_repository || !latest?.integration_store_stars) return null;
    const badge = domainText('span','','store-integration-stars'); badge.hidden = true;
    badge.dataset.integrationStars = item.id; badge.append(libraryIcon('star'),domainText('span',''));
    target.dataset.starItem = item.id;
    const cached = stars.get(item.id);
    if (cached && ((cached.repository && cached.repository !== item.github_repository) || cached.expires <= Date.now())) stars.delete(item.id);
    else if (cached) { stars.delete(item.id); stars.set(item.id,cached); }
    starObserver.observe(target);
    return badge;
  }
  function pumpStars() {
    if (!active() || !latest?.integration_store_stars) return;
    while (starReads.size < 2 && starQueue.size) {
      const id = starQueue.values().next().value; starQueue.delete(id);
      if (stars.has(id) || starReads.has(id)) continue;
      const epoch = authEpoch, serial = starGeneration, request = new AbortController(); starReads.set(id,request);
      (async () => {
        try {
          const result = await domainRequest(address('stars',{id}),'GET',undefined,{signal:request.signal});
          if (!active() || epoch !== authEpoch || serial !== starGeneration) return;
          stars.set(id,{...result,expires:Date.now() + (result.stale ? 300000 : 3600000)});
          if (stars.size > 256) stars.delete(stars.keys().next().value);
          paintStars(id);
        } catch (error) {
          if (epoch === authEpoch && serial === starGeneration && error.name !== 'AbortError')
            stars.set(id,{stars:null,expires:Date.now()+300000});
        } finally {
          if (serial === starGeneration) { starReads.delete(id); applyStarOrder(); pumpStars(); }
        }
      })();
    }
  }
  function stopStars(clear=false) {
    starGeneration++; for (const request of starReads.values()) request.abort();
    starReads.clear(); starQueue.clear(); starObserver.disconnect(); if (clear) stars.clear();
  }
  const filterRow = domainText('div','','file-option-fields integration-store-filters');
  filterRow.setAttribute('role','group');
  const sourceLabel = domainText('label','Source'), sourceSelect = document.createElement('select');
  sourceSelect.id = 'integration-store-provider';
  sourceSelect.append(new Option('SkillsMP','skillsmp'),new Option('skills.sh','skills.sh'));
  sourceLabel.append(sourceSelect); filterRow.append(sourceLabel);
  const orderLabel = domainText('label','Order'), orderSelect = document.createElement('select');
  orderSelect.id = 'integration-store-sort';
  orderSelect.append(new Option('Stars','stars'),new Option('Recently updated','recent'));
  orderLabel.append(orderSelect); filterRow.append(orderLabel);
  const filterMenus = [sourceSelect,orderSelect].map(select=>createTrailingFilterChip(select)).filter(Boolean);
  const sourceField = sourceSelect.closest('.file-filter-field') || sourceLabel;
  sourceSelect.addEventListener('change',()=>{
    provider=sourceSelect.value;
    if(provider==='skills.sh')order='stars';
    number=1;data=null;stopStars();syncUrl(true);load();
  });
  orderSelect.addEventListener('change',()=>{
    order=orderSelect.value;number=1;data=null;stopStars();syncUrl(true);load();
  });
  const localStars = () => order === 'stars' && (kind === 'mcps' || provider === 'skills.sh');
  function queueCatalogStars() {
    if(!active() || !kind || page.hidden || selected || !data || !localStars() || !latest?.integration_store_sort) return;
    for(const item of data.items || [])
      if(item.github_repository && !stars.has(item.id))starQueue.add(item.id);
    applyStarOrder();pumpStars();
  }
  function applyStarOrder() {
    if(!active() || !kind || page.hidden || selected || !data || !localStars()) return;
    const status=page.querySelector('#integration-store-order-status');
    if(!status)return;
    const items=data.items || [], pending=items.some(item=>item.github_repository && !stars.has(item.id));
    status.textContent=pending?'Reading repository stars…':'Stars in these results';
    if(pending)return;
    if(items.some(item=>!Number.isSafeInteger(stars.get(item.id)?.stars)))
      status.textContent+=' · Some counts unavailable';
    const grid=page.querySelector('.store-integration-grid');if(!grid)return;
    const nodes=new Map([...grid.children].map(node=>[node.dataset.integrationItem,node]));
    const count=item=>Number.isSafeInteger(stars.get(item.id)?.stars)?stars.get(item.id).stars:-1;
    const ordered=[...items].sort((a,b)=>count(b)-count(a)).map(item=>nodes.get(item.id)).filter(Boolean);
    if(ordered.every((node,index)=>node===grid.children[index]))return;
    const focus=grid.contains(document.activeElement)?document.activeElement:null, scroll=view.scrollTop;
    grid.replaceChildren(...ordered);focus?.focus({preventScroll:true});view.scrollTop=scroll;
  }
  function installed(targetKind) {
    const target = targetKind === 'mcps' ? 'connections' : 'skills';
    const url = new URL(location.href); url.searchParams.set('integrations', target);
    url.searchParams.set('view','integrations');
    for(const key of [...url.searchParams.keys()])if(key.startsWith('store-'))url.searchParams.delete(key);
    history.pushState(history.state, '', url); showView('integrations', {restore:true});
  }
  function external(label, url) {
    try { const parsed = new URL(url); if (parsed.protocol !== 'https:' || parsed.username || parsed.password) return null; }
    catch { return null; }
    const node = domainText('a', label, 'quiet store-integration-source');
    node.href = url; node.target = '_blank'; node.rel = 'noopener noreferrer';
    node.append(libraryIcon('openNew')); return node;
  }
  function loading(target, text) {
    target.setAttribute('aria-busy', 'true');
    const node = domainText('div', '', 'integration-store-loading'); node.setAttribute('role','status');
    if (window.MaterialLoadingCircle) node.append(MaterialLoadingCircle.create({size:'medium'}));
    node.append(domainText('span',text,'muted')); target.append(node);
  }
  function card(item, preview=false) {
    const button = domainButton('', () => open(item.kind, item.id), 'quiet store-integration-card');
    button.dataset.integrationItem = item.id;
    const heading = domainText('span', '', 'store-integration-card-heading');
    heading.append(domainText('strong', item.name));
    const mark = libraryIcon(item.kind === 'mcps' ? 'connection' : 'text');
    heading.prepend(mark); button.append(heading);
    if (item.description) button.append(domainText('span',item.description,'store-integration-description'));
    if (item.updated_at) button.append(domainText('small','Updated ' + new Date(item.updated_at).toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'}),'muted'));
    const meta = domainText('small','','store-integration-meta muted');
    meta.append(domainText('span',item.publisher));
    const badge = starBadge(item,button); if (badge) meta.append(badge); button.append(meta);
    button.title = item.name + (item.description ? ' · ' + item.description : '');
    if (!preview && item.version) button.append(domainText('small', 'Version ' + item.version, 'muted'));
    queueMicrotask(()=>paintStars(item.id)); return button;
  }
  function previewGeometry() {
    const style = getComputedStyle(previews);
    const minimum = parseFloat(style.getPropertyValue('--store-grid-min')) || 290;
    const gap = parseFloat(style.getPropertyValue('--store-grid-gap')) || 8;
    const columns = Math.max(1, Math.floor((previews.getBoundingClientRect().width + gap) / (minimum + gap)));
    return {columns, capacity:columns * 4};
  }
  function previewItems(items) {
    const {columns, capacity} = previewGeometry(), count = Math.min(capacity, items.length);
    return items.slice(0, count >= columns ? Math.floor(count / columns) * columns : count);
  }
  function renderPreviews() {
    const focused = previews.contains(document.activeElement) ? document.activeElement : null;
    const focusItem = focused?.dataset.integrationItem, focusLabel = focused?.getAttribute('aria-label');
    previews.replaceChildren();
    const intro = domainText('header','','store-integrations-heading');
    intro.append(domainText('h2','Integrations'), domainText('p','Extend what Klaude can do.','muted'));
    previews.append(intro);
    for (const name of ['mcps','skills']) {
      const section = domainText('section','','store-integration-collection'); section.id = `store-integration-${name}`;
      const header = domainText('div','','store-section-heading');
      const title = domainText('h3', names[name]); title.id = `store-integration-${name}-heading`;
      const see = domainButton(supported() ? 'See all' : 'Manage', () => supported() ? open(name) : installed(name), 'quiet');
      see.setAttribute('aria-label', `${supported() ? 'See all' : 'Manage'} ${names[name]}`);
      header.append(title,see); section.append(header, domainText('p',descriptions[name],'store-integration-caption muted'));
      section.setAttribute('aria-labelledby', title.id);
      const result = previewData.get(name);
      if (!supported()) {
        section.append(domainText('p','Restart the WebUI host to browse the catalog. Installed integrations remain available.','muted'));
      } else if (!result) loading(section, `Loading ${names[name]}…`);
      else {
        if (result.items?.length) {
          section.append(domainText('small',name === 'mcps' ? 'Search & research · Official MCP Registry' : 'For coding · SkillsMP','store-integration-caption muted'));
          const grid = domainText('div','','store-integration-grid');
          previewItems(result.items).forEach(item => grid.append(card(item,true))); section.append(grid);
        }
        if (result.error || !result.items?.length) {
          const state = domainText('div','','store-integration-empty'); state.setAttribute('role','status');
          state.append(domainText('p',result.error || `No ${names[name]} in this collection.`, 'muted'),
            domainButton(result.error ? 'Retry' : `Browse ${names[name]}`, () => result.error ? loadPreview(name,true) : open(name), 'quiet'));
          section.append(state);
        } else if (result.stale) section.append(domainText('small','Cached collection','muted'));
      }
      section.setAttribute('aria-busy', String(previewReads.has(name))); previews.append(section);
    }
    if (focusItem || focusLabel) {
      [...previews.querySelectorAll('button')].find(button => focusItem ? button.dataset.integrationItem === focusItem : button.getAttribute('aria-label') === focusLabel)?.focus({preventScroll:true});
    }
  }
  async function loadPreview(name, refresh=false, fillOnly=false) {
    if (!active() || !supported() || previewReads.has(name)) return;
    const controller = new AbortController(), epoch = authEpoch; previewReads.set(name,controller);
    try {
      const current = () => active() && epoch === authEpoch && !controller.signal.aborted;
      let result = fillOnly ? previewData.get(name) : await domainRequest(address('', {kind:name, refresh:refresh?'1':'0'}), 'GET', undefined, {signal:controller.signal});
      if (!current() || !result) return;
      result = {...result, _page:fillOnly ? result._page || 1 : 1};
      previewData.set(name,result); renderPreviews();
      // Fill wider previews from supported continuation pages, within Models' four-read budget.
      while (result.more && !result.error && result._page < 4 && result.items.length < previewGeometry().capacity) {
        const next = await domainRequest(address('', {kind:name, page:result._page + 1, refresh:refresh?'1':'0'}), 'GET', undefined, {signal:controller.signal});
        if (!current()) return;
        const items = [...new Map([...result.items, ...(next.items || [])].map(item => [item.id,item])).values()];
        result = {...next, items, _page:result._page + 1}; previewData.set(name,result); renderPreviews();
      }
    } catch(error) { if (epoch === authEpoch && !controller.signal.aborted) previewData.set(name,{...previewData.get(name),error:'Catalog unavailable. Try again.',more:false}); }
    finally { if (previewReads.get(name) === controller) { previewReads.delete(name); if (epoch === authEpoch) renderPreviews(); } }
  }
  const observer = new IntersectionObserver(entries => {
    if (!active() || !entries.some(entry => entry.isIntersecting) || !supported()) return;
    for (const name of ['mcps','skills']) if (!previewData.has(name)) loadPreview(name);
  }, {root:view, rootMargin:'300px'});
  let previewColumns = 0, previewResizeFrame = 0;
  const previewObserver = new ResizeObserver(() => {
    if (!active() || kind || !previews.isConnected || !previews.getClientRects().length) return;
    const columns = previewGeometry().columns;
    if (columns === previewColumns) return;
    previewColumns = columns; cancelAnimationFrame(previewResizeFrame);
    previewResizeFrame = requestAnimationFrame(() => {
      if (!active() || kind || !previews.isConnected) return;
      renderPreviews();
      for (const name of ['mcps','skills']) if (previewData.get(name)?.more) loadPreview(name,false,true);
    });
  });
  previewObserver.observe(previews);
  window.addEventListener('pagehide', () => {stopStars(); previewObserver.disconnect(); cancelAnimationFrame(previewResizeFrame);});
  window.addEventListener('pageshow', () => {previewColumns=0; previewObserver.observe(previews);if(active()){renderPreviews();if(kind)render();}});
  function preview(target) {
    if (previewEpoch !== authEpoch) { previewData.clear(); previewEpoch = authEpoch; }
    target.append(previews); renderPreviews(); observer.observe(previews);
  }
  function syncUrl(replace=false) {
    const url = new URL(location.href);
    for (const [key,value] of Object.entries({'store-integrations':kind,'store-integration-item':selected,
      'store-integration-query':query,'store-integration-source':provider,'store-integration-sort':order,'store-integration-page':number>1?String(number):''})) {
      if (kind && value) url.searchParams.set(key,value); else url.searchParams.delete(key);
    }
    history[replace?'replaceState':'pushState'](history.state,'',url);
  }
  function open(nextKind, id='') {
    if (!names[nextKind]) return;
    stopStars();
    if (!kind) { returnFocus=names[nextKind]; browseScroll=view.scrollTop; history.replaceState({...history.state,storeIntegrationScroll:browseScroll},'',location.href); }
    if (kind !== nextKind) { kind=nextKind; query=defaults[kind]; provider='skillsmp';order='stars'; number=1; data=null; }
    selected=id; pending=false; syncUrl(); render();
    view.scrollTop=0; page.querySelector('h1')?.focus({preventScroll:true});
    if (selected) loadDetail(); else load();
  }
  function back() {
    stopStars();
    if (selected) { selected=''; syncUrl(); render(); load(); return; }
    kind=''; selected=''; read?.abort(); detailRead?.abort(); generation++; detailSerial++; syncUrl(); render();renderPreviews();
    view.scrollTop=history.state?.storeIntegrationScroll || browseScroll;
    const button=previews.querySelector(`[aria-label="See all ${returnFocus || 'MCPs'}"]`); button?.focus({preventScroll:true});
  }
  function renderState() {
    const item=details.get(selected), entry=work.get(selected);
    const status=page.querySelector('#integration-store-feedback'), install=page.querySelector('#integration-store-install');
    const verify=page.querySelector('[data-verify-source]'); if(verify)verify.disabled=pending;
    const activity=page.querySelector('#integration-store-activity'); if(activity)activity.hidden=!entry;
    if (status) status.textContent=entry ? ({completed:kind==='mcps'?'Server added disabled. Enable it in Integrations.':'Skill installed.',
      failed:'Installation failed. Check Activity before reviewing again.',unknown:'Outcome unconfirmed. Check Activity; do not resubmit.'}[entry.state] || 'Installing…') : '';
    if (install) install.disabled=pending || !item?.management_allowed || !item?.can_install || Boolean(entry) || Boolean(latest?.active_turn_id) || Boolean(latest?.queue?.length);
  }
  function render() {
    filterMenus.forEach(menu=>menu.close());
    page.dataset.capabilities=capabilities();
    const opened=active() && Boolean(kind);
    page.hidden=!opened; view.classList.toggle('has-integration-store',opened);
    if (!opened) { view.setAttribute('aria-labelledby',byId('store-detail').hidden?'store-title':'store-detail-title'); return; }
    view.setAttribute('aria-labelledby','integration-store-title');
    const focused=page.contains(document.activeElement)?document.activeElement.id:'';
    const draftName=page.dataset.item===selected?page.querySelector('#integration-store-name')?.value:'';
    const sourceDraft=page.dataset.item===selected?page.querySelector('#integration-store-source-url')?.value:''; page.dataset.item=selected;
    page.replaceChildren();
    const backButton=domainButton(selected?names[kind]:'Store',back,'quiet model-detail-back'); backButton.prepend(libraryIcon('previous'));
    page.append(backButton);
    const header=domainText('header','','integration-store-heading');
    const item=details.get(selected);
    const title=domainText('h1',selected?item?.name || (item?.error?'Item unavailable':'Loading details…'):names[kind]); title.id='integration-store-title'; title.tabIndex=-1;
    header.append(title,domainText('p',selected?item?.publisher || '':descriptions[kind],'muted'));
    page.append(header);
    if (!supported()) { page.append(domainText('p','Restart the WebUI host and reload to browse integrations.','domain-status')); return; }
    if (selected) {
      if (!item) { loading(page,'Loading details…'); return; }
      if (item.error) { page.append(domainText('p',item.error,'domain-status'),domainButton('Retry',()=>loadDetail(),'quiet')); return; }
      const about=domainText('section','','integration-store-about');
      about.append(domainText('h2','About'),domainText('p',item.description || 'Read the source for details.'));
      const source=external('View source',item.source_url); if(source) about.append(source); page.append(about);
      const facts=domainText('dl','','preview-metadata integration-store-facts');
      for (const [label,value] of [['Catalog',item.source],['Updated',item.updated_at],['Version',item.version],['Commit',item.revision],['Skill file',item.skill_path],['License',item.license],['Remote server',item.endpoint]])
        if (value) facts.append(domainText('dt',label),domainText('dd',value));
      page.append(facts);
      if (item.github_repository && latest?.integration_store_stars) {
        const label=domainText('dt','GitHub stars'), value=domainText('dd','');
        label.hidden=value.hidden=true;
        const badge=starBadge(item,about); if(badge)value.append(badge); facts.append(label,value);
        queueMicrotask(()=>paintStars(item.id));
      }
      const setup=domainText('section','','integration-store-setup'); setup.append(domainText('h2',kind==='mcps'?'Connect this server':'Install this skill'));
      setup.append(domainText('p',item.notice,'muted'));
      if (kind==='skills' && !item.can_install) {
        if (!item.can_resolve) {
          const label=domainText('label','Original SKILL.md URL'); label.htmlFor='integration-store-source-url';
          const input=document.createElement('input'); input.type='url'; input.id=label.htmlFor; input.maxLength=1000;
          input.placeholder='https://github.com/owner/repo/blob/main/path/SKILL.md'; input.value=sourceDraft || ''; label.append(input); setup.append(label);
        }
        const resolve=domainButton('Verify source',()=>loadDetail(true),'secondary'); resolve.dataset.verifySource='true'; resolve.disabled=pending; const actions=domainText('div','','dialog-actions');actions.append(resolve);setup.append(actions);
      }
      if (item.can_install) {
        const label=domainText('label','Local name'); label.htmlFor='integration-store-name';
        const input=document.createElement('input'); input.id=label.htmlFor; input.maxLength=80; input.required=true;
        input.value=draftName || item.name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^[^a-z0-9]+/,'').slice(0,80) || 'integration';
        label.append(input); setup.append(label);
        const action=domainButton(item.install_label,()=>reviewItem(item)); action.id='integration-store-install';
        const actions=domainText('div','','dialog-actions'); actions.append(action); setup.append(actions);
      }
      const feedback=domainText('p','','domain-status'); feedback.id='integration-store-feedback'; feedback.setAttribute('role','status'); setup.append(feedback);
      const manage=domainButton(`Manage ${names[kind]}`,()=>installed(kind),'quiet');
      const activity=domainButton('View Activity',()=>showView('activity'),'quiet');activity.id='integration-store-activity';
      const footer=domainText('div','','dialog-actions');footer.append(activity,manage);setup.append(footer);page.append(setup);renderState();
    } else {
      const form=document.createElement('form'); form.className='domain-toolbar store-search-row integration-store-toolbar';
      const label=domainText('label','','file-search-label');
      label.append(domainText('span',`Search ${names[kind]}`,'visually-hidden'));
      const input=document.createElement('input'); input.type='search'; input.id='integration-store-query'; input.maxLength=120; input.placeholder=`Search ${names[kind]}…`; input.value=query;
      input.addEventListener('input',()=>{query=input.value;number=1;stopStars();read?.abort();generation++;data=null;clearTimeout(searchTimer);searchTimer=setTimeout(()=>{syncUrl(true);load();},300);});
      label.append(input); form.append(label); form.addEventListener('submit',event=>{event.preventDefault();clearTimeout(searchTimer);number=1;syncUrl(true);load();});
      const refresh=domainButton('',()=>load(true),'icon-button quiet');refresh.setAttribute('aria-label',`Refresh ${names[kind]}`);refresh.append(libraryIcon('refresh'));form.append(refresh);page.append(form);
      filterRow.setAttribute('aria-label',`${names[kind]} filters`);sourceField.hidden=kind!=='skills';
      sourceSelect.value=provider;orderSelect.value=order;orderSelect.disabled=!latest?.integration_store_sort;
      orderSelect.options[1].disabled=kind==='skills'&&provider==='skills.sh';
      filterMenus.forEach(menu=>menu.sync());page.append(filterRow);
      page.append(domainText('p',kind==='mcps'?'Official MCP Registry · bounded search results':'Community catalog · verify source before installing','store-integration-caption muted'));
      if(!latest?.integration_store_sort)page.append(domainText('p','Restart the WebUI host and reload to enable ordering.','muted'));
      else if(kind==='skills'&&provider==='skills.sh')page.append(domainText('p','Updated dates are unavailable from skills.sh. Choose SkillsMP for recently updated skills.','muted'));
      if(latest?.integration_store_sort && localStars()){
        const status=domainText('p','','store-integration-caption muted');status.id='integration-store-order-status';status.setAttribute('role','status');page.append(status);
      }
      if(!data) loading(page,`Loading ${names[kind]}…`);
      else {
        if(data.error) page.append(domainText('p',data.error,'domain-status'),domainButton('Retry',()=>load(true),'quiet'));
        else if(data.stale) page.append(domainText('p','Cached results','muted'));
        const grid=domainText('div','','store-integration-grid'); data.items?.forEach(item=>grid.append(card(item))); page.append(grid);
        if(!data.items?.length && !data.error) page.append(domainText('p','No matches. Try a different search.','muted'));
        if(number>1 || data.more) {
          const nav=domainText('nav','','pagination');nav.setAttribute('aria-label',`${names[kind]} pages`);
          const previous=domainButton('Previous',()=>{number--;syncUrl();load();},'quiet');previous.disabled=number<=1;
          const next=domainButton('Next',()=>{number++;syncUrl();load();},'quiet');next.disabled=!data.more;
          nav.append(previous,domainText('span',`Page ${number}`),next);page.append(nav);
        }
      }
    }
    if(focused) page.querySelector(`#${CSS.escape(focused)}`)?.focus({preventScroll:true});
    queueMicrotask(queueCatalogStars);
  }
  async function load(refresh=false) {
    if(!active() || !kind || selected || !supported()) return;
    stopStars();
    const id=++generation,epoch=authEpoch;read?.abort();const request=new AbortController();read=request; data=null;render();
    try {
      const grouped = kind === 'skills' && provider === 'skillsmp';
      const sourcePage = grouped ? (number - 1) * 2 + 1 : number;
      const params = {kind,query,provider,page:sourcePage,refresh:refresh?'1':'0',...(latest?.integration_store_sort?{sort:order}:{})};
      let result=await domainRequest(address('',params),'GET',undefined,{signal:request.signal});
      if (grouped && result.more && !result.error && active() && epoch===authEpoch && id===generation) {
        try {
          const next=await domainRequest(address('',{...params,page:sourcePage+1}),'GET',undefined,{signal:request.signal});
          const items=new Map([...(result.items || []),...(next.items || [])].map(item=>[item.id,item]));
          result={...next,items:[...items.values()],stale:result.stale || next.stale};
        } catch(error) {
          if(error.name==='AbortError')throw error;
          result={...result,more:false,error:'More results unavailable. Retry to load the complete page.'};
        }
      }
      if(!active() || epoch!==authEpoch || id!==generation) return;data=result;
    }catch(error){if(epoch===authEpoch && id===generation && error.name!=='AbortError')data={items:[],error:'Catalog unavailable. Retry or choose another source.'};}
    finally{if(epoch===authEpoch && id===generation)render();}
  }
  async function loadDetail(resolve=false) {
    if(!active() || !selected || !supported()) return;
    const id=selected,epoch=authEpoch,current=++detailSerial, source=page.querySelector('#integration-store-source-url')?.value.trim() || '';
    detailRead?.abort(); const request=new AbortController();detailRead=request;pending=true;renderState();
    try{
      const item=await domainRequest(address('detail',{id,...(resolve?{resolve:'1',source}:{})}),'GET',undefined,{signal:request.signal});
      if(!active() || epoch!==authEpoch || id!==selected || current!==detailSerial)return;
      details.set(id,item);pending=false;render();
    }catch(error){if(epoch===authEpoch && id===selected && current===detailSerial && error.name!=='AbortError'){
      if(details.has(id)) showError(error.message); else details.set(id,{error:error.message});
    }}finally{if(epoch===authEpoch && current===detailSerial){pending=false;renderState();}}
  }
  async function reviewItem(item) {
    if(pending || !item.management_allowed || work.has(item.id))return;
    const input=page.querySelector('#integration-store-name');if(!input.reportValidity())return;
    const epoch=authEpoch,id=selected;pending=true;renderState();
    try{
      await prepareChange({operation:kind==='mcps'?'mcp-store-add':'skill-store-install',id:item.id,name:input.value.trim()},{
        current:()=>active() && epoch===authEpoch && selected===id,
        onAccepted:receipt=>{if(epoch!==authEpoch)return;work.set(id,receipt);pending=false;renderState();startPolling();},
        onDiscard:()=>{if(epoch===authEpoch){pending=false;renderState();}},
      });
    }catch(error){if(epoch===authEpoch)showError(error.message);}
    finally{if(epoch===authEpoch && !reviewDialog.open){pending=false;renderState();}}
  }
  function startPolling(){clearInterval(poll);poll=setInterval(()=>{if(active() && [...work.values()].some(item=>!['completed','failed','unknown'].includes(item.state)))loadOperations();else{clearInterval(poll);poll=null;}},1500);}
  document.addEventListener('klaude-operations',event=>{for(const [id,old] of work){const item=event.detail.find(row=>row.request_id===old.request_id);if(item)work.set(id,item);}if(active()&&selected)renderState();});
  function restore(){
    canonicalizeStoreLocation();
    stopStars();
    const params=new URLSearchParams(location.search),next=params.get('store-integrations');
    if(!active() || !names[next]){kind='';selected='';render();return;}
    kind=next;selected=params.get('store-integration-item') || '';query=(params.get('store-integration-query') || defaults[kind]).slice(0,120);
    provider=params.get('store-integration-source')==='skills.sh'?'skills.sh':'skillsmp';number=Math.max(1,Math.min(kind==='skills'&&provider==='skillsmp'?5:1,Number(params.get('store-integration-page'))||1));
    order=params.get('store-integration-sort')==='recent'&&!(kind==='skills'&&provider==='skills.sh')?'recent':'stars';
    render();if(selected)loadDetail();else load();
  }
  window.addEventListener('popstate',restore);
  document.addEventListener('klaude-view',()=>{clearTimeout(searchTimer);if(active())restore();else{stopStars();read?.abort();detailRead?.abort();generation++;detailSerial++;for(const request of previewReads.values())request.abort();previewReads.clear();clearInterval(poll);page.hidden=true;}});
  document.addEventListener('klaude-snapshot',()=>{if(active()&&kind){if(!page.querySelector('h1') || page.dataset.capabilities!==capabilities())restore();else renderState();}});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!event.defaultPrevented&&active()&&kind&&!document.querySelector('dialog[open], [popover]:popover-open')){event.preventDefault();event.stopPropagation();back();}});
  document.addEventListener('klaude-auth-reset',()=>{stopStars(true);read?.abort();detailRead?.abort();generation++;detailSerial++;for(const request of previewReads.values())request.abort();previewReads.clear();previewData.clear();details.clear();work.clear();observer.disconnect();clearInterval(poll);clearTimeout(searchTimer);kind=selected='';order='stars';data=null;page.replaceChildren();page.hidden=true;previews.replaceChildren();cancelAnimationFrame(previewResizeFrame);previewColumns=0;view.classList.remove('has-integration-store');});
  return {preview,refresh:()=>{previewData.clear();if(previews.isConnected){renderPreviews();for(const name of ['mcps','skills'])loadPreview(name,true);}},isOpen:()=>active()&&Boolean(kind)};
})();

window.ModelStoreUI = (() => {
  const sections = ['discover', 'installed', 'downloads'];
  const labels = ['Discover', 'Installed', 'Downloads'];
  const categories = ['Coding', 'Reasoning', 'Vision', 'General-purpose', 'Lightweight'];
  let section = 'discover', collection = '', category = '', catalog = null, connections = [], endpoint = '', inventory = null;
  let runtime = 'ollama';
  const imageStore = () => runtime === 'sdcpp';
  const runtimeQuery = () => imageStore() ? '&runtime=sdcpp' : '';
  // Early hosts advertised SD support before the namespaced download contract.
  const imageStoreReady = () => latest?.model_store_sdcpp === true && latest?.model_store_sdcpp_revision === 1;
  const runtimeReady = () => runtime === 'ollama' || imageStoreReady();
  const modelKey = item => `${item.runtime || runtime}|${item.id || item.name}`;
  const allPageEnds = new Map();
  let livePageSize = 40;
  let liveCatalog = null, livePage = 1, liveSerial = 0, liveReading = null, searchTimer = null, detailReading = '', liveLoading = false;
  const liveDetails = new Map();
  const hub = () => imageStore() || collection === 'charts' || byId('store-source').value === 'huggingface';
  const liveLanding = () => hub() && !byId('store-query').value.trim() && !category && !collection && byId('store-sort').value === 'downloads';
  let popularCatalog = null, recentCatalog = null, popularReading = null, popularSerial = 0;
  let jobs = [], observedTransfers = [], jobsLoaded = false, serial = 0, allowed = false, pending = false, timer = null, reading = null, busyRead = false;
  const downloadBars = new Map();
  const downloadRates = new Map();
  const downloadRateKey = item => `${item.request_id ? 'owned' : 'observed'}:${item.request_id || item.id}`;
  function sampleDownloadRates(items) {
    const now = performance.now(), retained = new Set();
    for (const item of items) {
      const key = downloadRateKey(item), progress = item.progress;
      if (!['running','cancelling'].includes(item.state) || !Number.isFinite(progress?.completed) ||
          !Number.isFinite(progress?.total) || progress.total <= 0 || progress.completed < 0) continue;
      retained.add(key);
      const previous = downloadRates.get(key), elapsed = previous ? (now - previous.at) / 1000 : 0;
      if (previous && elapsed < .25 && previous.total === progress.total && previous.stage === progress.stage &&
          progress.completed >= previous.completed) continue;
      const comparable = previous && elapsed >= .25 && elapsed <= 15 && previous.total === progress.total &&
        previous.stage === progress.stage && progress.completed >= previous.completed;
      downloadRates.set(key, {at:now, total:progress.total, stage:progress.stage, completed:progress.completed,
        rate:comparable ? (progress.completed - previous.completed) / elapsed / 1_000_000 : null});
    }
    for (const key of downloadRates.keys()) if (!retained.has(key)) downloadRates.delete(key);
  }
  function downloadMetadata(item) {
    const installed = item.state === 'completed' && item.kind === 'model-pull' && item.connection === endpoint && !inventory?.stale
      ? inventory?.models?.find(row => row.name === item.model) : null;
    let variant;
    for (const collection of [catalog?.models || [], [...liveDetails.values()]]) {
      for (const model of collection) {
        variant = model.variants?.find(row => row.tag === item.model);
        if (variant) break;
      }
      if (variant) break;
    }
    const parameters = installed?.parameters || item.parameters || variant?.parameters;
    const size = installed?.size ?? item.size ?? variant?.size;
    const knownSize = Number.isFinite(size) && size >= 0;
    const fileSizeKnown = Number.isFinite(item.progress?.total) && item.progress.total > 0;
    return {parameters:typeof parameters === 'string' && parameters.trim() ? parameters : 'Parameters unknown',
      size:knownSize ? fileSize(size) : variant?.size_label || (fileSizeKnown ? `File ${fileSize(item.progress.total)}` : 'Size unknown')};
  }
  function downloadSpeed(item) {
    const rate = downloadRates.get(downloadRateKey(item))?.rate;
    return Number.isFinite(rate) ? `${rate.toLocaleString(undefined, {minimumFractionDigits:1, maximumFractionDigits:2})} MB/s` : '— MB/s';
  }
  function removeDownloadBar(key) { const bar = downloadBars.get(key); bar?.destroy?.(); bar?.element.remove(); downloadBars.delete(key); }
  function clearDownloadBars() { for (const key of downloadBars.keys()) removeDownloadBar(key); }
  const active = () => authenticated && currentView === 'store';
  const supported = () => latest?.model_store === true;
  const restartMessage = 'Restart the WebUI host, then reload this page to use Model Store. Connection settings remain available in Settings → Models.';
  const dialog = byId('store-detail'), downloadDialog = byId('store-download-dialog');
  const storeFilterMenus = ['store-runtime','store-source','store-sort','store-capability','store-size'].map(id => createTrailingFilterChip(byId(id))).filter(Boolean);
  const closeStoreFilters = () => storeFilterMenus.forEach(menu => menu.close());
  const downloadInfo = byId('store-download-info');
  let downloadInfoKey = '', downloadInfoSource = '', downloadInfoError = '';
  let variantPageSelection = '';
  let shownDetail = '', detailSignature = '', variantPage = 1;
  let browseContext = null, detailsOpen = new Set();
  let detail = '', variant = '', returnFocusId = '', inventoryRead = 0, installedPage = 1, observedCapability;
  const message = text => { byId('store-status').textContent = text; };
  const urlState = () => {
    canonicalizeStoreLocation();
    const p = new URLSearchParams(location.search);
    const nextRuntime = ['all','sdcpp'].includes(p.get('models-runtime')) ? p.get('models-runtime') : 'ollama';
    if (nextRuntime !== runtime) resetRuntime(nextRuntime);
    byId('store-runtime').value = runtime;
    const oldSection = p.get('models-section');
    if (oldSection === 'connections') {
      const url = new URL(location.href); for (const key of [...url.searchParams.keys()]) if (key.startsWith('models-')) url.searchParams.delete(key);
      url.searchParams.set('view','settings'); url.searchParams.set('settings','models');
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
      showView('settings', {section:'models', restore:true}); return false;
    }
    section = sections.includes(oldSection) ? oldSection : 'discover';
    collection = oldSection === 'charts' || p.get('models-collection') === 'charts' ? 'charts' : '';
    category = categories.includes(p.get('models-category')) ? p.get('models-category') : '';
    byId('store-query').value = (p.get('models-query') || '').slice(0, 200);
    detail = (p.get('models-detail') || '').slice(0, 200);
    variant = (p.get('models-variant') || '').slice(0, 200);
    const saved = history.state?.klaudeStoreBrowse;
    if (saved && typeof saved.scroll === 'number') { browseContext = saved; installedPage = Math.max(1, Math.min(1000, Number(saved.page) || 1)); returnFocusId = typeof saved.focus === 'string' ? saved.focus : ''; }
    if (runtime !== 'sdcpp' && connections.some(c => c.id === saved?.endpoint)) endpoint = saved.endpoint;
    byId('store-source').value = p.get('models-source') === 'offline' || category || ['tools','vision','thinking'].includes(p.get('models-capability')) ? 'curated' : 'huggingface';
    if (imageStore()) { category = ''; byId('store-source').value = 'huggingface'; byId('store-capability').value = 'all'; }
    byId('store-sort').value = p.get('models-sort') === 'lastModified' ? 'lastModified' : 'downloads';
    livePage = Math.max(1, Math.min(500, Number(p.get('models-page')) || 1));
    livePageSize = Math.max(1, Math.min(50, Number(p.get('models-page-size')) || 40));
    byId('store-size').value = ['8','16','32'].includes(p.get('models-size')) ? p.get('models-size') : 'all';
    byId('store-capability').value = ['tools','vision','thinking'].includes(p.get('models-capability')) ? p.get('models-capability') : 'all';
    return true;
  };
  function navigate(next, cat = '', id = '', replace = false, group = collection) {
    const enteringDiscover = next === 'discover' && section !== next;
    if (next !== section) { collection = ''; category = ''; livePage = 1; }
    if (group !== collection) livePage = 1;
    section = next; category = cat; detail = id; collection = section === 'discover' ? group : '';
    if (cat) { collection = ''; byId('store-source').value = 'curated'; }
    const url = new URL(location.href);
    for (const [key, value] of Object.entries({'models-runtime': runtime === 'ollama' ? '' : runtime, 'models-section': section, 'models-category': category,
      'models-collection': collection, 'models-page': livePage > 1 ? String(livePage) : '', 'models-page-size': livePage > 1 ? String(livePageSize) : '', 'models-detail': detail, 'models-variant': detail ? variant : '', 'models-query': byId('store-query').value,
      'models-source': byId('store-source').value === 'curated' ? 'offline' : 'huggingface', 'models-sort': byId('store-sort').value,
      'models-size': byId('store-size').value, 'models-capability': byId('store-capability').value})) {
      if (value && (value !== 'all' || key === 'models-runtime')) url.searchParams.set(key, value); else url.searchParams.delete(key);
    }
    history[replace ? 'replaceState' : 'pushState'](history.state, '', url.pathname + url.search + url.hash);
    render();
    if (section === 'downloads') loadJobs();
    if (section === 'discover' && liveLanding()) loadPopular(enteringDiscover);
    else if (section === 'discover' && hub()) loadLive(enteringDiscover);
  }
  function icon(name, size = 32) {
    const node = domainText('span', '', 'model-brand-icon'); node.setAttribute('aria-hidden', 'true');
    setModelBrandIcon(node, name, 'ollama', {appearance: 'color', size}); return node;
  }
  function link(label, url) {
    const a = domainText('a', label); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a;
  }
  function openDetail(id, trigger, targetRuntime = runtime) {
    const context = {scroll:byId('store-view').scrollTop, focus:trigger?.dataset.storeKey || trigger?.dataset.storeModel || id, page:installedPage, section, url:location.href, endpoint};
    if (runtime === 'all') {
      const selectedEndpoint = endpoint;
      resetRuntime(targetRuntime); byId('store-runtime').value = runtime;
      if (targetRuntime === 'ollama' && connections.some(c => c.id === selectedEndpoint)) endpoint = selectedEndpoint;
    }
    returnFocusId = context.focus; browseContext = context;
    history.replaceState({...history.state, klaudeStoreBrowse:browseContext}, '', location.href);
    message(''); variant = ''; variantPageSelection = ''; variantPage = 1; detailsOpen.clear(); detailSignature = '';
    navigate(section, category, id);
    if (context.url.includes('models-runtime=all')) load();
  }
  function restoreDetailFocus() {
    const target = [...byId('store-content').querySelectorAll('[data-store-model]')].find(node => (node.dataset.storeKey || node.dataset.storeModel) === returnFocusId);
    (target || byId('store-query')).focus({preventScroll:true});
  }
  function sectionHeading(title, action = '', onClick = null) {
    const header = domainText('div', '', 'store-section-heading');
    header.append(domainText('h2', title));
    if (action) header.append(domainButton(action, onClick, 'quiet'));
    return header;
  }
  function runtimeBadge(targetRuntime = runtime) {
    if (targetRuntime === 'sdcpp') {
      const badge = domainText('span', '', 'store-runtime-badge');
      badge.append(libraryIcon('image'), domainText('span', 'Stable Diffusion'));
      badge.title = 'Download to the local Stable Diffusion model directory'; return badge;
    }
    const runtime = domainText('span', '', 'store-runtime-badge');
    const runtimeIcon = domainText('span', '', 'model-brand-icon store-runtime-icon');
    runtimeIcon.setAttribute('aria-hidden', 'true');
    window.AIIcons?.setPlatformIcon(runtimeIcon, 'ollama', {size:16});
    runtimeIcon.removeAttribute('title'); // The whole runtime pill owns its tooltip.
    const server = connections.find(connection => connection.id === endpoint);
    const runtimeLabel = connections.length > 1 && server ? `Ollama · ${server.name}` : 'Ollama';
    runtime.append(runtimeIcon, domainText('span', runtimeLabel));
    runtime.title = server ? `Install via Ollama on ${server.name}` : 'Install via Ollama. Configure a server in Model settings.';
    runtime.setAttribute('aria-label', runtime.title);
    return runtime;
  }
  function modelTask(item) {
    if (!item || typeof item.id !== 'string') return '';
    // Older hosts put the Hub pipeline tag in summary; retain that metadata too.
    const known = new Set(['text-generation','text2text-generation','text-to-speech','text-to-audio','text-to-image','text-to-video','image-text-to-text','image-to-text','image-to-image','image-to-video','automatic-speech-recognition','audio-text-to-text','feature-extraction','sentence-similarity','image-classification','object-detection','visual-question-answering']);
    const source = [item, ...(popularCatalog?.models || []), ...(recentCatalog?.models || []), ...(liveCatalog?.models || [])].find(row => row && row.id === item.id && (row.task || known.has(row.summary)));
    const task = source?.task || (known.has(source?.summary) ? source.summary : '');
    return /^[a-z][a-z0-9-]{0,79}$/.test(task) ? task.charAt(0).toUpperCase() + task.slice(1) : '';
  }
  function modelUpdated(item) {
    const date = typeof item?.modified === 'string' && item.modified.trim() ? new Date(item.modified) : null;
    return date && Number.isFinite(date.getTime()) ? date : null;
  }
  const updatedLabel = date => date ? new Intl.DateTimeFormat(undefined, {dateStyle:'medium'}).format(date) : 'Unknown';
  function modelRow(item, rank = 0) {
    const button = domainButton('', () => openDetail(item.id, button, item.runtime || runtime), 'store-row quiet');
    button.dataset.storeModel = item.id; button.dataset.storeKey = modelKey(item);
    const content = domainText('span', '', 'store-card-content');
    content.append(domainText('strong', item.name));
    const purpose = Number.isInteger(item.downloads) ? `${item.downloads.toLocaleString()} Hub downloads` : item.categories?.join(' · ') || item.publisher || item.summary;
    if (Number.isInteger(item.downloads)) {
      const downloads = domainText('small', '', 'store-download-count muted');
      downloads.title = purpose; downloads.setAttribute('aria-label', purpose);
      downloads.append(libraryIcon('download'), domainText('span', item.downloads.toLocaleString()));
      const metadata = domainText('span', '', 'store-model-metadata');
      const modified = modelUpdated(item), updated = domainText('small', 'Updated ', 'store-last-updated muted');
      if (modified) {
        const time = domainText('time', updatedLabel(modified));
        time.dateTime = modified.toISOString(); time.title = modified.toLocaleString(); updated.append(time);
      } else updated.append(document.createTextNode('Unknown'));
      metadata.append(downloads, updated); content.append(metadata);
    } else content.append(domainText('small', purpose, 'muted'));
    const task = modelTask(item);
    if (task) content.append(domainText('small', task, 'store-task-label muted'));
    content.append(runtimeBadge(item.runtime || runtime));

    if (rank) { button.classList.add('store-ranked-row'); button.append(domainText('span', String(rank), 'store-rank')); }
    const installed = inventory?.models?.some(local => (!item.runtime || item.runtime === local.runtime) && item.variants?.some(v => v.tag === local.name));
    button.append(icon(item.id, 40), content, domainText('span', installed ? 'Installed' : 'View', 'store-cta'));
    button.title = `${item.name} · ${item.summary || purpose}`;
    return button;
  }
  function modelGrid(items, ranked = false) {
    const grid = domainText('div', '', 'store-model-grid');
    items.forEach((item, index) => grid.append(modelRow(item, ranked && runtime !== 'all' && Number.isInteger(item.downloads) ? index + 1 : 0)));
    return grid;
  }
  function filtered() {
    const query = byId('store-query').value.trim().toLocaleLowerCase(), capability = byId('store-capability').value;
    return (catalog?.models || []).filter(item => (!category || item.categories.includes(category)) &&
      (capability === 'all' || item.capabilities.includes(capability)) &&
      `${item.name} ${item.summary} ${item.categories.join(' ')} ${item.capabilities.join(' ')}`.toLocaleLowerCase().includes(query));
  }
  function emptyState(target, title, description, icon) {
    collectionEmpty(target, title, description, icon); target.classList.add('is-empty');
    target.querySelector('.collection-empty').setAttribute('role', 'status');
  }
  function catalogLoading(target) {
    const state = domainText('div', '', 'collection-empty store-catalog-loading');
    state.setAttribute('role', 'status'); target.setAttribute('aria-busy', 'true');
    const indicator = window.MaterialLoadingCircle?.create({size:'large'});
    if (indicator) state.append(indicator);
    state.append(domainText('p', 'Loading Catalog')); target.append(state);
  }
  function settingsLink(target) {
    target.append(domainButton('Open model settings', () => {
      showView('settings', {section:'models'}); ModelsSettingsNavigation.show('connections', {focus:true});
    }, 'quiet'));
  }
  function detailSection(title, identity) {
    const node = domainText('section', '', 'model-detail-section');
    const heading = domainText('h2', title); heading.id = identity;
    node.setAttribute('aria-labelledby', identity); node.append(heading); return node;
  }
  function focusVariants() {
    const group = byId('store-variants-section');
    group.scrollIntoView({block:'start', behavior:'instant'});
    (group.querySelector('input:checked') || group.querySelector('input') || group.querySelector('h2')).focus({preventScroll:true});
  }
  function selectVariant(tag) {
    variant = tag;
    const url = new URL(location.href); url.searchParams.set('models-variant', tag);
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    renderDetail();
  }
  function renderDetail() {
    if (!active() || !detail || dialog.hidden) return;
    const item = liveDetails.get(detail) || catalog?.models.find(item => item.id === detail) || liveCatalog?.models?.find(item => item.id === detail) || popularCatalog?.models?.find(item => item.id === detail) || recentCatalog?.models?.find(item => item.id === detail);
    const local = inventory?.models?.find(item => item.name === detail);
    const variants = item?.variants || (local ? [{tag:local.name,...local}] : []);
    const loading = detail.startsWith('hf:') && !item?.detailLoaded;
    if (!variants.some(row => row.tag === variant) && !loading && (item || local || catalog)) variant = local ? local.name : '';
    const selectedIndex = variants.findIndex(row => row.tag === variant);
    if (variant && selectedIndex >= 0 && variantPageSelection !== variant) { variantPage = Math.floor(selectedIndex / 20) + 1; variantPageSelection = variant; }
    const metadata = variants.find(row => row.tag === variant);
    const installed = metadata && inventory?.models?.find(row => row.name === variant);
    const downloadSize = installed?.size != null ? fileSize(installed.size) : metadata?.size != null ? fileSize(metadata.size) : metadata?.size_label || '';
    const destination = imageStore() ? 'Local Stable Diffusion models' : connections.find(c => c.id === endpoint)?.name || '';
    const current = Boolean(!imageStore() && installed && !latest?.requires_model_selection && (latest?.model_ref === `ollama@${endpoint}/${variant}` || endpoint === 'default-ollama' && [variant,`ollama/${variant}`].includes(latest?.model_ref || latest?.model)));
    const useAllowed = Boolean(!imageStore() && installed && !inventory.stale && !current && !pending && !runtimeChoiceInFlight && !latest?.active_turn_id && !latest?.queue?.length && (latest?.model_providers || endpoint === 'default-ollama'));
    const signature = JSON.stringify([detail,variant,variantPage,item,modelTask(item),local,inventory?.stale,inventory?.checked_at,connections,endpoint,pending,allowed,latest?.active_turn_id,latest?.queue?.length,jobs.map(job=>job.state),canWrite(),useAllowed,current,byId('store-status').textContent]);
    if (signature === detailSignature) return;
    detailSignature = signature;
    const focused = document.activeElement, focusId = dialog.contains(focused) ? focused.id : '';
    const focusPage = focused?.closest('#store-variants-pages') ? focused.dataset.page : '';
    for (const disclosure of dialog.querySelectorAll('details')) {
      if (disclosure.open) detailsOpen.add(disclosure.id); else detailsOpen.delete(disclosure.id);
    }
    const body = byId('store-detail-body'); body.replaceChildren();
    const identity = domainText('header', '', 'model-detail-identity'); identity.id = 'store-detail-identity';
    const logo = domainText('div', '', 'model-detail-logo'); logo.append(icon(item?.id || detail, 88));
    const summary = domainText('div', '', 'model-detail-summary');
    const title = domainText('h1', item?.name || local?.name || detail); title.id = 'store-detail-title'; title.tabIndex = -1;
    const byline = domainText('p', '', 'model-detail-byline muted');
    if (item?.publisher) {
      byline.append(document.createTextNode('By '));
      if (detail.startsWith('hf:')) {
        const author = link(item.publisher, `https://huggingface.co/${encodeURIComponent(item.publisher)}`);
        author.setAttribute('aria-label', `Open ${item.publisher} author profile in a new tab`);
        byline.append(author);
      } else byline.append(document.createTextNode(item.publisher));
    } else byline.textContent = destination ? `Installed on ${destination}` : 'Model details';
    summary.append(title, byline);
    summary.append(runtimeBadge());
    if (item?.stale) summary.append(domainText('p', 'Cached metadata', 'model-detail-source muted'));
    const actionArea = domainText('div', '', 'model-detail-actions');
    const install = domainButton(installed ? imageStore() ? 'Installed' : current ? 'Current model' : 'Use model' : variant ? `Download${downloadSize ? ` · ${downloadSize}` : ''}` : 'Choose model', async () => {
      if (!installed) {
        if (!variant) focusVariants(); else review('model-pull', variant);
        return;
      }
      if (installed) {
        if (!useAllowed) return; pending = true; renderDetail();
        try { await chooseRuntime('model', latest.model_providers ? `ollama@${endpoint}/${variant}` : variant, {onError:error => message(error.message)}); }
        finally { pending = false; renderDetail(); }
      }
    }, installed || variant ? 'model-detail-install' : 'secondary model-detail-choose'); install.id = 'store-detail-install';
    install.disabled = installed ? !useAllowed : variant ? !canWrite() || !inventory?.models || inventory.stale : !variants.length;
    if (!installed && variant) install.prepend(libraryIcon('download'));
    actionArea.append(install);
    let blocker = '';
    if (!loading && !variants.length) blocker = item?.error || 'No supported variants are available.';
    else if (!runtimeReady()) blocker = 'Restart the WebUI host and reload to browse Stable Diffusion models.';
    else if (!endpoint) blocker = 'Choose an enabled native Ollama connection in Model settings.';
    else if (!allowed && !installed) blocker = 'Installation requires an admin account.';
    else if (latest?.active_turn_id || latest?.queue?.length) blocker = 'Finish the conversation and queue before model work.';
    else if (!inventory?.models || inventory.stale) blocker = imageStore() ? 'The host image-model directory must exist and be writable. Refresh after configuring it.' : 'Refresh the native endpoint to verify its installed inventory.';
    else if (!canWrite() && !installed) blocker = 'Model work is active or unconfirmed. Check Downloads.';

    if (byId('store-status').textContent && !inventory?.stale) blocker = byId('store-status').textContent;
    const notice = domainText('p', blocker, 'model-detail-blocker muted'); notice.id = 'store-detail-blocker'; notice.setAttribute('role','status'); actionArea.append(notice);
    if (jobs.some(job => ['accepted','running','cancelling','unknown'].includes(job.state))) actionArea.append(domainButton('View downloads', () => navigate('downloads'), 'quiet'));
    if (!endpoint) settingsLink(actionArea);
    else if (!inventory?.models || inventory.stale) actionArea.append(domainButton('Refresh inventory', () => loadInventory(), 'quiet'));
    if (item?.error && detail.startsWith('hf:')) actionArea.append(domainButton('Retry source details', () => { liveDetails.delete(detail); detailSignature = ''; loadLiveDetail(detail); }, 'quiet'));
    identity.append(logo,summary,actionArea); body.append(identity);
    if (item?.source_url) {
      const cardLink = link('', item.source_url); cardLink.className = 'icon-button quiet model-card-link';
      cardLink.setAttribute('aria-label', 'Open model card in a new tab'); cardLink.title = 'Open model card in a new tab';
      cardLink.append(libraryIcon('openNew')); summary.append(cardLink);
    }
    const stats = domainText('dl', '', 'model-detail-stats'); stats.id = 'store-detail-stats';
    const size = metadata ? installed?.size != null ? fileSize(installed.size) : metadata.size != null ? fileSize(metadata.size) : metadata.size_label || 'Unknown' : 'Choose variant';
    const capabilities = item?.capabilities?.length ? item.capabilities.join(' · ') : 'Unknown';
    const facts = [];
    const task = modelTask(item);
    if (task) facts.push(['Task', task]);
    if (Number.isInteger(item?.downloads)) facts.push(['Hub downloads', new Intl.NumberFormat(undefined, {notation:'compact', maximumFractionDigits:1}).format(item.downloads)]);
    if (Number.isInteger(item?.downloads) || modelUpdated(item)) facts.push(['Updated', updatedLabel(modelUpdated(item))]);
    if (variants.length) facts.push(['Available variants', String(variants.length)]);
    if (metadata?.parameters) facts.push(['Parameters', metadata.parameters]);
    if (detail.startsWith('hf:') && variants.length) facts.push(['Format', imageStore() ? [...new Set(variants.map(v => v.tag.endsWith('.gguf') ? 'GGUF' : 'Safetensors'))].join(' · ') : 'GGUF']);
    if (item?.license) facts.push(['License', item.license]);
    for (const [label,value] of facts) {
      const stat = domainText('div', '', 'model-detail-stat'), term = domainText('dt', label);
      if (label === 'Hub downloads') {
        term.replaceChildren(libraryIcon('download'), domainText('span','Hub downloads','visually-hidden'));
        term.title = 'Hugging Face downloads';
      }
      stat.append(term,domainText('dd',value)); stats.append(stat);
    }
    stats.hidden = !facts.length;
    body.append(stats);
    const reading = domainText('div', '', 'model-detail-reading');
    const about = detailSection('About this model','store-detail-about');
    const description = item?.summary || (local ? imageStore() ? 'Downloaded image weights. Load this file and its required components in your Stable Diffusion server, then test and save the service in Settings → Models → Image generation.' : 'This exact model is installed on the selected native Ollama endpoint.' : 'Source metadata is not available for this model.');
    if (description.length > 360) {
      const preview = domainText('p',description.slice(0,360) + '…'); about.append(preview);
      const more = domainText('details', '', 'model-about-more'); more.id = 'store-detail-more'; more.open = detailsOpen.has(more.id);
      const summary = domainText('summary',''), label = domainText('span',more.open ? 'Show less' : 'Show more'); summary.id = 'store-detail-more-summary'; summary.append(label);
      more.append(decorateDisclosure(summary),domainText('p',description)); preview.hidden = more.open;
      more.addEventListener('toggle', () => { preview.hidden = more.open; label.textContent = more.open ? 'Show less' : 'Show more'; }); about.append(more);
    } else about.append(domainText('p',description));
    const genericAbout = modelTask(item).toLowerCase() === description || ['Community GGUF model. Capabilities and device fit are not verified.', 'Community GGUF. Read its model card and choose an exact file.'].includes(description);
    if (!genericAbout) reading.append(about);
    const variantSection = detailSection('Choose your download','store-variants-heading'); variantSection.id = 'store-variants-section'; variantSection.querySelector('h2').tabIndex = -1;
    const variantCount = domainText('p', loading ? 'Finding available variants…' : `${variants.length} ${variants.length === 1 ? 'variant' : 'variants'} available`, 'model-variant-count muted');
    variantCount.id = 'store-variant-count'; variantSection.append(variantCount);
    if (!imageStore() && connections.length > 1) {
      const label = domainText('label','Download to'), select = document.createElement('select'); select.id = 'store-detail-endpoint';
      select.replaceChildren(...connections.map(c=>new Option(c.name,c.id))); select.value = endpoint; select.disabled = pending;
      select.addEventListener('change', () => changeEndpoint(select.value)); label.append(select); variantSection.append(label);
    } else if (destination) variantSection.append(domainText('p',`Download to ${destination}`,'model-download-destination muted'));
    const fieldset = document.createElement('fieldset'); fieldset.id = 'store-variant-list'; fieldset.className = 'model-variant-list'; fieldset.setAttribute('aria-describedby','store-variant-count');
    const legend = domainText('legend','Exact variant'); legend.className = 'visually-hidden'; fieldset.append(legend);
    variantPage = Math.max(1,Math.min(variantPage,Math.ceil(variants.length / 20) || 1));
    variants.slice((variantPage - 1)*20,variantPage*20).forEach((row,index) => {
      const label = domainText('label','','model-variant-row');
      const input = document.createElement('input'); input.type = 'radio'; input.name = 'store-variant'; input.value = row.tag; input.checked = variant === row.tag; input.disabled = pending;
      input.id = `store-variant-${(variantPage - 1)*20+index}`;
      input.addEventListener('change', () => { if (input.checked) selectVariant(row.tag); });
      const copy = domainText('span','','model-variant-copy'); copy.append(domainText('strong',row.name || row.tag)); label.title = row.tag;
      const actual = inventory?.models?.find(local=>local.name===row.tag);
      const info = [row.quantization, row.parameters].filter(Boolean);
      if (info.length) copy.append(domainText('small',info.join(' · '),'muted'));
      const state = domainText('span', '', 'model-variant-state');
      state.append(domainText('strong', actual?.size != null ? fileSize(actual.size) : row.size != null ? fileSize(row.size) : row.size_label || 'Size unknown'));
      if (actual || input.checked) state.append(domainText('small',actual ? inventory.stale ? 'Cached' : 'Installed' : 'Selected'));
      label.append(input,copy,state); fieldset.append(label);
    });
    variantSection.append(fieldset);
    let variantFooter = null;
    if ((variants.length || loading) && !installed) {
      const choose = domainButton(loading ? 'Loading' : variant ? `Download${downloadSize ? ` · ${downloadSize}` : ''}` : 'Choose model', () => {
        if (!variant) focusVariants(); else review('model-pull', variant);
      }, 'model-detail-install');
      choose.id = 'store-variant-install';
      choose.disabled = loading || (variant ? !canWrite() || !inventory?.models || inventory.stale : false);
      if (variant) choose.prepend(libraryIcon('download'));
      variantFooter = domainText('div', '', 'model-variant-footer');
      variantFooter.append(choose);
    }
    if (!variants.length && !loading) variantSection.append(domainText('p',item?.error || 'No supported single-file variants are available. Open the source to inspect alternatives.','muted'));
    if (variants.length > 20) {
      const nav = domainText('nav','','pagination'); nav.id = 'store-variants-pages'; nav.setAttribute('aria-label','Variant pages');
      for (const [name,delta] of [['previous',-1],['next',1]]) {
        const button = domainButton('', () => { variantPage += delta; renderDetail(); },'quiet'); button.id = `store-variants-${name}`; button.setAttribute('aria-label',`${name} variant page`); button.append(libraryIcon(name));
        if (name === 'next') { const numbers = domainText('span','','page-numbers'); numbers.id = 'store-variants-numbers'; numbers.addEventListener('click',event=>{const button=event.target.closest('button[data-page]');if(button){variantPage=Number(button.dataset.page);renderDetail();}});nav.append(numbers); }
        nav.append(button);
      }
      const status = domainText('span','','visually-hidden'); status.id = 'store-variants-page'; status.setAttribute('role','status'); nav.append(status);variantSection.append(nav);
    }
    if (variantFooter) variantSection.append(variantFooter);
    reading.append(variantSection);
    const details = detailSection('Details','store-model-details');
    const disclosure = (id,title,text) => {
      const node = document.createElement('details'); node.id = id; node.className = 'model-detail-disclosure'; node.open = detailsOpen.has(id);
      const summary = domainText('summary',title); summary.id = `${id}-summary`;
      node.append(decorateDisclosure(summary),domainText('p',text)); return node;
    };
    if (variant) details.append(disclosure('store-exact-variant','Exact model reference',variant));
    if (imageStore()) details.append(disclosure('store-image-compatibility', 'Compatibility and loading', 'Only top-level single-file GGUF and Safetensors weights with published checksums are offered. Diffusers directories and split weights are excluded. Check the model card for architecture support, license and required components. Downloading saves weights on this host; a remote image server needs access to that directory. Load the model using your image server before testing and saving it in Settings.'));
    else details.append(disclosure('store-compatibility','Compatibility and technical information',`${metadata?.parameters || 'Parameter count unknown'}. Context and device fit are not verified. Runtime memory depends on context and concurrency; download size is not a RAM requirement. ${item?.capabilities?.length ? 'Dated catalog declarations: ' + capabilities + '. Activation checks the installed variant again.' : 'Tool use, image input and Thinking are not verified for this exact variant.'}`));
    details.append(disclosure('store-source-license','Source and license',`${item?.checked_at ? 'Source checked ' + new Date(item.checked_at * 1000).toLocaleString() + '. ' : ''}${item?.license ? 'Catalog license: ' + item.license + '. Inspect the source and exact artifact terms.' : 'License is unknown. Inspect the source terms before installation.'} ${detail.startsWith('hf:') ? imageStore() ? 'Only checksum-verified, top-level GGUF and Safetensors weights are offered.' : 'Only top-level single-file GGUF weights are offered. Split weights, projector-only files and subdirectory files are unsupported by this integration.' : catalog?.verified && item ? 'Curated source facts checked ' + catalog.verified + '.' : 'Source metadata is not recorded in the installed inventory.'}`));
    if (installed && !imageStore()) {
      const remove = domainButton('Delete model',()=>review('model-delete',variant),'quiet danger'); remove.disabled = !canWrite() || inventory.stale; details.append(remove);
    }
    if (imageStore() && installed) details.append(domainButton('Image generation settings', () => { showView('settings', {section:'models'}); ModelsSettingsNavigation.show('image', {focus:true}); }, 'quiet'));
    reading.append(details);
    const links = detailSection('Links','store-detail-links');
    if (metadata?.source_url) links.append(link('Exact variant source',metadata.source_url));
    if (!item?.source_url && !metadata?.source_url) links.append(domainText('p','No verified external source is recorded for this installed model.','muted'));
    if (links.querySelector('a, p')) reading.append(links); body.append(reading);
    if (variants.length > 20) updateDomainPager('store-variants',(variantPage-1)*20,{items:variants.slice((variantPage-1)*20,variantPage*20),total:variants.length,page_size:20,more:variantPage*20<variants.length});
    const previousFocus = (focusId ? byId(focusId) : null) || (focusPage ? byId('store-variants-numbers')?.querySelector(`[data-page="${focusPage}"]`) : null);
    previousFocus?.focus({preventScroll:true});
    if (loading && detailReading !== detail) loadLiveDetail(detail);
  }
  const canWrite = () => supported() && runtimeReady() && allowed && endpoint && !pending && !latest?.active_turn_id && !latest?.queue?.length &&
    !jobs.some(job => ['accepted', 'running', 'cancelling', 'unknown'].includes(job.state));
  async function review(operation, model, manual = false) {
    if (!canWrite()) return;
    if (imageStore()) operation = 'model-image-download';
    pending = true; const epoch = authEpoch, selectedEndpoint = endpoint;
    try {
      const opened = await prepareChange({operation, connection: endpoint, model}, {
        downloadDestination: imageStore() ? 'Local Stable Diffusion models' : connections.find(connection => connection.id === endpoint)?.name || endpoint,
        current: () => active() && epoch === authEpoch && selectedEndpoint === endpoint && (manual ? downloadDialog.open : variant === model && !dialog.hidden),
        beforeOpen: () => { detail = ''; dialog.hidden = true; downloadDialog.close(); navigate('downloads'); },
        onAccepted: () => { if (epoch === authEpoch) { pending = false; loadJobs(); } },
        onDiscard: () => { if (epoch === authEpoch) { pending = false; loadJobs(); } },
      });
      if (!opened) pending = false;
    } catch (error) { if (epoch === authEpoch) { pending = false; message(error.message); if (manual) byId('store-download-status').textContent = error.message; } }
    if (epoch === authEpoch) render();
  }
  async function jobAction(path, id) {
    if (pending) return; pending = true;
    const epoch = authEpoch;
    renderDownloadInfo();
    try {
      await domainRequest(path, 'POST', {request_id: id});
      if (path.endsWith('/reconcile')) loadInventory();
    }
    catch (error) { if (epoch === authEpoch) { openDownloadInfo('owned', id); downloadInfoError = error.message; renderDownloadInfo(); } }
    finally { if (epoch === authEpoch) { pending = false; await loadJobs(); } }
  }
  function downloadProgress(content, progress, label, key) {
    let bar = downloadBars.get(key);
    if (!Number.isFinite(progress?.total) || progress.total <= 0 || !Number.isFinite(progress.completed)) {
      removeDownloadBar(key); return;
    }
    const value = progress.completed / progress.total * 100;
    if (bar) { bar.setValue(value); return; }
    bar = MaterialProgress.create({thickness:'thin', value, label});
    bar.element.classList.add('model-download-progress'); bar.element.dataset.thickness = 'thin';
    downloadBars.set(key, bar); content.append(bar.element);
  }
  function downloadName(item) {
    if (item.source === 'ollama') return 'Ollama transfer';
    const model = item.model || 'Model download', tag = model.split(':').at(-1);
    return model.startsWith('hf.co/') && /\.(gguf|safetensors)$/i.test(tag) ? tag : model.split('/').at(-1);
  }
  function downloadState(item) {
    if (item.source === 'ollama') return item.state === 'quiet' ? 'No recent activity' : 'Downloading';
    if (item.source === 'sdcpp') return item.state === 'quiet' ? 'No recent activity' : 'Recent file activity';
    const stage = {'Checking manifest':'Preparing…', 'Preparing download':'Preparing…',
      'Downloading file':'Downloading', 'Verifying download':'Verifying…', 'Saving model':'Installing…', 'Complete':'Finishing…'};
    return {accepted:'Queued', running:item.kind === 'model-delete' ? 'Removing…' : stage[item.progress?.stage] || 'Downloading',
      completed:item.kind === 'model-delete' ? 'Removed' : 'Complete', failed:'Failed', cancelled:'Stopped',
      cancelling:'Stopping…', unknown:'Needs check'}[item.state] || item.state;
  }
  function infoRecord() {
    return downloadInfoSource === 'owned' ? jobs.find(job => job.request_id === downloadInfoKey)
      : observedTransfers.find(item => item.id === downloadInfoKey);
  }
  function openDownloadInfo(source, key) {
    if (!active() || section !== 'downloads' || detail) return;
    downloadInfoKey = key; downloadInfoSource = source; downloadInfoError = '';
    renderDownloadInfo();
    if (infoRecord()) { if (!downloadInfo.open) downloadInfo.showModal(); byId('store-download-info-close').focus(); }
  }
  function renderDownloadInfo() {
    if (!downloadInfoKey) return;
    const item = infoRecord();
    if (!item) { downloadInfo.close(); return; }
    const exactName = byId('store-download-info-name');
    if (exactName.textContent !== item.model) exactName.textContent = item.model;
    const metadata = byId('store-download-info-metadata'); metadata.replaceChildren();
    const rows = [['Status', downloadState(item)], ['Connection', item.connection === 'image:sdcpp' ? 'Local Stable Diffusion models' : connections.find(c => c.id === item.connection)?.name || item.connection]];
    const facts = downloadMetadata(item);
    rows.push(['Parameters', facts.parameters], ['Size', facts.size]);
    if (['running','cancelling'].includes(item.state)) rows.push(['Speed', downloadSpeed(item)]);
    if (item.kind === 'model-delete') rows.push(['Action', 'Remove model']);
    const progress = item.progress;
    if (Number.isFinite(progress?.total) && progress.total > 0 && Number.isFinite(progress.completed))
      rows.push(['Current file', `${fileSize(progress.completed)} / ${fileSize(progress.total)}`]);
    for (const [label, value] of rows) metadata.append(domainText('dt', label), domainText('dd', value));
    let note = downloadInfoError || item.message || '';
    if (downloadInfoSource === 'observed') note = item.source === 'sdcpp'
      ? 'Detected from recent model-file writes in the local Stable Diffusion model directory. Exact progress and final outcome are unavailable. Manage the transfer in the client that started it.'
      : item.source === 'ollama'
      ? 'Detected from local file activity. The model name, exact progress and final outcome are unavailable. Manage the transfer in the client that started it.'
      : 'Started in another Klaude client. Manage the download there.';
    else if (item.state === 'unknown') note = [note, 'The server has not confirmed the result. Check status before starting another model operation.'].filter(Boolean).join(' ');
    const message = byId('store-download-info-note');
    if (message.textContent !== note) message.textContent = note;
    message.hidden = !note;
    const check = byId('store-download-info-check'), remove = byId('store-download-info-remove');
    check.hidden = downloadInfoSource !== 'owned' || item.state !== 'unknown'; check.disabled = pending || !allowed;
    remove.hidden = downloadInfoSource !== 'owned' || item.cancellable || item.dismissed || !latest?.model_download_dismissal || !['completed','failed','cancelled','unknown'].includes(item.state);
    remove.disabled = pending || !allowed;
    downloadInfo.querySelector('.dialog-actions').hidden = check.hidden && remove.hidden;
  }
  function downloadAction(label, glyph, action, key) {
    const button = domainButton('', action, 'quiet icon-button');
    button.setAttribute('aria-label', label); button.title = label; button.dataset.downloadAction = key;
    button.append(libraryIcon(glyph)); return button;
  }
  function renderJobs(target) {
    if (!jobs.length && !observedTransfers.length) {
      clearDownloadBars(); target.replaceChildren();
      emptyState(target, 'No downloads yet', '', 'download');
      target.querySelector('.collection-empty p')?.remove();
      target.append(domainButton('Discover models', () => { byId('store-query').value = ''; navigate('discover', '', '', false, ''); }, 'secondary'));
      renderDownloadInfo();
      return;
    }
    const existing = new Map([...target.querySelectorAll('.store-download-row')].map(row => [row.dataset.downloadId, row]));
    for (const child of [...target.children]) if (!child.classList.contains('store-download-row')) child.remove();
    const retained = new Set();
    let position = 0;
    for (const item of [...observedTransfers, ...jobs]) {
      const observed = !item.request_id;
      if (item.dismissed && item.state !== 'unknown') continue;
      const key = item.request_id || item.id, source = observed ? 'observed' : 'owned', name = downloadName(item);
      const row = existing.get(key) || domainText('article', '', 'store-download-row collection-row library-card'); row.dataset.downloadId = key; retained.add(key);
      if (observed) row.classList.add('model-observed-transfer');
      if (item.dismissed) row.classList.add('model-dismissed-notice');
      row.setAttribute('aria-label', `${name}: ${downloadState(item)}`);
      const mark = domainText('div', '', 'store-download-icon'); mark.append(icon(item.model, 32));
      const content = domainText('div', '', 'store-download-content');
      const title = domainText('strong', name, 'store-download-name'); title.title = item.model;
      const progress = item.progress;
      const bytes = ['running','cancelling'].includes(item.state) && Number.isFinite(progress?.total) && progress.total > 0 && Number.isFinite(progress.completed);
      const status = domainText('span', bytes ? `${fileSize(progress.completed)} / ${fileSize(progress.total)}` : downloadState(item), 'store-download-status');
      status.dataset.state = item.state; status.title = status.textContent;
      const facts = downloadMetadata(item), metadata = domainText('div', '', 'store-download-metadata muted');
      content.append(title, domainText('span', facts.parameters, 'store-download-parameters muted'));
      metadata.append(status);
      if (['running','cancelling'].includes(item.state)) {
        const speed = domainText('span', downloadSpeed(item), 'store-download-speed');
        speed.title = Number.isFinite(item.progress?.completed) ?
          'Estimated from reported file progress; available after two updates' : 'Speed unavailable: byte progress is not reported';
        metadata.append(speed);
      } else metadata.append(domainText('span', facts.size, 'store-download-size'));
      const actions = domainText('div', '', 'store-download-actions');
      if (!observed && item.cancellable && ['model-pull','model-image-download'].includes(item.kind) && ['accepted','running'].includes(item.state))
        actions.append(downloadAction('Stop download', 'close', () => jobAction('/api/v1/models/cancel', key), 'stop'));
      else if (!observed && item.state === 'unknown')
        actions.append(downloadAction('Check download status', 'refresh', () => jobAction('/api/v1/models/reconcile', key), 'check'));
      else if (!observed && !item.cancellable && ['completed','failed','cancelled'].includes(item.state) && latest?.model_download_dismissal)
        actions.append(downloadAction('Remove download', 'close', () => jobAction('/api/v1/models/dismiss', key), 'remove'));
      for (const button of actions.children) button.disabled = pending || !allowed;
      const info = downloadAction('Download details', 'info', () => openDownloadInfo(source, key), 'info');
      info.id = `store-download-info-${source}-${key}`; info.setAttribute('aria-haspopup', 'dialog');
      actions.append(info);
      if (existing.has(key)) {
        row.querySelector('.store-download-icon').replaceWith(mark);
        row.querySelector('.store-download-content').replaceWith(content);
        row.querySelector('.store-download-actions').replaceWith(actions);
        row.querySelector('.store-download-metadata').replaceWith(metadata);
      } else row.append(mark, content, actions, metadata);
      if (['running','cancelling'].includes(item.state)) downloadProgress(row, progress, `Current file progress for ${name}`, key);
      else { removeDownloadBar(key); }
      if (target.children[position] !== row) target.insertBefore(row, target.children[position] || null);
      position++;

    }
    for (const [key, row] of existing) if (!retained.has(key)) { removeDownloadBar(key); row.remove(); }
    renderDownloadInfo();
  }
  function render() {
    if (!active()) return;
    const before = shownDetail || (!dialog.hidden ? '__visible' : ''), focused = document.activeElement, key = focused?.dataset?.storeKey || focused?.dataset?.storeModel;
    const fullPage = Boolean(detail && supported() && runtimeReady());
    if (fullPage || section !== 'downloads') downloadInfo.close();
    if (fullPage) clearDownloadBars();
    byId('store-view').classList.toggle('has-model-detail', fullPage);
    byId('store-view').querySelector(':scope > .view-heading').hidden = fullPage;
    byId('store-sections').hidden = fullPage; byId('store-panel').hidden = fullPage;
    dialog.hidden = !fullPage;
    byId('store-view').setAttribute('aria-labelledby', window.IntegrationStoreUI?.isOpen() ? 'integration-store-title' : fullPage ? 'store-detail-title' : 'store-title');
    if (fullPage) renderDetail(); else renderContent();
    shownDetail = fullPage ? detail : '';
    if (shownDetail && before !== shownDetail) {
      byId('store-view').scrollTop = 0;
      byId('store-detail-title')?.focus({preventScroll:true});
    } else if (!shownDetail && before) {
      detailSignature = '';
      const sameSection = !browseContext?.section || browseContext.section === section;
      const restore = () => {
        byId('store-view').scrollTop = sameSection ? Math.max(0, Number(browseContext?.scroll) || 0) : 0;
        if (sameSection) restoreDetailFocus();
      };
      restore(); requestAnimationFrame(() => { if (active() && !detail) restore(); });
    } else if (key && dialog.hidden && !byId('store-content').contains(focused)) {
      const row = [...byId('store-content').querySelectorAll('[data-store-model]')].find(node => (node.dataset.storeKey || node.dataset.storeModel) === key);
      row?.focus({preventScroll:true});
    }
  }
  function renderStoreCounts() {
    const counts = {
      installed: inventory?.truncated ? undefined : inventory?.models?.length,
      downloads: jobsLoaded ? observedTransfers.length + jobs.filter(job => !job.dismissed || job.state === 'unknown').length : undefined,
    };
    for (const name of ['installed', 'downloads']) {
      const button = byId(`store-tab-${name}`), total = counts[name];
      let badge = button.querySelector('.tab-count');
      if (!Number.isSafeInteger(total)) { badge?.remove(); continue; }
      if (!badge) { badge = domainText('span', '', 'tab-count'); button.prepend(badge); }
      const text = total.toLocaleString();
      if (badge.textContent !== text) badge.textContent = text;
    }
  }
  function renderContent() {
    if (!active()) return;
    const focusedRow = document.activeElement?.closest('.store-download-row');
    const downloadFocus = focusedRow ? {key:focusedRow.dataset.downloadId, action:document.activeElement.dataset.downloadAction} : null;
    if (section !== 'downloads') clearDownloadBars();
    renderStoreCounts();
    for (const button of byId('store-sections').children) {
      const selected = button.dataset.section === section;
      button.setAttribute('aria-pressed', String(selected));
      button.disabled = !supported();
    }
    byId('store-panel').setAttribute('aria-labelledby', `store-tab-${section}`);
    byId('store-search-row').hidden = section === 'downloads' || !supported();
    byId('store-query').placeholder = section === 'installed' ? 'Search installed models…' : hub() ? 'Search community models…' : 'Search offline collection…';
    byId('store-endpoint-label').hidden = imageStore() || !supported() || connections.length < 2 || section === 'discover' || section === 'downloads' && !jobs.length;
    byId('store-download-open').hidden = runtime !== 'ollama';
    byId('store-source').options[0].textContent = runtime === 'all' ? 'Hugging Face models' : imageStore() ? 'Hugging Face image models' : 'Hugging Face GGUF';
    for (const value of ['sdcpp','all']) byId('store-runtime').querySelector(`[value=${value}]`).disabled = !imageStoreReady();
    byId('store-download-open').disabled = !canWrite() || !inventory?.models || inventory.stale;
    byId('store-source').disabled = !latest?.model_store_catalog || section !== 'discover' || collection === 'charts';
    byId('store-sort').disabled = section !== 'discover' || !hub() || collection === 'charts';
    byId('store-capability').disabled = section !== 'discover' || hub();
    byId('store-size').disabled = section !== 'installed';
    byId('store-filter-chips').hidden = section === 'downloads' || !supported();
    for (const id of ['store-runtime','store-source','store-sort','store-capability','store-size']) {
      const select = byId(id), field = select.closest('.file-filter-field, label');
      field.hidden = id === 'store-runtime' ? false : section === 'installed' ? id !== 'store-size' : id === 'store-size' || id === 'store-capability' && hub() || imageStore() && id === 'store-source';
    }
    storeFilterMenus.forEach(menu => menu.sync());
    const target = byId('store-content'); if (section !== 'downloads' || !supported()) target.replaceChildren(); target.classList.remove('is-empty');
    target.setAttribute('aria-busy', 'false');
    byId('store-installed-pages').hidden = section !== 'installed' || !supported();
    if (!supported() || !runtimeReady()) {
      allowed = false; dialog.hidden = true; downloadDialog.close(); closeStoreFilters(); message(restartMessage);
      emptyState(target, 'Model Store needs the updated host', 'Restart the host and reload this page.', 'models'); settingsLink(target); return;
    }
    if (section === 'downloads') {
      renderJobs(target); renderDetail();
      if (downloadFocus && !downloadInfo.open) {
        const row = [...target.querySelectorAll('.store-download-row')].find(row => row.dataset.downloadId === downloadFocus.key);
        (row?.querySelector(`[data-download-action="${downloadFocus.action}"]`) || row?.querySelector('[data-download-action=info]') || byId('store-tab-downloads')).focus({preventScroll:true});
      }
      return;
    }
    if (section === 'installed') {
      if (inventory?.checked_at) target.append(domainText('p', `${inventory.stale ? 'Cached · ' : ''}Checked ${new Date(inventory.checked_at * 1000).toLocaleString()}`, 'store-source-note muted'));
      if (inventory?.truncated) target.append(domainText('p', 'Showing available models from the bounded inventory.', 'store-source-note muted'));
      const query = byId('store-query').value.trim().toLocaleLowerCase(), sizeLimit = byId('store-size').value;
      const rows = (inventory?.models || []).filter(row => row.name.toLocaleLowerCase().includes(query) && (sizeLimit === 'all' || Number.isFinite(row.size) && row.size <= Number(sizeLimit) * 1e9));
      if (!rows.length) {
        emptyState(target, inventory?.models ? query || sizeLimit !== 'all' ? 'No matching models' : 'No installed models' : 'Installed models unavailable', inventory?.models ? 'Discover a model or adjust your search and filters.' : imageStore() ? 'Configure the host image-model directory, then refresh.' : 'Check an enabled native Ollama connection in Model settings, then refresh.', 'models');
        if (!endpoint || !inventory?.models) settingsLink(target);
      }
      installedPage = Math.max(1, Math.min(installedPage, Math.ceil(rows.length / 20)));
      const list = domainText('div', '', 'store-installed-list');
      for (const row of rows.slice((installedPage - 1) * 20, installedPage * 20)) {
        const card = domainText('div', '', 'collection-row library-card');
        const button = domainButton('', () => { variant = ''; openDetail(row.name, button, row.runtime || runtime); }, 'store-row collection-open quiet'); button.dataset.storeModel = row.name; button.dataset.storeKey = modelKey(row);
        button.title = row.name;
        const copy = domainText('span', '', 'store-card-content');
        copy.append(domainText('strong', row.display_name || row.name), domainText('small', `${row.parameters || 'Parameters unknown'} · ${row.size != null ? fileSize(row.size) : 'Size unknown'}`, 'muted'));
        if (runtime === 'all') copy.append(runtimeBadge(row.runtime));
        button.append(icon(row.name, 40), copy, domainText('span', 'Manage', 'store-cta'));
        card.append(button); list.append(card);
      }
      if (rows.length) target.append(list);
      updateDomainPager('store-installed', (installedPage - 1) * 20, {items:rows.slice((installedPage - 1) * 20, installedPage * 20), total:rows.length, page_size:20, more:installedPage * 20 < rows.length});
      byId('store-installed-pages').hidden = rows.length <= 20;
      renderDetail(); return;
    }
    const landing = liveLanding();
    if (latest?.model_store_catalog && (landing && !popularCatalog && !recentCatalog ||
        !landing && hub() && liveLoading && !liveCatalog?.models?.length)) {
      byId('store-live-pages').hidden = true; catalogLoading(target); return;
    }
    if (landing) {
      byId('store-live-pages').hidden = true;
      const popular = completeLandingRows(landingRows('downloads'));
      target.append(sectionHeading('Popular models', 'See all', () => navigate('discover', '', '', false, 'charts')));
      target.append(domainText('p', 'By Hugging Face downloads' + (popularCatalog?.stale ? ' · Cached' : ''), 'store-source-note muted'));
      if (runtime === 'all' && popularCatalog?.error) target.append(domainText('p', popularCatalog.error, 'domain-status'));
      if (popular.length) target.append(modelGrid(popular, true));
      else target.append(domainText('p', popularCatalog?.error ? 'Catalog unavailable. Try Refresh.' : latest?.model_store_catalog ? 'Loading models…' : 'Update the host to explore more models.', 'muted'));
      const recent = completeLandingRows(landingRows('lastModified'));
      if (recent.length) {
        target.append(sectionHeading('Recently updated', 'See all', () => {
          byId('store-source').value = 'huggingface'; byId('store-sort').value = 'lastModified';
          navigate('discover', '', '', false, '');
        }), modelGrid(recent));
        if (recentCatalog.stale) target.append(domainText('p', 'Cached collection', 'store-source-note muted'));
      }
      window.IntegrationStoreUI?.preview(target);
      if (!popular.length && popularCatalog?.error) {
        target.append(sectionHeading('Available offline'), modelGrid(catalog?.models || []));
      }

    } else {
      const back = sectionHeading(category || (!hub() ? 'Offline collection' : collection === 'charts' ? runtime === 'all' ? 'Top models' : imageStore() ? 'Top image models' : 'Top GGUF models' : hub() && byId('store-sort').value === 'lastModified' ? 'Recently updated' : 'Search results'), 'Discover', () => {
        byId('store-query').value = ''; byId('store-source').value = 'huggingface'; byId('store-sort').value = 'downloads'; byId('store-capability').value = 'all'; navigate('discover', '', '', false, '');
      }); target.append(back);
      if (hub()) {
        target.append(domainText('p', runtime === 'all' ? 'Hugging Face models for Ollama and Stable Diffusion.' : imageStore() ? 'Hugging Face image models · check source compatibility and required components.' : 'Hugging Face public catalog · repository downloads, not Ollama usage. Capabilities and device fit are not verified.', 'store-source-note muted'));
        if (liveCatalog?.checked_at) target.append(domainText('p', `${liveCatalog.stale ? 'Cached' : 'Checked'} ${new Date(liveCatalog.checked_at * 1000).toLocaleString()} · ${livePageSize} results per page`, 'store-source-note muted'));
        if (liveCatalog?.error) target.append(domainText('p', liveCatalog.error, 'domain-status'));
        const rows = liveCatalog?.models || [];
        target.append(modelGrid(rows, collection === 'charts'));
        renderLivePager(liveCatalog);
        if (!liveLoading && !rows.length && !liveCatalog?.error) target.append(domainText('p', 'No matching community models. Offline collection and Installed remain available.', 'muted'));
      } else {
        const matches = filtered(); matches.forEach(item => target.append(modelRow(item)));
        if (!matches.length) emptyState(target, 'No matching curated models', 'Try another use case or choose the Hugging Face catalog in Filters.', 'models');
      }
    }
    renderDetail();
  }
  function landingGeometry(targetCount = 20) {
    const target = byId('store-content'), style = getComputedStyle(target);
    const minimum = parseFloat(style.getPropertyValue('--store-grid-min')) || 290;
    const gap = parseFloat(style.getPropertyValue('--store-grid-gap')) || 8;
    const columns = Math.max(1, Math.floor((target.getBoundingClientRect().width + gap) / (minimum + gap)));
    return {columns, capacity:columns * Math.max(1, Math.round(targetCount / columns))};
  }
  function completeLandingRows(rows) {
    const {columns, capacity} = landingGeometry(), count = Math.min(capacity, rows.length);
    return rows.slice(0, count >= columns ? Math.floor(count / columns) * columns : count);
  }
  function landingRows(sort) {
    const seen = new Set();
    const unique = rows => rows.filter(item => item?.id && !seen.has(modelKey(item)) && seen.add(modelKey(item)));
    const popular = unique((popularCatalog?.models || []).filter(item => Number.isInteger(item.downloads)));
    if (sort === 'downloads') return popular;
    const excluded = new Set(completeLandingRows(popular).map(modelKey));
    seen.clear();
    return unique((recentCatalog?.models || []).filter(item => !excluded.has(modelKey(item))));
  }
  async function readCatalog(url, options = {}) {
    if (runtime !== 'all') return domainRequest(url, 'GET', undefined, options);
    const epoch = authEpoch, source = new URL(url, location.origin);
    const page = Number(source.searchParams.get('page') || 1), limit = Number(source.searchParams.get('limit') || 20);
    const results = await Promise.allSettled(['ollama','sdcpp'].map(async (targetRuntime, index) => {
      const query = new URL(source), count = index ? Math.floor(limit / 2) : Math.ceil(limit / 2);
      if (!count) return {models:[], more:false};
      query.searchParams.set('runtime', targetRuntime); query.searchParams.set('limit', count);
      const identity = new URLSearchParams(query.searchParams); identity.delete('page'); identity.delete('refresh'); identity.sort();
      const key = identity.toString();
      const remembered = allPageEnds.get(key) ?? history.state?.klaudeStoreAllEnds?.[key];
      if (page === 1 && query.searchParams.get('refresh') === '1') allPageEnds.delete(key);
      else if (Number.isInteger(remembered) && page > remembered) return {models:[], more:false};
      const data = await domainRequest(query.pathname + query.search, 'GET', undefined, options);
      if (!options.signal?.aborted && epoch === authEpoch && active() && runtime === 'all' && !data.error) {
        if (!data.more) allPageEnds.set(key, page); else if (page === 1) allPageEnds.delete(key);
        while (allPageEnds.size > 64) allPageEnds.delete(allPageEnds.keys().next().value);
        history.replaceState({...history.state, klaudeStoreAllEnds:Object.fromEntries(allPageEnds)}, '', location.href);
      }
      return {...data, models:(data.models || []).map(item => ({...item, runtime:targetRuntime}))};
    }));
    if (options.signal?.aborted) throw new DOMException('Cancelled', 'AbortError');
    const available = results.filter(result => result.status === 'fulfilled').map(result => result.value);
    const errors = results.flatMap((result,index) => result.status === 'rejected' || result.value.error ?
      [index ? 'Stable Diffusion catalog unavailable.' : 'Ollama catalog unavailable.'] : []);
    const models = available.flatMap(result => result.models || []);
    models.sort((a,b) => source.searchParams.get('sort') === 'lastModified' ?
      (Date.parse(b.modified) || 0) - (Date.parse(a.modified) || 0) : (b.downloads ?? -1) - (a.downloads ?? -1));
    const checked = available.map(result => result.checked_at).filter(Number.isFinite);
    return {models, more:available.some(result => result.more), page, page_size:limit,
      checked_at:checked.length ? Math.min(...checked) : undefined,
      stale:errors.length > 0 || available.some(result => result.stale), error:errors.join(' ')};
  }
  async function loadPopular(force = false, fillOnly = false) {
    if (!active() || !runtimeReady() || !latest?.model_store_catalog || popularReading) return;
    const id = ++popularSerial, epoch = authEpoch, request = new AbortController(); popularReading = request;
    const valid = () => active() && epoch === authEpoch && id === popularSerial;
    const legacy = {downloads:popularCatalog?._legacy || false, lastModified:recentCatalog?._legacy || false};
    const get = sort => sort === 'downloads' ? popularCatalog : recentCatalog;
    const set = (sort, result) => { if (sort === 'downloads') popularCatalog = result; else recentCatalog = result; };
    async function readPage(sort, page, refresh) {
      const url = `/api/v1/models/store?source=huggingface&sort=${sort}&page=${page}&refresh=${refresh ? '1' : '0'}${runtimeQuery()}`;
      let data;
      try { data = await readCatalog(url + (legacy[sort] ? '' : '&limit=21'), {signal:request.signal}); }
      catch (error) {
        if (legacy[sort] || error.status !== 400 || !/Unknown Model Store filter/i.test(error.message)) throw error;
        legacy[sort] = true;
        data = await readCatalog(url, {signal:request.signal});
      }
      return {...data, _page:page, _legacy:legacy[sort], _refresh:refresh};
    }
    try {
      if (!fillOnly) await Promise.allSettled(['downloads', 'lastModified'].map(async sort => {
        try {
          if (!get(sort) && force) {
            const cached = await readPage(sort, 1, false);
            if (!valid()) return;
            set(sort, cached); render();
          }
          const result = await readPage(sort, 1, force);
          if (!valid()) return;
          set(sort, result);
        } catch (error) {
          if (error.name === 'AbortError' || !valid()) return;
          set(sort, {...get(sort), error:error.message, stale:true, _fillFailed:true});
        }
        render();
      }));
      // Popular is filled first so Recent can replace every displayed duplicate.
      for (const sort of ['downloads', 'lastModified']) {
        while (valid() && section === 'discover' && liveLanding() && !detail) {
          const previous = get(sort);
          if (!previous?.more || previous.error || previous._fillFailed || (previous._page || 1) >= 4 ||
              landingRows(sort).length >= landingGeometry().capacity) break;
          try {
            const next = await readPage(sort, (previous._page || 1) + 1, Boolean(previous._refresh));
            if (!valid()) return;
            set(sort, {...next, models:[...(previous.models || []), ...(next.models || [])],
              _fillFailed:Boolean(next.error)});
          } catch (error) {
            if (error.name === 'AbortError' || !valid()) return;
            set(sort, {...previous, error:error.message, stale:true, _fillFailed:true});
          }
          render();
        }
      }
    } finally { if (popularReading === request) popularReading = null; }
  }
  let landingGeometryKey = '', landingResizeFrame = 0;
  const landingObserver = new ResizeObserver(() => {
    if (!active() || section !== 'discover' || !hub() || detail) return;
    const geometry = landingGeometry(), key = `${geometry.columns}:${geometry.capacity}`;
    if (key === landingGeometryKey) return;
    landingGeometryKey = key; cancelAnimationFrame(landingResizeFrame);
    landingResizeFrame = requestAnimationFrame(() => {
      if (!active() || section !== 'discover' || !hub() || detail) return;
      if (liveLanding()) { render(); loadPopular(false, true); }
      else if (landingGeometry(40).capacity !== livePageSize) loadLive();
    });
  });
  landingObserver.observe(byId('store-content'));
  window.addEventListener('pagehide', () => { landingObserver.disconnect(); cancelAnimationFrame(landingResizeFrame); });
  window.addEventListener('pageshow', () => { landingGeometryKey = ''; landingObserver.observe(byId('store-content')); });

  function renderLivePager(data) {
    const rows = data?.models || [];
    const pager = byId('store-live-pages');
    pager.setAttribute('aria-label', byId('store-query').value.trim() ? 'Model search result pages' : byId('store-sort').value === 'lastModified' ? 'Recently updated model pages' : 'Top GGUF model pages');
    if (!data || !rows.length) { pager.hidden = true; return; }
    pager.hidden = false;
    const known = (livePage - 1) * livePageSize + rows.length + Number(Boolean(data.more));
    updateDomainPager('store-live', (livePage - 1) * livePageSize, {
      items: rows, total: known, page_size: livePageSize, more: Boolean(data.more),
    });
    byId('store-live-page').textContent = `Page ${livePage}`;
  }
  function moveLivePage(next) {
    if (next < 1 || next > 500 || next === livePage) return;
    livePage = next; liveCatalog = null;
    const url = new URL(location.href);
    if (livePage > 1) {
      url.searchParams.set('models-page', String(livePage));
      url.searchParams.set('models-page-size', String(livePageSize));
    } else { url.searchParams.delete('models-page'); url.searchParams.delete('models-page-size'); }
    history.pushState(history.state, '', url.pathname + url.search + url.hash);
    loadLive();
  }
  byId('store-live-previous').append(libraryIcon('previous'));
  byId('store-live-next').append(libraryIcon('next'));
  byId('store-live-numbers').addEventListener('click', event => {
    const button = event.target.closest('button[data-page]');
    if (button) moveLivePage(Number(button.dataset.page));
  });
  byId('store-live-previous').addEventListener('click', () => moveLivePage(livePage - 1));
  byId('store-live-next').addEventListener('click', () => moveLivePage(livePage + 1));
  async function loadLive(force = false) {
    if (!active() || !runtimeReady() || !latest?.model_store_catalog || section !== 'discover' || !hub()) return;
    const capacity = Math.min(50, landingGeometry(40).capacity);
    if (capacity !== livePageSize) {
      // Each size has its own provider cursor chain. Start that chain explicitly
      // rather than skipping models or reusing a cursor from another page size.
      livePageSize = capacity; livePage = 1; liveCatalog = null;
      const url = new URL(location.href);
      url.searchParams.delete('models-page'); url.searchParams.delete('models-page-size');
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    }
    const current = ++liveSerial, epoch = authEpoch;
    liveReading?.abort(); liveReading = new AbortController(); liveLoading = true; render();
    const parameters = new URLSearchParams({source: 'huggingface', query: byId('store-query').value.trim(), sort: collection === 'charts' ? 'downloads' : byId('store-sort').value, page: livePage, limit: livePageSize, refresh: force ? '1' : '0'});
    if (imageStore()) parameters.set('runtime', 'sdcpp');
    try {
      const result = await readCatalog(`/api/v1/models/store?${parameters}`, {signal: liveReading.signal});
      if (!active() || current !== liveSerial || epoch !== authEpoch) return;
      liveCatalog = result;
    } catch (error) { if (active() && current === liveSerial && epoch === authEpoch && error.name !== 'AbortError') liveCatalog = {...liveCatalog, error: error.message, stale: true}; }
    finally { if (current === liveSerial && epoch === authEpoch) { liveLoading = false; render(); } }
  }
  async function loadLiveDetail(id) {
    if (!runtimeReady()) return;
    const epoch = authEpoch, selectedRuntime = runtime; detailReading = id;
    try {
      const result = await domainRequest(`/api/v1/models/store/detail?id=${encodeURIComponent(id)}${runtimeQuery()}`);
      if (!active() || epoch !== authEpoch || selectedRuntime !== runtime || detail !== id) return;
      const base = liveCatalog?.models?.find(item => item.id === id) || popularCatalog?.models?.find(item => item.id === id) || recentCatalog?.models?.find(item => item.id === id) || {id, name: id.slice(3), source_url: 'https://huggingface.co/' + id.slice(3)};
      liveDetails.set(id, {...base, ...result, task:result.task || base.task || '', summary:result.summary === 'Community GGUF model. Capabilities and device fit are not verified.' ? base.summary || result.summary : result.summary || base.summary, variants: result.variants || [], detailLoaded: true});
      while (liveDetails.size > 20) liveDetails.delete(liveDetails.keys().next().value);
      renderDetail();
    } catch (error) { if (active() && epoch === authEpoch && selectedRuntime === runtime && detail === id) { liveDetails.set(id, {id, name:id.slice(3), publisher:id.slice(3).split('/')[0], summary:'Community GGUF model.', source_url:'https://huggingface.co/' + id.slice(3), capabilities:[], variants:[], detailLoaded:true, error:error.message}); detailSignature = ''; renderDetail(); } }
    finally { if (selectedRuntime === runtime && detailReading === id) detailReading = ''; }
  }
  async function loadInventory() {
    if ((!endpoint && runtime !== 'all') || !runtimeReady()) { inventory = null; render(); return; }
    const selected = endpoint, selectedRuntime = runtime, epoch = authEpoch, read = ++inventoryRead;
    try {
      let result;
      if (runtime === 'all') {
        const targets = [...(selected ? [{runtime:'ollama', connection:selected}] : []), {runtime:'sdcpp', connection:'image:sdcpp'}];
        const reads = await Promise.allSettled(targets.map(async target => {
          const data = await domainRequest(`/api/v1/models/installed?connection=${encodeURIComponent(target.connection)}`);
          if (!Array.isArray(data.models)) throw Error('Inventory unavailable');
          return {...data, models:data.models.map(row => ({...row, runtime:target.runtime}))};
        }));
        const available = reads.filter(row => row.status === 'fulfilled').map(row => row.value);
        if (!available.length) throw Error('Installed models unavailable for both runtimes.');
        const partial = reads.some(row => row.status === 'rejected') || !selected;
        result = {models:available.flatMap(row => row.models), stale:available.some(row => row.stale),
          checked_at:Math.min(...available.map(row => row.checked_at)),
          truncated:partial || available.some(row => row.truncated),
          error:partial ? 'Some installed models are unavailable. Refresh or check each runtime.' : ''};
      } else result = await domainRequest(`/api/v1/models/installed?connection=${encodeURIComponent(selected)}`);
      if (!active() || selected !== endpoint || selectedRuntime !== runtime || epoch !== authEpoch || read !== inventoryRead) return;
      if (result.models === null) throw Error(result.error || 'Installed models unavailable');
      inventory = result; message(result.error || (result.stale ? 'Showing cached installed models; refresh when the server is available.' : ''));
    } catch (error) {
      if (!active() || selected !== endpoint || selectedRuntime !== runtime || epoch !== authEpoch || read !== inventoryRead) return;
      if (inventory) inventory = {...inventory, stale: true};
      message(imageStore() ? 'Local Stable Diffusion inventory unavailable. Check the host model directory, then refresh.' : `${error.message} Offline discovery remains available.`);
    }
    render();
  }
  async function loadJobs() {
    if (!active() || !supported() || busyRead) return;
    busyRead = true; const epoch = authEpoch;
    try {
      const result = await domainRequest('/api/v1/models/downloads');
      if (!active() || epoch !== authEpoch) return;
      sampleDownloadRates([...result.items, ...(result.observed || [])]);
      const completed = jobs.some(old => ['running','accepted','unknown'].includes(old.state) && result.items.some(j => j.request_id === old.request_id && j.state === 'completed'));
      jobs = result.items; observedTransfers = result.observed || []; jobsLoaded = true; allowed = result.management_allowed; renderStoreCounts();
      if (completed) loadInventory();
      if (section === 'downloads') render(); else if (detail) renderDetail();
    } catch (error) { if (active() && epoch === authEpoch) message(error.message); }
    finally { busyRead = false; }
  }
  async function load() {
    if (!supported() || !runtimeReady()) { render(); return; }
    const id = ++serial, epoch = authEpoch; reading?.abort(); reading = new AbortController();
    const current = () => active() && serial === id && epoch === authEpoch;
    const results = await Promise.allSettled([
      domainRequest('/api/v1/models/store', 'GET', undefined, {signal: reading.signal}),
      domainRequest('/api/v1/models/connections', 'GET', undefined, {signal: reading.signal})]);
    if (!current()) return;
    if (results[0].status === 'fulfilled') { catalog = results[0].value; allowed = catalog.management_allowed; if (imageStore()) catalog = {...catalog, models:[]}; else if (runtime === 'all') catalog = {...catalog, models:catalog.models.map(item => ({...item, runtime:'ollama'}))}; }
    else message('Curated catalog unavailable. Installed models can still be refreshed.');
    if (imageStore()) { endpoint = 'image:sdcpp'; inventory = null; }
    else if (results[1].status === 'fulfilled') {
      connections = results[1].value.connections.filter(c => c.backend === 'ollama' && c.source === 'Local' && c.enabled);
      if (!connections.some(c => c.id === endpoint)) { endpoint = connections[0]?.id || ''; inventory = null; }
      const select = byId('store-endpoint'); select.replaceChildren(...connections.map(c => new Option(c.name, c.id)));
      if (!connections.length) select.append(new Option('No native Ollama endpoint configured', ''));
      select.value = endpoint;
    }
    render(); await Promise.allSettled([loadInventory(), loadJobs(), ...(section === 'discover' && hub() && !liveLanding() ? [loadLive(true)] : []), ...(section === 'discover' && liveLanding() ? [loadPopular(true)] : [])]);
  }
  for (const id of ['store-download-info-close', 'store-download-close']) byId(id).append(libraryIcon('close'));
  byId('store-download-info-close').addEventListener('click', () => downloadInfo.close());
  byId('store-download-info-check').addEventListener('click', () => jobAction('/api/v1/models/reconcile', downloadInfoKey));
  byId('store-download-info-remove').addEventListener('click', () => jobAction('/api/v1/models/dismiss', downloadInfoKey));
  downloadInfo.addEventListener('close', () => {
    const origin = byId(`store-download-info-${downloadInfoSource}-${downloadInfoKey}`);
    downloadInfoKey = downloadInfoSource = downloadInfoError = '';
    byId('store-download-info-name').textContent = ''; byId('store-download-info-metadata').replaceChildren();
    byId('store-download-info-note').textContent = '';
    if (active() && section === 'downloads' && !detail) (origin || byId('store-tab-downloads')).focus({preventScroll:true});
  });
  downloadInfo.addEventListener('click', event => {
    if (event.target !== downloadInfo) return;
    const rect = downloadInfo.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) downloadInfo.close();
  });
  sections.forEach((name, i) => { const b = domainButton(labels[i], () => navigate(name, '', '', false, ''), ''); b.replaceChildren(domainText('span', labels[i])); b.dataset.section = name; b.id = `store-tab-${name}`; b.setAttribute('aria-pressed', String(name === section)); b.setAttribute('aria-controls','store-panel'); byId('store-sections').append(b); });
  compactDomainPages.addEventListener('change', () => {
    const numbers = byId('store-installed-numbers');
    if (active() && section === 'installed' && numbers.dataset.current)
      renderDomainPageNumbers('store-installed', Number(numbers.dataset.current), Number(numbers.dataset.last));
  });
  byId('store-installed-previous').append(libraryIcon('previous'));
  byId('store-installed-next').append(libraryIcon('next'));
  byId('store-installed-previous').addEventListener('click', () => {
    installedPage = Math.max(1, installedPage - 1); render();
  });
  byId('store-installed-next').addEventListener('click', () => { installedPage++; render(); });
  byId('store-installed-numbers').addEventListener('click', event => {
    const button = event.target.closest('button[data-page]');
    if (button) { installedPage = Number(button.dataset.page); render(); }
  });
  byId('store-query').addEventListener('input', () => {
    installedPage = 1; livePage = 1; clearTimeout(searchTimer);
    if (section === 'discover' && hub()) {
      liveReading?.abort(); liveSerial += 1; liveCatalog = null;
      liveLoading = Boolean(byId('store-query').value.trim()); render();
      searchTimer = setTimeout(() => navigate(section, category, '', true), 350);
    } else navigate(section, category, '', true);
  });
  function resetRuntime(value) {
    runtime = value; endpoint = value === 'sdcpp' ? 'image:sdcpp' : connections[0]?.id || ''; inventory = catalog = null; inventoryRead++; serial++; reading?.abort();
    liveSerial++; liveReading?.abort(); liveCatalog = null; liveLoading = false; livePage = 1; livePageSize = 40;
    popularSerial++; popularReading?.abort(); popularReading = null; popularCatalog = recentCatalog = null;
    liveDetails.clear(); detailReading = detailSignature = detail = variant = ''; installedPage = 1;
    category = collection = ''; browseContext = null; message('');
  }
  byId('store-runtime').addEventListener('change', () => {
    resetRuntime(byId('store-runtime').value); byId('store-query').value = '';
    byId('store-source').value = 'huggingface'; byId('store-sort').value = 'downloads';
    byId('store-capability').value = byId('store-size').value = 'all';
    closeStoreFilters(); navigate(section, '', '', false, ''); load();
  });
  function changeEndpoint(value) { endpoint = value; byId('store-endpoint').value = value; byId('store-download-destination').textContent = connections.find(c => c.id === endpoint)?.name || ''; installedPage = 1; inventory = null; loadInventory(); }
  byId('store-endpoint').addEventListener('change', () => changeEndpoint(byId('store-endpoint').value));
  byId('store-download-open').append(libraryIcon('plus'));
  byId('store-download-open').addEventListener('click', () => { if (!byId('store-download-open').disabled) { closeStoreFilters(); byId('store-download-status').textContent = ''; byId('store-download-destination').textContent = connections.find(c => c.id === endpoint)?.name || ''; const picker = byId('store-download-endpoint'); picker.replaceChildren(...connections.map(c => new Option(c.name,c.id))); picker.value = endpoint; byId('store-download-endpoint-label').hidden = connections.length < 2; downloadDialog.showModal(); byId('store-download-tag').focus(); } });
  byId('store-download-endpoint').addEventListener('change', () => changeEndpoint(byId('store-download-endpoint').value));
  byId('store-download-close').addEventListener('click', () => downloadDialog.close());
  downloadDialog.addEventListener('close', () => byId('store-download-open').focus());
  byId('store-download-form').addEventListener('submit', event => { event.preventDefault(); review('model-pull', byId('store-download-tag').value.trim(), true); });
  byId('store-source').addEventListener('change', () => { category = ''; livePage = 1; liveCatalog = null; navigate(section, '', '', true, ''); });
  byId('store-sort').addEventListener('change', () => { livePage = 1; liveCatalog = null; navigate(section, category, '', true); });
  byId('store-size').addEventListener('change', () => { installedPage = 1; navigate(section, category, '', true); });
  byId('store-capability').addEventListener('change', () => navigate(section, category, '', true));
  byId('store-refresh').addEventListener('click', () => { load(); window.IntegrationStoreUI?.refresh(); });
  byId('store-home').addEventListener('click', event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault(); clearTimeout(searchTimer); closeStoreFilters();
    byId('store-query').value = '';
    byId('store-source').value = 'huggingface'; byId('store-sort').value = 'downloads';
    byId('store-capability').value = byId('store-size').value = 'all';
    livePage = 1;
    navigate('discover', '', '', false, '');
    byId('store-view').scrollTop = 0;
  });
  byId('store-detail-back').prepend(libraryIcon('previous'));
  byId('store-detail-back').addEventListener('click', () => {
    if (browseContext?.url && history.length > 1) history.back();
    else navigate(section, category, '', true);
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || event.defaultPrevented || !active() || !detail ||
        byId('store-detail').hidden || document.querySelector('dialog[open], :popover-open')) return;
    event.preventDefault();
    byId('store-detail-back').click();
  });
  document.addEventListener('klaude-view', () => {
    clearInterval(timer); timer = null;
    if (active()) { if (urlState() === false) return; render(); load(); if (supported()) timer = setInterval(loadJobs, 2000); }
    else { clearDownloadBars(); downloadRates.clear(); serial++; reading?.abort(); liveReading?.abort(); clearTimeout(searchTimer); popularSerial++; popularReading?.abort(); popularReading = null; dialog.hidden = true; downloadDialog.close(); closeStoreFilters(); downloadInfo.close(); }
  });
  document.addEventListener('klaude-snapshot', () => {
    const capability = supported();
    if (observedCapability === capability) { if (active() && detail) renderDetail(); return; }
    observedCapability = capability;
    if (!active()) return;
    clearInterval(timer); timer = null;
    render(); load();
    if (capability) timer = setInterval(loadJobs, 2000);
  });
  window.addEventListener('popstate', () => { if (active() && urlState() !== false) { loadInventory(); render(); if (liveLanding()) loadPopular(); else if (hub()) loadLive(); } });
  document.addEventListener('klaude-auth-reset', () => {
    downloadInfo.close(); downloadInfoKey = downloadInfoSource = downloadInfoError = '';
    clearDownloadBars(); downloadRates.clear(); allPageEnds.clear();
    const historyState = {...history.state}; delete historyState.klaudeStoreAllEnds; history.replaceState(historyState, '', location.href);
    shownDetail = detailSignature = variantPageSelection = ''; browseContext = null; detailsOpen.clear();
    clearInterval(timer); clearTimeout(searchTimer); popularSerial++; popularReading?.abort(); popularReading = null; popularCatalog = recentCatalog = null; closeStoreFilters(); byId('store-live-pages').hidden = true; livePage = 1; liveSerial++; liveReading?.abort(); liveDetails.clear(); liveCatalog = null; serial++; reading?.abort(); dialog.hidden = true; downloadDialog.close(); byId('store-download-tag').value = ''; catalog = inventory = null; jobs = []; connections = [];
    observedTransfers = []; jobsLoaded = false; renderStoreCounts();
    byId('store-installed-pages').hidden = true;
    byId('store-installed-numbers').replaceChildren(); byId('store-installed-page').textContent = ''; installedPage = 1;
    runtime = 'ollama'; byId('store-runtime').value = runtime;
    endpoint = detail = variant = collection = category = ''; observedCapability = undefined; pending = false; allowed = false; byId('store-query').value = ''; byId('store-content').replaceChildren(); byId('store-detail-body').replaceChildren(); message('');
  });
  function restoreFromLocation() {
    if (!active() || urlState() === false) return;
    render();
    if (detail && supported() && runtimeReady() && detail.startsWith('hf:') &&
        !liveDetails.has(detail) && detailReading !== detail) loadLiveDetail(detail);
  }
  return {render, restoreFromLocation};
})();

window.RoleModelPicker = (() => {
  const dialog = byId('role-model-picker');
  let target = '', role = '', entries = [], pending = null, serial = 0, page = 1, epoch, imageEndpoint = '';
  let imageProvider='',nativeData=null,nativeRecipe='',nativeModels={},nativeReceipt=null,nativeExpected=null,nativeBusy=false,nativePoll=null;
  const nativePanel=domainText('section','','image-model-setup');nativePanel.hidden=true;
  byId('role-picker-items').after(nativePanel);
  const nativeMode=()=>role==='image-generation'&&imageProvider==='sdcpp';
  const nativeCurrent=()=>valid()&&nativeMode()&&byId('image-service-provider').value==='sdcpp'&&byId('image-service-url').value.trim()===imageEndpoint;
  const valid = () => dialog.open && authenticated && epoch === authEpoch && currentView === 'settings' && settingsSection === 'models';
  function close() { dialog.close(); }
  function select(reference, label) {
    if (!valid()) return;
    const field = byId(target);
    if (!field) return close();
    if (role === 'image-generation') {
      const match = /^ollama(?:@[^/]+)?\/(.+)$/.exec(reference);
      if (!match || byId('image-service-url').value.trim() !== imageEndpoint || byId('image-service-provider').value !== 'ollama') return close();
      field.value = match[1]; field.dispatchEvent(new Event('input', {bubbles:true}));
    } else {
      if (![...field.options].some(option => option.value === reference)) field.add(new Option(label, reference));
      field.value = reference; field.dispatchEvent(new Event('change'));
    }
    close();
  }
  function render() {
    if (!valid()) return;
    nativePanel.hidden=!nativeMode();
    byId('role-picker-connection').closest('label').hidden=nativeMode();
    byId('role-picker-refresh').parentElement.classList.toggle('image-picker-toolbar',nativeMode());
    if(nativeMode())return renderNative();
    const query = byId('role-picker-query').value.trim().toLocaleLowerCase();
    const matches = entries.filter(entry => `${entry.name} ${entry.id}`.toLocaleLowerCase().includes(query));
    page = Math.max(1, Math.min(page, Math.ceil(matches.length / 20)));
    const rows = matches.slice((page - 1) * 20, page * 20);
    byId('role-picker-items').replaceChildren(...rows.map(entry => {
      const row = domainButton('', () => select(entry.id, entry.name), 'store-row quiet');
      const icon = domainText('span', '', 'model-brand-icon'); setModelBrandIcon(icon, entry.id, '', {size: 32});
      const content = domainText('span', '', 'store-card-content');
      content.append(domainText('strong', entry.name), domainText('small', entry.id, 'muted'),
        domainText('small', role === 'image-generation' ? (entry.roles?.[role] === true ? 'Supports image generation' : entry.roles?.[role] === false ? 'Image generation not declared' : 'Image generation capability not verified') : entry.roles[role] === null ? 'Role capability not verified' : 'Compatible with this role', 'muted'));
      row.append(icon, content); row.setAttribute('aria-pressed', String(role === 'image-generation' ? byId(target)?.value === entry.id.replace(/^ollama(?:@[^/]+)?\//, '') : byId(target)?.value === entry.id)); return row;
    }));
    if (!rows.length) byId('role-picker-items').append(domainText('p', 'No matching models in this connection.', 'muted'));
    updateDomainPager('role-picker', (page - 1) * 20, {items: rows, total: matches.length, page_size: 20, more: page * 20 < matches.length});
    byId('role-picker-pages').hidden = matches.length <= 20;
  }
  async function load() {
    if(nativeMode())return loadNative();
    const id = ++serial, selected = byId('role-picker-connection').value;
    pending?.abort(); pending = new AbortController(); page = 1; entries = [];
    if (!selected) { byId('role-picker-status').textContent = 'Add and enable a model connection first.'; render(); return; }
    byId('role-picker-status').textContent = 'Loading models…'; render();
    try {
      const catalog = `/api/v1/models/catalog?connection=${encodeURIComponent(selected)}`;
      let result, legacyImageCatalog = false;
      try {
        result = await domainRequest(`${catalog}&purpose=${role === 'image-generation' ? 'image-generation' : 'defaults'}`, 'GET', undefined, {signal: pending.signal});
      } catch (error) {
        if (role !== 'image-generation' || error.status !== 503) throw error;
        result = await domainRequest(catalog, 'GET', undefined, {signal: pending.signal});
        legacyImageCatalog = true;
      }
      if (!valid() || serial !== id) return;
      if (role === 'image-generation') {
        const expected = byId('role-picker-connection').selectedOptions[0]?.dataset.revision;
        const inventory = await domainRequest('/api/v1/settings/model-connections', 'GET', undefined, {signal: pending.signal});
        if (!valid() || serial !== id) return;
        const connection = inventory.connections.find(item => item.id === selected);
        if (!connection || !connection.enabled || connection.backend !== 'ollama' ||
            connection.revision !== expected || endpointKey(connection.url) !== endpointKey(imageEndpoint)) {
          throw new Error('The Ollama connection changed. Close and reopen the picker.');
        }
      }
      entries = role === 'image-generation' ? result.models.filter(entry => /^ollama(?:@[^/]+)?\/.+/.test(entry.id)) : result.models.filter(entry => entry.roles?.[role] !== false);
      if (role === 'image-generation') entries.sort((a, b) => (b.roles?.[role] === true) - (a.roles?.[role] === true));
      byId('role-picker-status').textContent = role === 'image-generation' ? (legacyImageCatalog ? 'Installed models are unverified. Restart the Web UI host and reload to check image generation capabilities.' : 'Installed models on this server. Use Test service to check the selected model before saving.') : 'Saving remains separate. Unknown capability labels are not a guarantee of provider support.'; render();
    } catch (error) { if (valid() && serial === id && error.name !== 'AbortError') byId('role-picker-status').textContent = error.message; }
  }
  function decorate(select, label, roleName, connections) {
    const button = domainButton('', () => {
      imageProvider='';nativeRecipe='';nativePanel.hidden=true;
      target = select.id; role = roleName; epoch = authEpoch; byId('role-picker-unset').hidden = false;
      byId('role-picker-title').textContent = `Choose ${label.toLocaleLowerCase()} model`;
      byId('role-picker-query').value = '';
      byId('role-picker-connection').replaceChildren(...connections.filter(c => c.enabled).map(c => new Option(`${c.name} · ${c.backend}`, c.id)));
      const identity = select.value.split('/')[0].split('@')[1];
      if ([...byId('role-picker-connection').options].some(option => option.value === identity)) byId('role-picker-connection').value = identity;
      dialog.showModal(); byId('role-picker-query').focus(); load();
    }, 'quiet model-choice-button');
    button.id = select.id + '-picker'; button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-label', `Choose ${label.toLocaleLowerCase()} model`);
    const valueLabel = domainText('span', '', 'model-role-value');
    const arrow = domainText('span', '›', 'model-role-chevron'); arrow.setAttribute('aria-hidden', 'true');
    button.append(valueLabel, arrow);
    const describe = () => { valueLabel.textContent = (select.value ? select.selectedOptions[0]?.textContent : 'Automatic / unconfigured') || 'Unconfigured'; button.title = select.value || 'Unset'; button.setAttribute('aria-label', `Choose ${label.toLocaleLowerCase()} model, ${valueLabel.textContent}`); };
    select.addEventListener('change', describe); describe();
    select.hidden = true;
    queueMicrotask(() => { const fieldLabel = document.querySelector(`label[for="${select.id}"]`); if (fieldLabel) fieldLabel.htmlFor = button.id; });
    return button;
  }
  function endpointKey(value) {
    try { const url = new URL(value); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return ''; return url.href.replace(/\/+$/, ''); }
    catch { return ''; }
  }
  async function openImage() {
    target = 'image-service-model-name'; role = 'image-generation'; epoch = authEpoch;
    imageEndpoint = byId('image-service-url').value.trim();
    imageProvider=byId('image-service-provider').value;nativeData=null;nativeRecipe='';nativeReceipt=null;nativeExpected=null;nativeBusy=false;
    byId('role-picker-title').textContent = 'Choose image model';
    byId('role-picker-unset').hidden = true; byId('role-picker-query').value = '';
    byId('role-picker-connection').replaceChildren(); entries = []; page = 1;
    dialog.showModal(); byId('role-picker-query').focus();
    if(nativeMode()){render();return loadNative();}
    const id = ++serial; pending?.abort(); pending = new AbortController();
    byId('role-picker-status').textContent = 'Loading connections…';
    try {
      const result = await domainRequest('/api/v1/settings/model-connections', 'GET', undefined, {signal:pending.signal});
      if (!valid() || id !== serial) return;
      const key = endpointKey(imageEndpoint);
      const matches = key ? result.connections.filter(c => c.enabled && c.backend === 'ollama' && endpointKey(c.url) === key) : [];
      byId('role-picker-connection').replaceChildren(...matches.map(c => {
        const option = new Option(c.name, c.id); option.dataset.revision = c.revision; return option;
      }));
      if (!matches.length) { byId('role-picker-status').textContent = 'No enabled Ollama connection matches this server URL. Enter the image model name manually.'; render(); return; }
      await load();
    } catch (error) { if (valid() && id === serial && error.name !== 'AbortError') byId('role-picker-status').textContent = error.message; }
  }
  async function loadNative(use=false,refresh=false) {
    const id=++serial;pending?.abort();pending=new AbortController();nativeBusy=true;
    byId('role-picker-status').textContent='Loading image models…';render();
    try {
      if(!latest?.image_model_selection)throw new Error('Restart the WebUI host and reload to choose Stable Diffusion models.');
      const data=await domainRequest('/api/v1/settings/models/image-models','POST',{endpoint:imageEndpoint,refresh},{signal:pending.signal});
      if(!nativeCurrent()||id!==serial)return;
      nativeData=data;nativeBusy=false;render();
      if(use&&nativeExpected&&data.runtime.recipe===nativeExpected.recipe&&
          Object.entries(nativeExpected.models).filter(([,file])=>file).every(([key,file])=>data.runtime.models[key]===file))await useLoaded();
    }catch(error){if(nativeCurrent()&&id===serial&&error.name!=='AbortError')byId('role-picker-status').textContent=error.message;}
    finally{if(id===serial){nativeBusy=false;if(nativeCurrent())renderNativeActions();}}
  }
  async function useLoaded() {
    if(!nativeCurrent()||!nativeData?.model||nativeBusy)return;
    const id=++serial;nativeBusy=true;renderNativeActions();
    try {
      const evidence=await domainRequest('/api/v1/settings/models/image-test','POST',{endpoint:imageEndpoint,provider:'sdcpp'});
      if(!nativeCurrent()||id!==serial)return;
      if(evidence.model!==nativeData.model)throw new Error('The loaded model changed. Refresh the model choices.');
      byId(target).value=evidence.model;byId(target).dispatchEvent(new Event('input',{bubbles:true}));close();
    }catch(error){if(nativeCurrent()&&id===serial)byId('role-picker-status').textContent=error.message;}
    finally{if(id===serial){nativeBusy=false;renderNativeActions();}}
  }
  function renderNativeActions() {
    const load=nativePanel.querySelector('[data-native-load]');
    if(load){
      const recipe=nativeData?.recipes.find(item=>item.id===nativeRecipe);
      const complete=recipe&&recipe.slots.every(slot=>!slot.required||nativeModels[slot.id])&&
        (recipe.required_any||[]).every(group=>group.some(key=>nativeModels[key]));
      load.disabled=nativeBusy||Boolean(nativeData?.pending)||nativeData?.runtime.state==='loading'||!complete;
    }
    for(const node of nativePanel.querySelectorAll('select,[data-native-recover]'))node.disabled=nativeBusy||Boolean(nativeData?.pending&&nativeData.pending.state!=='unknown');
  }
  function renderNative() {
    const list=byId('role-picker-items');list.replaceChildren();nativePanel.replaceChildren();
    byId('role-picker-pages').hidden=true;
    byId('role-picker-query').hidden=Boolean(nativeRecipe);
    if(!nativeData)return;
    const current=nativeData.runtime,state=nativeData.pending;
    byId('role-picker-status').textContent=nativeBusy?'Loading image models…':state?
      state.state==='unknown'?'Model loading is unconfirmed. Check the loaded state before another attempt.':'A shared model load is in progress.':
      current.state==='loading'?'The server is loading a model. Refresh to check its state.':
      !nativeData.files.length?'The server exposes no model files. Its model folder must include the downloaded weights. The currently loaded model remains available.':
      'Choose a model setup and its files. Loading requires review; saving the image default stays separate.';
    if(state?.state==='unknown'){
      const check=domainButton('Check loaded state',()=>reviewNative(true),'quiet');check.dataset.nativeRecover='true';nativePanel.append(check);
    }
    if(!nativeRecipe){
      if(current.state==='ready'&&nativeData.model){
        const loaded=domainButton('',useLoaded,'store-row quiet');
        const text=domainText('span','','store-card-content');text.append(domainText('strong',nativeData.model),domainText('small','Currently loaded · Use as image generation model','muted'));
        const icon=domainText('span','','model-brand-icon');setModelBrandIcon(icon,nativeData.model,'',{size:32});
        loaded.append(icon,text);loaded.setAttribute('aria-pressed',String(byId(target)?.value===nativeData.model));loaded.disabled=nativeBusy||Boolean(state);list.append(loaded);
      }
      const query=byId('role-picker-query').value.trim().toLocaleLowerCase();
      const matches=nativeData.recipes.filter(item=>`${item.name} ${item.description}`.toLocaleLowerCase().includes(query));
      page=Math.max(1,Math.min(page,Math.ceil(matches.length/20)||1));
      for(const recipe of matches.slice((page-1)*20,page*20)){
        const row=domainButton('',()=>{nativeRecipe=recipe.id;nativeModels={};
          for(const slot of recipe.slots){const value=recipe.models?.[slot.id];nativeModels[slot.id]=nativeData.files.some(file=>file.id===value&&slot.categories.includes(file.category))?value:'';}render();},'store-row quiet');
        const content=domainText('span','','store-card-content');content.append(domainText('strong',recipe.name));
        if(recipe.description)content.append(domainText('small',recipe.description,'muted'));
        const icon=domainText('span','','model-brand-icon');setModelBrandIcon(icon,recipe.name,'',{size:32});
        row.append(icon,content);row.setAttribute('aria-label',`Configure ${recipe.name}`);row.disabled=nativeBusy||Boolean(state);list.append(row);
      }
      updateDomainPager('role-picker',(page-1)*20,{items:matches.slice((page-1)*20,page*20),total:matches.length,page_size:20,more:page*20<matches.length});
      byId('role-picker-pages').hidden=matches.length<=20;
    }else{
      const recipe=nativeData.recipes.find(item=>item.id===nativeRecipe);
      if(!recipe){nativeRecipe='';return render();}
      nativePanel.append(domainButton('Model setups',()=>{nativeRecipe='';render();},'quiet'),domainText('h3',recipe.name));
      for(const slot of recipe.slots){
        const label=domainText('label',slot.label+(slot.required?' · Required':' · Optional'));
        const select=document.createElement('select');select.dataset.modelSlot=slot.id;
        select.append(new Option('Choose model file',''),...nativeData.files.filter(file=>slot.categories.includes(file.category)).map(file=>new Option(file.name,file.id)));
        select.value=nativeModels[slot.id]||'';select.addEventListener('change',()=>{nativeModels[slot.id]=select.value;renderNativeActions();});
        label.append(select);nativePanel.append(label);
      }
      for(const group of recipe.required_any||[])nativePanel.append(domainText('p','Choose at least one: '+group.map(key=>recipe.slots.find(slot=>slot.id===key)?.label||key).join(' or '),'muted'));
      const actions=domainText('div','','dialog-actions'),load=domainButton('Load and use model',()=>reviewNative());load.dataset.nativeLoad='true';actions.append(load);nativePanel.append(actions);
    }
    renderNativeActions();
  }
  async function reviewNative(recover=false) {
    if(!nativeCurrent()||nativeBusy||!nativeData)return;
    const data=nativeData,selected=nativeRecipe,models={...nativeModels};nativeBusy=true;renderNativeActions();
    try {
      await prepareChange(recover?{operation:'image-model-recover',endpoint:imageEndpoint,target:data.pending.request_id}:
        {operation:'image-model-load',endpoint:imageEndpoint,recipe:selected,models,catalog_revision:data.catalog_revision,runtime_revision:data.runtime_revision},{
          current:()=>nativeCurrent(),
          onAccepted:receipt=>{if(!nativeCurrent())return;nativeReceipt=receipt;nativeExpected=recover?null:{recipe:selected,models};nativeData.pending=receipt;nativeBusy=false;render();
            clearInterval(nativePoll);nativePoll=setInterval(()=>{if(nativeCurrent())loadOperations();},1000);},
          onDiscard:()=>{if(nativeCurrent()){nativeBusy=false;renderNativeActions();}},
        });
    }catch(error){if(nativeCurrent())byId('role-picker-status').textContent=error.message;}
    finally{if(nativeCurrent()){nativeBusy=false;renderNativeActions();}}
  }
  document.addEventListener('klaude-operations',event=>{
    if(!nativeCurrent()||!nativeReceipt)return;
    const receipt=event.detail.find(item=>item.request_id===nativeReceipt.request_id);if(!receipt)return;
    nativeReceipt=receipt;nativeData.pending=receipt;
    if(['completed','failed','cancelled','unknown'].includes(receipt.state)){
      clearInterval(nativePoll);nativePoll=null;nativeRecipe='';nativeReceipt=null;
      if(receipt.state==='completed')loadNative(Boolean(nativeExpected));else loadNative();
    }else render();
  });
  byId('image-service-model-name-picker').addEventListener('click', openImage);
  byId('role-picker-close').append(libraryIcon('close'));
  byId('role-picker-close').addEventListener('click', close);
  byId('role-picker-unset').addEventListener('click', () => select('', 'Unset'));
  byId('role-picker-query').addEventListener('input', () => { page = 1; render(); });
  byId('role-picker-connection').addEventListener('change', load);
  byId('role-picker-refresh').addEventListener('click', ()=>nativeMode()?loadNative(false,true):load());
  for (const [action, delta] of [['previous', -1], ['next', 1]]) {
    byId(`role-picker-${action}`).append(libraryIcon(action));
    byId(`role-picker-${action}`).addEventListener('click', () => { page += delta; render(); });
  }
  byId('role-picker-numbers').addEventListener('click', event => { const b = event.target.closest('[data-page]'); if (b) { page = Number(b.dataset.page); render(); } });
  dialog.addEventListener('close', () => { if (dialog.open) return; serial++; pending?.abort(); entries = [];nativeData=null;nativeReceipt=null;nativeExpected=null;nativeRecipe='';clearInterval(nativePoll);nativePoll=null;nativePanel.replaceChildren(); byId('role-picker-query').hidden=false;byId('role-picker-connection').closest('label').hidden=false;byId('role-picker-items').replaceChildren(); byId(target + '-picker')?.focus(); });
  document.addEventListener('klaude-view', () => { if (!valid()) close(); });
  document.addEventListener('klaude-auth-reset', () => { close(); byId('role-picker-query').value = ''; });
  return {decorate};
})();

window.ModelConnectionsUI = (() => {
  let data = null, read = null, serial = 0, pending = false, loading = false, lastOperations = '', formVersion = 0, selected = null, mode = 'add';
  const dialog = byId('model-connection-editor');
  const active = () => authenticated && currentView === 'settings';
  const message = value => { byId('model-connections-status').textContent = value; };
  const currentConnection = () => latest?.model_connection || `default-${latest?.provider?.replaceAll('_', '-')}`;
  const locked = () => !data?.management_allowed || pending || Boolean(data.pending) || Boolean(latest?.active_turn_id) || Boolean(latest?.queue?.length);
  let editorTrigger = null;
  function connectionMenu(trigger, actions, identity, label = 'Connection actions') {
    const menu = domainText('div', '', 'message-menu context-action-menu');
    menu.id = `connection-actions-${identity}`;
    menu.setAttribute('popover', 'auto'); menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', label);
    trigger.setAttribute('popovertarget', menu.id);
    trigger.setAttribute('aria-haspopup', 'menu'); trigger.setAttribute('aria-expanded', 'false');
    for (const [label, icon, action, disabled, danger] of actions) {
      const button = domainButton('', () => {
        menu.hidePopover(); trigger.focus({preventScroll:true}); action();
      }, 'message-action' + (danger ? ' danger' : ''));
      button.setAttribute('role', 'menuitem'); button.disabled = disabled;
      const mark = domainText('span', '', 'menu-action-icon'); mark.setAttribute('aria-hidden', 'true');
      mark.append(libraryIcon(icon)); button.append(mark, domainText('span', label)); menu.append(button);
    }
    let focusLast = false;
    trigger.addEventListener('keydown', event => {
      if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
      event.preventDefault(); focusLast = event.key === 'ArrowUp';
      if (!menu.matches(':popover-open')) trigger.click();
    });
    menu.addEventListener('toggle', () => {
      const open = menu.matches(':popover-open'); trigger.setAttribute('aria-expanded', String(open));
      if (!open) return;
      const anchor = trigger.getBoundingClientRect(), viewport = window.visualViewport;
      const left = (viewport?.offsetLeft || 0) + 8, top = (viewport?.offsetTop || 0) + 8;
      const right = left + (viewport?.width || innerWidth) - 16;
      const bottom = top + (viewport?.height || innerHeight) - 16;
      menu.style.maxHeight = `${Math.max(48, bottom - top)}px`;
      menu.style.left = `${Math.max(left, Math.min(anchor.right - menu.offsetWidth, right - menu.offsetWidth))}px`;
      menu.style.top = `${Math.max(top, Math.min(anchor.bottom + 4, bottom - menu.offsetHeight))}px`;
      const available = [...menu.querySelectorAll('button:not(:disabled)')];
      (focusLast ? available.at(-1) : available[0])?.focus({preventScroll:true}); focusLast = false;
    });
    menu.addEventListener('keydown', event => {
      const items = [...menu.querySelectorAll('button:not(:disabled)')];
      const index = items.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 :
        event.key === 'ArrowDown' ? (index + 1) % items.length :
        event.key === 'ArrowUp' ? (index - 1 + items.length) % items.length : null;
      if (next !== null) { event.preventDefault(); items[next]?.focus(); }
      if (event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation(); menu.hidePopover(); trigger.focus();
      }
    });
    return menu;
  }
  window.settingsActionMenu = connectionMenu;
  function render() {
    byId('model-connection-add').disabled = locked();
    const container = byId('model-settings-connections'); container.replaceChildren();
    if (!data) return;
    const query = byId('model-connection-query').value.trim().toLocaleLowerCase();
    const rows = data.connections.filter(item => `${item.name} ${item.backend} ${item.source} ${item.url}`.toLocaleLowerCase().includes(query));
    if (!rows.length) {
      const empty = domainText('p', query ? 'No matching connections' : 'No connections yet', 'muted collection-empty');
      empty.setAttribute('role', 'status'); container.append(empty);
    }
    for (const item of rows) {
      const node = domainText('article', '', 'management-row collection-row library-card model-connection-row');
      const content = domainText('div', '', 'management-content');
      const backend = window.AIIcons?.platform(item.backend)?.name || window.AIIcons?.provider(item.backend)?.name || (item.backend === 'openai_compatible' ? 'OpenAI compatible' : item.backend);
      const heading = domainText('div', '', 'model-connection-title');
      heading.append(domainText('h3', item.name), domainText('span', item.enabled ? 'Enabled' : 'Disabled', 'model-capability'));
      content.append(heading, domainText('p', `${backend} · ${item.source}`, 'muted'));
      if (item.url) content.append(domainText('p', item.url, 'model-connection-address'));
      content.append(domainText('small', item.credential_set ? 'Credential saved' : 'No saved credential', 'muted'));
      const actions = domainText('div', '', 'management-actions');
      const inUse = currentConnection() === item.id;
      const testConnection = async () => {
        if (pending) return; pending = true; message('Testing connection…'); render(); const epoch = authEpoch;
        try { const result = await domainRequest('/api/v1/settings/model-connections/test', 'POST', {connection: item.id, revision: item.revision}); if (epoch === authEpoch && active()) message(result.message); }
        catch (error) { if (epoch === authEpoch && active()) message(error.message); }
        finally { if (epoch === authEpoch) { pending = false; render(); } }
      };
      const disabled = locked() || inUse;
      const choices = [
        ['Test', 'connection', testConnection, locked()],
        ...(item.backend !== 'openai_codex' ? [['Edit', 'options', () => open('edit', item), disabled]] : []),
        [item.enabled ? 'Disable' : 'Enable', item.enabled ? 'close' : 'connection', () => review({operation: 'model-connection-enabled', connection: item.id, revision: item.revision, enabled: !item.enabled}), disabled],
        ...(item.credential_editable ? [['Credential', 'shield', () => open('credential', item), disabled]] : []),
        ['Remove', 'trash', () => review({operation: 'model-connection-remove', connection: item.id, revision: item.revision}), disabled, true],
      ];
      const more = domainButton('', () => {}, 'icon-button quiet');
      more.setAttribute('aria-label', `Options for ${item.name}`); more.title = 'Connection options';
      more.append(libraryIcon('more')); more.disabled = locked();
      const menu = connectionMenu(more, choices, item.id);
      if (inUse) actions.append(domainText('span', 'Current', 'muted model-connection-current'));
      actions.append(more);
      const icon = domainText('span', '', 'model-connection-icon'); icon.setAttribute('aria-hidden', 'true');
      const mark = domainText('span', '', 'model-brand-icon');
      window.AIIcons?.setPlatformIcon(mark, item.backend, {appearance:'color', size:24});
      icon.append(mark);
      node.append(icon, content, actions, menu); container.append(node);
    }
    const recovery = byId('model-connections-recovery'); recovery.replaceChildren();
    if (data.pending) {
      recovery.append(domainText('p', data.pending.state === 'unknown' ? 'Connection save unconfirmed. Check the exact saved state before another change.' : 'A shared connection change is in progress.', 'muted'));
      if (data.pending.state === 'unknown') recovery.append(domainButton('Check saved state', () => review({operation: 'model-connection-recover', target: data.pending.request_id}, true)));
    }
  }
  async function load() {
    if (!active()) return;
    if (!latest?.model_settings) { message('Restart the WebUI host and reload to manage model connections.'); render(); return; }
    const id = ++serial, epoch = authEpoch; loading = true; read?.abort(); read = new AbortController();
    try {
      const result = await domainRequest('/api/v1/settings/model-connections', 'GET', undefined, {signal: read.signal});
      if (!active() || epoch !== authEpoch || id !== serial) return;
      data = result;
      byId('model-connection-adapter').replaceChildren(...data.adapters.map(a => new Option(a.id, a.id)));
      message(result.management_allowed ? '' : 'Connection editing and credentials require an admin account.'); render();
    } catch (error) { if (id === serial && active() && epoch === authEpoch && error.name !== 'AbortError') message(error.message); }
    finally { if (id === serial) loading = false; }
  }
  function open(nextMode, item = null) {
    if (locked() || reviewDialog.open) return;
    editorTrigger = document.activeElement;
    mode = nextMode; selected = item; formVersion++; byId('model-connection-form').reset();
    byId('model-connection-title').textContent = mode === 'credential' ? `Credential · ${item.name}` : item ? `Edit ${item.name}` : 'Add model connection';
    byId('model-connection-definition').hidden = mode === 'credential'; byId('model-credential-fields').hidden = mode !== 'credential';
    for (const input of byId('model-connection-definition').querySelectorAll('input,select')) input.disabled = mode === 'credential';
    byId('model-credential-value').disabled = mode !== 'credential';
    byId('model-connection-name').value = item?.name || '';
    byId('model-connection-url').value = item?.url || 'http://127.0.0.1:11434';
    byId('model-connection-source').value = item?.source || 'Local';
    byId('model-connection-authentication').checked = Boolean(item?.authentication);
    byId('model-connection-adapter').value = item?.backend || 'ollama'; byId('model-connection-adapter').disabled = mode !== 'add';
    byId('model-credential-remove').hidden = mode !== 'credential' || !item?.credential_set;
    byId('model-connection-editor-status').textContent = ''; dialog.showModal();
    byId(mode === 'credential' ? 'model-credential-value' : 'model-connection-name').focus();
  }
  async function review(draft, recovery = false) {
    if (pending || !data?.management_allowed || !recovery && data.pending || reviewDialog.open) return;
    const epoch = authEpoch, version = formVersion, hasDialog = dialog.open;
    pending = true; render();
    try {
      const result = await prepareChange(draft, {
        current: () => epoch === authEpoch && active() && settingsSection === 'models' && (!hasDialog || dialog.open && version === formVersion),
        beforeOpen: () => { byId('model-credential-value').value = ''; if (dialog.open) dialog.close(); },
        onAccepted: () => { if (epoch === authEpoch) { pending = false; load(); } },
        onDiscard: result => { if (epoch === authEpoch) { pending = false; if (result.uncertain) message('Save unconfirmed. Check saved state before retrying.'); load(); } },
      });
      if (!result && epoch === authEpoch) pending = false;
    } catch (error) { if (epoch === authEpoch && active()) { pending = false; (dialog.open ? byId('model-connection-editor-status') : byId('model-connections-status')).textContent = error.message; } }
    if (epoch === authEpoch) render();
  }
  byId('model-connection-form').addEventListener('submit', event => {
    event.preventDefault();
    if (mode === 'credential') review({operation: 'model-connection-credential', connection: selected.id, revision: selected.revision, value: byId('model-credential-value').value});
    else review({operation: mode === 'add' ? 'model-connection-add' : 'model-connection-edit',
      ...(selected ? {connection: selected.id, revision: selected.revision} : {backend: byId('model-connection-adapter').value}),
      name: byId('model-connection-name').value.trim(), url: byId('model-connection-url').value.trim(), source: byId('model-connection-source').value, authentication: byId('model-connection-authentication').checked});
  });
  byId('model-credential-remove').addEventListener('click', () => review({operation: 'model-connection-credential', connection: selected.id, revision: selected.revision, value: ''}));
  byId('model-connection-adapter').addEventListener('change', () => {
    const adapter = byId('model-connection-adapter').value;
    byId('model-connection-url').value = data.adapters.find(a => a.id === adapter)?.url || (adapter === 'ollama' ? 'http://127.0.0.1:11434' : '');
    byId('model-connection-source').value = adapter === 'ollama' ? 'Local' : 'Cloud';
    byId('model-connection-authentication').checked = adapter !== 'ollama';
  });
  const closeConnectionMenus = () => byId('model-settings-connections').querySelectorAll(':popover-open').forEach(menu => menu.hidePopover());
  new MutationObserver(() => { if (byId('models-settings').hidden) closeConnectionMenus(); })
    .observe(byId('models-settings'), {attributes:true, attributeFilter:['hidden']});
  window.addEventListener('resize', closeConnectionMenus);
  document.addEventListener('klaude-view', closeConnectionMenus);
  byId('model-connection-filter').addEventListener('submit', event => event.preventDefault());
  byId('model-connection-query').addEventListener('input', render);
  byId('model-connection-add').addEventListener('click', () => open('add'));
  byId('model-connections-refresh').addEventListener('click', load);
  byId('model-connection-close').append(libraryIcon('close'));
  byId('model-connection-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { formVersion++; byId('model-credential-value').value = ''; (editorTrigger?.isConnected ? editorTrigger : byId('model-connection-add')).focus(); });
  document.addEventListener('klaude-view', () => { if (active()) load(); else { serial++; read?.abort(); dialog.close(); } });
  document.addEventListener('klaude-snapshot', () => { if (active() && !data && !loading && latest?.model_settings) load(); });
  document.addEventListener('klaude-operations', event => {
    if (!active()) return;
    const relevant = event.detail.filter(item => item.kind.startsWith('model-connection-'));
    const signature = JSON.stringify(relevant.map(item => [item.request_id, item.state]));
    if (signature !== lastOperations) { lastOperations = signature; load(); BrowserMedia.load(true); }
  });
  document.addEventListener('klaude-auth-reset', () => { serial++; read?.abort(); data = null; pending = false; lastOperations = ''; dialog.close(); byId('model-connection-query').value = ''; byId('model-connection-form').reset(); byId('model-settings-connections').replaceChildren(); byId('model-connections-recovery').replaceChildren(); message(''); });
})();

// Search indexes setting labels and definitions, never saved values or secrets.
window.SettingsSearch = (() => {
  const dialog = byId('settings-search-dialog'), query = byId('settings-search-query');
  const results = byId('settings-search-results'), status = byId('settings-search-status');
  let fields = [], read = null, serial = 0, agentReady = false, active = -1;
  query.setAttribute('role','combobox'); query.setAttribute('aria-autocomplete','list');
  query.setAttribute('aria-controls',results.id); query.setAttribute('aria-expanded','false');
  results.setAttribute('role','listbox'); results.setAttribute('aria-label','Settings results');
  function select(index) {
    const options=[...results.querySelectorAll('.settings-search-result')];
    active=index>=0 && index<options.length ? index : -1;
    options.forEach((option,i)=>option.setAttribute('aria-selected',String(i===active)));
    if (active<0) query.removeAttribute('aria-activedescendant');
    else {
      query.setAttribute('aria-activedescendant',options[active].id);
      options[active].scrollIntoView({block:'nearest'});
    }
  }
  const fixed = [
    ['Account','Account identity local admin','account','account-heading'],
    ['Account','Change password security','account','password-open'],
    ['Account','Sign out session','account','account-sign-out'],
    ['Theme','Color mode system light dark','theme','.theme-color-mode'],
    ['Theme','Color source presets accent image','theme','.theme-color-source'],
    ['Theme','Material palette variant','theme','.theme-variant-options'],
    ['Theme','Your palette presets','theme','.palette-options'],
    ['Theme','Custom accent hex color','theme','theme-accent-value'],
    ['Theme','Choose an image for colors','theme','theme-image-choose'],
    ['Theme','Chat view density compact comfortable','theme','[name="chat-density"]'],
    ['Theme','Reduced motion animation','theme','reduced-motion'],
    ['Theme','Generating indicator','theme','theme-loading-style'],
    ['Theme','Loading circle','theme','theme-loading-circle-style'],
    ['Theme','Loading bar','theme','theme-loading-bar-style'],
    ['Theme','Surface transparency','theme','theme-transparency'],
    ['Theme','Reset default appearance','theme','theme-default'],
    ['Models','Startup chat model default','models','default-value-chat-picker'],
    ['Models','Utility model default','models','default-value-utility-picker'],
    ['Models','Research model default','models','default-value-research-picker'],
    ['Models','Vision model default','models','default-value-vision-picker'],
    ...['Utility','Vision'].flatMap((role)=>[0,1,2].map(index=>
      ['Models',`${role} fallback ${index+1} model`, 'models',
        `default-value-${role==='Utility'?'fallbacks':'vision_fallbacks'}-${index}-picker`])),
    ['Models','Utility output tokens','models','default-output-tokens'],
    ['Models','Enable Vision image input analysis','models','default-vision-enabled'],
    ['Models','Model connections providers add edit remove credentials','models','model-connections-heading','connections'],
    ['Models','Connected models catalog search filter','models','models-query','catalog'],
    ['Models','Enable image generation','models','image-service-enabled','image'],
    ['Models','Image generation provider','models','image-service-provider','image'],
    ['Models','Image generation model','models','image-service-model-name','image'],
    ['Models','Image generation server URL endpoint','models','image-service-url','image'],
    ['Models','Test image service','models','image-service-test','image'],
    ['Memory','Automatic memory remember useful facts','memory','memory-auto'],
    ['Memory','Saved memories search edit forget','memory','memory-query'],
    ['Memory','Add memory','memory','memory-create'],
    ['System','Restart Web UI server','system','system-restart'],
    ['System','Shut down Klaude and terminal sessions','system','system-shutdown',null,'shutdown stop exit quit'],
  ].map(([category,label,section,target,screen,keywords])=>({category,label,section,target,screen,keywords}));
  function render() {
    const terms=query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    results.replaceChildren(); select(-1); query.setAttribute('aria-expanded','false');
    if (!terms.length) { status.textContent=agentReady ? '' : 'Loading Agent settings…'; return; }
    const choices=[...document.querySelectorAll('#theme-settings input[name="palette"], #theme-settings input[name="theme-variant-choice"], #theme-settings input[name="appearance"], #theme-settings input[name="color-source"], #theme-settings input[name="chat-density"]')].map(input=>({
      category:'Theme', label:input.closest('label')?.textContent.trim() || input.value,
      section:'theme', target:`#theme-settings input[name="${input.name}"][value="${CSS.escape(input.value)}"]`,
      keywords:input.name.replaceAll('-',' '),
    }));
    const entries=[...fixed.filter(item=>item.section!=='account'||loginMethod==='password'),...choices,...fields];
    const matches=entries.filter(item=>terms.every(term=>`${item.category} ${item.label} ${item.keywords||''}`.toLocaleLowerCase().includes(term)));
    status.textContent=agentReady ? `${matches.length} result${matches.length===1?'':'s'}` : `${matches.length} results · Loading Agent settings…`;
    query.setAttribute('aria-expanded',String(matches.length>0));
    for (const [index,entry] of matches.entries()) {
      const button=domainButton('',()=>navigate(entry),'quiet settings-search-result');
      button.id=`settings-search-result-${index}`; button.setAttribute('role','option');
      button.setAttribute('aria-selected','false');
      if (entry.settingId) button.dataset.settingId=entry.settingId;
      button.append(domainText('span',entry.label),domainText('small',entry.category,'muted'));
      results.append(button);
    }
  }
  async function load() {
    read?.abort(); read=new AbortController(); const id=++serial, epoch=authEpoch;
    agentReady=false; render();
    try {
      if (!latest?.profile_management) throw new Error('Agent settings require an updated host.');
      const data=await domainRequest('/api/v1/settings/agent','GET',undefined,{signal:read.signal});
      if (!dialog.open || epoch!==authEpoch || id!==serial) return;
      fields=data.fields.map(field=>({category:'Agent',label:field.label + (field.id.startsWith('permissions.') ? ' approval' : field.id.startsWith('tool_availability.') ? ' availability' : ''),section:'agent',
        target:`setting-${field.id.replaceAll('.','-')}`, settingId:field.id, keywords:field.id.replaceAll(/[._]/g,' ')}));
      agentReady=true; render();
    } catch(error) {
      if (id!==serial || error.name==='AbortError') return;
      agentReady=true; render(); status.textContent = [status.textContent,
        'Agent settings unavailable: '+error.message].filter(Boolean).join(' · ');
    }
  }
  function resolve(entry) {
    let el=entry.target.startsWith('.') || entry.target.startsWith('[') || entry.target.startsWith('#') ? document.querySelector(entry.target) : byId(entry.target);
    return el;
  }
  async function navigate(entry) {
    const epoch=authEpoch;
    showSettingsSection(entry.section);
    if (settingsSection!==entry.section) return;
    if (entry.section==='models') {
      ModelsSettingsNavigation.show(entry.screen||'overview');
      const targetScreen=entry.screen||'overview';
      const panel={overview:'model-default-settings',connections:'model-connections-settings',catalog:'models-configured',image:'image-service-settings'}[targetScreen];
      if (byId(panel).hidden) return;
    }
    dialog.close();
    // Category reads may replace dynamic controls immediately after navigation.
    await new Promise(resolve=>setTimeout(resolve,entry.section==='theme' ? 50 : 350));
    let element=resolve(entry);
    for(let i=0;!element && i<40 && authenticated && epoch===authEpoch;i++) {
      await new Promise(resolve=>setTimeout(resolve,50)); element=resolve(entry);
    }
    if (!element || !authenticated || epoch!==authEpoch || currentView!=='settings' || settingsSection!==entry.section) {
      if (authenticated && epoch===authEpoch) showError('This setting is unavailable. Refresh Settings and try again.');
      return;
    }
    for(let parent=element.parentElement;parent;parent=parent.parentElement) if(parent.tagName==='DETAILS') parent.open=true;
    if (entry.target==='image-service-model-name' && element.closest('[hidden]')) element=byId('image-service-model-name-picker');
    if(element.hidden || element.closest('[hidden]')) {
      const group=element.closest('.setting-row,.theme-setting-group,.theme-option-surface');
      element=group?.querySelector('button:not([hidden]),input:not([hidden]),select:not([hidden])') || group || element;
    }
    element.scrollIntoView({block:'center',inline:'nearest'});
    if (!element.matches('input,select,textarea,button,summary,[tabindex]')) element.tabIndex=-1;
    element.focus({preventScroll:true});
  }
  byId('settings-search-open').append(libraryIcon('search'));
  byId('settings-search-close').append(libraryIcon('close'));
  byId('settings-search-open').addEventListener('click',()=>{query.value=''; fields=[]; dialog.showModal(); query.focus(); load();});
  byId('settings-search-close').addEventListener('click',()=>dialog.close());
  query.addEventListener('input',render);
  results.addEventListener('focusin',event=>{
    const options=[...results.querySelectorAll('.settings-search-result')];
    select(options.indexOf(event.target));
  });
  dialog.addEventListener('keydown',event=>{
    if (event.key==='Escape' && !event.isComposing) {
      event.preventDefault(); event.stopPropagation(); dialog.close(); return;
    }
    if (event.isComposing || event.altKey || event.ctrlKey || event.metaKey ||
        event.target!==query && !results.contains(event.target)) return;
    const options=[...results.querySelectorAll('.settings-search-result')];
    if (!options.length) return;
    if (event.key==='ArrowDown' || event.key==='ArrowUp') {
      event.preventDefault(); event.stopPropagation();
      const focused=options.indexOf(document.activeElement), current=focused<0 ? active : focused;
      const direction=event.key==='ArrowDown' ? 1 : -1;
      select(current<0 ? (direction>0 ? 0 : options.length-1) :
        (current+direction+options.length)%options.length);
      if (focused>=0) options[active].focus({preventScroll:true});
    } else if (event.key==='Enter' && event.target===query) {
      event.preventDefault(); options[active<0 ? 0 : active].click();
    }
  });
  dialog.addEventListener('close',()=>{serial++;read?.abort();fields=[];query.value='';results.replaceChildren();select(-1);query.setAttribute('aria-expanded','false');if(currentView==='settings')byId('settings-search-open').focus({preventScroll:true});});
  document.addEventListener('klaude-auth-reset',()=>dialog.close());
  document.addEventListener('klaude-view',()=>{if(currentView!=='settings')dialog.close();});
})();
