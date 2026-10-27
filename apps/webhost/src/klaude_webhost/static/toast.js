/* Transient feedback, bundled into app.js without a new static route. */
window.KlaudeToast = (() => {
  const stacks = new Map(), entries = new Set();
  const make = (tag, className, value) => {
    const node = document.createElement(tag); node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  };
  function mount(stack) {
    const parent = [...document.querySelectorAll('dialog[open]')].at(-1) || document.body;
    if (stack.parentElement !== parent) parent.append(stack);
    if (stack.childElementCount && !stack.matches(':popover-open')) stack.showPopover();
  }
  function stackFor(position) {
    if (!stacks.has(position)) {
      const stack = make('section', 'toast-stack');
      stack.dataset.position = position; stack.setAttribute('popover', 'manual');
      stack.setAttribute('aria-label', `${position === 'top' ? 'Top' : 'Bottom'} notifications`);
      stacks.set(position, stack);
    }
    return stacks.get(position);
  }
  function remove(entry) {
    clearTimeout(entry.timer); clearTimeout(entry.exitTimer);
    entries.delete(entry); entry.node.remove();
    if (!entry.stack.childElementCount && entry.stack.matches(':popover-open')) entry.stack.hidePopover();
  }
  function dismiss(entry) {
    if (entry.closing || !entries.has(entry)) return;
    entry.closing = true; clearTimeout(entry.timer);
    if (entry.node.contains(document.activeElement) && entry.origin?.isConnected) entry.origin.focus({ preventScroll: true });
    entry.node.classList.add('toast-closing');
    const reduced = document.documentElement.dataset.motion === 'reduced' || matchMedia('(prefers-reduced-motion: reduce)').matches;
    entry.exitTimer = setTimeout(() => remove(entry), reduced ? 0 : 200);
  }
  function resume(entry) {
    clearTimeout(entry.timer);
    if (entry.closing || entry.hovered || entry.node.contains(document.activeElement)) return;
    entry.started = performance.now();
    entry.timer = setTimeout(() => dismiss(entry), entry.remaining);
  }
  function pause(entry) {
    if (entry.timer) entry.remaining = Math.max(0, entry.remaining - (performance.now() - entry.started));
    clearTimeout(entry.timer); entry.timer = null;
  }
  function show(message, { variant = 'info', position = 'top' } = {}) {
    message = String(message || '').trim();
    if (!message) return;
    position = position === 'bottom' ? 'bottom' : 'top';
    variant = ['error', 'success'].includes(variant) ? variant : 'info';
    const duplicate = [...entries].find(entry => !entry.closing && entry.message === message && entry.variant === variant && entry.position === position);
    if (duplicate) return () => dismiss(duplicate);
    const stack = stackFor(position), node = make('article', 'toast');
    node.dataset.variant = variant;
    const icon = make('span', 'toast-icon', variant === 'error' ? '!' : variant === 'success' ? '✓' : 'i');
    icon.setAttribute('aria-hidden', 'true');
    const content = make('div', 'toast-message', message);
    content.setAttribute('role', variant === 'error' ? 'alert' : 'status');
    content.setAttribute('aria-atomic', 'true');
    const close = make('button', 'toast-close quiet');
    close.type = 'button'; close.setAttribute('aria-label', 'Dismiss notification');
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', 'm6 6 12 12M18 6 6 18');
    svg.append(path); close.append(svg); node.append(icon, content, close);
    const entry = { node, stack, message, position, variant, remaining: 5000, origin: document.activeElement };
    entries.add(entry);
    close.addEventListener('click', () => dismiss(entry));
    node.addEventListener('pointerenter', () => { pause(entry); entry.hovered = true; });
    node.addEventListener('pointerleave', () => { entry.hovered = false; resume(entry); });
    node.addEventListener('focusin', () => pause(entry));
    node.addEventListener('focusout', () => queueMicrotask(() => resume(entry)));
    if (position === 'top') stack.prepend(node); else stack.append(node);
    const siblings = [...entries].filter(item => item.position === position);
    if (siblings.length > 5) remove(siblings[0]);
    mount(stack); resume(entry);
    return () => dismiss(entry);
  }
  function clear() { for (const entry of [...entries]) remove(entry); }
  // Keep notifications operable above native modal viewers and reviews.
  new MutationObserver(records => {
    if (records.some(record => record.target.tagName === 'DIALOG')) {
      for (const stack of stacks.values()) if (stack.childElementCount) mount(stack);
    }
  }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['open'] });
  for (const event of ['klaude-auth-reset', 'klaude-chat-session-changed']) document.addEventListener(event, clear);
  return Object.freeze({ show, clear });
})();
