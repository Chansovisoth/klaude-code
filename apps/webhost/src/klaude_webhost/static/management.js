"use strict";

// Profile data remains in memory and is cleared at sign-out. Every effect uses
// the same exact-review dialog and durable operation receipts as Library.
window.BrowserManagement = (() => {
  let memory = null, connections = null;
  let memoryLoad = 0, connectionsLoad = 0;
  let memoryRead = null, connectionsRead = null;
  let settings = null, settingsRead = null, settingsLoad = 0;
  const settingsGroups = new Map();
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
      for (const input of form.querySelectorAll("input, select, button")) input.disabled = busy(`setting:${form.dataset.setting}`);
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
  async function loadSettings() {
    if (!active("settings")) return;
    if (!latest?.profile_management) { byId("agent-settings-status").textContent = restartHint; return; }
    const generation = ++settingsLoad;
    settingsRead?.abort(); settingsRead = new AbortController();
    const finish = beginLoading(byId("agent-settings-fields"), { kind: "rows", count: 3, preserve: Boolean(settings), label: "Loading settings…" });
    try {
      const result = await domainRequest("/api/v1/settings/agent", "GET", undefined, { signal: settingsRead.signal });
      if (generation !== settingsLoad || !active("settings")) return;
      settings = result;
      const rows = [], labels = { time_settings: "Date and time", runtime_options: "Execution", tool_availability: "Tools", permissions: "Permissions", search_settings: "Web search", fetch_settings: "Web pages", research: "Research budgets" };
      const icons = { time_settings: "clock", runtime_options: "options", tool_availability: "tools", permissions: "shield", search_settings: "search", fetch_settings: "web", research: "text" };
      let group = "", groupBody;
      for (const field of settings.fields) {
        const current = field.id.split(".")[0];
        if (current !== group) {
          const section = domainText("details", "", "settings-disclosure");
          section.id = `agent-group-${current}`;
          section.open = settingsGroups.get(current) ?? ["time_settings", "runtime_options"].includes(current);
          section.addEventListener("toggle", () => { if (section.isConnected) settingsGroups.set(current, section.open); });
          const summary = document.createElement("summary");
          const heading = domainText("h3", labels[current], "settings-heading");
          heading.prepend(libraryIcon(icons[current]));
          summary.append(heading); decorateDisclosure(summary);
          groupBody = domainText("div", "", "settings-group-body");
          if (current === "runtime_options") groupBody.classList.add("settings-form-grid");
          section.append(summary, groupBody); rows.push(section); group = current;
        }
        const form = domainText("form", "", "setting-row"); form.dataset.setting = field.id;
        const label = domainText("label", field.label);
        const input = document.createElement(["policy", "choice"].includes(field.type) ? "select" : "input");
        const id = `setting-${field.id.replaceAll(".", "-")}`;
        input.id = id; label.htmlFor = id;
        if (["policy", "choice"].includes(field.type)) {
          const choices = field.type === "policy" ? [{ value: "ask", label: "Ask each time" }, { value: "allow", label: "Allow" }, { value: "deny", label: "Deny" }] : field.choices;
          for (const choice of choices) {
            const option = domainText("option", choice.label); option.value = choice.value; input.append(option);
          }
          input.value = field.value;
        } else if (field.type === "boolean") {
          input.type = "checkbox"; input.checked = field.value;
          input.setAttribute("role", "switch");
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
        const submit = () => review({ operation: "setting-save", id: field.id, revision: field.revision,
          value: field.type === "boolean" ? !field.value : field.type === "number" ? Number(input.value) : input.value }, `setting:${field.id}`, "settings");
        if (field.type === "boolean") input.addEventListener("change", () => { input.checked = field.value; submit(); });
        else { const button = domainButton("Review", () => form.requestSubmit()); button.setAttribute("aria-label", `Review ${field.label}`); controls.append(button); }
        form.addEventListener("submit", event => { event.preventDefault(); submit(); });
        if (field.description) {
          const text = domainText("div", "", "settings-label");
          const help = domainText("p", field.description, "muted"); help.id = `${id}-help`;
          input.setAttribute("aria-describedby", help.id);
          text.append(label, help); form.append(text, controls);
        } else form.append(label, controls);
        groupBody.append(form);
      }
      byId("agent-settings-fields").replaceChildren(...rows); render();
      byId("agent-settings-status").textContent = "";
    } catch (error) { if (generation === settingsLoad) domainError(error, "agent-settings-status"); }
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
  byId("agent-settings-refresh").addEventListener("click", loadSettings);
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
