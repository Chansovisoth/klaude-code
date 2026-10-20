"use strict";

const byId = (id) => document.getElementById(id);
const messages = byId("messages");
const notice = byId("notice");
const prompt = byId("prompt");
const activity = byId("activity");
const approvals = byId("approvals");
const questions = byId("questions");
const queue = byId("queue");
let csrf = "";
let clientId = "";
let cursor = "";
let eventCursor = "";
let stream = null;
let pending = false;
let latest = null;
let linkedMessage = null;
let messageHighlightTimer = null;
let pendingIntent = null;
let pendingSessionChoice = null;
let pendingRuntimeChoice = null;
let localModels = [];
let pollTimer = null;
let sessionsLoad = 0;
let sessionsLoaded = false;
let modelsLoad = 0;
let workspaceLoad = 0;
let authenticated = false;
let authEpoch = 0;
let loginMethod = "password";
const viewNames = ["chat", "workspace", "library", "integrations", "activity", "settings"];
let currentView = "chat";
let sessions = [];
let approvalSignature = "";
let questionSignature = "";
const layout = document.querySelector(".layout");
layout.inert = true;
byId("logout").disabled = true;
const narrowScreen = matchMedia("(max-width: 850px)");
const compactInspector = matchMedia("(max-width: 1240px)");
const systemMotion = matchMedia("(prefers-reduced-motion: reduce)");
const preferenceKey = "klaude.webui.appearance.v1";
const paletteNames = ["slate", "lavender", "sage", "peach", "ocean", "rose", "teal", "amber"];
const defaultAppearance = { version: 1, theme: "system", palette: "lavender", reduced: false };
let appearance = readAppearance();

// Delayed, owned placeholders: a stale request cannot clear a newer load.
const loadingStates = new WeakMap();
const activeLoading = new Set();
function loadingSkeleton(kind, count, label, artwork) {
  const root = document.createElement(["count", "text"].includes(kind) ? "span" : "div");
  root.className = `loading-skeleton skeleton-${kind}`;
  if (kind === "count") { root.setAttribute("aria-hidden", "true"); return root; }
  root.setAttribute("role", "status");
  const status = document.createElement("span");
  status.className = "visually-hidden";
  status.textContent = label;
  root.append(status);
  for (let index = 0; index < count; index++) {
    const item = document.createElement(kind === "text" ? "span" : "div");
    item.className = `skeleton-item skeleton-${kind === "cards" ? "card" : "row"}`;
    item.setAttribute("aria-hidden", "true");
    if (kind === "detail" || kind === "cards" && artwork) {
      const image = document.createElement("span");
      image.className = "skeleton-image";
      item.append(image);
    }
    const lines = kind === "rows" || kind === "text" ? 1 : kind === "code" ? 8 : kind === "cards" ? 4 : 3;
    for (let line = 0; line < lines; line++) {
      const bar = document.createElement("span");
      bar.className = `skeleton-line skeleton-width-${(line + index) % 3}`;
      item.append(bar);
    }
    root.append(item);
  }
  return root;
}
function cancelLoading(target) {
  const state = loadingStates.get(target);
  if (!state) return;
  clearTimeout(state.timer);
  state.placeholder?.remove();
  target.classList.remove("is-loading");
  target.setAttribute("aria-busy", "false");
  loadingStates.delete(target);
  activeLoading.delete(state);
}
function beginLoading(target, { kind = "rows", count = 3, label = "Loading…", preserve = true, prepend = false, artwork = false } = {}) {
  if (!target) return () => false;
  cancelLoading(target);
  if (!preserve && !prepend) target.replaceChildren();
  const state = { target, placeholder: null, timer: null };
  loadingStates.set(target, state);
  activeLoading.add(state);
  target.setAttribute("aria-busy", "true");
  if (!preserve || !target.hasChildNodes()) {
    state.timer = setTimeout(() => {
      if (loadingStates.get(target) !== state || !target.isConnected) return;
      state.placeholder = loadingSkeleton(kind, count, label, artwork);
      if (target.closest('[role="status"]')) state.placeholder.removeAttribute("role");
      target.classList.add("is-loading");
      if (prepend) target.prepend(state.placeholder);
      else target.replaceChildren(state.placeholder);
    }, 120);
  }
  return () => {
    if (loadingStates.get(target) !== state) return false;
    cancelLoading(target);
    return true;
  };
}
function beginChatLoading() {
  const target = byId("chat-loading");
  if (!target) return () => {};
  if (!latest) byId("welcome").hidden = true;
  target.hidden = false;
  const finish = beginLoading(target, { kind: "conversation", count: 2, preserve: false, label: "Loading conversation…" });
  return () => { if (finish()) target.hidden = true; };
}
document.addEventListener("klaude-auth-reset", () => {
  for (const state of [...activeLoading]) cancelLoading(state.target);
  if (byId("chat-loading")) byId("chat-loading").hidden = true;
  sessionsLoad += 1;
  modelsLoad += 1;
  workspaceLoad += 1;
  sessionsLoaded = false;
  sessions = [];
  localModels = [];
  byId("session-list").replaceChildren();
  byId("model-status").textContent = "";
  byId("model-choice").replaceChildren();
  byId("workspace-result").textContent = "Browse a directory, read a file or inspect your changes.";
  delete byId("workspace-result").dataset.contentKey;
});

function resizePrompt() {
  prompt.style.height = "auto";
  prompt.style.height = `${prompt.scrollHeight}px`;
}
prompt.addEventListener("input", resizePrompt);

function readAppearance(value) {
  try {
    const data = JSON.parse(value === undefined ? localStorage.getItem(preferenceKey) : value);
    if (data?.version === 1 && ["system", "light", "dark"].includes(data.theme) &&
        paletteNames.includes(data.palette) && typeof data.reduced === "boolean") {
      return { version: 1, theme: data.theme, palette: data.palette, reduced: data.reduced };
    }
  } catch { /* Private browsing or corrupt preferences keep the usable defaults. */ }
  return { ...defaultAppearance };
}

