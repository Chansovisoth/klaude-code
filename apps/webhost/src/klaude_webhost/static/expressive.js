"use strict";

// Klaude Expressive. Independent web components; no end-4 QML implementation is
// included. Measured design behavior and deviations: docs/webui/klaude-expressive-reference.md.
window.KlaudeExpressive = (() => {
  const root = document.documentElement;
  const reduced = () => matchMedia('(prefers-reduced-motion: reduce)').matches || root.dataset.motion === 'reduced';
  const svgNS = 'http://www.w3.org/2000/svg';
  const closest = (target, selector) => target instanceof Element ? target.closest(selector) : null;
  let imageGeneration = 0;
  let barPreviewInstances = [], materialCirclePreview = null, barPreviewStyle = null, circlePreviewStyle = null;
  function shape(name, size = 48) {
    const points = window.MaterialLoadingGeometry.shapes?.[name] || window.MaterialLoadingGeometry.lockShapes?.[name];
    if (!points) return document.createElement('span');
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '-1 -1 2 2'); svg.setAttribute('width', size); svg.setAttribute('height', size);
    svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false');
    svg.classList.add('material-shape');
    const path = document.createElementNS(svgNS, 'path');
    let d = `M${points[0]},${points[1]}`;
    for (let i = 2; i < points.length; i += 6) d += `C${points.slice(i, i + 6).join(',')}`;
    path.setAttribute('d', d + 'Z'); path.setAttribute('fill', 'currentColor'); svg.append(path);
    return svg;
  }
  function themePreview(value, sync = false) {
    if (sync) {
      const source = document.querySelector(`input[name="color-source"][value="${value.colorSource || 'preset'}"]`);
      if (source) source.checked = true;
      for (const [id, next] of Object.entries({ 'theme-accent': value.accent || '#65558f',
        'theme-variant': value.variant || 'tonal-spot', 'theme-transparency': value.transparency || 0,
        'theme-loading-style': value.loadingStyle || 'expressive',
        'theme-loading-bar-style': value.loadingBarStyle || 'material',
        'theme-loading-circle-style': value.loadingCircleStyle || 'material' })) {
        const input = document.getElementById(id); if (input) input.value = next;
      }
    }
    for (const input of document.querySelectorAll('input[name="theme-variant-choice"]'))
      input.checked = input.value === (value.variant || 'tonal-spot');
    const accent = document.getElementById('theme-accent-value');
    if (accent && (sync || document.activeElement !== accent)) accent.value = value.accent || '#65558f';
    const transparency = document.getElementById('theme-transparency-value');
    if (transparency) transparency.textContent = `${value.transparency || 0}%`;
    const range = document.getElementById('theme-transparency');
    if (range) {
      const amount = Number(value.transparency) || 0;
      const maximum = Number(range.max) || 50;
      const minimum = Number(range.min) || 0;
      const track = range.parentElement;
      track.style.setProperty('--range-progress', `${Math.max(0, Math.min(100, (amount - minimum) / (maximum - minimum) * 100))}%`);
      track.dataset.atMax = String(amount >= maximum);
      track.querySelector('.material-slider-value').textContent = `${amount}%`;
    }
    const chatMode = document.getElementById('theme-chat-preview-mode');
    if (chatMode) chatMode.textContent = value.chatDensity === 'comfortable' ? 'Comfortable' : 'Compact';
    const loadingName = document.getElementById('theme-loading-name');
    if (loadingName) loadingName.textContent = value.loadingStyle === 'classic' ? 'Classic spinner' : 'Material shapes';
    const progressName = document.getElementById('theme-progress-name');
    if (progressName) progressName.textContent = ({ material: 'Material wavy', 'material-static': 'Material wavy static',
      classic: 'Classic linear', expressive: 'Classic wavy static' }[value.loadingBarStyle] || 'Material wavy');
    const circleName = document.getElementById('theme-circle-name');
    if (circleName) circleName.textContent = value.loadingCircleStyle === 'material' ? 'Material wavy' :
      value.loadingCircleStyle === 'classic' ? 'Classic' : 'Material wavy static';
    syncLoadingPreview(true);
  }
  function syncLoadingPreview(refreshMaterial = false) {
    const preview = document.getElementById('theme-loading-preview');
    const progressPreview = document.getElementById('theme-progress-preview');
    const progressPreviewThick = document.getElementById('theme-progress-preview-thick');
    const circlePreview = document.getElementById('theme-circle-preview');
    if (!preview || !progressPreview || !progressPreviewThick || !circlePreview) return;
    const showing = !byId('settings-view').hidden && !byId('theme-settings').hidden &&
      !document.querySelector('.layout').hidden;
    if (!showing) {
      barPreviewInstances.forEach(instance => instance.destroy?.()); barPreviewInstances = []; barPreviewStyle = null;
      materialCirclePreview?.destroy(); materialCirclePreview = null; circlePreviewStyle = null;
      preview.replaceChildren(); progressPreview.replaceChildren(); progressPreviewThick.replaceChildren(); circlePreview.replaceChildren(); return;
    }
    if (!preview.firstElementChild && window.MaterialLoading)
      preview.append(MaterialLoading.create({ size: 'large', contained: true }));
    const barStyle = root.dataset.loadingBarStyle || 'material';
    if (barPreviewStyle !== barStyle || (barStyle === 'material' && refreshMaterial)) {
      barPreviewInstances.forEach(instance => instance.destroy?.()); barPreviewInstances = [];
      progressPreview.replaceChildren(); progressPreviewThick.replaceChildren(); barPreviewStyle = barStyle;
    }
    if ((!progressPreview.firstElementChild || !progressPreviewThick.firstElementChild) && window.MaterialProgress) {
      for (const [container, thickness] of [[progressPreview, 'thin'], [progressPreviewThick, 'thick']]) {
        const instance = MaterialProgress.create({ preview: true, thickness });
        container.replaceChildren(instance.element);
        barPreviewInstances.push(instance);
      }
    }
    const circleStyle = root.dataset.loadingCircleStyle || 'material';
    if (circlePreviewStyle !== circleStyle || (circleStyle === 'material' && refreshMaterial)) {
      materialCirclePreview?.destroy(); materialCirclePreview = null;
      circlePreview.replaceChildren(); circlePreviewStyle = circleStyle;
    }
    if (!circlePreview.firstElementChild && window.MaterialCircularProgress) {
      const instance = MaterialCircularProgress.create({ value: 51, size: 48, preview: true });
      circlePreview.append(instance.element);
      if (circleStyle === 'material') materialCirclePreview = instance;
    }
    if (reduced()) requestAnimationFrame(() => {
      barPreviewInstances.forEach(instance => instance.freeze?.()); materialCirclePreview?.freeze();
    });
  }
  function setupSegments() {
    const selector = '.segmented, .section-chips, .cp-tabs, .settings-tabs, .file-view-modes, .cp-view-modes, .suggestions';
    const groups = new Map(), pending = new Set();
    let frame = 0;
    function queue(group) {
      if (!groups.has(group)) return;
      pending.add(group);
      if (!frame) frame = requestAnimationFrame(layout);
    }
    const resize = new ResizeObserver(entries => {
      for (const { target } of entries) queue(groups.has(target) ? target : target.parentElement);
    });
    function register(group) {
      const previous = groups.get(group), items = [...group.children].filter(item => item.matches('button, label'));
      if (!previous) resize.observe(group);
      for (const item of previous || []) if (!items.includes(item)) resize.unobserve(item);
      for (const item of items) if (!previous?.includes(item)) resize.observe(item);
      groups.set(group, items); queue(group);
    }
    function discover(element) {
      if (element.matches(selector)) register(element);
      for (const group of element.querySelectorAll(selector)) register(group);
    }
    function layout() {
      frame = 0;
      const updates = [];
      // Read all layout before changing markers. offset coordinates exclude the
      // press scale, so pointer feedback cannot change row membership.
      for (const group of pending) {
        const items = groups.get(group);
        if (!items || !group.isConnected) continue;
        const visible = items.filter(item => item.getClientRects().length && item.offsetWidth && item.offsetHeight);
        if (!visible.length) continue;
        const rows = [], heights = new Map(), rtl = getComputedStyle(group).direction === 'rtl';
        for (const item of visible) {
          const face = item.matches('label') ? item.querySelector('input + span') : item;
          heights.set(item, (face || item).offsetHeight / 2);
          let row = rows.find(row => Math.abs(row.top - item.offsetTop) <= 1);
          if (!row) { row = { top: item.offsetTop, items: [] }; rows.push(row); }
          row.items.push(item);
        }
        const starts = new Set(), ends = new Set();
        for (const row of rows) {
          row.items.sort((a, b) => (a.offsetLeft - b.offsetLeft) * (rtl ? -1 : 1));
          starts.add(row.items[0]); ends.add(row.items.at(-1));
        }
        updates.push({ group, items, starts, ends, heights });
      }
      pending.clear();
      for (const { group, items, starts, ends, heights } of updates) {
        group.setAttribute('data-segment-layout', '');
        for (const item of items) {
          item.toggleAttribute('data-segment-start', starts.has(item));
          item.toggleAttribute('data-segment-end', ends.has(item));
          // Animate to the real half-height, like the reference. A 9999px pill
          // would stay visually clamped through almost the entire transition.
          if (heights.has(item)) {
            const radius = `${heights.get(item)}px`;
            if (item.style.getPropertyValue('--segment-pill-radius') !== radius)
              item.style.setProperty('--segment-pill-radius', radius);
          }
        }
      }
    }
    discover(document.body);
    new MutationObserver(records => {
      const changed = new Set();
      for (const record of records) {
        changed.add(record.target);
        if (record.type === 'childList') for (const node of record.addedNodes)
          if (node instanceof Element) discover(node);
        const group = closest(record.target, selector);
        if (group) register(group);
      }
      for (const [group, items] of groups) {
        if (!group.isConnected || !group.matches(selector)) {
          resize.unobserve(group); for (const item of items) resize.unobserve(item);
          groups.delete(group); pending.delete(group);
        } else if ([...changed].some(element => element.contains(group))) queue(group);
      }
    }).observe(document.body, { subtree: true, childList: true, attributes: true,
      attributeFilter: ['hidden', 'open', 'class', 'dir'] });
    const refresh = () => { for (const group of groups.keys()) queue(group); };
    window.addEventListener('resize', refresh);
    document.fonts.ready.then(refresh);
  }
  function setup() {
    for (const element of document.querySelectorAll('[data-material-shape]')) element.append(shape(element.dataset.materialShape));
    const emblem = document.querySelector('.welcome-emblem');
    if (emblem) { const backing = shape('cookie', 90); backing.classList.add('welcome-shape'); emblem.prepend(backing); }
    themePreview(appearance, true);
    const loadingVisibility = new MutationObserver(() => syncLoadingPreview());
    for (const element of [byId('settings-view'), byId('theme-settings'), document.querySelector('.layout')])
      loadingVisibility.observe(element, { attributes: true, attributeFilter: ['hidden'] });
    syncLoadingPreview();
    // The source uses wrapping connected choices, rather than a dropdown, for
    // palette variants. The existing select remains the single form value.
    const variants = document.createElement('fieldset'), variantLegend = document.createElement('legend');
    variantLegend.textContent = 'Material palette variant'; variants.append(variantLegend);
    const variantChoices = document.createElement('div'); variantChoices.className = 'theme-variant-options segmented';
    for (const option of byId('theme-variant').options) {
      const label = document.createElement('label'), input = document.createElement('input'), caption = document.createElement('span');
      input.type = 'radio'; input.name = 'theme-variant-choice'; input.value = option.value;
      input.checked = option.value === byId('theme-variant').value; caption.textContent = option.text;
      input.onchange = () => { byId('theme-variant').value = input.value; byId('theme-variant').dispatchEvent(new Event('change')); };
      label.append(input, caption); variantChoices.append(label);
    }
    variants.append(variantChoices);
    const variantLabel = document.querySelector('.theme-variant-label');
    byId('theme-variant').hidden = true;
    variants.append(byId('theme-variant')); variantLabel.replaceWith(variants);
    setupSegments();
    const preview = () => { applyAppearance(appearanceDraft()); byId('theme-status').textContent = 'Preview · not saved'; };
    for (const id of ['theme-accent', 'theme-transparency']) byId(id).addEventListener('input', () => {
      if (id === 'theme-accent') document.querySelector('input[name="color-source"][value="custom"]').checked = true;
      preview();
    });
    const accentHex = byId('theme-accent-value');
    const commitAccentHex = () => {
      let hex = accentHex.value.trim().replace(/^#/, '');
      if (!/^(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(hex)) {
        accentHex.value = byId('theme-accent').value;
        return;
      }
      if (hex.length === 3) hex = [...hex].map(char => char + char).join('');
      const next = `#${hex.toLowerCase()}`;
      accentHex.value = next;
      if (next === byId('theme-accent').value) return;
      byId('theme-accent').value = next;
      byId('theme-accent').dispatchEvent(new Event('input', { bubbles: true }));
    };
    accentHex.addEventListener('blur', commitAccentHex);
    accentHex.addEventListener('keydown', event => {
      if (event.key === 'Enter') { event.preventDefault(); accentHex.blur(); }
      if (event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation();
        accentHex.value = byId('theme-accent').value;
        accentHex.blur();
      }
    });
    byId('theme-image-choose').addEventListener('click', () => byId('theme-image').click());
    byId('theme-image').addEventListener('change', async event => {
      const generation = ++imageGeneration, file = event.target.files[0]; event.target.value = '';
      if (!file) return;
      const button = byId('theme-image-choose'), status = byId('theme-image-status');
      button.disabled = true; status.textContent = 'Finding colors on this device…';
      try {
        const accent = await window.KlaudeColors.fromImage(file);
        if (generation !== imageGeneration) return;
        byId('theme-accent').value = accent;
        document.querySelector('input[name="color-source"][value="image"]').checked = true;
        preview(); status.textContent = 'Palette ready. Apply changes to save the accent.';
      } catch (error) { if (generation === imageGeneration) status.textContent = error.message; }
      finally { if (generation === imageGeneration) button.disabled = false; }
    });
    function clearImage() {
      imageGeneration++; byId('theme-image-choose').disabled = false; byId('theme-image-status').textContent = '';
    }
    byId('theme-reset').addEventListener('click', clearImage);
    byId('theme-default').addEventListener('click', clearImage);
    document.addEventListener('klaude-view', clearImage);
    document.addEventListener('klaude-auth-reset', clearImage);
    new MutationObserver(() => { if (byId('theme-settings').hidden) clearImage(); }).observe(
      byId('theme-settings'), { attributes: true, attributeFilter: ['hidden'] });

    // One bounded, interruptible ripple per pressed button. The state layer is a
    // pseudo element, leaving labels/DOM identity and all existing handlers alone.
    const ripples = new WeakMap();
    function press(button, x, y) {
      if (!button || button.disabled || reduced() || button.matches('.file-open, .cp-file-preview')) return;
      const box = button.getBoundingClientRect();
      button.style.setProperty('--ripple-x', `${x ?? box.width / 2}px`);
      button.style.setProperty('--ripple-y', `${y ?? box.height / 2}px`);
      ripples.get(button)?.cancel();
      const ripple = button.animate([{ opacity: .18, transform: 'scale(0)' },
        { opacity: .08, offset: .7, transform: 'scale(1)' }, { opacity: 0, transform: 'scale(1)' }],
        { duration: 1200, easing: 'cubic-bezier(0,0,0,1)', pseudoElement: '::after' });
      ripples.set(button, ripple);
    }
    document.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      const button = closest(event.target, 'button, a.icon-button'); if (!button) return;
      const box = button.getBoundingClientRect(); press(button, event.clientX - box.left, event.clientY - box.top);
    });
    document.addEventListener('keydown', event => {
      if (!event.repeat && ['Enter', ' '].includes(event.key)) press(closest(event.target, 'button, a.icon-button'));
    });
    // Native radios retain their arrow/Space behavior. Independent toolbar
    // buttons gain the same predictable Home/End and arrow-key navigation.
    document.addEventListener('keydown', event => {
      const group = closest(event.target, '.section-chips, .file-view-modes, .cp-view-modes, .connection-filters');
      if (event.defaultPrevented || !group || group.getAttribute('role') === 'tablist' ||
          !group.querySelector('[aria-pressed]') || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      const buttons = [...group.querySelectorAll('button')].filter(button => !button.disabled && !button.hidden);
      const index = buttons.indexOf(event.target); if (index < 0) return;
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
        (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
      event.preventDefault(); buttons[next].focus(); buttons[next].click();
    });
    // Spatial gallery navigation uses actual rendered cell positions, so columns
    // adapt to panel width without a second layout implementation.
    document.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key) || event.altKey || event.ctrlKey || event.metaKey) return;
      const button = closest(event.target, '.file-open'), grid = button?.closest('[data-view]');
      if (!grid) return;
      const buttons = [...grid.querySelectorAll('.file-open')], index = buttons.indexOf(button);
      const rect = button.getBoundingClientRect();
      let next;
      if (event.key === 'Home') next = buttons[0];
      else if (event.key === 'End') next = buttons.at(-1);
      else if (['ArrowLeft', 'ArrowRight'].includes(event.key)) next = buttons[index + (event.key === 'ArrowRight' ? 1 : -1)];
      else {
        const direction = event.key === 'ArrowDown' ? 1 : -1;
        next = buttons.filter(candidate => (candidate.getBoundingClientRect().top - rect.top) * direction > 4)
          .sort((a, b) => {
            const score = candidate => { const r = candidate.getBoundingClientRect();
              return Math.abs(r.top - rect.top) * 2 + Math.abs(r.left - rect.left); };
            return score(a) - score(b);
          })[0];
      }
      if (next) { event.preventDefault(); next.focus({ preventScroll: true }); next.scrollIntoView({ block: 'nearest' }); }
    });
    setupTooltips();
    setupCommands();
  }
  function setupTooltips() {
    const tooltip = document.createElement('div'); tooltip.id = 'expressive-tooltip';
    tooltip.className = 'expressive-tooltip'; tooltip.setAttribute('role', 'tooltip'); tooltip.setAttribute('popover', 'manual');
    document.body.append(tooltip); let target, nativeTitle = '';
    function hide() {
      if (target) {
        const descriptions = (target.getAttribute('aria-describedby') || '').split(/\s+/).filter(id => id && id !== tooltip.id);
        if (descriptions.length) target.setAttribute('aria-describedby', descriptions.join(' ')); else target.removeAttribute('aria-describedby');
        if (nativeTitle && !target.getAttribute('title')) target.setAttribute('title', nativeTitle);
      }
      target = null; nativeTitle = ''; if (tooltip.matches(':popover-open')) tooltip.hidePopover();
      tooltip.textContent = '';
    }
    function show(element) {
      if (!element || element === target) return;
      hide(); const label = element.getAttribute('data-tooltip') || element.getAttribute('title') || element.getAttribute('aria-label');
      if (!label) return;
      target = element; nativeTitle = element.getAttribute('title') || ''; if (nativeTitle) element.setAttribute('title', '');
      tooltip.textContent = label;
      element.setAttribute('aria-describedby', [element.getAttribute('aria-describedby'), tooltip.id].filter(Boolean).join(' '));
      const viewport = window.visualViewport, inset = 8, gap = 10;
      const viewportLeft = viewport?.offsetLeft || 0, viewportTop = viewport?.offsetTop || 0;
      const width = viewport?.width || innerWidth, height = viewport?.height || innerHeight;
      tooltip.style.maxWidth = `${Math.max(0, Math.min(280, width - inset * 2))}px`;
      // Measure from an unconstrained position after viewport/anchor changes.
      tooltip.style.left = `${viewportLeft + inset}px`; tooltip.style.top = `${viewportTop + inset}px`;
      tooltip.showPopover();
      const rect = element.getBoundingClientRect(), box = tooltip.getBoundingClientRect();
      const left = Math.max(viewportLeft + inset, Math.min(viewportLeft + width - box.width - inset,
        rect.left + (rect.width - box.width) / 2));
      const above = rect.top - viewportTop - inset, below = viewportTop + height - inset - rect.bottom;
      const placeBelow = below >= box.height + gap || above < box.height + gap && below >= above;
      tooltip.dataset.placement = placeBelow ? 'bottom' : 'top';
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${Math.max(viewportTop + inset, Math.min(viewportTop + height - box.height - inset,
        placeBelow ? rect.bottom + gap : rect.top - box.height - gap))}px`;
      tooltip.style.setProperty('--tooltip-arrow-x', `${Math.max(10, Math.min(box.width - 10,
        rect.left + rect.width / 2 - left))}px`);
    }
    const owner = event => closest(event.target, '[title], .icon-button[aria-label], [data-tooltip]');
    document.addEventListener('pointerover', event => { if (event.pointerType !== 'touch') show(owner(event)); });
    document.addEventListener('pointerout', event => { if (target && !target.contains(event.relatedTarget)) hide(); });
    document.addEventListener('focusin', event => { if (event.target instanceof Element && event.target.matches(':focus-visible')) show(owner(event)); });
    document.addEventListener('focusout', hide);
    document.addEventListener('pointerdown', hide);
    document.addEventListener('scroll', hide, true);
    document.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
    window.addEventListener('resize', hide);
    window.visualViewport?.addEventListener('resize', hide);
    window.visualViewport?.addEventListener('scroll', hide);
    document.addEventListener('klaude-auth-reset', hide);
  }
  function setupCommands() {
    const text = (tag, value, className = '') => { const element = document.createElement(tag);
      element.textContent = value; element.className = className; return element; };
    const mac = /Mac|iPhone|iPad/.test(navigator.platform), mod = mac ? '⌘' : 'Ctrl';
    const trigger = text('button', '', 'icon-button command-trigger'); trigger.id = 'command-open'; trigger.type = 'button';
    trigger.setAttribute('aria-label', 'Search commands'); trigger.title = `Search commands (${mod}+K)`;
    trigger.setAttribute('aria-haspopup', 'dialog'); trigger.setAttribute('aria-controls', 'command-palette');
    trigger.append(libraryIcon('search')); document.querySelector('.topbar-actions').prepend(trigger);
    const dialog = text('dialog', '', 'command-palette domain-dialog'); dialog.id = 'command-palette';
    dialog.setAttribute('aria-labelledby', 'command-title');
    const heading = text('div', '', 'dialog-heading'), title = text('h2', 'Find your next action'); title.id = 'command-title';
    const close = text('button', '', 'icon-button quiet'); close.type = 'button'; close.setAttribute('aria-label', 'Close commands');
    close.append(libraryIcon('close'));
    close.onclick = () => dialog.close(); heading.append(title, close);
    const search = text('input', ''); search.id = 'command-query'; search.type = 'search'; search.placeholder = 'Search commands, pages and conversations…';
    search.setAttribute('aria-label', 'Search commands'); search.setAttribute('role', 'combobox'); search.setAttribute('aria-autocomplete', 'list');
    search.setAttribute('aria-expanded', 'true'); search.setAttribute('aria-controls', 'command-results');
    const modes = text('div', '', 'section-chips command-modes'); modes.setAttribute('role', 'group'); modes.setAttribute('aria-label', 'Command search mode');
    const results = text('div', '', 'command-results'); results.id = 'command-results'; results.setAttribute('role', 'listbox'); results.setAttribute('aria-label', 'Commands');
    const status = text('p', '', 'muted command-count'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
    const footer = text('div', '↑ ↓ to explore · Enter to open · Esc to close', 'command-footer muted');
    let mode = 'commands', active = 0, actions = [], origin;
    for (const [value, label] of [['commands', 'Commands'], ['shortcuts', 'Shortcuts']]) {
      const button = text('button', label, 'quiet'); button.type = 'button'; button.dataset.mode = value;
      button.onclick = () => { mode = value; active = 0; render(); search.focus(); }; modes.append(button);
    }
    dialog.append(heading, search, modes, results, status, footer); document.body.append(dialog);
    const shortcuts = () => [
      ['Navigation', 'Search commands', `${mod}+K`], ['Navigation', 'Keyboard shortcuts', `${mod}+Shift+/`],
      ['Navigation', 'Open Settings', `${mod}+,`], ['Chat', 'Send message', enterSends() ? 'Enter' : 'Send button'],
      ['Chat', 'New line', enterSends() ? 'Shift+Enter' : 'Enter'],
      ['Dialogs', 'Dismiss dialog or menu', 'Esc'], ['Controls', 'Move between choices', '← → / ↑ ↓'],
      ['Library', 'Move between files', '← → ↑ ↓'], ['Library', 'First / last file', 'Home / End'],
      ['File preview', 'Previous / next image', '← / →'], ['File preview', 'Zoom', '+ / −'],
    ];
    function commands() {
      const pages = [['chat', 'Chat'], ['workspace', 'Workspaces'], ['library', 'Library'], ['store', 'Store'],
        ['integrations', 'Integrations'], ['activity', 'Activity'], ['settings', 'Settings']];
      const available = pages.map(([page, label]) => ({ group: 'Navigate', label: `Open ${label}`, run: () => showView(page) }));
      available.push({ group: 'Chat', label: 'Switch model', run: () => { showView('chat'); window.MobileChatUI?.openModels(); } },
        { group: 'Chat', label: 'Find a conversation', run: () => { toggleSessions(true); byId('session-search').focus(); } },
        { group: 'Chat', label: 'Toggle Context Panel', run: () => byId('inspector-toggle').click() },
        { group: 'Help', label: 'Show keyboard shortcuts', run: () => open('shortcuts') });
      if (!byId('new-session').disabled) available.push({ group: 'Chat', label: 'New conversation', run: () => byId('new-session').click() });
      if (!byId('cancel').disabled && !byId('cancel').hidden) available.push({ group: 'Chat', label: 'Cancel current turn', run: () => byId('cancel').click() });
      if (latest?.parallel_sessions || !latest?.active_turn_id && !latest?.queue?.length) for (const session of sessions.slice(0, 30)) {
        const id = session.id || session.session_id;
        if (id && id !== latest?.session_id && session.resumable) available.push({ group: 'Conversations', label: session.title || session.name || id, run: () => switchSession(id) });
      }
      return available;
    }
    function select(index) {
      active = Math.max(0, Math.min(actions.length - 1, index));
      for (const [i, option] of [...results.querySelectorAll('[role="option"]')].entries()) option.setAttribute('aria-selected', String(i === active));
      const selected = results.querySelector('[aria-selected="true"]');
      if (selected) { search.setAttribute('aria-activedescendant', selected.id); selected.scrollIntoView({ block: 'nearest' }); }
      else search.removeAttribute('aria-activedescendant');
    }
    function render() {
      for (const button of modes.children) button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
      const query = search.value.trim().toLocaleLowerCase();
      const all = mode === 'shortcuts' ? shortcuts().map(([group, label, key]) => ({ group, label, key })) : commands();
      actions = all.filter(action => `${action.group} ${action.label} ${action.key || ''}`.toLocaleLowerCase().includes(query));
      results.replaceChildren(); let previous = '', group;
      for (const [index, action] of actions.entries()) {
        if (action.group !== previous) {
          group = text('div', ''); group.setAttribute('role', 'group'); group.setAttribute('aria-label', action.group);
          const label = text('h3', action.group); label.setAttribute('aria-hidden', 'true'); group.append(label);
          results.append(group); previous = action.group;
        }
        const option = text('div', '', 'command-option'); option.id = `command-option-${index}`; option.setAttribute('role', 'option');
        option.append(text('span', action.label)); if (action.key) option.append(text('kbd', action.key));
        option.onclick = () => execute(index); group.append(option);
      }
      status.textContent = actions.length ? `${actions.length} ${mode === 'shortcuts' ? 'shortcuts' : 'actions'}` : 'No matches. Try a page or conversation name.';
      footer.hidden = mode === 'shortcuts'; select(0);
    }
    function execute(index) {
      const action = actions[index]; if (!action?.run) return;
      const run = action.run; dialog.close(); run();
    }
    function open(next = 'commands') {
      if (!authenticated || document.querySelector('dialog[open]')) return;
      origin = document.activeElement; mode = next; search.value = ''; dialog.showModal(); render(); search.focus();
    }
    trigger.onclick = () => open(); search.addEventListener('input', render);
    search.addEventListener('keydown', event => {
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        if (['Home', 'End'].includes(event.key) && search.value) return;
        event.preventDefault(); select(event.key === 'Home' ? 0 : event.key === 'End' ? actions.length - 1 : active + (event.key === 'ArrowDown' ? 1 : -1));
      } else if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); execute(active); }
    });
    dialog.addEventListener('close', () => { search.value = ''; results.replaceChildren();
      if (origin?.isConnected && !origin.closest('[hidden], [inert]')) origin.focus({ preventScroll: true }); });
    dialog.addEventListener('keydown', event => {
      if (event.key === 'Escape') { event.preventDefault(); dialog.close(); }
    });
    document.addEventListener('klaude-auth-reset', () => { if (dialog.open) dialog.close(); trigger.hidden = true; });
    document.addEventListener('klaude-snapshot', () => { trigger.hidden = !authenticated; });
    document.addEventListener('keydown', event => {
      if (!authenticated || event.repeat || event.isComposing || event.altKey || !(mac ? event.metaKey : event.ctrlKey)) return;
      if (event.key.toLowerCase() === 'k' && !event.shiftKey) { event.preventDefault(); if (dialog.open) dialog.close(); else open(); }
      else if ((event.key === '?' || event.code === 'Slash') && event.shiftKey) { event.preventDefault(); open('shortcuts'); }
      else if (event.key === ',' && !event.shiftKey && !document.querySelector('dialog[open]')) { event.preventDefault(); showView('settings'); }
    });
    trigger.hidden = !authenticated;
  }
  function workspace(result, source, operation, path) {
    const pre = result.querySelector('pre');
    if (operation === 'file') {
      const language = typeof sourceLanguage === 'function' ? sourceLanguage({ filename: path }) : 'text';
      const code = document.createElement('code');
      if (window.ChatMarkdown?.highlight) ChatMarkdown.highlight(code, source, language);
      else code.textContent = source;
      pre.replaceChildren(code); pre.tabIndex = 0; pre.setAttribute('aria-label', `File contents: ${path}`);
      const toolbar = document.createElement('div'); toolbar.className = 'workspace-preview-toolbar';
      const type = document.createElement('span'); type.textContent = language === 'text' ? 'Plain text' : language.toUpperCase();
      const status = document.createElement('span'); status.setAttribute('role', 'status'); status.className = 'muted';
      const copy = document.createElement('button'); copy.type = 'button'; copy.className = 'quiet'; copy.textContent = 'Copy preview';
      copy.onclick = async () => {
        copy.disabled = true;
        const copied = await window.ChatMarkdown?.copyText(source);
        if (status.isConnected) status.textContent = copied ? 'Preview copied.' : 'Select the preview text to copy it.';
        copy.disabled = false;
      };
      toolbar.append(type, status, copy); result.insertBefore(toolbar, pre);
      return;
    }
    if (operation === 'diff') {
      pre.classList.add('workspace-diff'); pre.replaceChildren();
      for (const line of source.split('\n')) {
        const row = document.createElement('span'); row.textContent = line || '\u00a0';
        row.className = line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@') || line.startsWith('diff ') ?
          'diff-heading' : line.startsWith('+') ? 'diff-added' : line.startsWith('-') ? 'diff-removed' : '';
        pre.append(row);
      }
      return;
    }
    if (operation !== 'files') return;
    // Parse only the service's documented d/f rows. Ambiguous filenames retain
    // the original text response; every navigation still passes the server jail.
    const lines = source.split('\n');
    if (source !== '(empty)' && !lines.every(line => /^[df] [^\x00-\x1f]+$/.test(line))) return;
    const crumbs = document.createElement('nav'); crumbs.className = 'workspace-breadcrumbs'; crumbs.setAttribute('aria-label', 'Workspace path');
    const navigate = (next, kind = 'files') => { byId('workspace-path').value = next; workspaceRead(kind); };
    function crumb(label, next) { const button = document.createElement('button'); button.type = 'button'; button.className = 'quiet';
      button.textContent = label; button.onclick = () => navigate(next); crumbs.append(button); }
    crumb('Workspace', '.');
    const parts = path.replace(/^\.\//, '').split('/').filter(part => part && part !== '.');
    if (!path.startsWith('/') && !parts.includes('..')) parts.forEach((part, index) => crumb(part, parts.slice(0, index + 1).join('/')));
    result.insertBefore(crumbs, pre);
    if (source === '(empty)') { pre.textContent = 'This directory is empty.'; return; }
    const list = document.createElement('div'); list.className = 'workspace-files'; list.setAttribute('role', 'list');
    for (const line of lines) {
      const directory = line[0] === 'd', filePath = line.slice(2);
      const button = document.createElement('button'); button.type = 'button'; button.className = 'workspace-file-row';
      const icon = document.createElementNS(svgNS, 'svg'); icon.setAttribute('viewBox', '0 0 24 24'); icon.classList.add('icon'); icon.setAttribute('aria-hidden', 'true');
      const outline = document.createElementNS(svgNS, 'path'); outline.setAttribute('fill', 'none'); outline.setAttribute('stroke', 'currentColor'); outline.setAttribute('stroke-width', '1.7');
      outline.setAttribute('d', directory ? 'M3 6h7l2 2h9v12H3Z' : 'M5 3h9l5 5v13H5ZM14 3v6h5M8 13h8M8 17h5'); icon.append(outline);
      const name = document.createElement('span'); name.textContent = filePath.split('/').at(-1);
      const kind = document.createElement('small'); kind.textContent = directory ? 'Folder' :
        name.textContent.includes('.') ? name.textContent.split('.').at(-1).toUpperCase() : 'File';
      button.append(icon, name, kind); button.setAttribute('aria-label', `${directory ? 'Open folder' : 'Read file'} ${filePath}`);
      button.onclick = () => navigate(filePath, directory ? 'files' : 'file');
      const item = document.createElement('div'); item.setAttribute('role', 'listitem'); item.append(button); list.append(item);
    }
    pre.replaceWith(list);
  }
  document.addEventListener('DOMContentLoaded', setup, { once: true });
  return Object.freeze({ shape, themePreview, reduced, workspace });
})();

// Shared credential decoration. Native password controls remain the sole owner
// of secret values, selection, form submission and password-manager integration.
window.KlaudeSecretFields = (() => {
  const sequence = ['clover-4', 'arrow', 'pill', 'soft-burst', 'diamond', 'clam-shell', 'pentagon'];
  const fields = new Map();
  function sync(input, state) {
    if (input.type !== 'password') return;
    const length = input.value.length, start = input.selectionStart ?? length, end = input.selectionEnd ?? length;
    const focused = document.activeElement === input;
    const css = getComputedStyle(input), left = parseFloat(css.paddingLeft) + parseFloat(css.borderLeftWidth);
    const right = parseFloat(css.paddingRight) + parseFloat(css.borderRightWidth);
    const width = Math.max(0, input.offsetWidth - left - right);
    state.mask.style.left = `${left}px`; state.mask.style.right = `${right}px`;
    let scroll = input.scrollLeft;
    if (focused && start === end) {
      if (end * 20 - scroll > width - 2) scroll = Math.max(0, end * 20 - width + 2);
      else if (end * 20 < scroll) scroll = end * 20;
      input.scrollLeft = scroll;
    }
    // Render only visible slots, even for long pasted API credentials.
    const first = Math.max(0, Math.floor(scroll / 20)), last = Math.min(length, first + Math.ceil(width / 20) + 1);
    const key = [first, last, start, end, scroll, focused, width].join(':');
    if (state.key === key) return;
    state.key = key;
    // Keep overlapping slots mounted so typing, selection and focus changes
    // do not restart every shape's entry animation.
    for (const slot of [...state.shapes.children]) {
      const position = Number(slot.dataset.position);
      if (position < first || position >= last) slot.remove();
    }
    let next = state.shapes.firstElementChild;
    for (let i = first; i < last; i++) {
      let slot;
      if (next && Number(next.dataset.position) === i) {
        slot = next; next = next.nextElementSibling;
      } else {
        slot = document.createElement('span'); slot.className = 'password-shape-slot';
        slot.dataset.position = String(i);
        slot.append(window.KlaudeExpressive.shape(sequence[i % sequence.length], 64));
        state.shapes.insertBefore(slot, next);
      }
      slot.classList.toggle('selected', i >= start && i < end);
    }
    state.shapes.style.transform = `translateX(${first * 20 - scroll}px)`;
    state.cursor.style.transform = `translateX(${Math.max(0, Math.min(width - 2, end * 20 - scroll))}px)`;
    state.cursor.hidden = !focused || start !== end || !length;
  }
  function enhance(input) {
    if (input.id === 'login-password' || fields.has(input)) return;
    try {
      if (!sequence.every(name => window.KlaudeExpressive.shape(name, 64).querySelector('path[d]'))) return;
    } catch { return; }
    const wrapper = document.createElement('span'); wrapper.className = 'secret-shape-field';
    const mask = document.createElement('span'); mask.className = 'secret-shape-mask'; mask.setAttribute('aria-hidden', 'true');
    const shapes = document.createElement('span'); shapes.className = 'secret-shape-slots';
    const cursor = document.createElement('span'); cursor.className = 'shape-password-cursor'; cursor.hidden = true;
    input.before(wrapper); wrapper.append(input, mask); mask.append(shapes, cursor);
    const state = { mask, shapes, cursor, key: '' }; fields.set(input, state);
    for (const event of ['input', 'select', 'click', 'keyup', 'focus', 'blur', 'scroll', 'compositionend'])
      input.addEventListener(event, () => sync(input, state));
    sync(input, state);
  }
  function refresh() {
    document.querySelectorAll('input[type="password"]').forEach(enhance);
    for (const [input, state] of fields) {
      if (!input.isConnected) { fields.delete(input); continue; }
      if (input.getClientRects().length) sync(input, state);
    }
  }
  function setup() {
    refresh();
    // Covers dynamically mounted dialogs and credential fields, without watching
    // our decorative child nodes and recursively triggering the observer.
    new MutationObserver(records => {
      if (records.some(record => record.type === 'attributes' || [...record.addedNodes].some(node =>
        node.nodeType === 1 && (node.matches('input[type="password"]') || node.querySelector('input[type="password"]'))))) refresh();
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['type'] });
    document.addEventListener('selectionchange', refresh);
    document.addEventListener('reset', () => setTimeout(refresh, 0));
    window.addEventListener('resize', refresh);
    // Autofill and application-owned .value assignments need not emit input.
    setInterval(() => { if (!document.hidden) refresh(); }, 250);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', setup, { once: true });
  else setup();
  return Object.freeze({ refresh });
})();
