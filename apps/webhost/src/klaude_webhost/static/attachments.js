"use strict";

window.ChatAttachmentsUI = (() => {
  const dialog = byId("attach-dialog");
  const list = byId("chat-attachments");
  const status = byId("attach-status");
  byId("attach-close").append(libraryIcon("close"));
  for (const type of ["laptop", "smartphone"]) {
    const icon = libraryIcon(type);
    icon.classList.add(`attachment-device-${type}`);
    byId("attach-device").prepend(icon);
  }
  byId("attach-library").prepend(byId("nav-library").querySelector("svg").cloneNode(true));
  let selected = [];
  let jobs = 0;
  let generation = 0;
  let offset = 0;
  let read = 0;
  let rendered = "";
  let uploadError = "";
  const messageCards = new WeakMap();

  function attachmentType(item) {
    const extension = item.name.split(".").pop().toUpperCase();
    if (item.image) return "Image";
    if (item.mime === "application/pdf" || extension === "PDF") return "PDF";
    return /^[A-Z0-9]{1,8}$/.test(extension) && item.name.includes(".") ? extension : "File";
  }
  function fileCard(item, previewURL = "", onOpen = null) {
    const type = attachmentType(item);
    const card = document.createElement(onOpen ? "button" : "div");
    card.className = "attachment-card";
    if (onOpen) {
      card.type = "button"; card.classList.add("attachment-preview");
      card.setAttribute("aria-label", `Preview ${item.name}`);
      card.setAttribute("aria-haspopup", "dialog");
      card.addEventListener("click", () => onOpen(card));
    } else card.setAttribute("role", "listitem");
    const tile = document.createElement("span");
    tile.className = `attachment-artwork${type === "PDF" ? " attachment-pdf" : ""}`;
    tile.setAttribute("aria-hidden", "true");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", item.image ?
      "M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm0 13 5-5 4 4 3-3 5 5M8 7h.01" :
      "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M8 13h8M8 17h5");
    svg.append(path);
    tile.append(svg);
    if (type === "PDF") {
      const badge = document.createElement("span");
      badge.className = "attachment-type-badge";
      badge.textContent = "PDF";
      tile.append(badge);
    }
    if (previewURL && item.preview) {
      const image = document.createElement("img");
      image.alt = "";
      image.width = image.height = 44;
      image.decoding = "async";
      image.loading = "lazy";
      image.addEventListener("error", () => image.remove(), { once: true });
      image.src = previewURL;
      tile.append(image);
    }
    const detail = document.createElement("div");
    detail.className = "attachment-detail";
    const name = document.createElement("span");
    name.className = "attachment-name";
    name.textContent = item.name;
    name.title = item.name;
    const meta = document.createElement("span");
    meta.className = "attachment-meta";
    const size = item.size < 1024 ? `${item.size} B` : item.size < 1024 * 1024 ?
      `${(item.size / 1024).toFixed(1)} KiB` : `${(item.size / 1024 / 1024).toFixed(1)} MiB`;
    meta.textContent = `${type} · ${size}${item.truncated ? " · Text truncated" : ""}`;
    detail.append(name, meta);
    card.append(tile, detail);
    return card;
  }
  function previewURL(params) {
    return `/api/v1/chat/attachments/preview?${new URLSearchParams({ session: latest.session_id, ...params })}`;
  }
  function renderMessage(article, message, session) {
    if (message.role !== "user" || !Array.isArray(message.attachments) || !message.attachments.length) return;
    const body = article.querySelector(".message-body");
    if (!body) return;
    const files = message.attachments.slice(0, 4);
    const key = JSON.stringify([session, message.content, files]);
    if (messageCards.get(article) === key && body.querySelector(".message-attachments")) return;
    const suffix = `\n\n[Attached files: ${files.map(item => item.name).join(", ")}]`;
    const text = document.createElement("div");
    text.className = "message-prompt";
    text.textContent = message.content.endsWith(suffix) ? message.content.slice(0, -suffix.length) : message.content;
    const cards = document.createElement("div");
    cards.className = "message-attachments";
    cards.setAttribute("role", "list");
    cards.setAttribute("aria-label", "Attached files");
    files.forEach((item, index) => {
      const row = document.createElement("div"); row.className = "message-attachment-item";
      row.setAttribute("role", "listitem");
      row.append(fileCard(item, item.preview ? previewURL({ session, message: message.id, file: index }) : "",
        origin => openChatAttachment({ session, message: message.id, file: index, descriptor: item, origin,
          created: message.created_at })));
      cards.append(row);
    });
    body.replaceChildren(text, cards);
    messageCards.set(article, key);
  }

  function discard(id) {
    if (authenticated) jsonRequest("/api/v1/chat/attachments/discard", "POST", { id }).catch(() => {});
  }
  function refresh() {
    list.hidden = !selected.length;
    const key = selected.map(item => item.id).join(",");
    if (rendered !== key) {
      list.replaceChildren();
      rendered = key;
      for (const item of selected) {
        const chip = fileCard(item, item.preview ? previewURL({ selection: item.id, client: clientId }) : "");
        chip.classList.add("attachment-chip");
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "icon-button";
        remove.append(libraryIcon("close"));
        remove.setAttribute("aria-label", `Remove ${item.name}`);
        remove.disabled = pending;
        remove.addEventListener("click", () => {
          uploadError = "";
          selected = selected.filter(entry => entry.id !== item.id);
          discard(item.id);
          refresh();
        });
        chip.append(remove);
        list.append(chip);
      }
    }
    for (const button of list.querySelectorAll("button")) button.disabled = pending;
    const waiting = selected.length && latest?.active_turn_id;
    const available = latest?.attachments === true;
    const label = latest && !available ?
      "Attachments require a server update. Restart Web UI, then reload this page." :
      uploadError || (jobs ? "Preparing attachment…" : waiting ?
      "Files are ready. Send when the current reply finishes." :
      selected.some(item => item.truncated) ? "Long file text is truncated to 32,000 characters." : "");
    byId("chat-attachment-status").textContent = label;
    byId("chat-attachment-status").hidden = !label;
    byId("send").disabled = pending || jobs > 0 || Boolean(waiting) || Boolean(latest?.requires_model_selection);
    byId("steer").disabled = pending || jobs > 0 || Boolean(selected.length);
    byId("attach-file").disabled = pending || !available;
    byId("attach-file").title = available ? "Attach file" :
      "Restart Web UI, then reload to enable attachments";
    document.dispatchEvent(new Event("klaude-attachments"));
  }
  async function attach(body, context = generation) {
    if (selected.length >= 4) throw new Error("Attach up to four files per message.");
    const session = latest?.session_id;
    const epoch = authEpoch;
    jobs++;
    refresh();
    try {
      const item = await jsonRequest("/api/v1/chat/attachments", "POST", body);
      if (!authenticated || epoch !== authEpoch || session !== latest?.session_id || context !== generation) {
        discard(item.id);
        return;
      }
      if (selected.length >= 4 ||
          selected.reduce((sum, file) => sum + file.size, 0) + item.size > 32 * 1024 * 1024) {
        discard(item.id);
        throw new Error("Attach up to four files within 32 MiB.");
      }
      selected.push(item);
      uploadError = "";
      status.textContent = `${item.name} attached${item.truncated ? " · Text truncated" : ""}`;
    } finally { jobs--; refresh(); }
  }
  async function attachLibrary(item) {
    if (!authenticated || latest?.attachments !== true)
      throw new Error("Restart Web UI, then reload to enable attachments.");
    if (pending || jobs) throw new Error("Wait for the current files or message to finish sending.");
    try { await attach({ artifact_id: item.id, revision: item.revision }); }
    catch (error) { rejectUpload(error.message); throw error; }
  }
  byId("attach-file").addEventListener("click", () => {
    status.textContent = "";
    dialog.showModal();
  });
  byId("attach-close").addEventListener("click", () => dialog.close());
  byId("attach-device").addEventListener("click", () => byId("attach-device-input").click());
  byId("attach-device-input").addEventListener("change", async (event) => {
    const files = [...event.target.files];
    event.target.value = "";
    await uploadFiles(files);
  });
  function rejectUpload(message) {
    uploadError = message;
    status.textContent = message;
    refresh();
  }
  async function uploadFiles(files) {
    if (!files.length) return;
    if (!authenticated || !latest?.session_id || latest.attachments !== true) {
      rejectUpload("Attachments require a server update. Restart Web UI, then reload this page."); return;
    }
    if (pending || jobs) { rejectUpload("Wait for the current files or message to finish sending."); return; }
    const context = generation, epoch = authEpoch, session = latest?.session_id;
    const current = () => authenticated && context === generation && epoch === authEpoch && session === latest?.session_id;
    uploadError = "";
    jobs++; refresh();
    try {
      if (selected.length + files.length > 4) throw new Error("Attach up to four files per message.");
      if (files.some(file => !file.size || file.size > 32 * 1024 * 1024))
        throw new Error("Choose nonempty files up to 32 MiB.");
      if (selected.reduce((sum, file) => sum + file.size, 0) +
          files.reduce((sum, file) => sum + file.size, 0) > 32 * 1024 * 1024)
        throw new Error("Attachments must fit within 32 MiB total.");
      for (const file of files) {
        if (!current()) return;
        const upload_id = await uploadForReview(file);
        if (context !== generation || epoch !== authEpoch || session !== latest?.session_id) {
          discardStagedUpload(upload_id, epoch);
          return;
        }
        await attach({ upload_id }, context);
      }
    } catch (error) { if (current()) rejectUpload(error.message); }
    finally { jobs--; refresh(); }
  }
  window.FileDropUI?.register({
    active: () => currentView === "chat",
    state: () => {
      const available = latest?.attachments === true;
      const allowed = available && !pending && !jobs && selected.length < 4;
      return { allowed, title: allowed ? "Drop files into your chat" : "Files can’t be added yet",
        detail: !available ? "Restart Web UI, then reload to enable attachments." : pending || jobs ?
          "Wait for the current files or message to finish sending." : selected.length >= 4 ?
          "Remove an attachment to add another file." : "Add context, then send when you’re ready.",
        note: "Up to 4 files or images · 32 MiB total" };
    },
    receive: uploadFiles, receiveLibrary: attachLibrary, reject: rejectUpload,
  });

  async function libraryFiles() {
    const job = ++read, epoch = authEpoch;
    byId("attach-library-panel").hidden = false;
    status.textContent = "Loading saved files…";
    try {
      const query = new URLSearchParams({ kind: "all", archived: "false", offset,
        query: byId("attach-search").value, sort: "newest" });
      const data = await jsonRequest(`/api/v1/library/items?${query}`);
      if (job !== read || epoch !== authEpoch || !authenticated) return;
      const rows = data.items.map(item => {
        const row = document.createElement("div");
        row.className = "attachment-library-item";
        const artwork = document.createElement("span");
        artwork.className = "file-artwork";
        artwork.setAttribute("aria-hidden", "true");
        artwork.append(canPreviewImage(item) ? artifactImage(item) : fileIcon(item));
        const detail = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = item.name;
        const meta = document.createElement("p");
        meta.className = "muted";
        meta.textContent = `${fileType(item)[1]} · ${fileSize(item.size)}`;
        detail.append(title, meta);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "secondary";
        button.textContent = "Attach";
        button.setAttribute("aria-label", `Attach ${item.name}`);
        button.addEventListener("click", async () => {
          button.disabled = true;
          try { await attach({ artifact_id: item.id, revision: item.revision }); }
          catch (error) { status.textContent = error.message; }
          finally { button.disabled = false; }
        });
        row.append(artwork, detail, button);
        return row;
      });
      byId("attach-library-items").replaceChildren(...rows);
      status.textContent = rows.length ? "Choose a file to attach." : "No matching files.";
      byId("attach-previous").disabled = !offset;
      byId("attach-next").disabled = !data.more;
    } catch (error) { if (job === read && epoch === authEpoch) status.textContent = error.message; }
  }
  byId("attach-library").addEventListener("click", () => { offset = 0; libraryFiles(); });
  byId("attach-search-form").addEventListener("submit", event => {
    event.preventDefault(); offset = 0; libraryFiles();
  });
  byId("attach-next").addEventListener("click", () => { offset += 20; libraryFiles(); });
  byId("attach-previous").addEventListener("click", () => { offset = Math.max(0, offset - 20); libraryFiles(); });
  function clear() {
    generation++;
    read++;
    selected.forEach(item => discard(item.id));
    selected = [];
    uploadError = "";
    if (dialog.open) dialog.close();
    byId("attach-library-items").replaceChildren();
    refresh();
  }
  document.addEventListener("klaude-auth-reset", clear);
  document.addEventListener("klaude-chat-session-changed", clear);
  refresh();
  return Object.freeze({ ids: () => selected.map(item => item.id), preparing: () => jobs > 0,
    artifactIds: () => selected.map(item => item.artifact_id).filter(Boolean),
    attachLibrary, clear, refresh, renderMessage });
})();