function applyAppearance(value, syncControls = false) {
  document.documentElement.dataset.theme = value.theme;
  document.documentElement.dataset.palette = value.palette;
  document.documentElement.dataset.motion = value.reduced ? "reduced" : "full";
  if (value.reduced || systemMotion.matches) {
    document.getAnimations().forEach((animation) => animation.cancel());
  }
  if (syncControls) {
    document.querySelector(`input[name="appearance"][value="${value.theme}"]`).checked = true;
    document.querySelector(`input[name="palette"][value="${value.palette}"]`).checked = true;
    byId("reduced-motion").checked = value.reduced;
  }
}

function appearanceDraft() {
  return { version: 1,
    theme: document.querySelector('input[name="appearance"]:checked').value,
    palette: document.querySelector('input[name="palette"]:checked').value,
    reduced: byId("reduced-motion").checked };
}

applyAppearance(appearance, true);
systemMotion.addEventListener("change", () => {
  if (systemMotion.matches) document.getAnimations().forEach((animation) => animation.cancel());
});
for (const input of document.querySelectorAll('.theme-settings input')) {
  input.addEventListener("change", () => {
    applyAppearance(appearanceDraft());
    byId("theme-status").textContent = "Preview · not saved";
  });
}
byId("theme-apply").addEventListener("click", () => {
  const draft = appearanceDraft();
  try {
    localStorage.setItem(preferenceKey, JSON.stringify(draft));
    appearance = draft;
    byId("theme-status").textContent = "Saved on this device";
  } catch { byId("theme-status").textContent = "Could not save. Preview is temporary."; }
});
byId("theme-reset").addEventListener("click", () => {
  applyAppearance(defaultAppearance, true);
  byId("theme-status").textContent = "Default preview · Apply to save";
});
window.addEventListener("storage", (event) => {
  if (event.key !== preferenceKey && event.key !== null) return;
  appearance = readAppearance(event.key === null ? null : event.newValue);
  applyAppearance(appearance, true);
  byId("theme-status").textContent = "Updated from another tab";
});

function setConnection(connected, label) {
  byId("connection-state").textContent = label;
  document.querySelector(".topbar-context").dataset.connected = String(connected);
  document.querySelector(".inspector-note").lastChild.textContent = connected ?
    "Connected to the shared agent" : "Waiting to reconnect";
}

function toggleSessions(open) {
  layout.classList.toggle("sessions-open", narrowScreen.matches && open);
  if (!narrowScreen.matches) layout.classList.toggle("sessions-collapsed", !open);
  byId("session-sidebar").inert = !open;
  byId("sessions-toggle").setAttribute("aria-expanded", String(open));
  byId("drawer-scrim").hidden = !narrowScreen.matches || !open;
  if (open && narrowScreen.matches) byId("close-sessions").focus();
  else if (!open && byId("session-sidebar").contains(document.activeElement)) byId("sessions-toggle").focus();
}
byId("sessions-toggle").addEventListener("click", () => toggleSessions(narrowScreen.matches ?
  !layout.classList.contains("sessions-open") : layout.classList.contains("sessions-collapsed")));
