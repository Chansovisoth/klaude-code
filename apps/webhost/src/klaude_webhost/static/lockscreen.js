"use strict";

// Independent browser adaptation of measured end-4 presentation. Geometry is
// exported from the existing Apache-2.0 Google Material / AndroidX pipeline.
// Source map, licenses and browser deviations: docs/webui/lockscreen-validation.md.
window.KlaudeLockScreen = (() => {
  const screen = document.getElementById('local-access');
  if (!screen) return null;
  const root = document.documentElement, by = id => document.getElementById(id);
  const password = by('login-password'), field = by('lock-password-field');
  const shapes = by('lock-password-shapes'), mask = field.querySelector('.shape-password-mask');
  const sequence = Object.freeze(['clover-4', 'arrow', 'pill', 'soft-burst', 'diamond', 'clam-shell', 'pentagon']);
  const svgNS = 'http://www.w3.org/2000/svg';
  let clockTimer = null, exitTimer = null, visible = false, lastMinute = '', maskState = '';
  let activeState = 'Locked', maskReady = false;
  const iconPaths = {
    lock: 'M7 10V7a5 5 0 0 1 10 0v3M6 10h12v11H6ZM12 14v3',
    account: 'M20 21a8 8 0 0 0-16 0M16 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM23 12a11 11 0 1 1-22 0 11 11 0 0 1 22 0Z',
    arrow: 'M4 12h15M13 6l6 6-6 6',
    globe: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z',
    help: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9 9a3 3 0 1 1 4 3c-1 0-1 1-1 2M12 17h.01',
    reload: 'M20 9a8 8 0 1 0 0 6M20 4v5h-5',
  };
  for (const target of screen.querySelectorAll('[data-lock-icon]')) {
    const svg = document.createElementNS(svgNS, 'svg'), path = document.createElementNS(svgNS, 'path');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2'); svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round'); path.setAttribute('d', iconPaths[target.dataset.lockIcon]);
    svg.append(path); target.append(svg);
  }
  const vector = name => window.KlaudeExpressive.shape(name, 64);
  by('lock-clock-face').append(vector('clock-cookie'));
  by('lock-day-shape').append(vector('pentagon'));
  by('lock-month-shape').append(vector('pill'));
  for (let index = 0; index < 60; index++) {
    const mark = document.createElementNS(svgNS, 'rect');
    const hour = index % 5 === 0;
    mark.setAttribute('x', hour ? '113' : '114'); mark.setAttribute('y', '22');
    mark.setAttribute('width', hour ? '4' : '2'); mark.setAttribute('height', hour ? '18' : '7');
    mark.setAttribute('rx', hour ? '2' : '1');
    mark.setAttribute('transform', `rotate(${index * 6} 115 115)`);
    by('lock-clock-marks').append(mark);
  }

  function clockState(date = new Date()) {
    const hour = date.getHours(), minute = date.getMinutes();
    return { hour: String(hour).padStart(2, '0'), minute: String(minute).padStart(2, '0'),
      day: String(date.getDate()), month: String(date.getMonth() + 1).padStart(2, '0'),
      hourAngle: (hour % 12 + minute / 60) * 30, minuteAngle: minute * 6,
      label: new Intl.DateTimeFormat(undefined, { dateStyle: 'full', timeStyle: 'short' }).format(date) };
  }
  function tick() {
    clearTimeout(clockTimer); clockTimer = null;
    if (!visible || document.hidden) return;
    const date = new Date(), state = clockState(date);
    // Every minute is read from wall time rather than accumulated ticks. A 1Hz
    // wake-up detects wall-clock/timezone changes and silent password autofill;
    // the clock DOM is touched only when its displayed values change.
    const key = JSON.stringify(state);
    if (key !== lastMinute) {
      const previous = by('lock-clock-minute').textContent;
      for (const part of ['hour', 'minute', 'day', 'month']) by('lock-' + (part === 'hour' || part === 'minute' ? 'clock-' : '') + part).textContent = state[part];
      by('lock-clock').setAttribute('aria-label', state.label);
      // SVG rotation uses clockwise unwrapped angles at midnight/hour wrap.
      for (const part of ['hour', 'minute']) {
        const hand = by('lock-' + part + '-hand'), angle = state[part + 'Angle'];
        const old = Number(hand.dataset.angle || angle), unwrapped = angle + Math.ceil((old - angle) / 360) * 360;
        hand.style.transform = `rotate(${unwrapped}deg)`;
        hand.dataset.angle = String(unwrapped);
      }
      if (!previous) screen.classList.add('lock-clock-ready');
      let format;
      try { format = new Intl.DateTimeFormat(undefined, { timeZoneName: 'shortOffset' }); }
      catch { format = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }); }
      by('lock-timezone').textContent = format.formatToParts(date).find(p => p.type === 'timeZoneName')?.value || '';
      by('lock-timezone').parentElement.title = format.resolvedOptions().timeZone;
      lastMinute = key;
    }
    syncPassword();
    clockTimer = setTimeout(tick, 1000 - Date.now() % 1000);
  }

  function syncPassword() {
    if (!maskReady) return;
    // Only length and native selection offsets enter the decorative layer.
    // No character, substring, credential, or hash is retained in this module.
    const length = password.value.length;
    const start = password.selectionStart ?? length, end = password.selectionEnd ?? length;
    const focused = document.activeElement === password, width = mask.clientWidth;
    let scroll = password.scrollLeft;
    // A password manager may replace .value while an already-focused editor
    // retains its old scroll offset. Bring the collapsed caret into view using
    // the same 20px slot advance as the native monospace editor.
    if (focused && start === end) {
      if (end * 20 - scroll > width - 2) password.scrollLeft = Math.max(0, end * 20 - width + 2);
      else if (end * 20 < scroll) password.scrollLeft = end * 20;
      scroll = password.scrollLeft;
    }
    const state = [length, start, end, scroll, width, focused].join(':');
    if (state === maskState) return;
    maskState = state;
    while (shapes.children.length > length) shapes.lastChild.remove();
    while (shapes.children.length < length) {
      const position = shapes.children.length, slot = document.createElement('span');
      slot.className = 'password-shape-slot'; slot.dataset.shape = sequence[position % sequence.length];
      slot.append(vector(slot.dataset.shape)); shapes.append(slot);
    }
    for (let index = 0; index < length; index++) shapes.children[index].classList.toggle('selected', index >= start && index < end);
    shapes.style.transform = `translateX(${-scroll}px)`;
    const cursor = mask.querySelector('.shape-password-cursor');
    cursor.style.transform = `translateX(${Math.max(0, Math.min(width - 2, end * 20 - scroll))}px)`;
    cursor.hidden = !focused || start !== end;
  }
  try {
    maskReady = sequence.every(name => vector(name).querySelector('path[d]'));
    if (maskReady) field.classList.add('shape-mask-ready');
  } catch { maskReady = false; } // Native masked input is the fail-safe.
  for (const event of ['input', 'select', 'click', 'keyup', 'focus', 'blur', 'scroll', 'compositionend'])
    password.addEventListener(event, syncPassword);
  password.addEventListener('input', () => {
    password.removeAttribute('aria-invalid'); field.removeAttribute('data-error');
  });
  password.addEventListener('keydown', event => {
    by('lock-caps').hidden = !event.getModifierState('CapsLock');
    if (event.key === 'Escape') { event.preventDefault(); password.value = ''; syncPassword(); }
  });
  document.addEventListener('selectionchange', () => { if (visible) syncPassword(); });
  document.addEventListener('visibilitychange', tick);
  window.addEventListener('focus', tick); window.addEventListener('pageshow', tick);
  const viewport = () => {
    const view = window.visualViewport;
    if (view && visible) {
      screen.style.setProperty('--lock-viewport-height', `${view.height}px`);
      screen.style.setProperty('--lock-viewport-top', `${view.offsetTop}px`);
      screen.dataset.keyboard = String(view.height < innerHeight - 120);
    }
  };
  function fitQuote() {
    if (!visible) return;
    const container = screen.querySelector('.lock-quote');
    const text = by('lock-quote-text');
    container.style.removeProperty('width');
    const textRange = document.createRange();
    textRange.selectNodeContents(text);
    const lines = [...textRange.getClientRects()];
    if (lines.length < 2) return;
    const originalWidth = container.getBoundingClientRect().width;
    const copyWidth = text.getBoundingClientRect().width;
    const attribution = by('lock-quote-attribution');
    let contentWidth = Math.max(...lines.map(line => line.width));
    if (!attribution.classList.contains('visually-hidden')) {
      const authorRange = document.createRange();
      authorRange.selectNodeContents(attribution);
      contentWidth = Math.max(contentWidth, ...[...authorRange.getClientRects()].map(line => line.width));
    }
    const fittedWidth = Math.ceil(contentWidth + originalWidth - copyWidth + 1);
    if (fittedWidth >= originalWidth) return;
    container.style.width = `${fittedWidth}px`;
    if (textRange.getClientRects().length > lines.length) container.style.removeProperty('width');
  }
  window.visualViewport?.addEventListener('resize', viewport); window.visualViewport?.addEventListener('scroll', viewport);
  window.addEventListener('resize', () => { viewport(); fitQuote(); });
  document.fonts.ready.then(fitQuote);
  by('lock-reload').addEventListener('click', () => location.reload());
  by('lock-reconnect').addEventListener('click', () => by('access-retry').click());
  const help = screen.querySelector('.lock-help');
  document.addEventListener('pointerdown', event => {
    if (help.open && !help.contains(event.target)) help.open = false;
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && help.open) {
      help.open = false;
      help.querySelector('summary').focus({ preventScroll: true });
    }
  });

  function show({ reauthenticate = false, signedOut = false, passwordLogin = true } = {}) {
    if (!visible) {
      const quote = window.KlaudeLockQuotes?.next();
      if (quote) {
        by('lock-quote-text').textContent = quote.quote;
        const attribution = by('lock-quote-attribution');
        attribution.textContent = quote.attribution;
        attribution.classList.toggle('visually-hidden', !quote.attribution || quote.source_kind === 'easter_egg' || quote.attribution === 'Klaude' || /\bproverb\b/i.test(quote.attribution));
        attribution.title = quote.source_kind === 'easter_egg' ?
          quote.origin === 'user_prompt' ? 'User requested Easter egg' : 'Original Klaude Easter egg' :
          quote.source_title ? `${quote.source_title} · entry ${quote.source_entry}` : 'Original Klaude quote';
        const container = screen.querySelector('.lock-quote');
        container.title = attribution.title;
        container.dataset.quoteId = String(quote.id);
        if (quote.source_url) container.setAttribute('cite', quote.source_url);
        else container.removeAttribute('cite');
      }
    }
    clearTimeout(exitTimer); visible = true;
    screen.hidden = false; screen.inert = false; screen.removeAttribute('aria-hidden');
    screen.classList.remove('lock-unlocking');
    root.dataset.access = 'locked';
    document.querySelector('.shell').inert = true;
    document.querySelector('.shell').setAttribute('aria-hidden', 'true');
    for (const dialog of document.querySelectorAll('dialog[open]')) dialog.close();
    for (const popover of document.querySelectorAll(':popover-open')) popover.hidePopover();
    by('login-username').closest('.lock-island').hidden = !passwordLogin;
    by('lock-bootstrap').hidden = passwordLogin;
    by('account-login').hidden = !passwordLogin;
    activeState = !passwordLogin ? 'Connect browser' : reauthenticate ? 'Session expired' : signedOut ? 'Signed out' : 'Locked';
    by('lock-state').textContent = activeState;
    password.readOnly = false; password.removeAttribute('aria-invalid'); field.removeAttribute('data-error');
    syncPassword(); viewport(); fitQuote(); tick();
    if (passwordLogin && matchMedia('(pointer: fine)').matches) password.focus({ preventScroll: true });
  }
  function hide() {
    visible = false; clearTimeout(clockTimer); clockTimer = null;
    root.dataset.access = 'ready';
    const shell = document.querySelector('.shell'), starting = root.dataset.startup === 'loading';
    shell.inert = starting;
    if (starting) shell.setAttribute('aria-hidden', 'true');
    else shell.removeAttribute('aria-hidden');
    screen.inert = true; screen.setAttribute('aria-hidden', 'true');
    by('lock-state').textContent = 'Signed in'; syncPassword();
    screen.classList.add('lock-unlocking');
    clearTimeout(exitTimer);
    if (window.KlaudeExpressive.reduced()) screen.hidden = true;
    else exitTimer = setTimeout(() => { screen.hidden = true; }, 200);
  }
  function pending(value) {
    password.readOnly = value;
    by('account-login').setAttribute('aria-busy', String(value));
    by('lock-state').textContent = value ? 'Signing in…' : visible ? activeState : 'Signed in';
    by('login-submit').setAttribute('aria-label', value ? 'Signing in' : 'Sign in');
  }
  function error() {
    password.value = ''; syncPassword(); password.setAttribute('aria-invalid', 'true');
    field.dataset.error = 'true';
    if (!window.KlaudeExpressive.reduced()) field.animate([
      { transform: 'translateX(0)' }, { transform: 'translateX(-30px)' }, { transform: 'translateX(30px)' },
      { transform: 'translateX(-15px)' }, { transform: 'translateX(15px)' }, { transform: 'translateX(0)' },
    ], { duration: 210 });
    password.focus({ preventScroll: true });
  }
  return Object.freeze({ show, hide, pending, error, syncPassword, fitQuote, clockState, passwordShapes: sequence });
})();