// Context Panel is a view of the existing session snapshot and Library APIs.
// Keep it bundled here so existing hosts do not need another static route.
window.ContextPanel = (() => {
  const root = byId("inspector"), timeline = byId("cp-activity");
  let panel = readNavigationChoice("context-panel-tab", ["agent", "library"], "agent");
  let section = readNavigationChoice("context-inspector-tab", ["activity", "changes", "details"], "activity");
  let scope = readNavigationChoice("context-library-scope", ["current", "all"], "current");
  let view = readNavigationChoice("context-library-view", ["list", "grid", "gallery"], "list");
  let session = "", offset = 0, libraryRead = 0, controller, timer, loadedKey = "", selectedKey = "";
  let changesKey = "", detailsKey = "";
  const eventSignatures = new WeakMap();
  const items = byId("cp-file-items"), status = byId("cp-library-status");
  const mobileAttachments = matchMedia("(max-width: 850px)");
  const desktopHint = "Drag a file into chat to attach it.";
  const touchHint = "Use the chat attachment menu to add files.";
  const attachmentHint = () => mobileAttachments.matches ? touchHint : desktopHint;
  function updateAttachmentHint() {
    for (const hint of [desktopHint, touchHint]) {
      if (status.textContent.endsWith(hint)) {
        status.textContent = status.textContent.slice(0, -hint.length) + attachmentHint();
        break;
      }
    }
  }
  mobileAttachments.addEventListener("change", updateAttachmentHint);
  const text = (tag, value, className = "") => {
    const node = document.createElement(tag); node.textContent = String(value ?? "");
    if (className) node.className = className;
    return node;
  };
  const duration = seconds => seconds < 1 ? "<1s" : seconds < 60 ? `${Math.round(seconds)}s` :
    `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  function tabs(ids, chosen, activate) {
    ids.forEach(id => {
      const button = byId(id), active = id === chosen;
      button.setAttribute("aria-selected", String(active)); button.tabIndex = active ? 0 : -1;
      button.onclick = () => activate(id);
      button.onkeydown = event => {
        let index = ids.indexOf(id);
        if (event.key === "ArrowRight") index = (index + 1) % ids.length;
        else if (event.key === "ArrowLeft") index = (index + ids.length - 1) % ids.length;
        else if (event.key === "Home") index = 0;
        else if (event.key === "End") index = ids.length - 1;
        else return;
        event.preventDefault(); activate(ids[index]); byId(ids[index]).focus();
      };
    });
  }
  function choosePanel(value) {
    panel = value; saveNavigationChoice("context-panel-tab", value);
    tabs(["cp-tab-agent", "cp-tab-library"], `cp-tab-${panel}`, id => choosePanel(id.slice(7)));
    byId("cp-agent").hidden = panel !== "agent"; byId("cp-library").hidden = panel !== "library";
    if (panel === "library") loadLibrary();
  }
  function chooseSection(value) {
    section = value; saveNavigationChoice("context-inspector-tab", value);
    const names = ["activity", "changes", "details"];
    tabs(names.map(name => `cp-tab-${name}`), `cp-tab-${section}`, id => chooseSection(id.slice(7)));
    names.forEach(name => { byId(`cp-${name}`).hidden = name !== section; });
  }
  function chooseScope(value) {
    scope = value; offset = 0; saveNavigationChoice("context-library-scope", value);
    tabs(["cp-scope-current", "cp-scope-all"], `cp-scope-${scope}`, id => chooseScope(id.slice(9)));
    byId("cp-files").setAttribute("aria-labelledby", `cp-scope-${scope}`);
    loadLibrary();
  }
  function chooseView(value) {
    view = value; offset = 0; saveNavigationChoice("context-library-view", value);
    for (const button of byId("cp-view-modes").children)
      button.setAttribute("aria-pressed", String(button.dataset.cpView === value));
    items.dataset.view = view; loadLibrary();
  }
  for (const [id, icon] of [["cp-previous", "previous"], ["cp-next", "next"]]) byId(id).append(libraryIcon(icon));
  for (const button of byId("cp-view-modes").children) {
    button.append(libraryIcon(button.dataset.cpView));
    button.onclick = () => chooseView(button.dataset.cpView);
  }
  function executionStatus(snapshot) {
    if (snapshot.active_turn_id && snapshot.approvals?.length) return "Awaiting Approval";
    if (snapshot.active_turn_id) return "Running";
    return { completed: "Completed", cancelled: "Cancelled", failed: "Failed",
      partial: "Incomplete", interrupted: "Interrupted", running: "Interrupted" }[snapshot.activity?.lifecycle] || "Idle";
  }
  function eventRows(events) {
    const rows = new Map();
    // Snapshot IDs are authoritative, globally ordered and stable across replay.
    for (const event of [...events].sort((a, b) => Number(a.id) - Number(b.id))) {
      if (event.kind.startsWith("tool.") && event.execution_id) {
        const key = `${event.turn_id}:tool:${event.execution_id}`;
        const row = rows.get(key) || { key, turn: event.turn_id, type: "tool", inspection: {} };
        row.tool = event.tool || row.tool || "Tool";
        row.inspection = { ...row.inspection, ...event.inspection };
        if (event.kind === "tool.requested") row.requested = event.timestamp;
        if (event.kind === "tool.started") row.started = event.timestamp;
        if (event.kind === "tool.finished") row.finished = event;
        rows.set(key, row);
      } else rows.set(`${event.turn_id}:${event.id}`, { key: `${event.turn_id}:${event.id}`, ...event });
    }
    return [...rows.values()];
  }
  const eventNames = {
    "turn.accepted": "Execution accepted", "turn.started": "Execution started",
    "turn.completed": "Execution completed", "turn.failed": "Execution failed",
    "turn.partial": "Execution incomplete", "turn.cancelled": "Execution cancelled",
    "turn.interrupted": "Execution interrupted", "approval.required": "Approval requested",
    "approval.resolved": "Approval resolved", "user_input.required": "Question asked",
    "user_input.resolved": "Question resolved",
  };
  function renderEvents(snapshot) {
    const projection = snapshot.inspector;
    const rows = eventRows(projection?.events || []);
    const old = new Map([...timeline.querySelectorAll("[data-event-key]")].map(node => [node.dataset.eventKey, node]));
    const children = [];
    if (!rows.length) children.push(text("p", snapshot.context_panel ? projection?.history_missing ?
      "Execution history is no longer available for this task." :
      "Start a conversation to see execution history." : "Restart Web UI, then reload to enable Inspector history.", "muted"));
    else children.push(text("p", projection.limited ? "Recent execution history · limited to 320 public events" :
      "Execution history", "cp-section-caption"));
    for (const row of rows) {
      const signature = JSON.stringify([row, snapshot.active_turn_id, snapshot.activity?.lifecycle]);
      const previous = old.get(row.key);
      if (previous && eventSignatures.get(previous) === signature) { children.push(previous); continue; }
      let label = eventNames[row.kind] || "Execution event", outcome = "", detail = "";
      if (row.type === "tool") {
        label = row.tool;
        outcome = row.finished ? ({ succeeded: "Completed", failed: "Failed", denied: "Denied",
          cancelled: "Cancelled", skipped: "Not run", rejected: "Not executed" }[row.finished.status] || "Unconfirmed") :
          row.turn === snapshot.active_turn_id ? (row.started ? "Running" : "Requested") : "Unconfirmed";
        detail = row.inspection.path || "";
      } else {
        outcome = row.status || (row.kind.endsWith(".required") ? "Needs attention" : "");
        detail = row.tool || "";
        if (row.kind === "approval.resolved") label = { accepted: "Approval accepted", denied: "Approval denied",
          expired: "Approval expired" }[row.status] || label;
      }
      const node = document.createElement("details"); node.className = "cp-event";
      node.dataset.eventKey = row.key; eventSignatures.set(node, signature);
      node.dataset.outcome = outcome; node.open = previous?.open || false;
      const summary = document.createElement("summary");
      const symbol = text("span", "", "cp-event-icon"); symbol.setAttribute("aria-hidden", "true");
      symbol.append(libraryIcon(outcome === "Failed" || row.kind === "turn.failed" ? "info" :
        outcome === "Running" ? "refresh" : outcome === "Denied" || outcome === "Cancelled" ||
        row.kind === "turn.cancelled" ? "close" : row.type === "tool" ? "check" : "info"));
      const caption = document.createElement("span"); caption.className = "cp-event-summary";
      caption.append(text("strong", label), text("small", [detail, outcome].filter(Boolean).join(" · ")));
      const arrow = libraryIcon("disclosure"); arrow.classList.add("cp-disclosure");
      summary.append(symbol, caption, arrow); node.append(summary);
      const body = document.createElement("div"); body.className = "cp-event-expanded";
      const fields = document.createElement("dl"); fields.className = "cp-diagnostics";
      function pair(name, value) { fields.append(text("dt", name), text("dd", value)); }
      pair("Turn", row.turn || row.turn_id);
      if (row.type === "tool") {
        if (row.inspection.path) pair("Path", row.inspection.path);
        if (row.finished) pair("Execution", row.finished.executed === true ? "Executed" :
          row.finished.executed === false ? "Not executed" : "Unavailable");
        if (row.started && row.finished?.timestamp >= row.started)
          pair("Duration", duration(row.finished.timestamp - row.started));
        if (row.inspection.changed) pair("Change", `+${row.inspection.added ?? "?"} / −${row.inspection.removed ?? "?"} lines`);
        if (row.inspection.error_type) pair("Error", row.inspection.error_type);
      }
      const timestamp = row.timestamp || row.requested || row.started || row.finished?.timestamp;
      if (timestamp) pair(row.type === "tool" && row.requested ? "Requested" : "Time",
        new Date(timestamp * 1000).toLocaleString());
      body.append(fields);
      if (row.type === "tool") body.append(text("p", "Raw arguments and output bodies are private.", "muted"));
      node.append(body);
      if (previous?.contains(document.activeElement)) requestAnimationFrame(() => summary.focus({ preventScroll: true }));
      children.push(node);
    }
    timeline.replaceChildren(...children);
  }
  function inspectWorkspace(operation, path = ".") {
    showView("workspace"); byId("workspace-path").value = path;
    workspaceRead(operation);
    if (compactInspector.matches) setContextPanel(false);
    byId("workspace-result").setAttribute("tabindex", "-1"); byId("workspace-result").focus();
  }
  function renderChanges(snapshot) {
    const changes = snapshot.inspector?.file_changes || [];
    const key = JSON.stringify([session, changes, snapshot.inspector?.limited]);
    if (key === changesKey) return; changesKey = key;
    const container = byId("cp-changes"); container.replaceChildren();
    container.append(text("p", changes.length ? "Verified edits from this session’s recent execution history." :
      "No verified workspace edits in the available session history.", "muted"));
    for (const change of changes) {
      const row = document.createElement("div"); row.className = "cp-change";
      const caption = document.createElement("div");
      caption.append(text("strong", change.path.split("/").pop()), text("small", `${change.path} · ${change.status}`));
      const button = text("button", "Inspect", "quiet"); button.type = "button";
      button.setAttribute("aria-label", `Inspect current file ${change.path}`);
      button.onclick = () => inspectWorkspace("file", change.path);
      row.append(fileIcon({ name: change.path, filename: change.path, mime: "text/plain" }), caption, button); container.append(row);
    }
    const diff = text("button", "Current workspace diff", "secondary"); diff.type = "button";
    diff.onclick = () => inspectWorkspace("diff"); container.append(diff);
    container.append(text("p", "Diff shows current uncommitted workspace changes, including edits outside this session. Committed edits may have no remaining diff.", "muted"));
  }
  function renderDetails(snapshot, state) {
    const info = snapshot.inspector || {};
    const values = [["Session", info.name || "Unnamed conversation"], ["Session ID", snapshot.session_id],
      ["Model", snapshot.model || "Unavailable"], ["Provider", snapshot.provider || "Unavailable"],
      ["Status", state], ["Mode", snapshot.mode || "Unavailable"],
      ["Reasoning effort", snapshot.effort || "Unavailable"], ["Tool calls (current task)", info.tool_count ?? "Unavailable"]];
    if (snapshot.model_connection) values.push(["Connection", snapshot.model_connection]);
    if (typeof snapshot.plan_mode === "boolean") values.push(["Plan mode", snapshot.plan_mode ? "On" : "Off"]);
    if (info.started_at && info.completed_at >= info.started_at)
      values.push(["Execution duration", duration(info.completed_at - info.started_at)]);
    else if (info.started_at && snapshot.active_turn_id)
      values.push(["Started", new Date(info.started_at * 1000).toLocaleString()]);
    values.push(["Context / tokens", "Unavailable"], ["Subagents", "Unavailable"]);
    const key = JSON.stringify(values); if (key === detailsKey) return; detailsKey = key;
    const list = document.createElement("dl"); list.className = "cp-diagnostics";
    values.forEach(([name, value]) => list.append(text("dt", name), text("dd", value)));
    byId("cp-details").replaceChildren(list);
  }
  function render(snapshot) {
    if (!authenticated || snapshot.session_id !== latest?.session_id) return;
    if (session !== snapshot.session_id) { reset(); session = snapshot.session_id; }
    const state = executionStatus(snapshot), info = snapshot.inspector || {};
    byId("cp-status").textContent = state; byId("cp-status").dataset.state = state;
    const request = [...(snapshot.messages || [])].reverse().find(item => item.role === "user");
    byId("cp-task-label").textContent = info.turn_id && request ? request.content.slice(0, 500) : "No active task";
    const running = eventRows(info.events || []).filter(row => row.type === "tool" &&
      row.turn === snapshot.active_turn_id && row.started && !row.finished).at(-1);
    const operation = running ? [running.tool, running.inspection.path].filter(Boolean).join(" · ") :
      snapshot.active_turn_id ? snapshot.activity?.label : "";
    byId("cp-operation").hidden = !operation; byId("cp-operation").textContent = operation || "";
    byId("cp-model").textContent = [snapshot.model, snapshot.provider].filter(Boolean).join(" · ") || "Model unavailable";
    byId("cp-tool-count").textContent = info.tool_count == null ? "Tool count unavailable" :
      `${info.tool_count} tool call${info.tool_count === 1 ? "" : "s"}`;
    const approvals = snapshot.approvals?.length || 0;
    byId("cp-approvals").hidden = !approvals;
    byId("cp-approval-count").textContent = `${approvals} approval${approvals === 1 ? " needs" : "s need"} attention`;
    renderEvents(snapshot); renderChanges(snapshot); renderDetails(snapshot, state);
    if (panel === "library") loadLibrary();
  }
  byId("cp-view-approvals").onclick = () => {
    showView("chat"); if (compactInspector.matches) setContextPanel(false);
    byId("approvals").scrollIntoView({ block: "center" }); byId("approvals").querySelector("button")?.focus();
  };
  function fileRow(item) {
    const { card: row, open: preview } = createFileTile(item, preview =>
      openArtifact(item.id, { origin: preview, item }).catch(error => { status.textContent = error.message; }));
    row.className = "cp-file file-item"; row.draggable = true;
    row.dataset.artifact = item.id;
    preview.classList.add("cp-file-preview", "quiet");
    preview.setAttribute("aria-label", `Preview ${item.name}`);
    preview.querySelector(".file-artwork").classList.add("cp-file-art");
    preview.querySelector(".file-name-group").classList.add("cp-file-caption");
    row.addEventListener("dragstart", event => {
      if (!authenticated || !latest?.attachments) { event.preventDefault(); return; }
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("application/x-klaude-library-artifact", JSON.stringify({
        id: item.id, revision: item.revision, session: latest.session_id,
      }));
      event.dataTransfer.setData("text/plain", item.name);
    });
    return row;
  }
  function canLoad() { return authenticated && latest?.session_id && panel === "library" && contextPanelOpen; }
  async function loadLibrary() {
    if (!canLoad()) return;
    if (latest.context_panel !== true) {
      items.replaceChildren(); status.textContent = "Restart Web UI, then reload to enable the context Library."; return;
    }
    const references = ChatAttachmentsUI.artifactIds().join(",");
    const query = new URLSearchParams({ kind: "all", archived: "false", scope, sort: "newest",
      query: byId("cp-search").value, offset, images: view === "gallery" ? "1" : "0", references });
    const key = `${latest.session_id}:${query}`;
    if (key === loadedKey) return;
    loadedKey = key; controller?.abort(); controller = new AbortController();
    const read = ++libraryRead, epoch = authEpoch, current = latest.session_id;
    const valid = () => read === libraryRead && epoch === authEpoch && current === latest?.session_id && authenticated;
    status.textContent = "Loading files…"; byId("cp-files").setAttribute("aria-busy", "true");
    // Never leave another scope/session’s files actionable while a read is pending.
    items.replaceChildren(); byId("cp-previous").disabled = byId("cp-next").disabled = true;
    try {
      const result = await jsonRequest(`/api/v1/library/items?${query}`, "GET", undefined, { signal: controller.signal });
      if (!valid()) return;
      if (result.session_id !== current || result.scope !== scope) throw new Error("Conversation changed.");
      const nodes = [];
      let previousMonth = "";
      for (const item of result.items) {
        if (view === "gallery") {
          const month = fileDate(item.created, { month: "long", year: "numeric" });
          if (month !== previousMonth) {
            nodes.push(text("h2", month, "gallery-month")); previousMonth = month;
          }
        }
        nodes.push(fileRow(item));
      }
      items.replaceChildren(...nodes);
      status.textContent = (result.scope_limited ? "Older attachment links may only appear in All. " : "") +
        (result.items.length ? attachmentHint() :
          scope === "current" ? "No matching files linked to this conversation. Try All." : "No matching saved files.");
      byId("cp-previous").disabled = offset === 0; byId("cp-next").disabled = !result.more;
      byId("cp-page").textContent = `Page ${Math.floor(offset / 20) + 1}${result.total ? ` of ${Math.ceil(result.total / 20)}` : ""}`;
    } catch (error) {
      if (valid() && error.name !== "AbortError") { status.textContent = `${error.message} Select Library to retry.`; loadedKey = ""; }
    } finally { if (valid()) byId("cp-files").removeAttribute("aria-busy"); }
  }
  byId("cp-search").oninput = () => { clearTimeout(timer); timer = setTimeout(() => { offset = 0; loadLibrary(); }, 220); };
  byId("cp-search-form").onsubmit = event => { event.preventDefault(); clearTimeout(timer); offset = 0; loadLibrary(); };
  byId("cp-previous").onclick = () => { offset = Math.max(0, offset - 20); loadLibrary(); };
  byId("cp-next").onclick = () => { offset += 20; loadLibrary(); };
  function reset() {
    ++libraryRead; controller?.abort(); clearTimeout(timer); loadedKey = ""; session = "";
    changesKey = detailsKey = ""; offset = 0; selectedKey = "";
    items.replaceChildren(); timeline.replaceChildren(text("p", "No execution history loaded.", "muted"));
    byId("cp-changes").replaceChildren(); byId("cp-details").replaceChildren();
    byId("cp-task-label").textContent = "No active task"; byId("cp-status").textContent = "Idle";
    byId("cp-status").dataset.state = "Idle";
    byId("cp-model").textContent = "Model unavailable"; byId("cp-operation").hidden = true;
    byId("cp-operation").textContent = ""; byId("cp-approval-count").textContent = "";
    byId("cp-tool-count").textContent = "0 tool calls"; byId("cp-approvals").hidden = true;
    byId("cp-page").textContent = "Page 1";
    byId("cp-previous").disabled = byId("cp-next").disabled = true;
    byId("cp-files").removeAttribute("aria-busy"); status.textContent = "";
  }
  document.addEventListener("klaude-snapshot", event => render(event.detail));
  document.addEventListener("klaude-context-panel", () => { if (canLoad()) loadLibrary(); });
  document.addEventListener("klaude-attachments", () => {
    const next = ChatAttachmentsUI.artifactIds().join(",");
    if (next !== selectedKey) { selectedKey = next; if (scope === "current") loadLibrary(); }
  });
  document.addEventListener("klaude-chat-session-changed", reset);
  document.addEventListener("klaude-auth-reset", () => { reset(); byId("cp-search").value = ""; });
  choosePanel(panel); chooseSection(section); chooseScope(scope); chooseView(view);
  if (latest) render(latest);
  return Object.freeze({ render });
})();