byId("close-sessions").addEventListener("click", () => toggleSessions(false));
byId("drawer-scrim").addEventListener("click", () => toggleSessions(false));
byId("inspector-toggle").addEventListener("click", () => {
  const open = compactInspector.matches ? !layout.classList.contains("inspector-open") :
    layout.classList.contains("inspector-closed");
  layout.classList.toggle("inspector-open", open);
  layout.classList.toggle("inspector-closed", !open);
  byId("inspector").inert = !open;
  byId("inspector-toggle").setAttribute("aria-expanded", String(open));
});
function updatePanelLayout() {
  toggleSessions(!narrowScreen.matches && !layout.classList.contains("sessions-collapsed"));
  layout.classList.remove("inspector-open", "inspector-closed");
  byId("inspector-toggle").setAttribute("aria-expanded", String(!compactInspector.matches));
  byId("inspector").inert = compactInspector.matches;
}
compactInspector.addEventListener("change", updatePanelLayout);
narrowScreen.addEventListener("change", () => toggleSessions(!narrowScreen.matches && !layout.classList.contains("sessions-collapsed")));
updatePanelLayout();
document.addEventListener("click", (event) => {
  const menu = byId("model-menu");
  if (menu.open && !menu.contains(event.target)) menu.open = false;
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (narrowScreen.matches) toggleSessions(false);
    byId("model-menu").open = false;
    if (compactInspector.matches && layout.classList.contains("inspector-open")) {
      layout.classList.remove("inspector-open");
      byId("inspector").inert = true;
      byId("inspector-toggle").setAttribute("aria-expanded", "false");
      byId("inspector-toggle").focus();
    }
  }
  if (event.key === "Tab" && narrowScreen.matches && layout.classList.contains("sessions-open")) {
    const controls = [...byId("session-sidebar").querySelectorAll('button:not(:disabled), input')];
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
for (const button of document.querySelectorAll("[data-prompt]")) {
  button.addEventListener("click", () => { prompt.value = button.dataset.prompt; resizePrompt(); prompt.focus(); });
}

function requestId() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function advanceCursor(next) {
  if (!next) return;
  const [epoch, raw] = next.split(":", 2);
  const [currentEpoch, currentRaw] = cursor.split(":", 2);
  if (!cursor || epoch !== currentEpoch || Number(raw) > Number(currentRaw)) cursor = next;
}

function isNewCursor(next, previous = cursor) {
  if (!next) return false;
  if (!previous) return true;
  const [epoch, raw] = next.split(":", 2);
  const [currentEpoch, currentRaw] = previous.split(":", 2);
  return epoch !== currentEpoch || Number(raw) > Number(currentRaw);
}

async function jsonRequest(path, method = "GET", body = undefined) {
  const epoch = authEpoch;
  const options = { method, credentials: "same-origin", headers: {} };
  if (clientId) options.headers["X-Klaude-Client"] = clientId;
  if (method !== "GET" && latest && path !== "/api/v1/auth/logout") {
    options.headers["X-Klaude-Session"] = latest.session_id;
  }
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.headers["X-Klaude-CSRF"] = csrf;
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error?.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.authEpoch = epoch;
    throw error;
  }
  return data;
}

async function controlledRequest(path, body, includeControlEpoch = true) {
  const sessionId = latest?.session_id;
  const epoch = authEpoch;
  const checkContext = (state = latest) => {
    if (!authenticated || epoch !== authEpoch || !sessionId ||
        latest?.session_id !== sessionId || state?.session_id !== sessionId) {
      const error = new Error("Session changed; try the action again");
      error.authEpoch = epoch;
      throw error;
    }
  };
  // Acquire only for an explicit action. Watching, polling and focusing a tab
  // never take control away from another client. Refresh control independently
  // of the rendered snapshot so a question's draft stays intact.
  for (let attempt = 0; attempt < 2; attempt++) {
    const state = await jsonRequest("/api/v1/session");
    checkContext(state);
    let controlEpoch = state.control_epoch;
    if (controlEpoch > 0 && !state.has_control) {
      try {
        const claim = await jsonRequest("/api/v1/control/claim", "POST", {
          request_id: requestId(), expected_epoch: controlEpoch,
        });
        controlEpoch = claim.control_epoch;
      } catch (error) {
        // Only retry acquisition; an action with an uncertain outcome is never
        // automatically repeated.
        if (error.status === 409 && attempt === 0) continue;
        throw error;
      }
    }
    checkContext();
    return jsonRequest(path, "POST", includeControlEpoch ?
      { ...body, control_epoch: controlEpoch } : body);
  }
}

function showError(error) {
  if (error.authEpoch !== undefined && error.authEpoch !== authEpoch) return;
  if (error.status === 401) { showLocalAccess(); return; }
  notice.textContent = error.message || String(error);
}

function showLocalAccess(signedOut = false) {
  authEpoch += 1;
  authenticated = false;
  document.dispatchEvent(new Event("klaude-auth-reset"));
  byId("change-password").reset();
  byId("login-password").value = "";
  byId("account-shortcut").hidden = true;
  csrf = "";
  clientId = "";
  latest = null;
  linkedMessage = null;
  pendingIntent = null;
  pendingRuntimeChoice = null;
  pendingSessionChoice = null;
  messages.replaceChildren();
  activity.replaceChildren();
  byId("activity-feed").replaceChildren();
  if (stream) stream.close();
  stream = null;
  clearInterval(pollTimer);
  layout.hidden = true;
  layout.inert = true;
  byId("local-access").hidden = false;
  const passwordLogin = loginMethod === "password";
  byId("access-title").textContent = signedOut ? "Signed out" :
    passwordLogin ? "Sign in to Klaude" : "Connect this browser";
  byId("access-message").textContent = passwordLogin ? "Welcome back to your local workspace." :
    "Open /settings web in Klaude and select Open Web UI to connect this browser.";
  byId("account-login").hidden = !passwordLogin;
  byId("login-help").hidden = !passwordLogin;
  byId("access-retry").hidden = passwordLogin;
  byId("logout").disabled = true;
  byId("sessions-toggle").disabled = true;
  byId("inspector-toggle").disabled = true;
  setConnection(false, "Not connected");
}

function addMessage(role, content, id, streaming = false) {
  if (window.ChatMarkdown) {
    const article = ChatMarkdown.create(role, content, id, streaming);
    ChatMarkdown.metadata?.(article, { onAction: performMessageAction, sessionId: latest?.session_id });
    messages.append(article);
    return article;
  }
  // An older still-running host may not yet serve the new Markdown assets.
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.dataset.id = id;
  const heading = document.createElement("div");
  heading.className = "who";
  heading.textContent = role === "user" ? "You" : "Klaude";
  const text = document.createElement("pre");
  text.textContent = content;
  article.append(heading, text);
  messages.append(article);
  return article;
}

function updateMessage(article, content, streaming = false) {
  if (window.ChatMarkdown) ChatMarkdown.update(article, content, streaming);
  else if (article.querySelector("pre").textContent !== content) article.querySelector("pre").textContent = content;
}

function addActivity(label) {
  const row = document.createElement("li");
  row.textContent = label.slice(0, 200);
  activity.prepend(row);
  byId("activity-feed").prepend(row.cloneNode(true));
  byId("activity-empty").hidden = true;
  byId("inspector-empty").hidden = true;
  while (activity.children.length > 80) activity.lastChild.remove();
  while (byId("activity-feed").children.length > 80) byId("activity-feed").lastChild.remove();
}

function renderApprovals(items) {
  const signature = JSON.stringify(items);
  if (approvalSignature === signature) return;
  approvalSignature = signature;
  approvals.replaceChildren();
  for (const item of items) {
    const card = document.createElement("div");
    card.className = "approval";
    const title = document.createElement("strong");
    title.textContent = `Allow ${item.tool}?`;
    const detail = document.createElement("p");
    detail.textContent = item.detail || "No arguments";
    card.append(title, detail);
    for (const [label, decision] of [["Allow once", "allow_once"], ["Deny", "deny"]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = decision === "deny" ? "secondary" : "";
      button.textContent = label;
      button.addEventListener("click", async () => {
        for (const sibling of card.querySelectorAll("button")) sibling.disabled = true;
        try {
          await controlledRequest(`/api/v1/interactions/${encodeURIComponent(item.id)}/decision`,
            { request_id: requestId(), decision });
          await snapshot();
        } catch (error) { approvalSignature = ""; showError(error); await snapshot().catch(showError); }
      });
      card.append(button);
    }
    approvals.append(card);
  }
}

function renderQuestions(items) {
  const signature = JSON.stringify(items);
  if (questionSignature === signature) return;
  questionSignature = signature;
  questions.replaceChildren();
  for (const item of items) {
    const card = document.createElement("form");
    card.className = "question";
    const title = document.createElement("strong");
    title.textContent = item.header || "Klaude asks";
    const question = document.createElement("p");
    question.textContent = item.question;
    const choices = document.createElement("div");
    choices.className = "field-row";
    const input = document.createElement("input");
    input.maxLength = 1000;
    input.placeholder = "Your answer";
    input.setAttribute("aria-label", item.question);
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = "Answer";
    card.append(title, question);
    for (const option of item.options || []) {
      const choice = document.createElement("button");
      choice.type = "button";
      choice.className = "secondary";
      choice.textContent = option;
      choice.addEventListener("click", () => { input.value = option; card.requestSubmit(); });
      choices.append(choice);
    }
    choices.append(input, submit);
    card.append(choices);
    card.addEventListener("submit", async (event) => {
      event.preventDefault();
      const answer = input.value.trim().replace(/\s+/g, " ");
      if (!answer) return;
      for (const button of card.querySelectorAll("button")) button.disabled = true;
      try {
        await controlledRequest(`/api/v1/interactions/${encodeURIComponent(item.id)}/answer`,
          { request_id: requestId(), answer });
        await snapshot();
      } catch (error) { questionSignature = ""; showError(error); await snapshot().catch(showError); }
    });
    questions.append(card);
  }
}

function renderQueue(items) {
  queue.replaceChildren();
  queue.hidden = !items.length;
  if (!items.length) return;
  const heading = document.createElement("strong");
  heading.textContent = "Queued work";
  queue.append(heading);
  for (const item of items) {
    const row = document.createElement("p");
    row.textContent = item.mine ? `${item.state}: ${item.text}` : `${item.state}: another client's message`;
    queue.append(row);
  }
}

async function snapshot() {
  const epoch = authEpoch;
  const finish = latest ? () => {} : beginChatLoading();
  let data;
  try { data = await jsonRequest("/api/v1/session"); }
  finally { finish(); }
  if (!authenticated || epoch !== authEpoch) return;
  const previousModel = latest?.model;
  const previousSession = latest?.session_id;
  if (latest && latest.session_id !== data.session_id) {
    document.dispatchEvent(new Event("klaude-chat-session-changed"));
    linkedMessage = null;
    if (stream) stream.close();
    stream = null;
    cursor = "";
    eventCursor = "";
    pendingIntent = null;
    pendingRuntimeChoice = null;
    activity.replaceChildren();
    byId("activity-feed").replaceChildren();
    byId("activity-empty").hidden = false;
    byId("inspector-empty").hidden = false;
    refreshSessions().catch(showError);
  }
  if (cursor && data.cursor) {
    const [epoch, raw] = data.cursor.split(":", 2);
    const [currentEpoch, currentRaw] = cursor.split(":", 2);
    if (epoch === currentEpoch && Number(raw) < Number(currentRaw)) return;
  }
  latest = data;
  setConnection(true, "Connected");
  if (previousModel !== data.model || previousSession !== data.session_id) {
    byId("model-choice").value = "";
  }
  if (stream && cursor && data.cursor &&
      data.cursor.split(":", 1)[0] !== cursor.split(":", 1)[0]) {
    stream.close();
    stream = null;
    eventCursor = "";
  }
  advanceCursor(data.cursor);
  byId("model").textContent = data.model;
  byId("mode-toggle").title = data.mode === "thinking" ?
    "Turn Thinking off" : "Turn Thinking on";
  byId("mode-toggle").disabled = Boolean(data.active_turn_id) ||
    Boolean(data.queue?.length);
  byId("mode-toggle").setAttribute("aria-pressed", String(data.mode === "thinking"));
  byId("session").textContent = `Session ${data.session_id.slice(0, 8)}`;
  byId("session").title = data.session_id;
  byId("state").textContent = data.state;
  byId("plan-toggle").title = data.plan_mode ? "Disable Plan mode" : "Enable Plan mode";
  byId("plan-toggle").setAttribute("aria-pressed", String(data.plan_mode));
  byId("plan-toggle").disabled = Boolean(data.active_turn_id);
  byId("tool-policy").textContent = data.tools;
  byId("enable-edits").hidden = data.tools === "file edits enabled";
  byId("enable-edits").disabled = Boolean(data.active_turn_id);
  byId("new-session").disabled = Boolean(data.active_turn_id) ||
    Boolean(data.queue?.length);
  renderModelOptions();
  const busy = Boolean(data.active_turn_id);
  byId("cancel").hidden = !busy;
  byId("steer").hidden = !busy;
  byId("send").setAttribute("aria-label", busy ? "Queue message" : "Send message");
  byId("send").title = busy ? "Queue message" : "Send message";
  byId("send").disabled = pending;
  if (window.ChatAttachmentsUI) window.ChatAttachmentsUI.refresh();
  else {
    byId("attach-file").disabled = true;
    byId("attach-file").title = "Restart Web UI, then reload to enable attachments";
    byId("chat-attachment-status").textContent =
      "Attachments could not load. Restart Web UI, then reload this page.";
    byId("chat-attachment-status").hidden = false;
  }
  byId("steer").disabled = pending;
  byId("cancel").disabled = pending;
  const nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 100;
  renderApprovals(data.approvals || []);
  renderQuestions(data.questions || []);
  renderQueue(data.queue || []);
  const visibleMessages = [...data.messages];
  const earlierLink = linkedMessage?.sessionId === data.session_id &&
    !visibleMessages.some(message => message.id === linkedMessage.message.id);
  if (earlierLink) visibleMessages.unshift(linkedMessage.message);
  if (data.partial) visibleMessages.push({ role: "assistant", content: data.partial, id: "partial" });
  // Promote the streamed article in place so completion preserves selection,
  // code scroll positions and focused Copy controls.
  const partialArticle = messages.querySelector('[data-id="partial"]');
  if (partialArticle && window.ChatMarkdown) {
    const source = ChatMarkdown.source(partialArticle);
    const completed = [...data.messages].reverse().find((message) =>
      message.role === "assistant" && message.content.startsWith(source) &&
      ![...messages.children].some((element) => element.dataset.id === message.id));
    if (source && completed) partialArticle.dataset.id = completed.id;
  }
  const retained = new Set(visibleMessages.map((message) => message.id));
  if (earlierLink) retained.add("linked-message-gap");
  for (const element of [...messages.children]) {
    if (!retained.has(element.dataset.id)) element.remove();
  }
  for (const message of visibleMessages) {
    const existing = [...messages.children].find((element) => element.dataset.id === message.id);
    const streaming = message.id === "partial" && busy;
    const article = existing || addMessage(message.role, message.content, message.id, streaming);
    if (earlierLink && message.id === linkedMessage.message.id &&
        messages.firstElementChild !== article) messages.prepend(article);
    if (existing) updateMessage(existing, message.content, streaming);
    window.ChatMarkdown?.metadata?.(article, {
      createdAt: message.created_at,
      sessionId: data.session_id,
      canAct: data.message_actions === true && !busy && !data.queue?.length && !pending &&
        message.id.startsWith("stored:"),
    });
    window.ChatAttachmentsUI?.renderMessage(article, message, data.session_id);
  }
  if (earlierLink && !messages.querySelector('[data-id="linked-message-gap"]')) {
    const gap = document.createElement("p");
    gap.dataset.id = "linked-message-gap";
    gap.className = "message-history-gap muted";
    gap.textContent = "Later messages omitted · Latest messages below";
    messages.firstElementChild.after(gap);
  }
  byId("welcome").hidden = visibleMessages.length > 0 || busy;
  renderSessionList();
  if (nearBottom) messages.scrollTop = messages.scrollHeight;
  connect();
}

function renderModelOptions() {
  if (!latest) return;
  const select = byId("model-choice");
  const selected = select.value;
  select.replaceChildren();
  const choices = localModels.some((item) => item.id === latest.model) ?
    localModels : [{ id: latest.model, name: latest.model }, ...localModels];
  for (const item of choices) {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.name;
    select.append(option);
  }
  select.value = choices.some((item) => item.id === selected) ? selected : latest.model;
  const locked = Boolean(latest.active_turn_id) || Boolean(latest.queue?.length);
  select.disabled = locked || !localModels.length;
  byId("apply-model").disabled = locked || !localModels.length ||
    select.value === latest.model;
}

async function refreshModels() {
  const load = ++modelsLoad;
  const epoch = authEpoch;
  const finish = beginLoading(byId("model-status"), { kind: "text", count: 1, preserve: localModels.length > 0, label: "Loading models…" });
  try {
    const data = await jsonRequest("/api/v1/models/local");
    if (load !== modelsLoad || epoch !== authEpoch || !authenticated) return;
    localModels = data.models;
    byId("model-status").textContent = localModels.length ?
      `${localModels.length} local model${localModels.length === 1 ? "" : "s"}` :
      "No local models found";
  } catch (error) {
    if (load !== modelsLoad || epoch !== authEpoch || !authenticated) return;
    byId("model-status").textContent = error.message;
  }
  finally { finish(); }
  renderModelOptions();
}

async function chooseRuntime(kind, value) {
  if (!latest || latest.active_turn_id || latest.queue?.length) return;
  const key = `${latest.session_id}\u0000${kind}\u0000${value}`;
  if (!pendingRuntimeChoice || pendingRuntimeChoice.key !== key) {
    pendingRuntimeChoice = { key, requestId: requestId() };
  }
  try {
    await controlledRequest(`/api/v1/session/${kind}`, {
      request_id: pendingRuntimeChoice.requestId,
      [kind === "model" ? "model_id" : "mode"]: value,
      expected_revision: latest.settings_revision,
    });
    pendingRuntimeChoice = null;
    await snapshot();
    await refreshSessions();
  } catch (error) { showError(error); await snapshot().catch(showError); }
}
byId("model-choice").addEventListener("change", renderModelOptions);
byId("apply-model").addEventListener("click", () =>
  chooseRuntime("model", byId("model-choice").value));
byId("refresh-models").addEventListener("click", refreshModels);
byId("mode-toggle").addEventListener("click", () =>
  chooseRuntime("mode", latest?.mode === "thinking" ? "standard" : "thinking"));

async function refreshSessions() {
  const load = ++sessionsLoad;
  const epoch = authEpoch;
  const finish = beginLoading(byId("session-list"), { kind: "rows", count: 5, preserve: sessionsLoaded, label: "Loading conversations…" });
  if (!sessionsLoaded) byId("session-empty").hidden = true;
  try {
    const data = await jsonRequest("/api/v1/sessions");
    if (load !== sessionsLoad || epoch !== authEpoch || !authenticated) return;
    sessions = data.sessions;
    sessionsLoaded = true;
    renderSessionList();
  } finally { finish(); }
}

function renderSessionList() {
  const list = byId("session-list");
  if (!sessionsLoaded && loadingStates.has(list)) return;
  list.replaceChildren();
  const filter = byId("session-search").value.trim().toLowerCase();
  for (const item of sessions) {
    if (filter && !`${item.title || ""} ${item.preview || ""} ${item.session_id}`.toLowerCase().includes(filter)) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = item.title || item.preview || item.session_id.slice(0, 12);
    button.title = item.resumable ? item.preview : "Requires this session's model and mode";
    button.className = item.session_id === latest?.session_id ? "selected" : "";
    button.disabled = !item.resumable || item.session_id === latest?.session_id ||
      Boolean(latest?.active_turn_id) || Boolean(latest?.queue?.length);
    button.addEventListener("click", () => switchSession(item.session_id));
    list.append(button);
  }
  byId("session-empty").hidden = Boolean(list.children.length);
  byId("session-empty").textContent = filter ? "No matching conversations." : "Your conversations will appear here.";
}
byId("session-search").addEventListener("input", renderSessionList);

async function switchSession(sessionId, { fromLink = false } = {}) {
  if (!latest || latest.active_turn_id || latest.queue?.length) return false;
  const key = `${latest.session_id}\u0000${sessionId}`;
  if (!pendingSessionChoice || pendingSessionChoice.key !== key) {
    pendingSessionChoice = { key, requestId: requestId() };
  }
  const finish = beginChatLoading();
  try {
    await controlledRequest("/api/v1/session/select", {
      request_id: pendingSessionChoice.requestId,
      expected_session_id: latest.session_id,
      session_id: sessionId,
    });
    pendingSessionChoice = null;
    if (narrowScreen.matches) toggleSessions(false);
    await snapshot();
    finish();
    if (!fromLink) rememberLinkedSession();
    await refreshSessions();
    return true;
  } catch (error) { showError(error); await snapshot().catch(showError); return false; }
  finally { finish(); }
}
byId("new-session").addEventListener("click", () => switchSession(""));
byId("refresh-sessions").addEventListener("click", () => refreshSessions().catch(showError));

async function performMessageAction(action, article) {
  if (!latest || pending || latest.active_turn_id || latest.queue?.length) return;
  const messageId = article.dataset.id;
  const message = latest.messages.find(message => message.id === messageId) ||
    (linkedMessage?.sessionId === latest.session_id ? linkedMessage.message : null);
  if (message?.id !== messageId || message.role !== "assistant") return;
  pending = true;
  const finish = beginChatLoading();
  try {
    await controlledRequest("/api/v1/messages/action", {
      request_id: requestId(), source_session_id: latest.session_id,
      message_id: messageId, action,
    });
    await snapshot();
    finish();
    rememberLinkedSession();
    await refreshSessions();
  } catch (error) { showError(error); }
  finally { finish(); pending = false; snapshot().catch(showError); }
}

function connect() {
  if (!authenticated || stream || !cursor) return;
  if (!eventCursor) eventCursor = cursor;
  const source = new EventSource(`/api/v1/events?after=${encodeURIComponent(eventCursor)}`);
  stream = source;
  source.onmessage = (event) => {
    if (stream !== source) return;
    let item;
    try { item = JSON.parse(event.data); } catch { return; }
    if (!isNewCursor(item.cursor, eventCursor)) return;
    eventCursor = item.cursor;
    const changesState = isNewCursor(item.cursor);
    advanceCursor(item.cursor);
    if (item.kind === "stream.reset_required") {
      stream.close();
      stream = null;
      eventCursor = "";
      snapshot().catch(showError);
      return;
    }
    if (item.kind === "message.delta" && changesState) {
      let partial = messages.querySelector('[data-id="partial"]');
      if (!partial) partial = addMessage("assistant", "", "partial", true);
      const nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 100;
      byId("welcome").hidden = true;
      if (window.ChatMarkdown) ChatMarkdown.append(partial, item.text || "");
      else partial.querySelector("pre").textContent += item.text || "";
      if (nearBottom) messages.scrollTop = messages.scrollHeight;
    }
    if (item.kind === "tool.requested") addActivity(`Requested ${item.tool || "tool"}`);
    if (item.kind === "tool.started") addActivity(`Running ${item.tool || "tool"}`);
    if (item.kind === "tool.finished") {
      addActivity(`${item.tool || "Tool"}: ${item.executed ? "finished" : "not run"}`);
    }
    if (item.kind.startsWith("turn.")) addActivity(item.kind.replace(".", " "));
    if (["approval.required", "approval.resolved", "user_input.required",
      "user_input.resolved", "queue.changed", "session.state", "settings.changed",
      "workspace.changed",
      "message.completed", "turn.completed", "turn.partial", "turn.failed",
      "turn.cancelled", "turn.interrupted"].includes(item.kind) && changesState) {
      snapshot().catch(showError);
    }
  };
  source.onerror = () => {
    if (stream !== source) return;
    stream.close();
    stream = null;
    setConnection(false, "Reconnecting");
    setTimeout(() => snapshot().catch(showError), 1200);
  };
}

async function sendMessage(disposition) {
  const text = prompt.value.trim();
  if (!text || pending || !latest) return;
  const attachments = window.ChatAttachmentsUI?.ids() || [];
  if (window.ChatAttachmentsUI?.preparing() || attachments.length && latest.active_turn_id) return;
  const activeTurn = latest.active_turn_id;
  const effectiveDisposition = disposition === "steer" ? "steer" :
    activeTurn ? "queue" : "start";
  const intentKey = `${effectiveDisposition}\u0000${activeTurn || ""}\u0000${text}\u0000${attachments.join(",")}`;
  if (!pendingIntent || pendingIntent.key !== intentKey) {
    pendingIntent = { key: intentKey, requestId: requestId() };
  }
  pending = true;
  notice.textContent = "";
  try {
    if (disposition === "steer") {
      if (!latest.active_turn_id) return;
      await controlledRequest(`/api/v1/turns/${encodeURIComponent(latest.active_turn_id)}/steer`,
        { request_id: pendingIntent.requestId, text });
    } else {
      await jsonRequest("/api/v1/turns", "POST", {
        request_id: pendingIntent.requestId, text,
        disposition: effectiveDisposition,
        ...(attachments.length ? { attachments } : {}),
      });
    }
    pendingIntent = null;
    prompt.value = "";
    prompt.style.height = "auto";
    window.ChatAttachmentsUI?.clear();
    await snapshot();
  } catch (error) { showError(error); }
  finally { pending = false; snapshot().catch(showError); }
}

byId("composer").addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage("send");
});
byId("steer").addEventListener("click", () => sendMessage("steer"));
byId("cancel").addEventListener("click", async () => {
  if (!latest?.active_turn_id || pending) return;
  pending = true;
  try {
    await controlledRequest(`/api/v1/turns/${encodeURIComponent(latest.active_turn_id)}/cancel`,
      { request_id: requestId() });
    await snapshot();
  } catch (error) { showError(error); }
  finally { pending = false; snapshot().catch(showError); }
});
byId("plan-toggle").addEventListener("click", async () => {
  if (!latest || latest.active_turn_id) return;
  try {
    await controlledRequest("/api/v1/session/plan-mode", {
      request_id: requestId(), enabled: !latest.plan_mode,
      expected_revision: latest.settings_revision,
    });
    await snapshot();
  } catch (error) { showError(error); await snapshot().catch(showError); }
});

