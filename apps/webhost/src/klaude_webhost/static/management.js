"use strict";

// Category-local drafts never enter browser storage. The saved baseline is a
// confirmed read; an operation receipt alone is not a replacement for that read.
window.SettingsDraftState = class {
  constructor() { this.entries = new Map(); }
  static equal(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  // Settings are JSON values; copy them without an additional browser API
  // dependency so the draft store also works in older browser environments.
  static clone(value) { return value === undefined ? undefined : JSON.parse(JSON.stringify(value)); }
  ingest(fields) {
    for (const field of fields) {
      const entry = this.entries.get(field.id);
      if (!entry) this.entries.set(field.id, { base: field, latest: field, value: window.SettingsDraftState.clone(field.value) });
      else {
        entry.latest = field;
        if (!entry.pending && (!this.dirty(entry) || window.SettingsDraftState.equal(entry.value, field.value))) {
          entry.base = field; entry.value = window.SettingsDraftState.clone(field.value); entry.conflict = false;
        } else if (!entry.pending) {
          entry.conflict = !window.SettingsDraftState.equal(entry.base.version, field.version);
        }
      }
    }
  }
  dirty(entry) { return !entry.recovery && (Boolean(entry.conflict) || !window.SettingsDraftState.equal(entry.value, entry.base.value)); }
  changed() { return [...this.entries.values()].filter(entry => this.dirty(entry)); }
  get(id) { return this.entries.get(id)?.value; }
  set(id, value) {
    const entry = this.entries.get(id);
    if (!entry || entry.pending) return;
    entry.value = window.SettingsDraftState.clone(value); entry.error = "";
    if (window.SettingsDraftState.equal(value, entry.latest.value)) {
      entry.base = entry.latest; entry.conflict = false;
    }
  }
  discard(id) {
    for (const entry of id ? [this.entries.get(id)] : this.entries.values()) {
      if (!entry || entry.pending) continue;
      entry.base = entry.latest; entry.value = window.SettingsDraftState.clone(entry.latest.value);
      entry.conflict = false; entry.error = "";
    }
  }
  rebase(id) {
    const entry = this.entries.get(id);
    if (entry && !entry.pending) { entry.base = entry.latest; entry.conflict = false; entry.error = ""; }
  }
  confirm(entry) {
    entry.base = entry.latest; entry.value = window.SettingsDraftState.clone(entry.latest.value);
    entry.pending = null; entry.conflict = false; entry.error = "";
  }
};

window.SettingsDrafts = (() => {
  const categories = new Map();
  const terminal = new Set(["completed", "failed", "cancelled", "unknown"]);
  let securityDialog, securityResolve;
  const equal = window.SettingsDraftState.equal;
  function category(id) { return categories.get(id); }
  function register(id, adapter) {
    const state = { id, adapter, drafts: new window.SettingsDraftState(), saving: false, message: "" };
    const bar = domainText("div", "", "settings-save-bar"); bar.id = `${id}-save-bar`; bar.hidden = true;
    const summary = domainText("div", "", "settings-save-summary");
    const count = domainText("strong", ""); count.id = `${id}-unsaved-count`;
    count.setAttribute("role", "status"); count.setAttribute("aria-atomic", "true");
    const status = domainText("span", "", "muted"); status.id = `${id}-save-status`; status.setAttribute("role", "status");
    summary.append(count, status);
    const actions = domainText("div", "", "settings-save-actions");
    const check = domainButton("Check save status", () => checkPending(state)); check.id = `${id}-save-check`;
    const discard = domainButton("Discard", () => {
      if (state.saving || pending(state).length) return;
      state.drafts.discard(); state.message = ""; adapter.render(); render(state);
    }); discard.id = `${id}-discard`;
    const save = domainButton("Save changes", () => saveCategory(state), ""); save.id = `${id}-save`;
    actions.append(check, discard, save);
    const conflicts = domainText("div", "", "settings-conflicts");
    bar.append(summary, actions, conflicts);
    byId(adapter.panel).append(bar);
    window.SettingsActions?.register(bar, byId(adapter.panel));
    Object.assign(state, { bar, count, status, check, discard, save, conflicts }); categories.set(id, state);
    return state;
  }
  const pending = state => [...state.drafts.entries.values()].filter(entry => entry.pending);
  function render(state) {
    const changed = state.drafts.changed(), unresolved = pending(state);
    const count = changed.reduce((total, entry) => total + (state.adapter.count?.(entry) ?? 1), 0);
    state.bar.hidden = !changed.length && !unresolved.length;
    state.count.textContent = `${count} unsaved change${count === 1 ? "" : "s"}`;
    state.status.textContent = state.message;
    state.check.hidden = !unresolved.length;
    state.check.disabled = state.saving;
    state.discard.disabled = state.saving || Boolean(unresolved.length);
    state.save.disabled = state.saving || Boolean(unresolved.length) || !changed.length || changed.some(entry => entry.conflict) || Boolean(state.adapter.blocked?.());
    state.bar.setAttribute("aria-busy", String(state.saving));
    state.conflicts.replaceChildren();
    for (const entry of changed.filter(item => item.conflict)) {
      const row = domainText("div", "", "settings-conflict");
      row.append(domainText("p", `${entry.base.label} changed elsewhere. Saved: ${display(entry.latest.value)}. Your draft: ${display(entry.value)}.`));
      const saved = domainButton("Use saved value", () => {
        if (state.saving) return;
        state.drafts.discard(entry.base.id); state.adapter.render(); render(state);
      });
      const keep = domainButton("Keep my change", () => {
        if (state.saving) return;
        state.drafts.rebase(entry.base.id); state.adapter.render(); render(state);
      });
      saved.disabled = keep.disabled = state.saving || Boolean(unresolved.length);
      row.append(saved, keep);
      state.conflicts.append(row);
    }
  }
  function display(value) { return Array.isArray(value) ? value.join(", ") || "Unset" : value === null || value === "" ? "Unset" : typeof value === "object" ? Object.entries(value).map(([key, item]) => `${key}: ${item}`).join(", ") : String(value); }
  function ingest(id, fields) { const state = category(id); state.drafts.ingest(fields); render(state); }
  function set(id, key, value) {
    const state = category(id); if (state.saving) return;
    state.drafts.set(key, value); state.message = ""; render(state); state.adapter.changed?.();
  }
  function confirmSecurity(warnings) {
    if (!warnings.length) return Promise.resolve(true);
    if (securityDialog?.open) return Promise.resolve(false);
    if (!securityDialog) {
      securityDialog = domainText("dialog", "", "domain-dialog settings-security"); securityDialog.id = "settings-security";
      securityDialog.setAttribute("aria-labelledby", "settings-security-title");
      const title = domainText("h2", "Allow these access changes?"); title.id = "settings-security-title";
      const text = domainText("p", "These changes relax access or approval restrictions. Other backend protections still apply.");
      const list = domainText("ul", ""); list.id = "settings-security-details";
      const actions = domainText("div", "", "dialog-actions");
      const cancel = domainButton("Cancel", () => securityDialog.close()); cancel.id = "settings-security-cancel";
      const allow = domainButton("Save changes", () => { securityResolve?.(true); securityResolve = null; securityDialog.close(); }, ""); allow.id = "settings-security-confirm";
      actions.append(cancel, allow); securityDialog.append(title, text, list, actions); document.body.append(securityDialog);
      securityDialog.addEventListener("close", () => { securityResolve?.(false); securityResolve = null; });
    }
    byId("settings-security-details").replaceChildren(...warnings.map(text => domainText("li", text)));
    securityDialog.showModal(); byId("settings-security-cancel").focus();
    return new Promise(resolve => { securityResolve = resolve; });
  }
  function accessWarning(entry) {
    const id = entry.base.id, from = entry.base.value, to = entry.value;
    if (id.startsWith("permissions.")) {
      const rank = { deny: 0, ask: 1, allow: 2 };
      const labels = { deny: "Deny", ask: "Ask first", allow: "Automatic" };
      if (rank[to] > rank[from]) return `${entry.base.label}: ${labels[from]} → ${labels[to]}. ${to === "allow" ? "The tool can execute without an approval prompt." : "The tool can request execution approval instead of being denied."}`;
    }
    if (id.startsWith("tool_availability.") && to === true && from === false)
      return `${entry.base.label}: enable this tool for future turns. Its configured approval policy and access checks apply.`;
    if (["fetch_settings.exa_fallback", "fetch_settings.exa_enabled"].includes(id) && to === true && from === false)
      return `${entry.base.label}: allow web content requests through the configured Exa service.`;
    return null;
  }
  function current(epoch) { return authenticated && authEpoch === epoch; }
  async function bounded(promise) {
    let timer;
    try {
      return await Promise.race([promise, new Promise((resolve, reject) => {
        timer = setTimeout(() => reject(new Error("Connection timed out. Reconnect and check save status if a save was submitted.")), 30000);
      })]);
    } finally { clearTimeout(timer); }
  }
  const request = (...args) => bounded(domainRequest(...args));
  async function prepare(entry, operation, epoch) {
    const prepared = await request("/api/v1/library/review", "POST", { draft: operation });
    if (!current(epoch)) {
      domainRequest("/api/v1/library/discard", "POST", { review_id: prepared.review_id }).catch(() => {});
      throw new DOMException("Signed out", "AbortError");
    }
    entry.pending = { review_id: prepared.review_id, request_id: requestId(), phase: "submitting" };
    return submit(entry);
  }
  async function submit(entry) {
    const receipt = entry.pending;
    try {
      const operation = await request("/api/v1/library/submit", "POST", {
        review_id: receipt.review_id, request_id: receipt.request_id,
      });
      receipt.phase = "accepted"; return operation;
    } catch (error) {
      if (error.name === "AbortError") throw error;
      // Keep the exact request ID even for a rejected retry: a prior response
      // could have been lost. Only a confirmed status resolves that uncertainty.
      if (receipt.phase === "submitting" && error.status >= 400 && error.status < 500) {
        entry.pending = null;
        domainRequest("/api/v1/library/discard", "POST", { review_id: receipt.review_id }).catch(() => {});
      } else receipt.phase = "unconfirmed";
      throw error;
    }
  }
  async function waitFor(entry, operation, epoch) {
    const deadline = Date.now() + 15000;
    while (!terminal.has(operation.state)) {
      if (!current(epoch)) throw new DOMException("Signed out", "AbortError");
      if (Date.now() > deadline) throw new Error("Save is still running. Check save status to continue.");
      await new Promise(resolve => setTimeout(resolve, 350));
      operation = await request(`/api/v1/library/operation?id=${entry.pending.request_id}`);
    }
    if (operation.state === "unknown") {
      entry.pending.phase = "unknown";
      throw new Error("Save outcome is unconfirmed. Check Activity and the saved-state recovery controls before retrying.");
    }
    if (operation.state !== "completed") {
      await releaseSnapshot(entry.pending);
      entry.pending = null;
      throw new Error("Save was rejected. Refresh the saved values, resolve any conflicts, then save again.");
    }
    entry.pending.phase = "persisted";
    await releaseSnapshot(entry.pending);
  }
  async function releaseSnapshot(receipt) {
    // A terminal receipt can be checked without its preparation token. Release
    // only that snapshot slot, so a category with >16 edits can finish saving.
    // The server refuses this cleanup for running/unknown operations.
    await request("/api/v1/library/discard", "POST", { review_id: receipt.review_id }).catch(() => {});
  }
  async function finishEntry(state, entry, epoch) {
    await bounded(state.adapter.refresh());
    if (!current(epoch)) throw new DOMException("Signed out", "AbortError");
    if (entry.recovery) { state.drafts.entries.delete("recovery"); return; }
    // A concurrent edit after our successful save is still a conflict, rather
    // than evidence that our draft was the final value in storage.
    entry.pending = null;
    if (!equal(entry.latest.value, state.adapter.normalized?.(entry) ?? entry.value)) {
      entry.conflict = true;
      throw new Error(`${entry.base.label} changed again. Choose which value to keep.`);
    }
    state.drafts.confirm(entry);
  }
  async function saveCategory(state) {
    if (state.save.disabled || state.saving) return;
    const entries = state.drafts.changed().sort((a, b) => (state.adapter.order?.(a) || 0) - (state.adapter.order?.(b) || 0));
    if (!entries.length || !state.adapter.validate(entries)) return;
    const epoch = authEpoch;
    state.saving = true; state.message = ""; render(state); state.adapter.changed?.();
    let saved = 0, savingLabel = "";
    try {
      const warnings = entries.map(entry => state.adapter.warning?.(entry) || accessWarning(entry)).filter(Boolean);
      if (!await confirmSecurity(warnings) || !current(epoch)) return;
      for (const entry of entries) {
        savingLabel = entry.base.label;
        state.message = `Saving ${entry.base.label}… ${saved} of ${entries.length} saved. Changes are saved individually.`; render(state);
        const operation = await prepare(entry, state.adapter.operation(entry), epoch);
        render(state);
        await waitFor(entry, operation, epoch);
        await finishEntry(state, entry, epoch); saved += 1;
      }
      state.message = "";
    } catch (error) {
      if (current(epoch)) {
        state.message = `${saved ? `${saved} change${saved === 1 ? "" : "s"} saved. ` : ""}${savingLabel ? `${savingLabel}: ` : ""}${error.message}${pending(state).length ? " Use Check save status; do not start another save." : " Your remaining drafts are kept."}`;
        // Read-only refresh exposes CAS conflicts without rebasing the draft.
        if (!pending(state).length) await bounded(state.adapter.refresh()).catch(() => {});
      }
    } finally {
      if (current(epoch)) { state.saving = false; render(state); state.adapter.render(); }
      loadOperations();
    }
  }
  async function checkPending(state) {
    if (state.saving) return;
    const epoch = authEpoch; state.saving = true; state.message = "Checking the original save…"; render(state); state.adapter.changed?.();
    try {
      for (const entry of pending(state)) {
        if (entry.pending.phase !== "persisted") {
          let operation;
          try { operation = await request(`/api/v1/library/operation?id=${entry.pending.request_id}`); }
          catch (error) {
            if (error.status !== 400) throw error;
            // Retry only the original immutable snapshot and ID. Never create
            // a second mutation to recover a lost acknowledgement.
            try { operation = await submit(entry); }
            catch (submitError) {
              if (submitError.status >= 400 && submitError.status < 500) {
                try { operation = await request(`/api/v1/library/operation?id=${entry.pending.request_id}`); }
                catch (statusError) { if (statusError.status === 400) entry.pending = null; throw submitError; }
              } else throw submitError;
            }
          }
          await waitFor(entry, operation, epoch);
        }
        await finishEntry(state, entry, epoch);
      }
      state.message = state.drafts.changed().length ? "Save status confirmed. Remaining changes are still drafts." : "";
    } catch (error) { if (current(epoch)) state.message = `${error.message} Your remaining drafts are kept.`; }
    finally { if (current(epoch)) { state.saving = false; render(state); state.adapter.render(); } loadOperations(); }
  }
  async function recover(id, operation) {
    const state = category(id), epoch = authEpoch;
    if (state.saving || state.drafts.entries.get("recovery")?.pending) return;
    state.saving = true; state.message = "Checking the exact saved state…"; render(state); state.adapter.changed?.();
    // Recovery itself has a durable receipt, retained if its acknowledgement is
    // lost. It never submits the original settings mutation again.
    const entry = { base: { id: "recovery", label: "Saved-state check" }, value: null, recovery: true };
    state.drafts.entries.set("recovery", entry);
    try {
      const receipt = await prepare(entry, operation, epoch);
      await waitFor(entry, receipt, epoch);
      entry.pending = null; state.drafts.entries.delete("recovery");
      await bounded(state.adapter.refresh());
      state.message = "Saved-state check completed. Check the original save status before saving remaining drafts.";
    } catch (error) {
      if (current(epoch)) {
        if (!entry.pending) state.drafts.entries.delete("recovery");
        state.message = `${error.message} Check Activity before retrying.`;
      }
    } finally {
      if (current(epoch)) {
        state.saving = false; render(state); state.adapter.render();
        if (state.adapter.status) byId(state.adapter.status).textContent = state.message;
      }
      loadOperations();
    }
  }
  function validateInput(input) {
    if (!input || input.checkValidity()) return true;
    for (let parent = input.parentElement; parent; parent = parent.parentElement) if (parent.tagName === "DETAILS") parent.open = true;
    input.reportValidity(); return false;
  }
  document.addEventListener("klaude-auth-reset", () => {
    securityDialog?.close();
    for (const state of categories.values()) {
      state.drafts.entries.clear(); state.saving = false; state.message = ""; render(state);
    }
  });
  const normalizedEndpoint = value => value.trim().replace(/\/+$/, "").replace(/^[^:]+(?=:)/, scheme => scheme.toLowerCase());
  return { register, ingest, set, category, accessWarning, validateInput, recover, normalizedEndpoint,
    value: (id, key) => category(id).drafts.get(key),
    locked: id => category(id)?.saving || pending(category(id)).length > 0,
    render: id => render(category(id)) };
})();

// Profile data remains in memory and is cleared at sign-out. Settings drafts
// use the existing exact snapshots and durable receipts without per-field dialogs.
window.BrowserManagement = (() => {
  let memory = null, connections = null;
  let memoryLoad = 0, connectionsLoad = 0;
  let memoryRead = null, connectionsRead = null;
  let settings = null, settingsRead = null, settingsLoad = 0;
  const settingsGroups = new Map();
  SettingsDrafts.register("agent", {
    panel: "agent-settings", render: renderAgentSettings, changed: render,
    refresh: () => loadSettings(true), blocked: () => !settings,
    operation: entry => ({ operation: "setting-save", id: entry.base.id,
      revision: entry.base.revision, value: entry.value }),
    normalized: entry => entry.base.type === "text" ? SettingsDrafts.normalizedEndpoint(entry.value) : entry.value,
    warning: entry => {
      if (!entry.base.id.startsWith("tool_availability.") || entry.value !== true || entry.base.value !== false) return null;
      const policy = SettingsDrafts.value("agent", entry.base.id.replace("tool_availability.", "permissions."));
      return `${entry.base.label}: enable this tool for future turns. ${policy === "allow" ?
        "Automatic approval lets it execute without an approval prompt." : policy === "deny" ?
          "Deny continues to block execution until you change the approval policy." :
          "Ask first requires an approval prompt before execution."} Workspace, network and other access checks still apply.`;
    },
    // Tighten approval before enabling a tool, so a staged Ask first policy
    // cannot temporarily inherit the previous Automatic policy during a batch.
    order: entry => {
      if (entry.base.id.startsWith("permissions.")) {
        const rank = { deny: 0, ask: 1, allow: 2 };
        return rank[entry.value] < rank[entry.base.value] ? -2 : 1;
      }
      if (entry.base.id.startsWith("tool_availability.")) return entry.value ? 2 : -1;
      return 0;
    },
    validate: entries => entries.every(entry => SettingsDrafts.validateInput(byId(`setting-${entry.base.id.replaceAll(".", "-")}`))),
  });
  let jobs = null, jobsRead = null, jobsLoad = 0;
  let profileReady;
  const changes = new Map();
  const connectionFailures = new Map();
  let detailConnection = null;
  let connectionFilter = "all";
  let connectionNotice = "";
  const connectionDialog = byId("connection-detail");
  let selectedSession = null;
  const sessionDialog = byId("session-management");
  const restartHint = "Restart the Web UI host and reload this page to use these controls.";
  const generationDialog = byId("image-generate-panel");
  const generationAdd = byId("image-add");
  // Other management controls also load with the earlier inline image form.
  const generationStatusId = generationDialog ? "image-generate-status" : "generated-jobs-status";
  const generationTabs = byId("generation-tabs");
  let generationType = "image";
  let generationPreparation = 0;

  function active(kind) {
    if (kind === "image") return authenticated && currentView === "library";
    return authenticated && (kind === "sessions" || (kind === "jobs" ? currentView === "library" && librarySection === "outputs" : ["memory", "settings", "media"].includes(kind) ? currentView === "settings" :
      currentView === "integrations" && integrationSection === "connections"));
  }
  function busy(resource) { return changes.has(resource); }
  function row(title, metadata) {
    const node = domainText("article", "", "management-row");
    const text = domainText("div", "", "management-content");
    text.append(domainText("p", title), domainText("small", metadata, "muted"));
    const actions = domainText("div", "", "management-actions");
    node.append(text, actions);
    return { node, actions };
  }
  async function review(draft, resource, kind, options = {}) {
    if (busy(resource)) return;
    const direct = ["mcp-enable", "mcp-disable"].includes(draft.operation);
    const state = { phase: direct ? "preparing" : "review", target: draft.name }, epoch = authEpoch;
    const settingsGeneration = ["settings", "memory", "media"].includes(kind) ? settingsSectionGeneration : null;
    changes.set(resource, state);
    render();
    try {
      const opened = await (direct ? submitToggleChange : prepareChange)(draft, {
        filename: options.filename,
        current: () => active(kind) && epoch === authEpoch &&
          (settingsGeneration === null || settingsGeneration === settingsSectionGeneration) && (options.current?.() ?? true),
        beforeOpen: () => { if (kind === "sessions") sessionDialog.close(); options.beforeOpen?.(); },
        onSubmitting: receipt => {
          if (epoch !== authEpoch) return;
          state.phase = "submitting"; state.request_id = receipt.request_id; render();
        },
        onAccepted: operation => {
          if (epoch !== authEpoch) return;
          state.phase = "accepted"; state.request_id = operation.request_id;
          if (draft.operation === "memory-add") byId("memory-add").reset();
          if (draft.operation === "mcp-add") byId("connection-add").reset();
          if (draft.operation === "research-create") byId("research-create").reset();
          if (draft.operation === "image-generate") byId("image-prompt").value = "";
          options.onAccepted?.(operation);
          render();
        },
        onDiscard: result => {
          if (epoch !== authEpoch) return;
          if (result.uncertain) { state.phase = "unknown"; state.request_id = result.request_id; }
          else changes.delete(resource);
          options.onDiscard?.(result);
          render();
        },
      });
      if (["preparing", "review"].includes(state.phase) && !opened) changes.delete(resource);
    } catch (error) {
      if (epoch === authEpoch) {
        changes.delete(resource);
        if (options.current?.() ?? true) {
          options.onError?.(error);
          domainError(error, options.statusId || (kind === "image" ? "vision-status" : kind === "media" ? "media-settings-status" : kind === "jobs" ? "generated-jobs-status" : kind === "sessions" ? "session-management-status" : kind === "settings" ? "agent-settings-status" : kind === "memory" ? "memory-status" : "connections-status"));
        }
      }
    } finally { render(); }
  }
  function renderMemory() {
    if (!memory) return;
    byId("memory-auto").checked = memory.enabled;
    byId("memory-auto").disabled = busy("memory-settings");
    byId("memory-add").querySelector("button").disabled = busy("memory-facts");
    const query = byId("memory-query").value.trim().toLowerCase();
    const items = memory.entries.filter(item => `${item.fact} ${item.id}`.toLowerCase().includes(query));
    byId("memory-items").replaceChildren(...items.map(item => {
      const pending = changes.get("memory-facts");
      const { node, actions } = row(item.fact, pending ?
        pending.phase === "unknown" ? "Unconfirmed change · check Activity" : "Change pending" : "Saved memory");
      const edit = domainButton("Edit", () => editMemory(item));
      const remove = domainButton("Forget", () => review({ operation: "memory-delete", id: item.id }, "memory-facts", "memory"));
      edit.disabled = Boolean(pending) || item.truncated;
      if (item.truncated) edit.title = "This long memory can be edited in the CLI";
      remove.disabled = Boolean(pending);
      actions.append(edit, remove);
      return node;
    }));
    if (!items.length) byId("memory-items").append(domainText("p", query ? "No matching memories." : "No saved memories.", "muted"));
  }
  function editMemory(item) {
    const { node, actions } = row("", "Edit this saved fact");
    const input = document.createElement("textarea");
    input.value = item.fact; input.maxLength = 500; input.rows = 3;
    input.setAttribute("aria-label", "Replacement memory");
    node.firstChild.prepend(input);
    actions.append(domainButton("Review edit", () => {
      review({ operation: "memory-edit", id: item.id, fact: input.value }, "memory-facts", "memory");
    }), domainButton("Cancel", renderMemory));
    const target = [...byId("memory-items").children].find(child => child.firstChild.firstChild.textContent === item.fact);
    if (target) { target.replaceWith(node); input.focus(); }
  }
  function renderConnections() {
    if (!connections) return;
    const allowed = connections.management_allowed;
    byId("connection-add").querySelector("button").disabled = !allowed || busy("browser-mcp");
    byId("integration-add-connections").disabled = !allowed || busy("browser-mcp");
    const query = byId("connections-query").value.trim().toLowerCase();
    byId("connections-summary").textContent = `${connections.servers.length}${connections.truncated ? "+" : ""} configured · ${connections.servers.filter(item => item.enabled).length} enabled`;
    const items = connections.servers.filter(item => `${item.name} ${item.description}`.toLowerCase().includes(query) &&
      (connectionFilter === "all" || item.enabled === (connectionFilter === "enabled")));
    const nodes = items.map(item => {
      const metadata = [item.enabled ? "Enabled" : "Disabled", item.transport === "stdio" ? "Local program" : "HTTP", countLabel(item.tool_count, "tool")].join(" · ");
      const node = collectionRow(item.name, item.name, metadata, "connection",
        () => openConnection(item), JSON.stringify(item));
      node.classList.add("connection-card", "integration-card");
      node.firstChild.setAttribute("aria-label", `Details for ${item.name}`);
      node.firstChild.setAttribute("aria-description", `${item.description || "No description provided."} ${metadata}.`);
      const text = node.querySelector(".collection-content");
      if (item.description) text.insertBefore(domainText("span", item.description, "collection-description"), text.lastChild);
      const toggle = domainButton("", () => changeConnection(item), "connection-toggle integration-toggle");
      toggle.setAttribute("role", "switch");
      toggle.setAttribute("aria-label", `Enable ${item.name}`);
      const track = domainText("span", "", "integration-switch-track");
      track.setAttribute("aria-hidden", "true");
      toggle.append(track);
      node.append(toggle, domainText("span", "", "integration-row-status"));
      return node;
    });
    reconcileRows(byId("connection-items"), nodes);
    const catalog = new Map(connections.servers.map(item => [item.name, item]));
    for (const node of byId("connection-items").querySelectorAll(".connection-card")) {
      const item = catalog.get(node.dataset.rowKey), toggle = node.querySelector(".connection-toggle");
      const pending = changes.get("browser-mcp");
      toggle.setAttribute("aria-checked", String(item.enabled));
      toggle.setAttribute("aria-busy", String(pending?.target === item.name));
      toggle.disabled = !allowed || Boolean(pending) || !item.enabled && item.oauth;
      toggle.title = !allowed ? "Manage connections from the local Web UI" : !item.enabled && item.oauth ?
        "Sign in through the CLI to enable this OAuth connection" : `${item.enabled ? "Disable" : "Enable"} ${item.name}`;
      const status = node.querySelector(".integration-row-status");
      status.textContent = connectionStatus(item);
      status.setAttribute("role", "status");
    }
    if (!items.length) collectionEmpty(byId("connection-items"), query || connectionFilter !== "all" ? "No matching MCP connections" : "No MCP connections",
      query || connectionFilter !== "all" ? "Try another search or status filter." : "Add a server to get started.", "connection");
    if (connectionDialog.open) {
      const current = catalog.get(detailConnection?.name);
      if (current) { detailConnection = current; renderConnectionDetails(); }
      else { connectionDialog.close(); detailConnection = null; }
    }
  }
  function connectionStatus(item) {
    const pending = changes.get("browser-mcp");
    if (pending?.target === item.name) return pending.phase === "review" ? "Awaiting review" :
      pending.phase === "unknown" ? "Unconfirmed · check Activity before retrying" : "Updating…";
    return connectionFailures.get(item.name) || (!connections.management_allowed ? "Manage from the local Web UI." :
      !item.enabled && item.oauth ? "Sign in through the CLI to enable this OAuth connection." : "");
  }
  function renderConnectionDetails() {
    if (!detailConnection || !connections) return;
    const item = detailConnection;
    byId("connection-detail-title").textContent = item.name;
    byId("connection-detail-description").textContent = item.description || "No description provided.";
    const metadata = byId("connection-detail-metadata");
    metadata.replaceChildren();
    for (const [label, value] of [["Status", item.enabled ? "Enabled" : "Disabled"],
      ["Connection", item.transport === "stdio" ? "Local program" : "HTTP"],
      ["Tools", item.tool_count], ["Source", item.source_label], ["OAuth", item.oauth ? "Configured" : "Not configured"]]) {
      if (value !== undefined && value !== null) metadata.append(domainText("dt", label), domainText("dd", String(value)));
    }
    byId("connection-detail-status").textContent = connectionStatus(item);
    const unavailable = !connections.management_allowed || busy("browser-mcp");
    byId("connection-detail-change").textContent = item.enabled ? "Disable" : "Enable";
    byId("connection-detail-change").disabled = unavailable || !item.enabled && item.oauth;
    byId("connection-detail-remove").disabled = unavailable;
  }
  function openConnection(item) {
    detailConnection = item; renderConnectionDetails(); connectionDialog.showModal();
  }
  function changeConnection(item, operation = item?.enabled ? "mcp-disable" : "mcp-enable") {
    if (!item || !connections?.management_allowed || busy("browser-mcp") || reviewDialog.open ||
      operation === "mcp-enable" && item.oauth) return;
    connectionFailures.delete(item.name);
    connectionNotice = "";
    review({ operation, name: item.name, fingerprint: item.fingerprint }, "browser-mcp", "connections", {
      current: () => connections?.servers.some(current => current.name === item.name && current.fingerprint === item.fingerprint),
      beforeOpen: () => connectionDialog.close(),
      onError: () => connectionFailures.set(item.name, "Could not update connection. Its confirmed state is unchanged."),
    });
  }
  function render() {
    renderMemory(); renderConnections(); if (sessionsLoaded) renderSessionList();
    renderSessionControls();
    if (generationAdd) {
      generationAdd.disabled = !latest?.profile_management || !jobs || !generationTabs && busy("image-generate");
      generationAdd.title = latest?.profile_management ? generationTabs ? "Create an image or research" : "Generate an image" : restartHint;
    }
    byId("image-generate").querySelector("button").disabled =
      !latest?.profile_management || !jobs?.image_settings.enabled || busy("image-generate");
    byId("research-create").querySelector("button").disabled =
      !latest?.profile_management || !jobs || busy("research-create");
    for (const form of byId("agent-settings-fields").querySelectorAll("[data-setting]")) {
      for (const input of form.querySelectorAll("input, select, button")) input.disabled = SettingsDrafts.locked("agent") || busy(`setting:${form.dataset.setting}`);
    }
    for (const card of byId("agent-settings-fields").querySelectorAll("[data-agent-tool]")) {
      const available = settings?.fields.find(field => field.id === card.dataset.availability);
      const policy = settings?.fields.find(field => field.id === card.dataset.permission);
      const change = changes.get(`setting:${available?.id}`) || changes.get(`setting:${policy?.id}`);
      const blocked = Boolean(change) || SettingsDrafts.locked("agent");
      const enabled = SettingsDrafts.value("agent", available?.id) ?? available?.value;
      const availability = card.querySelector(".tool-availability-form input");
      if (availability) availability.disabled = blocked;
      const controls = card.querySelector(".tool-policy-form");
      if (controls) controls.disabled = blocked || enabled === false;
      const status = card.querySelector(".tool-permission-status");
      const message = change ? change.phase === "unknown" ? "Save unconfirmed. Check Activity before retrying." :
        change.phase === "review" ? "Awaiting confirmation." : "Saving…" : "";
      if (status.textContent !== message) status.textContent = message;
      status.hidden = !message;
    }
    window.BrowserMedia?.renderBusy();
    window.BrowserVision?.renderBusy();
  }
  async function loadJobs() {
    if (!active("jobs")) return;
    if (!latest?.profile_management) {
      byId("generated-jobs-status").textContent = restartHint;
      for (const id of ["research-create", "image-generate"]) byId(id).querySelector("button").disabled = true;
      render();
      return;
    }
    const generation = ++jobsLoad;
    jobsRead?.abort(); jobsRead = new AbortController();
    try {
      const result = await domainRequest("/api/v1/library/jobs", "GET", undefined, { signal: jobsRead.signal });
      if (generation !== jobsLoad || !active("jobs")) return;
      jobs = result;
      byId("research-model-source").querySelector('[value="default"]').disabled = !result.research_model;
      if (!result.research_model) byId("research-model-source").value = "chat";
      byId("research-model-label").textContent = result.research_model ? `Research default: ${result.research_model}. Current chat: ${latest.model}. Queue a question, then start it after review.` : `Uses your current chat model, ${latest.model}, and saved Research budgets. Choose a Research default in Settings to use a separate model.`;
      const imageStatus = byId("image-service-status");
      if (result.image_settings.enabled) imageStatus.textContent = `Image model: ${result.image_settings.model}`;
      else {
        const link = domainText("a", "Model Defaults");
        link.href = "?view=settings&settings=models";
        link.addEventListener("click", event => {
          if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          showView("settings", { section: "models" });
          const heading = byId("model-default-heading");
          heading.tabIndex = -1;
          heading.focus({ preventScroll: true });
          heading.scrollIntoView({ block: "center" });
        });
        imageStatus.replaceChildren("Enable an image service in Klaude's ", link, " to generate images.");
      }
      for (const [kind, items] of [["research", result.research], ["image", result.images]]) {
        const rows = items.map(item => {
          const identity = item.id || item.job;
          const { node, actions } = row(kind === "research" ? item.question : item.model, `${item.status}${item.phase ? ` · ${item.phase}` : ""}`);
          node.dataset.rowKey = identity; node.dataset.rowSignature = JSON.stringify(item) + busy(`${kind}:${identity}`);
          if (kind === "research") {
            if (!["running", "completed"].includes(item.status)) actions.append(domainButton("Start", () => reviewJob({ operation: "research-run", target: identity, revision: item.revision }, `research:${identity}`, kind)));
            if (["running", "queued", "interrupted"].includes(item.status)) actions.append(domainButton("Stop", () => reviewJob({ operation: "research-stop", target: identity, revision: item.revision }, `research-control:${identity}`, kind)));
          } else if (!item.artifact && item.status !== "cancelled") {
            actions.append(domainButton("Recover output", () => reviewJob({ operation: "image-recover", target: identity }, `image-recovery:${identity}`, kind)));
            actions.append(domainButton("Cancel job", () => reviewJob({ operation: "image-cancel", target: identity }, `image-control:${identity}`, kind)));
          }
          const artifact = kind === "research" ? item.report : item.artifact;
          if (artifact) actions.append(domainButton("Open output", () => openArtifact(artifact).catch(domainError)));
          for (const button of actions.children) button.disabled = busy(`${kind}:${identity}`) && button.textContent === "Start";
          return node;
        });
        reconcileRows(byId(`${kind}-jobs`), rows);
        if (!rows.length) byId(`${kind}-jobs`).replaceChildren(domainText("p", `No ${kind === "research" ? "Research" : "image"} jobs yet.`, "muted"));
      }
      byId("generated-jobs-status").textContent = result.research_more || result.images_more ? "Showing the 20 most recent jobs of each type." : "";
      render();
    } catch (error) { if (generation === jobsLoad) domainError(error, "generated-jobs-status"); }
  }
  function generationContext(type) {
    const generation = generationPreparation;
    const dialogForm = Boolean(generationTabs || type === "image" && generationDialog);
    return {
      current: () => !dialogForm || generationDialog.open && generation === generationPreparation &&
        (!generationTabs || type === generationType),
      beforeOpen: () => { if (dialogForm) generationDialog.close(); },
      statusId: dialogForm ? generationStatusId : "generated-jobs-status",
    };
  }
  function reviewJob(draft, resource, type) {
    const context = generationContext(type);
    if (!active("jobs") || !context.current() || reviewDialog.open || busy(resource)) return;
    byId(context.statusId).textContent = "Preparing review…";
    review(draft, resource, "jobs", context);
  }
  function selectGenerationType(type, focus = false) {
    if (!generationTabs) return;
    if (type !== generationType) {
      generationPreparation += 1;
      byId(generationStatusId).textContent = "";
      generationDialog.scrollTop = 0;
    }
    generationType = type;
    for (const tab of generationTabs.querySelectorAll("[data-generation]")) {
      const selected = tab.dataset.generation === type;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      byId(tab.getAttribute("aria-controls")).hidden = !selected;
      if (selected && focus) tab.focus();
    }
  }
  for (const tab of generationTabs?.querySelectorAll("[data-generation]") || [])
    tab.addEventListener("click", () => selectGenerationType(tab.dataset.generation));
  generationTabs?.addEventListener("keydown", event => {
    const tabs = [...generationTabs.querySelectorAll("[role='tab']")];
    const index = tabs.indexOf(document.activeElement);
    if (index < 0) return;
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
      event.key === "ArrowRight" ? (index + 1) % tabs.length :
        event.key === "ArrowLeft" ? (index - 1 + tabs.length) % tabs.length : null;
    if (next !== null) { event.preventDefault(); selectGenerationType(tabs[next].dataset.generation, true); }
  });
  byId("research-create").addEventListener("submit", event => {
    event.preventDefault();
    if (byId("research-create").querySelector("button").disabled) return;
    reviewJob({ operation: "research-create", question: byId("research-question").value,
      model: byId("research-model-source").value === "default" && jobs?.research_model ? jobs.research_model : latest?.model_ref, format: byId("research-format").value }, "research-create", "research");
  });
  generationAdd?.append(libraryIcon("plus"));
  generationAdd?.addEventListener("click", () => {
    if (!active("jobs") || byId("image-add").disabled || reviewDialog.open) return;
    generationPreparation += 1;
    byId(generationStatusId).textContent = "";
    generationDialog.showModal();
    byId(generationType === "research" ? "research-question" : "image-prompt").focus();
  });
  byId("image-generate-close")?.append(libraryIcon("close"));
  byId("image-generate-close")?.addEventListener("click", () => generationDialog?.close());
  generationDialog?.addEventListener("close", () => {
    if (generationDialog.open) return;
    generationPreparation += 1;
    byId("image-generate-status").textContent = "";
  });
  window.addEventListener("popstate", () => generationDialog?.close());
  byId("image-generate").addEventListener("submit", event => {
    event.preventDefault();
    if (byId("image-generate").querySelector("button").disabled) return;
    reviewJob({ operation: "image-generate", prompt: byId("image-prompt").value,
      width: Number(byId("image-width").value), height: Number(byId("image-height").value),
      steps: Number(byId("image-steps").value) }, "image-generate", "image");
  });
  // Presentation metadata for the browser's audited read-tool allowlist. A
  // control is created only when the settings response supplies its field.
  const toolDescriptions = {
    read_file: ["File Operations", "file", "Read text from files in the selected workspace."],
    list_dir: ["File Operations", "folder", "List files and folders in the selected workspace."],
    workspace_info: ["File Operations", "info", "Read workspace location and project information."],
    grep: ["File Operations", "search", "Search text inside workspace files."],
    git_status: ["Git", "code", "Inspect changed files without modifying the repository."],
    git_diff: ["Git", "code", "Read the repository's current changes."],
    web_search: ["Web", "search", "Find web results with your configured search providers."],
    fetch_url: ["Web", "web", "Read a public web page with your configured page reader."],
    http_probe: ["Web", "info", "Inspect public HTTP response headers and status."],
    query_knowledge: ["Knowledge & Skills", "knowledge", "Search your indexed Knowledge libraries."],
    read_skill: ["Knowledge & Skills", "skill", "Read guidance from an enabled installed Skill."],
    current_time: ["Utilities", "clock", "Read the host clock in the selected timezone."],
  };
  function settingsDisclosure(id, title, icon, initiallyOpen = false) {
    const section = domainText("details", "", "settings-disclosure");
    section.id = `agent-group-${id}`;
    section.open = settingsGroups.get(id) ?? initiallyOpen;
    section.addEventListener("toggle", () => { if (section.isConnected) settingsGroups.set(id, section.open); });
    const summary = document.createElement("summary");
    const heading = domainText("h3", title, "settings-heading");
    heading.prepend(libraryIcon(icon)); summary.append(heading);
    section.append(decorateDisclosure(summary));
    return section;
  }
  function settingForm(field, { labelText = field.label, description = field.description, icon = null } = {}) {
    field = { ...field, value: SettingsDrafts.value("agent", field.id) };
    const form = domainText("form", "", "setting-row"); form.dataset.setting = field.id;
    const label = domainText("label", labelText);
    if (icon) { label.classList.add("tool-permission-label"); label.prepend(libraryIcon(icon)); }
    const input = document.createElement(["policy", "choice"].includes(field.type) ? "select" : "input");
    const id = `setting-${field.id.replaceAll(".", "-")}`;
    input.id = id; label.htmlFor = id;
    if (["policy", "choice"].includes(field.type)) {
      const choices = field.type === "policy" ? [{ value: "allow", label: "Automatic" }, { value: "ask", label: "Ask first" }, { value: "deny", label: "Deny" }] : field.choices;
      for (const choice of choices) {
        const option = domainText("option", choice.label); option.value = choice.value; input.append(option);
      }
      input.value = field.value;
    } else if (field.type === "boolean") {
      input.type = "checkbox"; input.checked = field.value; input.setAttribute("role", "switch");
    } else if (field.type === "text") {
      input.type = "url"; input.maxLength = field.max_length; input.value = field.value; input.required = !field.optional;
      input.autocomplete = "off"; input.spellcheck = false;
    } else { input.type = "number"; input.min = field.min; input.max = field.max; input.step = "1"; input.value = field.value; input.required = true; }
    const controls = domainText("div", "", "settings-controls");
    if (field.type === "number") controls.classList.add("settings-number");
    if (field.type === "boolean") {
      form.classList.add("settings-toggle-row");
      const toggle = domainText("label", "", "switch");
      const track = domainText("span", ""); track.setAttribute("aria-hidden", "true");
      toggle.append(input, track); controls.append(toggle);
    } else controls.append(input);
    const submit = () => {
      if (input.disabled) return;
      SettingsDrafts.set("agent", field.id, field.type === "boolean" ? input.checked : field.type === "number" ? (input.value === "" ? "" : Number(input.value)) : input.value);
    };
    input.addEventListener(field.type === "boolean" || input.tagName === "SELECT" ? "change" : "input", submit);
    form.addEventListener("submit", event => { event.preventDefault(); submit(); });
    if (description) {
      const text = domainText("div", "", "settings-label");
      const help = domainText("p", description, "muted"); help.id = `${id}-help`;
      input.setAttribute("aria-describedby", help.id);
      text.append(label, help); form.append(text, controls);
    } else form.append(label, controls);
    return form;
  }
  function toolApproval(field, descriptionId, statusId) {
    const group = document.createElement("fieldset");
    group.className = "segmented tool-policy-form";
    group.id = `setting-${field.id.replaceAll(".", "-")}`;
    group.dataset.setting = field.id;
    group.setAttribute("aria-describedby", `${descriptionId} tools-permissions-guidance ${statusId}`);
    group.append(domainText("legend", `${field.label} approval policy`, "visually-hidden"));
    for (const [value, text] of [["allow", "Automatic"], ["ask", "Ask first"], ["deny", "Deny"]]) {
      const label = document.createElement("label"), input = document.createElement("input");
      input.type = "radio"; input.name = field.id; input.value = value;
      input.id = `${group.id}-${value}`; label.htmlFor = input.id;
      input.checked = SettingsDrafts.value("agent", field.id) === value;
      input.addEventListener("change", () => {
        if (!group.disabled && !input.disabled && input.checked)
          SettingsDrafts.set("agent", field.id, input.value);
      });
      label.append(input, domainText("span", text)); group.append(label);
    }
    return group;
  }
  function toolSettings(fields) {
    const section = settingsDisclosure("tools_permissions", "Tools & Permissions", "tools");
    section.append(domainText("p", "Control tool access and approval behavior.", "muted"));
    const guidance = domainText("p", "Automatic skips approval prompts. Ask first requests permission. Deny blocks execution. Workspace, network and other access checks still apply. Disabled tools keep their approval preference.", "muted");
    guidance.id = "tools-permissions-guidance"; section.append(guidance);
    const availability = new Map(fields.filter(field => field.id.startsWith("tool_availability.") && field.type === "boolean").map(field => [field.id.split(".")[1], field]));
    const permissions = new Map(fields.filter(field => field.id.startsWith("permissions.") && field.type === "policy").map(field => [field.id.split(".")[1], field]));
    const names = new Set([...availability.keys(), ...permissions.keys()]);
    const groups = new Map(["File Operations", "Git", "Web", "Knowledge & Skills", "Utilities", "Other tools"].map(name => [name, []]));
    for (const name of names) {
      const available = availability.get(name), policy = permissions.get(name);
      const [group, icon, description] = toolDescriptions[name] || ["Other tools", "tools", "Manage this tool's availability and approval preference."];
      const card = domainText("article", "", "tool-permission-card");
      card.dataset.agentTool = name; card.dataset.availability = available?.id || ""; card.dataset.permission = policy?.id || "";
      const body = domainText("div", "", "tool-permission-body");
      if (available) {
        const form = settingForm(available, { icon, description: null });
        form.classList.add("tool-availability-form");
        form.querySelector("input").setAttribute("aria-label", `Enable ${available.label}`);
        body.append(form);
      } else {
        const title = domainText("h5", policy.label, "settings-heading"); title.prepend(libraryIcon(icon));
        body.append(title);
      }
      const help = domainText("p", description, "muted tool-permission-description");
      help.id = `tool-${name}-description`; body.append(help);
      const toggle = body.querySelector(".tool-availability-form input");
      toggle?.setAttribute("aria-describedby", help.id);
      const status = domainText("p", "", "muted tool-permission-status");
      status.id = `tool-${name}-status`; status.setAttribute("role", "status"); status.hidden = true;
      if (policy) {
        body.append(toolApproval(policy, help.id, status.id));
      }
      card.append(body, status); groups.get(group).push(card);
    }
    for (const [name, cards] of groups) {
      if (!cards.length) continue;
      const group = domainText("section", "", "tool-permission-group");
      const heading = domainText("h4", name); heading.id = `tool-group-${name.toLowerCase().replaceAll(/[^a-z]+/g, "-")}`;
      const list = domainText("div", "", "tool-permission-list"); list.append(...cards);
      group.setAttribute("aria-labelledby", heading.id); group.append(heading, list); section.append(group);
    }
    const mcp = domainText("section", "", "tool-permission-group tool-permission-links");
    const mcpHeading = domainText("h4", "MCP", "settings-heading"); mcpHeading.prepend(libraryIcon("connection"));
    const connections = domainButton("Manage connections", () => {
      byId("integration-sections").querySelector('[data-integration="connections"]').click(); showView("integrations");
    }, "quiet"); connections.id = "tool-mcp-settings";
    mcp.append(mcpHeading, domainText("p", "Manage MCP tool availability per server in Connections. Configured MCP calls require review unless denied.", "muted"), connections); section.append(mcp);
    const advanced = settingsDisclosure("advanced_permissions", "Advanced permission rules", "shield");
    const body = domainText("div", "", "settings-advanced-body");
    body.append(domainText("h4", "Workspace protections"), domainText("p", "Workspace boundaries, protected files and network restrictions apply independently of approval preferences.", "muted"),
      domainText("h4", "File editing"), domainText("p", "Activate edits from Workspaces on loopback after the clean-worktree check. Every edit still requires an exact review. LAN clients cannot activate or approve edits.", "muted"));
    const workspace = domainButton("Open workspace controls", () => showView("workspace"), "quiet"); workspace.id = "tool-workspace-settings";
    body.append(workspace, domainText("h4", "Shell and Git changes"), domainText("p", "Shell execution and Git mutations are unavailable in the WebUI. Additional terminal permission policies remain in Klaude's terminal settings.", "muted"));
    advanced.append(body); section.append(advanced);
    return section;
  }
  function renderAgentSettings() {
    if (!settings) return;
    for (const section of byId("agent-settings-fields").querySelectorAll("details[id^='agent-group-']"))
      settingsGroups.set(section.id.slice("agent-group-".length), section.open);
    const rows = [], labels = { time_settings: "Date and time", runtime_options: "Execution", search_settings: "Web search", fetch_settings: "Web pages", research: "Research budgets" };
    const icons = { time_settings: "clock", runtime_options: "options", search_settings: "search", fetch_settings: "web", research: "text" };
    let group = "", groupBody, renderedTools = false;
    for (const field of settings.fields) {
      const current = field.id.split(".")[0];
      if (["tool_availability", "permissions"].includes(current)) {
        if (!renderedTools) { rows.push(toolSettings(settings.fields)); renderedTools = true; }
        group = ""; continue;
      }
      if (current !== group) {
        const section = settingsDisclosure(current, labels[current], icons[current], ["time_settings", "runtime_options"].includes(current));
        groupBody = domainText("div", "", "settings-group-body");
        if (current === "runtime_options") groupBody.classList.add("settings-form-grid");
        section.append(groupBody); rows.push(section); group = current;
      }
      groupBody.append(settingForm(field));
    }
    byId("agent-settings-fields").replaceChildren(...rows); render();
  }
  async function loadSettings(force = false) {
    if (!force && !active("settings")) return;
    if (!latest?.profile_management) {
      byId("agent-settings-status").textContent = restartHint;
      if (force) throw new Error(restartHint);
      return;
    }
    const generation = ++settingsLoad;
    settingsRead?.abort(); settingsRead = new AbortController();
    const finish = beginLoading(byId("agent-settings-fields"), { kind: "rows", count: 3, preserve: Boolean(settings), label: "Loading settings…" });
    try {
      const result = await domainRequest("/api/v1/settings/agent", "GET", undefined, { signal: settingsRead.signal });
      if (generation !== settingsLoad || !force && !active("settings")) {
        if (force) throw new Error("Saved values are refreshing. Check save status to confirm them.");
        return;
      }
      settings = result;
      SettingsDrafts.ingest("agent", settings.fields.map(field => ({ ...field, version: field.revision,
        label: field.label + (field.id.startsWith("permissions.") ? " approval" : field.id.startsWith("tool_availability.") ? " availability" : "") })));
      renderAgentSettings();
      byId("agent-settings-status").textContent = "";
    } catch (error) { if (generation === settingsLoad) domainError(error, "agent-settings-status"); if (force) throw error; }
    finally { finish(); }
  }
  function renderSessionControls() {
    if (!selectedSession) return;
    const current = !selectedSession.archived && selectedSession.session_id === latest?.session_id;
    const working = current && (latest?.active_turn_id || latest?.queue?.length);
    byId("session-archive").disabled = Boolean(working) || busy(`session:${selectedSession.session_id}`);
    const description = byId("session-management-description");
    description.textContent = working ?
      "Wait for the reply and queued messages to finish before archiving." : current ?
        "Archiving this conversation opens a new chat." : "";
    description.hidden = !description.textContent;
  }
  function sessionRow(item, button) {
    if (!latest?.profile_management) return button;
    const wrapper = domainText("div", "", "session-row");
    const manage = domainButton("", () => {
      selectedSession = item;
      byId("session-management-status").textContent = "";
      byId("session-name").value = item.title || "";
      byId("session-export").href = `/api/v1/sessions/export?id=${encodeURIComponent(item.session_id)}`;
      byId("session-archive").replaceChildren(libraryIcon("archive"),
        domainText("span", item.archived ? "Restore" : "Archive"));
      renderSessionControls();
      byId("session-delete").hidden = !item.archived;
      sessionDialog.showModal();
      byId("session-management-close").focus();
    });
    button.disabled ||= item.archived;
    button.disabled ||= busy(`session:${item.session_id}`);
    manage.append(libraryIcon("more"));
    manage.setAttribute("aria-label", `Manage conversation: ${item.title || item.session_id}`);
    manage.disabled = busy(`session:${item.session_id}`);
    wrapper.append(button, manage);
    return wrapper;
  }
  byId("session-management-close").append(libraryIcon("close"));
  byId("session-export").prepend(libraryIcon("download"));
  byId("session-management-close").addEventListener("click", () => sessionDialog.close());
  byId("session-rename").addEventListener("submit", event => {
    event.preventDefault();
    if (selectedSession) review({ operation: "session-rename", target: selectedSession.session_id,
      name: byId("session-name").value }, `session:${selectedSession.session_id}`, "sessions");
  });
  for (const action of ["archive", "delete"]) byId(`session-${action}`).addEventListener("click", () => {
    if (selectedSession) review({ operation: `session-${action === "archive" && selectedSession.archived ? "restore" : action}`,
      target: selectedSession.session_id }, `session:${selectedSession.session_id}`, "sessions");
  });
  async function loadMemory() {
    if (!active("memory")) return;
    if (!latest?.profile_management) {
      byId("memory-status").textContent = restartHint;
      byId("memory-auto").disabled = true; byId("memory-add").querySelector("button").disabled = true;
      return;
    }
    const generation = ++memoryLoad;
    memoryRead?.abort(); memoryRead = new AbortController();
    const finish = beginLoading(byId("memory-items"), { kind: "rows", count: 3, preserve: Boolean(memory), label: "Loading memories…" });
    try {
      const result = await domainRequest("/api/v1/settings/memory", "GET", undefined, { signal: memoryRead.signal });
      if (generation !== memoryLoad || !active("memory")) return;
      memory = result;
      byId("memory-status").textContent = [result.hidden ? `${result.hidden} sensitive memories hidden.` : "", result.more ? "Showing the first 200 saved memories." : ""].filter(Boolean).join(" ");
      renderMemory();
    } catch (error) { if (generation === memoryLoad) domainError(error, "memory-status"); }
    finally { finish(); }
  }
  async function loadConnections() {
    if (!active("connections")) return;
    if (!latest?.profile_management) {
      byId("connections-status").textContent = restartHint;
      byId("connection-add").querySelector("button").disabled = true;
      byId("integration-add-connections").disabled = true;
      return;
    }
    const generation = ++connectionsLoad;
    connectionsRead?.abort(); connectionsRead = new AbortController();
    const finish = beginLoading(byId("connection-items"), { kind: "rows", count: 3, preserve: Boolean(connections), label: "Loading connections…" });
    try {
      const result = await domainRequest("/api/v1/integrations/connections", "GET", undefined, { signal: connectionsRead.signal });
      if (generation !== connectionsLoad || !active("connections")) return;
      connections = result;
      byId("connections-status").textContent = [connectionNotice, !result.management_allowed ? "Manage connections from the local Web UI on the Klaude server." : result.truncated ? "Connection inventory limit reached." : ""].filter(Boolean).join(" ");
      renderConnections();
    } catch (error) { if (generation === connectionsLoad) domainError(error, "connections-status"); }
    finally { finish(); }
  }
  byId("memory-refresh").addEventListener("click", loadMemory);
  byId("agent-settings-refresh").addEventListener("click", () => loadSettings());
  byId("memory-query").addEventListener("input", renderMemory);
  byId("connections-query").addEventListener("input", renderConnections);
  byId("connections-filter").addEventListener("submit", event => { event.preventDefault(); renderConnections(); });
  for (const button of byId("connections-state-filter").querySelectorAll("button")) button.addEventListener("click", () => {
    connectionFilter = button.dataset.connectionState;
    for (const sibling of button.parentElement.children) sibling.setAttribute("aria-pressed", String(sibling === button));
    renderConnections();
  });
  byId("connection-detail-close").append(libraryIcon("close"));
  byId("connection-detail-close").addEventListener("click", () => connectionDialog.close());
  byId("connection-detail-change").addEventListener("click", () => changeConnection(detailConnection));
  byId("connection-detail-remove").addEventListener("click", () => changeConnection(detailConnection, "mcp-remove"));
  window.addEventListener("popstate", () => connectionDialog.close());
  byId("memory-auto").addEventListener("change", () => {
    if (!memory) return;
    const enabled = byId("memory-auto").checked;
    byId("memory-auto").checked = memory.enabled;
    review({ operation: "memory-auto", enabled, expected_enabled: memory.enabled }, "memory-settings", "memory");
  });
  byId("memory-add").addEventListener("submit", event => {
    event.preventDefault();
    review({ operation: "memory-add", fact: byId("memory-fact").value }, "memory-facts", "memory");
  });
  byId("connection-add").addEventListener("submit", event => {
    event.preventDefault();
    const context = integrationAddContext("connections");
    if (!context.current()) return;
    connectionNotice = "";
    byId("integration-add-status").textContent = "Preparing review…";
    review({ operation: "mcp-add", name: byId("connection-name").value.trim(), url: byId("connection-url").value.trim() }, "browser-mcp", "connections", {
      ...context, statusId: "integration-add-status",
    });
  });
  document.addEventListener("klaude-view", () => {
    if (active("memory")) { loadMemory(); loadSettings(); loadOperations(); }
    else { memoryRead?.abort(); memoryLoad += 1; settingsRead?.abort(); settingsLoad += 1; }
    if (!active("connections")) { connectionsRead?.abort(); connectionsLoad += 1; connectionDialog.close(); }
    if (active("jobs")) loadJobs(); else { jobsRead?.abort(); jobsLoad += 1; generationDialog?.close(); }
  });
  document.addEventListener("klaude-operations", event => {
    let settled = false;
    for (const [resource, state] of changes) {
      const operation = event.detail.find(item => item.request_id === state.request_id);
      if (!operation || !["completed", "failed", "unknown", "cancelled"].includes(operation.state)) continue;
      if (operation.state === "unknown") { state.phase = "unknown"; continue; }
      changes.delete(resource); settled = true;
      if (resource === "browser-mcp" && state.target && operation.state !== "completed")
        connectionFailures.set(state.target, "Change rejected. Refresh and review the current connection.");
      const status = resource.startsWith("vision") ? "vision-status" : resource.startsWith("media-") ? "media-settings-status" : resource.startsWith("research") || resource.startsWith("image") ? "generated-jobs-status" : resource.startsWith("setting:") ? "agent-settings-status" : resource.startsWith("session:") ? "session-management-status" : resource.startsWith("memory-") ? "memory-status" : "connections-status";
      const imageSettings = ["media-image_service", "media-recovery-image_service"].includes(resource);
      byId(imageSettings ? "image-settings-status" : status).textContent = operation.state === "completed" ? "Saved." : "Change rejected. Refresh and review the current item.";
      if (resource === "browser-mcp") connectionNotice = byId("connections-status").textContent;
    }
    if (settled) { if (active("memory")) { loadMemory(); loadSettings(); } if (active("connections")) loadConnections(); refreshSessions().catch(showError); }
    if (active("jobs")) loadJobs();
    render();
  });
  document.addEventListener("klaude-auth-reset", () => {
    settingsGroups.clear();
    memoryRead?.abort(); connectionsRead?.abort(); memoryLoad += 1; connectionsLoad += 1;
    memory = connections = null; changes.clear();
    connectionNotice = ""; connectionFilter = "all";
    byId("connections-summary").textContent = "";
    for (const button of byId("connections-state-filter").children) button.setAttribute("aria-pressed", String(button.dataset.connectionState === "all"));
    connectionFailures.clear(); detailConnection = null; connectionDialog.close();
    for (const id of ["connection-detail-title", "connection-detail-description", "connection-detail-metadata", "connection-detail-status"]) byId(id).replaceChildren();
    profileReady = undefined;
    settingsRead?.abort(); settingsLoad += 1; settings = null;
    jobsRead?.abort(); jobsLoad += 1; jobs = null;
    generationPreparation += 1; generationDialog?.close();
    selectGenerationType("image");
    if (generationAdd) generationAdd.disabled = true;
    byId("image-generate").querySelector("button").disabled = true;
    byId(generationStatusId).textContent = "";
    byId("research-create").reset(); byId("image-generate").reset();
    for (const id of ["research-jobs", "image-jobs", "generated-jobs-status", "research-model-label", "image-service-status"]) byId(id).replaceChildren();
    byId("agent-settings-fields").replaceChildren(); byId("agent-settings-status").textContent = "";
    selectedSession = null; sessionDialog.close();
    byId("session-rename").reset(); byId("session-export").removeAttribute("href");
    byId("session-management-status").textContent = "";
    for (const id of ["memory-items", "connection-items"]) byId(id).replaceChildren();
    for (const id of ["memory-status", "connections-status", "memory-query", "connections-query"]) {
      byId(id).textContent = ""; if ("value" in byId(id)) byId(id).value = "";
    }
    byId("memory-add").reset(); byId("connection-add").reset();
    byId("memory-auto").checked = false; byId("memory-auto").disabled = true;
  });
  function capabilitiesChanged() {
    renderSessionControls();
    const ready = Boolean(latest?.profile_management);
    if (ready === profileReady) return;
    profileReady = ready;
    if (active("memory")) { loadMemory(); loadSettings(); }
    if (active("connections")) loadConnections();
    if (active("jobs")) loadJobs();
  }
  return { review, busy, loadConnections, loadJobs, sessionRow, capabilitiesChanged, hasPending: () => [...changes.values()].some(item => item.phase === "accepted") };
})();
