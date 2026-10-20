"use strict";

// Untrusted model output becomes allowlisted DOM nodes, never executable HTML.
// Parser/highlighter versions, licenses and provenance live in static/vendor.
window.ChatMarkdown = (() => {
  const parser = typeof window.markdownit === "function" ? window.markdownit({
    html: false, linkify: true, typographer: false, breaks: false, maxNesting: 40,
  }) : null;
  const MAX_MARKDOWN = 128000;
  const MAX_TOKENS = 10000;
  const MAX_HIGHLIGHT = 12000;
  const states = new WeakMap();
  const protectedUpdates = new Set();
  let activeSpeech = null;
  let actionDialog = null;
  let dialogOwner = null;
  let messageMenu = null;
  let menuState = null;
  const icons = {
    copy: ["M9 9h11v11H9z", "M5 15H3V3h12v2"],
    check: ["m5 12 4 4L19 6"],
    speaker: ["M11 4 6 8H3v8h3l5 4V4Z", "M15 8a6 6 0 0 1 0 8", "M18 5a10 10 0 0 1 0 14"],
    stop: ["M6 6h12v12H6z"],
    share: ["M18 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "M6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "M18 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z", "m9 10 6-4M9 14l6 4"],
    more: ["M12 4h.01M12 12h.01M12 20h.01"],
    book: ["M12 6C9 3 5 3 2 4v15c3-1 7-1 10 2 3-3 7-3 10-2V4c-3-1-7-1-10 2Zm0 0v15"],
    branch: ["M6 3v12a5 5 0 0 0 5 5h7", "m15 17 3 3-3 3", "M6 11a8 8 0 0 0 8-8", "m11 5 3-3 3 3"],
    retry: ["M20 11a8 8 0 1 0-2 6", "M20 4v7h-7"],
    email: ["M3 5h18v14H3z", "m3 5 9 7 9-7"],
    // Simple Icons 15.13.0, CC0-1.0; see share-icons-LICENSE.txt.
    whatsapp: ["M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"],
    telegram: ["M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"],
    discord: ["M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z"],
  };
  const filledIcons = new Set(["whatsapp", "telegram", "discord"]);
  const aliases = { js: "javascript", ts: "typescript", py: "python", sh: "bash",
    shell: "bash", html: "markup", xml: "markup", yml: "yaml" };
  const tags = new Set(["p", "blockquote", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td", "em", "strong", "s"]);

  function node(tag, text, className) {
    const result = document.createElement(tag);
    if (text !== undefined) result.textContent = text;
    if (className) result.className = className;
    return result;
  }
  function safeHref(value) {
    if (typeof value !== "string" || value.length > 4096 || /[\u0000-\u0020\u007f]/.test(value)) return null;
    try {
      const url = new URL(value);
      return ["http:", "https:", "mailto:"].includes(url.protocol) ? url.href : null;
    } catch { return null; }
  }
  function link(href, title) {
    const safe = safeHref(href);
    const result = node(safe ? "a" : "span");
    if (safe) {
      result.href = safe;
      result.target = "_blank";
      result.rel = "noopener noreferrer";
      result.referrerPolicy = "no-referrer";
    }
    if (title) result.title = title;
    return result;
  }
  function announce(message) {
    document.getElementById("copy-status")?.replaceChildren(document.createTextNode(message));
  }
  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    for (const [key, value] of Object.entries({ viewBox: "0 0 24 24",
      fill: filledIcons.has(name) ? "currentColor" : "none",
      stroke: filledIcons.has(name) ? "none" : "currentColor",
      "stroke-width": name === "more" ? "4" : "1.7", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true", focusable: "false" })) svg.setAttribute(key, value);
    svg.classList.add("icon");
    for (const d of icons[name]) {
      const path = document.createElementNS(svg.namespaceURI, "path");
      path.setAttribute("d", d);
      svg.append(path);
    }
    return svg;
  }
  function actionButton(name, label, text) {
    const button = node("button", undefined, "quiet message-action");
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    button.append(icon(name));
    if (text) button.append(node("span", text));
    return button;
  }
  async function copyText(text, container = document.body) {
    if (navigator.clipboard?.writeText) {
      try { await navigator.clipboard.writeText(text); return true; } catch { /* Try the LAN/HTTP fallback. */ }
    }
    // A selected, offscreen text node supports HTTP/LAN without focusing an
    // input, opening the keyboard, or moving the user's viewport.
    const selection = window.getSelection();
    if (!selection) return false;
    const previous = Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index).cloneRange());
    const source = node("pre", text, "clipboard-source");
    source.setAttribute("aria-hidden", "true");
    container.append(source);
    const range = document.createRange();
    range.selectNodeContents(source);
    let copied = false;
    const exactCopy = (event) => {
      if (event.clipboardData) {
        event.clipboardData.setData("text/plain", text);
        event.preventDefault();
      }
    };
    document.addEventListener("copy", exactCopy, { capture: true, once: true });
    try {
      selection.removeAllRanges();
      selection.addRange(range);
      copied = document.execCommand("copy");
    } catch { /* The browser can deny clipboard access. */ }
    finally {
      document.removeEventListener("copy", exactCopy, true);
      selection.removeAllRanges();
      for (const prior of previous) selection.addRange(prior);
      source.remove();
    }
    return copied;
  }
  function copyButton(getText, label, compact = false, caption = "Copy") {
    const button = compact ? actionButton("copy", label) : node("button", caption, "quiet copy-button");
    button.classList.add("copy-button");
    button.type = "button";
    button.setAttribute("aria-label", label);
    button.addEventListener("click", async () => {
      const success = await copyText(getText());
      if (compact) button.replaceChildren(icon(success ? "check" : "copy"));
      else button.textContent = success ? "Copied" : "Select to copy";
      const copied = label.replace(/^Copy /, "");
      announce(success ? `${copied[0].toUpperCase()}${copied.slice(1)} copied` : "Copy unavailable. Select the text and copy it using your browser.");
      setTimeout(() => {
        if (compact) button.replaceChildren(icon("copy"));
        else button.textContent = caption;
      }, 1800);
    });
    return button;
  }
  function plainText(state) {
    const clone = state.body.cloneNode(true);
    clone.querySelectorAll(".code-toolbar,input").forEach((element) => element.remove());
    clone.querySelectorAll("p,li,h2,h3,h4,h5,h6,blockquote,pre,tr,.markdown-block").forEach((element) => element.append(document.createTextNode("\n")));
    return clone.textContent.trim();
  }
  function openDialog(state, title) {
    if (!actionDialog) {
      actionDialog = node("dialog", undefined, "message-dialog");
      actionDialog.setAttribute("aria-labelledby", "message-dialog-title");
      actionDialog.addEventListener("close", () => {
        // A native close event can arrive after another action reopened it.
        if (!actionDialog.open) { actionDialog.replaceChildren(); dialogOwner = null; }
      });
      actionDialog.addEventListener("click", (event) => {
        if (event.target !== actionDialog) return;
        const bounds = actionDialog.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) actionDialog.close();
      });
      document.body.append(actionDialog);
    }
    const heading = node("div", undefined, "dialog-heading");
    const name = node("h2", title);
    name.id = "message-dialog-title";
    const close = node("button", "Close", "quiet");
    close.type = "button";
    close.addEventListener("click", () => actionDialog.close());
    heading.append(name, close);
    actionDialog.replaceChildren(heading);
    dialogOwner = state.article;
    if (!actionDialog.open) actionDialog.showModal();
    return actionDialog;
  }
  function references(state) {
    const found = new Map();
    function walk(tokens) {
      for (let index = 0; index < tokens.length && found.size < 100; index++) {
        const token = tokens[index];
        if (token.children) walk(token.children);
        if (token.type !== "link_open") continue;
        const href = safeHref(token.attrGet("href"));
        if (!href || !/^https?:/.test(href) || found.has(href)) continue;
        let title = "";
        for (let next = index + 1; next < tokens.length && tokens[next].type !== "link_close"; next++) title += tokens[next].content || "";
        found.set(href, title || href);
      }
    }
    try { for (const group of groups(state.source) || []) walk(group); } catch { /* No parsed references. */ }
    return found;
  }
  function showSources(state) {
    const sources = references(state);
    const dialog = openDialog(state, "Sources");
    dialog.append(node("p", sources.size ? "References linked in this reply." : "No references were included in this reply.", "muted"));
    if (!sources.size) return;
    const list = node("ol", undefined, "message-sources");
    for (const [href, title] of sources) {
      const item = node("li");
      const source = link(href);
      source.append(node("strong", title), node("span", new URL(href).hostname, "muted"));
      item.append(source);
      list.append(item);
    }
    dialog.append(list);
  }
  function shareMessage(state) {
    const messageId = state.article.dataset.id;
    if (!/^[a-f0-9]{32}$/.test(state.sessionId || "") ||
        !/^stored:[1-9]\d{0,18}$/.test(messageId || "")) return;
    // Build a fresh owner-authenticated link; never copy bootstrap fragments,
    // unrelated query parameters, credentials or conversation content.
    const url = new URL(location.pathname, location.origin);
    url.searchParams.set("session", state.sessionId);
    url.searchParams.set("message", messageId);
    const href = url.href;
    const dialog = openDialog(state, "Share message");
    dialog.append(node("p", "Opens this message in its conversation on your Klaude server. Sign-in required.", "muted"));
    const address = node("p", undefined, "message-share-link");
    const anchor = link(href);
    anchor.textContent = href;
    address.append(anchor);
    const actions = node("div", undefined, "message-dialog-actions");
    const copy = copyButton(() => href, "Copy link", false, "Copy link");
    const via = actionButton("share", "Share via", "Share via");
    const status = node("p", "", "muted");
    status.setAttribute("role", "status");
    const targets = node("div", undefined, "message-share-targets");
    targets.setAttribute("role", "group");
    targets.setAttribute("aria-label", "Share to an app");
    let discord;
    let sharing = false;
    for (const [name, destination] of [
      ["WhatsApp", `https://wa.me/?text=${encodeURIComponent(href)}`],
      ["Telegram", `https://t.me/share/url?url=${encodeURIComponent(href)}`],
      ["Discord", null],
      ["Email", `mailto:?subject=Klaude%20message&body=${encodeURIComponent(href)}`],
    ]) {
      const target = destination ? link(destination) : node("button");
      target.dataset.shareApp = name.toLowerCase();
      target.append(icon(name.toLowerCase()), node("span", name));
      target.setAttribute("aria-label", `Share via ${name}`);
      if (name === "Email") target.removeAttribute("target");
      if (name === "Discord") {
        target.type = "button";
        target.title = "Choose Discord in your device’s share sheet";
        discord = target;
        target.addEventListener("click", () => shareToDevice("Discord"));
      }
      targets.append(target);
    }
    const showShareProblem = (message, preferredApp) => {
      if (!dialog.open || !state.article.isConnected || dialogOwner !== state.article) return;
      status.textContent = message;
      if (!preferredApp) targets.querySelector("a").focus({ preventScroll: true });
    };
    async function shareToDevice(preferredApp = "") {
      if (sharing) return;
      sharing = true;
      via.disabled = discord.disabled = true;
      status.textContent = preferredApp ? "Choose Discord in your device’s share sheet." : "";
      const fallback = preferredApp ?
        "Use your browser’s Share menu to choose Discord, or use Copy link." :
        "Choose an app below.";
      try {
        if (!window.isSecureContext) {
          showShareProblem(`Your browser needs HTTPS to open the system share sheet. ${fallback}`, preferredApp);
          return;
        }
        if (typeof navigator.share !== "function") {
          showShareProblem(`System sharing is unavailable in this browser. ${fallback}`, preferredApp);
          return;
        }
        const data = { title: "Klaude message", url: href };
        if (typeof navigator.canShare === "function" && !navigator.canShare(data)) {
          showShareProblem(`Your browser cannot share this link with the system. ${fallback}`, preferredApp);
          return;
        }
        // Keep this call in the click's activation; no network/clipboard awaits
        // before invoking the native iOS, Android or desktop sharing mechanism.
        await navigator.share(data);
        status.textContent = "";
      } catch (error) {
        if (error.name === "AbortError") { status.textContent = ""; return; }
        showShareProblem(error.name === "InvalidStateError" ?
          `Another share window is open. Finish it and try again. ${fallback}` :
          `Your browser could not open system sharing. ${fallback}`, preferredApp);
      } finally { sharing = false; via.disabled = discord.disabled = false; }
    }
    via.addEventListener("click", () => shareToDevice());
    actions.append(copy, via);
    dialog.append(address, actions, targets, status);
  }
  function stopSpeech() {
    if (!activeSpeech) return;
    const previous = activeSpeech;
    activeSpeech = null;
    window.speechSynthesis?.cancel();
    previous.state.speak.replaceChildren(icon("speaker"));
    previous.state.speak.setAttribute("aria-label", "Read aloud");
    previous.state.speak.title = "Read aloud";
    previous.state.speak.setAttribute("aria-pressed", "false");
  }
  function readAloud(state) {
    if (activeSpeech?.state === state) { stopSpeech(); announce("Reading stopped"); return; }
    stopSpeech();
    const text = plainText(state);
    if (!text) return;
    const speech = { state, remaining: text, utterance: null };
    activeSpeech = speech;
    state.speak.replaceChildren(icon("stop"));
    state.speak.setAttribute("aria-label", "Stop reading");
    state.speak.title = "Stop reading";
    state.speak.setAttribute("aria-pressed", "true");
    function next() {
      if (activeSpeech !== speech) return;
      if (!state.article.isConnected || !speech.remaining) { stopSpeech(); return; }
      let end = Math.min(1200, speech.remaining.length);
      if (end < speech.remaining.length) {
        const space = speech.remaining.lastIndexOf(" ", end);
        if (space > 600) end = space;
      }
      const utterance = new SpeechSynthesisUtterance(speech.remaining.slice(0, end));
      speech.remaining = speech.remaining.slice(end).trimStart();
      utterance.lang = document.documentElement.lang || navigator.language;
      const voices = window.speechSynthesis.getVoices();
      const voice = voices.find((item) => item.localService && item.lang.split("-")[0] === utterance.lang.split("-")[0]);
      if (voice) utterance.voice = voice;
      utterance.onend = next;
      utterance.onerror = () => {
        if (activeSpeech !== speech) return;
        stopSpeech();
        announce("Read aloud is unavailable. Check your device's speech voices and try again.");
      };
      speech.utterance = utterance;
      try { window.speechSynthesis.speak(utterance); }
      catch { utterance.onerror(); }
    }
    next();
  }
  function closeMenu(restoreFocus = false) {
    if (!menuState) return;
    const state = menuState;
    menuState = null;
    if (typeof messageMenu.hidePopover === "function") {
      if (messageMenu.matches(":popover-open")) messageMenu.hidePopover();
    } else messageMenu.hidden = true;
    state.more.setAttribute("aria-expanded", "false");
    if (restoreFocus && state.more.isConnected) state.more.focus({ preventScroll: true });
  }
  function positionMenu() {
    if (!menuState) return;
    const bounds = menuState.more.getBoundingClientRect();
    const menu = messageMenu.getBoundingClientRect();
    messageMenu.style.left = `${Math.max(12, Math.min(bounds.left, innerWidth - menu.width - 12))}px`;
    const below = bounds.bottom + 6;
    messageMenu.style.top = `${Math.max(12, below + menu.height <= innerHeight - 12 ? below : bounds.top - menu.height - 6)}px`;
  }
  function showMessageMenu(state) {
    if (menuState === state) { closeMenu(true); return; }
    closeMenu();
    if (!messageMenu) {
      messageMenu = node("div", undefined, "message-menu");
      messageMenu.id = "message-options-menu";
      messageMenu.setAttribute("role", "menu");
      messageMenu.setAttribute("aria-label", "Message options");
      if (typeof messageMenu.showPopover === "function") messageMenu.setAttribute("popover", "auto");
      else messageMenu.hidden = true;
      messageMenu.addEventListener("toggle", () => {
        if (menuState && !messageMenu.matches(":popover-open")) closeMenu();
      });
      messageMenu.addEventListener("keydown", (event) => {
        const items = [...messageMenu.querySelectorAll("[role=menuitem]:not(:disabled)")];
        const index = items.indexOf(document.activeElement);
        let next;
        if (event.key === "ArrowDown") next = (index + 1) % items.length;
        if (event.key === "ArrowUp") next = (index - 1 + items.length) % items.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = items.length - 1;
        if (next !== undefined && items.length) { event.preventDefault(); items[next].focus(); }
        if (event.key === "Escape") { event.preventDefault(); closeMenu(true); }
        if (event.key === "Tab") closeMenu();
      });
      document.body.append(messageMenu);
    }
    menuState = state;
    const timestamp = node("time", "Time unavailable", "message-menu-time");
    if (Number.isFinite(state.createdAt) && state.createdAt > 0) {
      const date = new Date(state.createdAt * 1000);
      timestamp.dateTime = date.toISOString();
      timestamp.textContent = `${new Intl.DateTimeFormat(undefined, { month: "long", day: "numeric" }).format(date)}, ${new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", hour12: true }).format(date).toLowerCase()}`;
    }
    const separator = node("div", undefined, "message-menu-divider");
    separator.setAttribute("role", "separator");
    messageMenu.replaceChildren(timestamp, separator);
    for (const [action, label] of [["branch", "Branch in new chat"], ["retry", "Retry"]]) {
      const button = actionButton(action, label, label);
      button.setAttribute("role", "menuitem");
      button.disabled = !state.canAct || !state.onAction;
      if (action === "retry") button.title = "Generate another answer in a new chat, keeping this reply";
      if (button.disabled) button.title = "Finish active work before using this action";
      button.addEventListener("click", () => { closeMenu(); state.onAction?.(action, state.article); });
      messageMenu.append(button);
    }
    state.more.setAttribute("aria-expanded", "true");
    if (typeof messageMenu.showPopover === "function") messageMenu.showPopover();
    else messageMenu.hidden = false;
    positionMenu();
    messageMenu.querySelector("[role=menuitem]:not(:disabled)")?.focus({ preventScroll: true });
  }
  function responseActions(state) {
    const row = node("div", undefined, "message-actions");
    row.setAttribute("role", "group");
    row.setAttribute("aria-label", "Response actions");
    row.setAttribute("aria-live", "off");
    state.copy = copyButton(() => state.source, "Copy response", true);
    state.speak = actionButton("speaker", "Read aloud");
    state.speak.setAttribute("aria-pressed", "false");
    state.speechSupported = !!window.speechSynthesis && typeof window.SpeechSynthesisUtterance === "function";
    if (!state.speechSupported) state.speak.title = "Read aloud is unavailable in this browser";
    state.speak.addEventListener("click", () => readAloud(state));
    const share = actionButton("share", "Share message");
    share.addEventListener("click", () => shareMessage(state));
    const more = state.more = actionButton("more", "More options");
    more.setAttribute("aria-haspopup", "menu");
    more.setAttribute("aria-expanded", "false");
    more.setAttribute("aria-controls", "message-options-menu");
    more.addEventListener("click", () => showMessageMenu(state));
    const sources = actionButton("book", "Sources", "Sources");
    sources.setAttribute("aria-haspopup", "dialog");
    sources.addEventListener("click", () => showSources(state));
    row.append(state.copy, state.speak, share, more, sources);
    state.actions = row;
    return row;
  }
  function highlight(code, content, language) {
    const grammar = window.Prism?.languages[aliases[language] || language];
    if (!grammar || content.length > MAX_HIGHLIGHT) { code.textContent = content; return; }
    let remaining = MAX_TOKENS;
    function append(parent, value, depth = 0) {
      if (--remaining < 0 || depth > 32) throw new Error("Highlight bound");
      if (typeof value === "string") parent.append(document.createTextNode(value));
      else if (Array.isArray(value)) value.forEach((part) => append(parent, part, depth + 1));
      else {
        const span = node("span", undefined, "token");
        for (const name of [value.type, ...[].concat(value.alias || [])]) {
          if (/^[a-z][a-z0-9-]{0,40}$/i.test(name)) span.classList.add(name);
        }
        append(span, value.content, depth + 1);
        parent.append(span);
      }
    }
    try { append(code, window.Prism.tokenize(content, grammar)); }
    catch { code.textContent = content; }
  }
  function codeBlock(token) {
    const box = node("div", undefined, "code-block");
    const toolbar = node("div", undefined, "code-toolbar");
    toolbar.setAttribute("aria-live", "off");
    const info = token.info.trim().split(/\s+/, 1)[0].toLowerCase();
    const language = /^[a-z0-9_+-]{1,40}$/.test(info) ? info : "";
    toolbar.append(node("span", language || "Code", "code-language"), copyButton(() => token.content, "Copy code", true));
    const pre = node("pre");
    pre.tabIndex = 0;
    pre.setAttribute("aria-label", `${language || "Plain text"} code`);
    const code = node("code");
    highlight(code, token.content, language);
    pre.append(code);
    box.append(toolbar, pre);
    return box;
  }
  function renderTokens(tokens) {
    const fragment = document.createDocumentFragment();
    const stack = [fragment];
    let remaining = MAX_TOKENS;
    function walk(items) {
      for (const token of items) {
        if (--remaining < 0) throw new Error("Markdown token bound");
        const parent = stack.at(-1);
        if (token.type === "inline") {
          let children = token.children || [];
          const first = children[0];
          const task = first?.type === "text" && /^\[([ xX])\]\s+/.exec(first.content);
          const item = parent.nodeType === Node.ELEMENT_NODE ? parent.closest("li") : null;
          if (task && item && !item.textContent && !item.querySelector("input")) {
            item.classList.add("task-list-item");
            const checkbox = node("input", undefined, "task-checkbox");
            checkbox.type = "checkbox";
            checkbox.checked = task[1].toLowerCase() === "x";
            checkbox.disabled = true;
            checkbox.setAttribute("aria-label", token.content.slice(task[0].length, 240) || "Task");
            parent.append(checkbox);
            children = [{ ...first, content: first.content.slice(task[0].length) }, ...children.slice(1)];
          }
          walk(children);
        } else if (token.type === "text" || token.type.startsWith("html_")) {
          parent.append(document.createTextNode(token.content));
        } else if (token.type === "softbreak") parent.append(document.createTextNode("\n"));
        else if (token.type === "hardbreak") parent.append(node("br"));
        else if (token.type === "code_inline") parent.append(node("code", token.content));
        else if (token.type === "fence" || token.type === "code_block") parent.append(codeBlock(token));
        else if (token.type === "hr") parent.append(node("hr"));
        else if (token.type === "image") {
          // Images never silently contact third-party hosts or execute SVG.
          const image = link(token.attrGet("src"), token.attrGet("title"));
          image.classList.add("markdown-image-link");
          image.textContent = `Image: ${token.content || "open image"}`;
          parent.append(image);
        } else if (token.nesting === 1) {
          if (token.hidden) { stack.push(parent); continue; }
          let element;
          if (token.type === "link_open") element = link(token.attrGet("href"), token.attrGet("title"));
          else if (tags.has(token.tag)) {
            // The page owns h1; response headings start at h2.
            const tag = /^h[1-6]$/.test(token.tag) ? `h${Math.min(6, Number(token.tag[1]) + 1)}` : token.tag;
            element = node(tag);
            if (token.type === "ordered_list_open") {
              const value = token.attrGet("start");
              const start = Number(value);
              if (value !== null && Number.isSafeInteger(start) && start >= 0) element.start = start;
            }
            if (token.tag === "th") element.scope = "col";
            const alignment = /^text-align:(left|center|right)$/.exec(token.attrGet("style") || "");
            if (alignment) element.classList.add(`align-${alignment[1]}`);
          } else { stack.push(parent); continue; }
          if (token.tag === "table") {
            const scroll = node("div", undefined, "markdown-table");
            scroll.tabIndex = 0;
            scroll.setAttribute("role", "region");
            scroll.setAttribute("aria-label", "Table");
            scroll.append(element);
            parent.append(scroll);
          } else parent.append(element);
          stack.push(element);
        } else if (token.nesting === -1) {
          if (stack.length > 1) stack.pop();
        } else if (token.content) parent.append(document.createTextNode(token.content));
      }
    }
    walk(tokens);
    return fragment;
  }
  function groups(source) {
    if (!parser || source.length > MAX_MARKDOWN) return null;
    const tokens = parser.parse(source, {});
    if (tokens.length > MAX_TOKENS) return null;
    const result = [];
    let current = [], depth = 0;
    for (const token of tokens) {
      current.push(token);
      depth += token.nesting;
      if (depth === 0) { result.push(current); current = []; }
    }
    if (current.length) result.push(current);
    return result;
  }
  function protectedNode(element) {
    if (element.contains(document.activeElement)) return true;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return false;
    for (let index = 0; index < Math.min(selection.rangeCount, 8); index++) {
      if (selection.getRangeAt(index).intersectsNode(element)) return true;
    }
    return false;
  }
  function render(state) {
    clearTimeout(state.timer);
    state.timer = null;
    if (state.role !== "assistant") { state.body.textContent = state.source; state.renderedSource = state.source; return; }
    let parts;
    try {
      const parsed = groups(state.source);
      parts = parsed ? parsed.map((tokens) => ({ key: JSON.stringify(tokens), tokens })) :
        [{ key: state.source, plain: state.source }];
    } catch { parts = [{ key: state.source, plain: state.source }]; }
    if (state.blocks.some((block, index) => block.key !== parts[index]?.key && protectedNode(block.element))) {
      protectedUpdates.add(state);
      return;
    }
    protectedUpdates.delete(state);
    let blocks;
    try {
      blocks = parts.map((part, index) => {
        if (state.blocks[index]?.key === part.key) return state.blocks[index];
        const element = node("div", undefined, "markdown-block");
        if (part.plain !== undefined) element.append(node("div", part.plain, "message-plain"));
        else element.append(renderTokens(part.tokens));
        return { key: part.key, element };
      });
    } catch {
      const element = node("div", undefined, "markdown-block");
      element.append(node("div", state.source, "message-plain"));
      blocks = [{ key: state.source, element }];
    }
    for (let index = 0; index < blocks.length; index++) {
      const existing = state.body.children[index];
      if (existing !== blocks[index].element) state.body.insertBefore(blocks[index].element, existing || null);
    }
    const retained = new Set(blocks.map((block) => block.element));
    for (const element of [...state.body.children]) if (!retained.has(element)) element.remove();
    state.blocks = blocks;
    state.renderedSource = state.source;
  }
  function schedule(state) {
    if (state.timer !== null) return;
    state.timer = setTimeout(() => {
      if (!state.article.isConnected) { protectedUpdates.delete(state); return; }
      const scroll = state.article.closest(".messages");
      const atBottom = scroll && scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 100;
      render(state);
      if (atBottom) scroll.scrollTop = scroll.scrollHeight;
    }, 80);
  }
  function update(article, content, streaming = false) {
    const state = states.get(article);
    if (!state) return;
    state.source = content;
    article.setAttribute("aria-busy", String(streaming));
    if (state.actions) {
      for (const button of state.actions.children) button.disabled = streaming || !content.trim() || (button === state.speak && !state.speechSupported);
    }
    if (state.renderedSource !== content) {
      if (streaming) schedule(state);
      else render(state);
    }
  }
  function create(role, content, id, streaming = false) {
    const article = node("article", undefined, `message ${role === "user" ? "user" : "assistant"}`);
    article.dataset.id = id;
    const meta = node("div", undefined, "message-meta");
    meta.append(node("div", role === "user" ? "You" : "Klaude", "who"));
    const body = node("div", undefined, role === "assistant" ? "message-body markdown-body" : "message-body message-plain");
    const state = { article, body, source: content, renderedSource: null, role, blocks: [], timer: null, copy: null };
    states.set(article, state);
    article.append(meta, body);
    if (role === "assistant") article.append(responseActions(state));
    article.addEventListener("focusout", () => { if (protectedUpdates.has(state)) schedule(state); });
    update(article, content, streaming);
    if (streaming) render(state);
    return article;
  }
  function append(article, delta) {
    const state = states.get(article);
    if (state) update(article, state.source + delta, true);
  }
  function metadata(article, options) {
    const state = states.get(article);
    if (!state) return;
    Object.assign(state, options);
    if (menuState === state && messageMenu) {
      for (const button of messageMenu.querySelectorAll("[role=menuitem]")) button.disabled = !state.canAct || !state.onAction;
    }
  }
  function retryProtected() {
    for (const state of protectedUpdates) {
      if (state.article.isConnected) schedule(state);
      else protectedUpdates.delete(state);
    }
  }
  document.addEventListener("selectionchange", retryProtected);
  function cleanUpActions() {
    closeMenu();
    stopSpeech();
    if (actionDialog?.open) actionDialog.close();
  }
  document.addEventListener("klaude-auth-reset", cleanUpActions);
  window.addEventListener("pagehide", cleanUpActions);
  window.addEventListener("resize", positionMenu);
  document.addEventListener("scroll", positionMenu, true);
  document.addEventListener("click", (event) => {
    if (menuState && !messageMenu.contains(event.target) && !menuState.more.contains(event.target)) closeMenu();
  });
  new MutationObserver(() => {
    if (activeSpeech && !activeSpeech.state.article.isConnected) stopSpeech();
    if (dialogOwner && !dialogOwner.isConnected) actionDialog.close();
    if (menuState && !menuState.article.isConnected) closeMenu();
  }).observe(document.body, { childList: true, subtree: true });
  return Object.freeze({ create, update, append, metadata, copyText, source: (article) => states.get(article)?.source || "" });
})();