// Keep navigation local to this tab; store only allowlisted page identifiers.
function readNavigationChoice(key, choices, fallback) {
  try {
    const saved = sessionStorage.getItem(`klaude.webui.navigation.v1.${key}`);
    if (choices.includes(saved)) return saved;
  } catch { /* Navigation still works when browser storage is unavailable. */ }
  return fallback;
}
function saveNavigationChoice(key, value) {
  try { sessionStorage.setItem(`klaude.webui.navigation.v1.${key}`, value); }
  catch { /* Browser storage is optional. */ }
}

function showView(view) {
  if (!viewNames.includes(view)) view = "chat";
  if (currentView === "settings" && view !== "settings") {
    applyAppearance(appearance, true);
    byId("change-password").reset();
    byId("password-status").textContent = "";
  }
  for (const name of viewNames) {
    byId(`${name}-view`).hidden = name !== view;
    byId(`nav-${name}`).classList.toggle("selected", name === view);
    if (name === view) byId(`nav-${name}`).setAttribute("aria-current", "page");
    else byId(`nav-${name}`).removeAttribute("aria-current");
  }
  const target = byId(`${view}-view`);
  if (view !== currentView && !systemMotion.matches && document.documentElement.dataset.motion !== "reduced") {
    target.getAnimations().forEach((animation) => animation.cancel());
    target.animate([{ opacity: .3, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }],
      { duration: 220, easing: "cubic-bezier(.2,0,0,1)" });
  }
  currentView = view;
  saveNavigationChoice("page", view);
  if (view === "workspace" && authenticated) workspaceRead("files");
  document.dispatchEvent(new CustomEvent("klaude-view", { detail: view }));
  if (narrowScreen.matches) toggleSessions(false);
}
byId("nav-chat").addEventListener("click", () => showView("chat"));
byId("nav-workspace").addEventListener("click", () => showView("workspace"));
byId("nav-activity").addEventListener("click", () => showView("activity"));
byId("nav-settings").addEventListener("click", () => showView("settings"));
byId("account-shortcut").addEventListener("click", () => {
  showView("settings");
  byId("account-settings").scrollIntoView({ block: "start", behavior: "instant" });
  byId("account-heading").focus({ preventScroll: true });
});
byId("enable-edits").addEventListener("click", async () => {
  if (!latest) return;
  const button = byId("enable-edits");
  button.disabled = true;
  try {
    const result = await controlledRequest("/api/v1/workspace/activate-edits", {
      request_id: requestId(), expected_revision: latest.workspace_revision,
      acknowledge: true,
    }, false);
    byId("edit-status").textContent = result.status;
    await snapshot();
  } catch (error) { byId("edit-status").textContent = error.message; }
  finally { button.disabled = false; }
});

async function workspaceRead(operation) {
  const path = byId("workspace-path").value || ".";
  const result = byId("workspace-result");
  result.querySelector(".loading-error")?.remove();
  const load = ++workspaceLoad;
  const epoch = authEpoch;
  const sessionId = latest?.session_id;
  const params = new URLSearchParams();
  if (["files", "file", "search"].includes(operation)) params.set("path", path);
  if (operation === "search") params.set("pattern", byId("search-pattern").value);
  const key = `${operation}?${params}`;
  const finish = beginLoading(result, { kind: "code", count: 1, preserve: result.dataset.contentKey === key, label: "Loading workspace…" });
  try {
    const data = await jsonRequest(`/api/v1/workspace/${operation}?${params}`);
    if (load !== workspaceLoad || epoch !== authEpoch || !authenticated || sessionId !== latest?.session_id) return;
    result.replaceChildren();
    const title = document.createElement("h2");
    title.textContent = operation === "files" ? `Files in ${path}` :
      operation === "file" ? path : operation === "search" ? "Search results" :
        operation === "status" ? "Changes" : "Diff";
    const text = document.createElement("pre");
    text.textContent = data.text;
    result.append(title, text);
    result.dataset.contentKey = key;
  } catch (error) {
    if (load !== workspaceLoad || epoch !== authEpoch || !authenticated || sessionId !== latest?.session_id) return;
    if (error.status === 401) showLocalAccess();
    else if (result.dataset.contentKey === key && result.querySelector("pre")) {
      const status = document.createElement("p");
      status.className = "loading-error muted";
      status.textContent = error.message;
      result.prepend(status);
    } else result.textContent = error.message;
  } finally { finish(); }
}
for (const [id, operation] of [["browse", "files"], ["read-file", "file"],
  ["search", "search"], ["git-status", "status"], ["git-diff", "diff"]]) {
  byId(id).addEventListener("click", () => workspaceRead(operation));
}

byId("logout").addEventListener("click", async () => {
  if (!authenticated) { showLocalAccess(); return; }
  try {
    await jsonRequest("/api/v1/auth/logout", "POST", {});
    csrf = "";
    clientId = "";
    latest = null;
    messages.replaceChildren();
    showLocalAccess(true);
  } catch (error) { showError(error); }
});

function highlightLinkedMessage(article) {
  clearTimeout(messageHighlightTimer);
  for (const previous of messages.querySelectorAll(".linked-message"))
    previous.classList.remove("linked-message", "linked-message-faded");
  article.classList.add("linked-message");
  messageHighlightTimer = setTimeout(() => {
    messageHighlightTimer = null;
    if (article.isConnected) article.classList.add("linked-message-faded");
  }, 3000);
}

function rememberLinkedSession(messageId = null) {
  const url = new URL(location.href);
  if (!url.searchParams.has("session") || !latest) return;
  url.searchParams.set("session", latest.session_id);
  if (messageId) url.searchParams.set("message", messageId);
  else url.searchParams.delete("message");
  url.hash = "";
  history.replaceState({ ...history.state, klaudeLinkedSession: latest.session_id,
    klaudeLinkedMessage: messageId }, "", url.pathname + url.search);
}

async function openConversationLink() {
  const parameters = new URLSearchParams(location.search);
  const target = parameters.get("session");
  const messageId = parameters.get("message");
  if (target === null && messageId === null) return;
  if (!/^[a-f0-9]{32}$/.test(target || "") || parameters.getAll("session").length !== 1 ||
      parameters.getAll("message").length > 1 || messageId !== null &&
      (!/^stored:[1-9]\d{0,18}$/.test(messageId) ||
        BigInt(messageId.slice(7)) > 9223372036854775807n)) {
    notice.textContent = "This conversation link is invalid.";
    return;
  }
  const openedBefore = history.state?.klaudeLinkedSession === target &&
    (history.state?.klaudeLinkedMessage || null) === messageId;
  const previousView = currentView;
  if (target !== latest?.session_id) {
    if (latest?.active_turn_id || latest?.queue?.length) {
      notice.textContent = "Finish the current reply before opening this conversation.";
      return;
    }
    if (!await switchSession(target, { fromLink: true })) return;
  }
  if (!openedBefore && currentView === previousView) showView("chat");
  if (messageId !== null) {
    if (!latest.messages.some(message => message.id === messageId)) {
      const epoch = authEpoch;
      const query = new URLSearchParams({ session: target, message: messageId });
      const finish = beginChatLoading();
      try {
        const data = await jsonRequest(`/api/v1/session?${query}`);
        if (!authenticated || epoch !== authEpoch || latest?.session_id !== target ||
            data.session_id !== target) return;
        if (data.linked_message?.id !== messageId ||
            !["user", "assistant"].includes(data.linked_message.role) ||
            typeof data.linked_message.content !== "string") {
          notice.textContent = "This message is unavailable in the current conversation history.";
          return;
        }
        linkedMessage = { sessionId: target, message: data.linked_message };
        await snapshot();
      } catch (error) { showError(error); return; }
      finally { finish(); }
    }
    if (currentView === "chat") {
      const article = [...messages.children].find(element => element.dataset.id === messageId);
      if (!article) return;
      highlightLinkedMessage(article);
      article.tabIndex = -1;
      article.focus({ preventScroll: true });
      article.scrollIntoView({ block: "start", inline: "nearest", behavior: "instant" });
    }
  }
  rememberLinkedSession(messageId);
}

async function initialize() {
  const epoch = ++authEpoch;
  byId("access-status").textContent = "";
  const method = await jsonRequest("/api/v1/auth/method");
  if (epoch !== authEpoch) return;
  loginMethod = method.method;
  byId("account-settings").hidden = loginMethod !== "password";
  const code = location.hash.slice(1);
  if (code && loginMethod === "bootstrap") {
    history.replaceState(null, "", location.pathname + location.search);
    const response = await fetch("/api/v1/auth/exchange", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const data = await response.json();
    if (epoch !== authEpoch) return;
    if (!response.ok) {
      showLocalAccess();
      byId("access-status").textContent = "This browser link expired or was already used. Open a fresh link from Klaude.";
      return;
    }
    csrf = data.csrf;
  } else {
    if (code) history.replaceState(null, "", location.pathname + location.search);
    const auth = await jsonRequest("/api/v1/auth");
    if (epoch !== authEpoch) return;
    csrf = auth.csrf;
    const username = auth.username || "admin";
    byId("account-initial").textContent = Array.from(username)[0].toLocaleUpperCase();
    byId("account-shortcut").setAttribute("aria-label", `Account settings for ${username}`);
  }
  const client = await jsonRequest("/api/v1/clients", "POST", {});
  if (epoch !== authEpoch) return;
  clientId = client.client_id;
  authenticated = true;
  showView(readNavigationChoice("page", viewNames, "chat"));
  layout.hidden = false;
  layout.inert = false;
  byId("local-access").hidden = true;
  byId("account-shortcut").hidden = loginMethod !== "password";
  byId("logout").disabled = false;
  byId("sessions-toggle").disabled = false;
  byId("inspector-toggle").disabled = false;
  await snapshot();
  await openConversationLink();
  await refreshSessions();
  await refreshModels();
  if (!authenticated) return;
  clearInterval(pollTimer);
  pollTimer = setInterval(() => { if (authenticated && !stream) snapshot().catch(showError); }, 2000);
}
function initializationFailed(error) {
  if (error.authEpoch !== undefined && error.authEpoch !== authEpoch) return;
  showLocalAccess();
  if (error.status !== 401) byId("access-status").textContent = error.message || String(error);
}
byId("access-retry").addEventListener("click", () => initialize().catch(initializationFailed));
byId("account-login").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = byId("login-submit");
  if (button.disabled) return;
  button.disabled = true;
  byId("access-status").textContent = "";
  try {
    const result = await jsonRequest("/api/v1/auth/login", "POST", {
      username: byId("login-username").value, password: byId("login-password").value,
    });
    csrf = result.csrf;
    byId("login-password").value = "";
    await initialize();
  } catch (error) { byId("access-status").textContent = error.message || String(error); }
  finally { button.disabled = false; }
});
byId("change-password").addEventListener("submit", async (event) => {
  event.preventDefault();
  const replacement = byId("new-password").value;
  if (replacement !== byId("confirm-password").value) {
    byId("password-status").textContent = "The new passwords do not match.";
    return;
  }
  const button = byId("password-submit");
  if (button.disabled) return;
  button.disabled = true;
  byId("password-status").textContent = "";
  try {
    await jsonRequest("/api/v1/auth/password", "POST", {
      current_password: byId("current-password").value, new_password: replacement,
    });
    byId("change-password").reset();
    csrf = "";
    clientId = "";
    latest = null;
    messages.replaceChildren();
    showLocalAccess(true);
    byId("access-status").textContent = "Password changed. Sign in with your new password.";
  } catch (error) {
    if (error.status === 401) showLocalAccess();
    else byId("password-status").textContent = error.message || String(error);
  } finally { button.disabled = false; }
});
window.addEventListener("hashchange", () => {
  if (location.hash.length > 1) initialize().catch(initializationFailed);
});
initialize().catch(initializationFailed);
