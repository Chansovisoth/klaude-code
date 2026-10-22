"use strict";

// Browse the existing configured catalog; selection uses the same fenced runtime
// action as the composer. Connection definitions and secrets stay host-owned.
window.BrowserModelsUI = (() => {
  let connections = [], catalog = [], selected = "", catalogConnection = "";
  let reading = null, generation = 0, loading = false, choosing = "", page = 1;
  let ready;
  const pageSize = 20;
  const active = () => authenticated && currentView === "models";
  const backendLabel = value => ({ ollama: "Ollama", openai_compatible: "OpenAI compatible", openai_codex: "OpenAI Codex", openai_api: "OpenAI", openrouter: "OpenRouter", gemini_api: "Google", deepseek: "DeepSeek", anthropic: "Anthropic" }[value] || value);
  function render() {
    if (!active() || !latest) return;
    byId("models-current-name").textContent = latest.requires_model_selection ? "Choose a model" : latest.model;
    byId("models-current-name").title = latest.model_ref || latest.model;
    byId("models-current-status").textContent = choosing ? "Changing model…" : latest.active_turn_id || latest.queue?.length ?
      "Models can be changed when this conversation is idle." : latest.requires_model_selection ? "Select a model to start chatting." : "";
    byId("models-refresh").disabled = loading;
    byId("models-refresh").setAttribute("aria-busy", String(loading));
    const nodes = connections.map(item => {
      const button = domainButton("", () => { selected = item.id; page = 1; load(false); }, "models-connection quiet");
      button.append(domainText("span", item.name, "models-connection-name"), domainText("small", `${item.source} · ${backendLabel(item.backend)}${item.enabled ? "" : " · Disabled"}`, "muted"));
      button.title = item.name;
      button.dataset.rowKey = item.id;
      button.dataset.rowSignature = JSON.stringify([item, selected === item.id, Boolean(choosing)]);
      button.setAttribute("aria-pressed", String(selected === item.id));
      button.disabled = !item.enabled || Boolean(choosing);
      return button;
    });
    reconcileRows(byId("models-connections"), nodes);
    if (!connections.length && !loading) byId("models-connections").replaceChildren(domainText("p", "No configured connections.", "muted"));
    const connection = connections.find(item => item.id === selected);
    byId("models-catalog-title").textContent = connection?.name || "Available models";
    const query = byId("models-query").value.trim().toLocaleLowerCase();
    const items = catalogConnection === selected ? catalog.filter(item => `${item.name} ${item.id}`.toLocaleLowerCase().includes(query)) : [];
    const totalPages = Math.max(1, Math.ceil(items.length / pageSize));
    page = Math.min(page, totalPages);
    byId("models-count").textContent = catalogConnection === selected ? `${items.length.toLocaleString()} shown` : "";
    byId("models-query").disabled = !catalogConnection;
    const currentModel = latest.model_providers ? latest.model_ref : latest.model;
    const rows = items.slice((page - 1) * pageSize, page * pageSize).map(item => {
      const current = currentModel === item.id && !latest.requires_model_selection;
      const node = domainText("article", "", "models-model library-card collection-row");
      node.dataset.rowKey = item.id;
      node.dataset.current = String(current);
      node.dataset.rowSignature = JSON.stringify([item, current, choosing, runtimeChoiceInFlight, Boolean(latest.active_turn_id), Boolean(latest.queue?.length)]);
      const content = domainText("div", "", "models-model-content");
      const artwork = domainText("span", "", "collection-icon");
      artwork.append(libraryIcon("models"));
      const name = domainText("h3", item.name); name.title = item.name;
      const reference = domainText("p", item.id, "muted models-model-ref"); reference.title = item.id;
      content.append(name, reference);
      const efforts = (item.effort_levels || []).filter(level => level !== "off");
      if (efforts.length) {
        const capabilities = domainText("div", "", "model-capabilities");
        capabilities.setAttribute("aria-label", "Available Thinking efforts");
        capabilities.append(domainText("span", "Thinking", "muted"));
        for (const effort of efforts) capabilities.append(domainText("span", effort, "model-capability"));
        content.append(capabilities);
      }
      const use = domainButton(choosing === item.id ? "Changing…" : current ? "Current" : "Use model", () => useModel(item), current ? "quiet" : "secondary");
      use.setAttribute("aria-label", current ? `${item.name}, current chat model` : `Use ${item.name} for this conversation`);
      use.disabled = current || runtimeChoiceInFlight || Boolean(choosing) || Boolean(latest.active_turn_id) || Boolean(latest.queue?.length);
      node.append(artwork, content, use);
      return node;
    });
    const target = byId("models-items");
    // Keep delayed skeletons owned by beginLoading until a catalog is available.
    if (rows.length) reconcileRows(target, rows);
    else if (!loading) collectionEmpty(target, query ? "No matching models" : "No models available",
      query ? "Try another model name." : selected ? "Refresh this connection to check its available models." : "Enable a connection in Klaude’s terminal Model settings.", "models");
    updateDomainPager("models", (page - 1) * pageSize, { items: rows, total: items.length, page_size: pageSize, more: page < totalPages });
    byId("models-pages").hidden = items.length <= pageSize;
  }
  async function useModel(item) {
    if (choosing || !active() || runtimeChoiceInFlight || latest.active_turn_id || latest.queue?.length) return;
    choosing = item.id;
    const epoch = authEpoch;
    render();
    const ok = await chooseRuntime("model", item.id, { onError: error => {
      if (epoch === authEpoch && active()) byId("models-status").textContent = error.message;
    } });
    if (epoch !== authEpoch) return;
    choosing = "";
    if (ok && active()) byId("models-status").textContent = `${item.name} is ready for this conversation.`;
    render();
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
        const inventory = latest.model_providers ? (await domainRequest("/api/v1/models/connections", "GET", undefined, { signal: reading.signal })).connections :
          [{ id: "legacy-local", name: "Local models", source: "Local", backend: "ollama", enabled: true }];
        if (!current()) return;
        connections = inventory;
        if (!connections.some(item => item.id === selected && item.enabled)) selected =
          connections.find(item => item.id === latest.model_connection && item.enabled)?.id || connections.find(item => item.enabled)?.id || "";
      }
      if (!selected) { catalog = []; catalogConnection = ""; byId("models-status").textContent = "No enabled model connection."; return; }
      const connectionId = selected;
      const result = await domainRequest(latest.model_providers ? `/api/v1/models/catalog?connection=${encodeURIComponent(connectionId)}` : "/api/v1/models/local", "GET", undefined, { signal: reading.signal });
      if (!current()) return;
      catalog = result.models; catalogConnection = connectionId;
      byId("models-status").textContent = "";
    } catch (error) { if (current()) byId("models-status").textContent = `${error.message}${catalog.length ? " Previously loaded models remain visible." : ""}`; }
    finally {
      finish();
      if (loadId === generation) { loading = false; render(); }
    }
  }
  byId("models-previous").append(libraryIcon("previous"));
  byId("models-next").append(libraryIcon("next"));
  byId("models-refresh").addEventListener("click", () => load());
  byId("models-defaults").addEventListener("click", () => showView("settings", { section: "models" }));
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
    generation += 1; reading?.abort(); loading = false; choosing = "";
    connections = []; catalog = []; selected = catalogConnection = ""; ready = undefined; page = 1;
    byId("models-query").value = "";
    for (const id of ["models-connections", "models-items", "models-status", "models-count", "models-current-status", "models-numbers"]) byId(id).replaceChildren();
    byId("models-current-name").textContent = "Choose a model";
    byId("models-current-name").removeAttribute("title");
    byId("models-catalog-title").textContent = "Available models";
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
  const busy = kind => !settings || SettingsDrafts.locked("models") || Boolean(settings.pending[kind]) || manager().busy(`media-${kind}`);
  const labels = { chat: "Startup chat", utility: "Utility", research: "Research", vision: "Vision",
    fallbacks: "Utility fallbacks", vision_fallbacks: "Vision fallbacks", output_tokens: "Utility output tokens", vision_enabled: "Vision image input", image_service: "Image generation service" };
  SettingsDrafts.register("models", {
    panel: "models-settings", status: "media-settings-status", render: renderSettings, changed: renderBusy,
    refresh: () => load(false, true), blocked: () => !settings || Object.keys(settings.pending).length > 0,
    operation: entry => entry.base.id === "image_service" ?
      { operation: "image-settings-save", ...entry.value, revision: entry.base.version } :
      { operation: "defaults-save", field: entry.base.id, value: entry.value, expected: entry.base.value },
    order: entry => entry.base.id === "vision_enabled" ? entry.value ? 2 : -2 : entry.base.id === "image_service" ? 3 : 0,
    count: entry => entry.base.id === "image_service" ? ["endpoint", "enabled"].filter(key => entry.value[key] !== entry.base.value[key]).length : 1,
    normalized: normalizedDraft,
    validate: entries => entries.every(entry => {
      const inputs = entry.base.id === "image_service" ? [byId("image-service-url")] :
        [...byId("default-model-fields").querySelectorAll(`[data-draft-field="${entry.base.id}"]`)];
      return inputs.every(SettingsDrafts.validateInput);
    }),
    warning: entry => entry.base.id === "vision_enabled" && entry.value && !entry.base.value ?
      "Enable Vision image input: images can be sent to your configured Vision model and fallbacks when you request analysis." :
      entry.base.id === "image_service" && entry.value.enabled && (!entry.base.value.enabled || entry.value.endpoint !== entry.base.value.endpoint) ?
        `Image generation: enable requests to ${entry.value.endpoint}. Generation prompts will be sent to this server.` : null,
  });
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
      ...choices.map(item => option(item.id, `${item.name}${item.roles[role] === null ? " · Verified when saving" : ""}`)));
    if (value && !choices.some(item => item.id === value)) select.append(option(value, `Saved · ${value}`));
    select.value = value || "";
    const describe = () => { select.title = select.selectedOptions[0]?.textContent || ""; };
    select.addEventListener("change", describe); describe();
    return select;
  }
  const stage = (field, value) => SettingsDrafts.set("models", field, value);
  function recovery(kind) {
    const container = byId(kind === "defaults" ? "defaults-recovery" : "image-settings-recovery");
    const pending = settings.pending[kind];
    container.replaceChildren();
    if (!pending) return;
    container.append(domainText("p", pending.state === "unknown" ? "The last save is unconfirmed. Check its saved state before making another change." : "A shared save is in progress.", "muted"));
    if (pending.state === "unknown") {
      const button = domainButton("Check saved state", () => SettingsDrafts.recover("models", {
        operation: kind === "defaults" ? "defaults-recover" : "image-settings-recover", target: pending.request_id,
      }));
      const state = SettingsDrafts.category("models");
      button.disabled = state.saving || Boolean(state.drafts.entries.get("recovery")?.pending); container.append(button);
    }
  }
  function renderBusy() {
    for (const input of byId("default-model-fields").querySelectorAll("input, select, button")) input.disabled = busy("defaults");
    for (const input of byId("image-service-save").querySelectorAll("input, button")) input.disabled = busy("image_service");
    byId("default-model-catalog").querySelector("button").disabled = !settings || loadingCatalog;
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
      controls.append(select);
      select.addEventListener("change", () => stage(field, select.value || null));
      form.append(title, controls); form.addEventListener("submit", event => { event.preventDefault(); stage(field, select.value || null); });
      roleFields.append(form);
    }
    fields.push(roles);
    const fallbacks = domainText("details", "", "settings-disclosure settings-fallbacks");
    fallbacks.id = "model-fallbacks"; fallbacks.open = fallbacksOpen;
    fallbacks.addEventListener("toggle", () => { if (fallbacks.isConnected) fallbacksOpen = fallbacks.open; });
    fallbacks.append(decorateDisclosure(domainText("summary", "Fallback models")));
    for (const [field, label, icon] of [["fallbacks", "Utility fallbacks", "tools"], ["vision_fallbacks", "Vision fallbacks", "vision"]]) {
      const form = domainText("form", "", "settings-fallback-form");
      const heading = domainText("h3", "", "model-role-label");
      heading.append(libraryIcon(icon), domainText("span", label));
      form.append(heading, domainText("p", "Optional models, tried in this order only when the primary cannot complete the request.", "muted"));
      const selects = [0, 1, 2].map(index => {
        const row = domainText("div", "", "setting-row");
        const label = domainText("label", `Fallback ${index + 1}`);
        const select = modelSelect(`default-value-${field}-${index}`, defaults[field][index], field === "fallbacks" ? "utility" : "vision");
        select.dataset.draftField = field;
        label.htmlFor = select.id;
        const controls = domainText("div", "", "settings-controls"); controls.append(select);
        row.append(label, controls); form.append(row); return select;
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
    fields.push(options, fallbacks);
    byId("default-model-fields").replaceChildren(...fields);
    const image = SettingsDrafts.value("models", "image_service");
    byId("image-service-url").value = image.endpoint;
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
      SettingsDrafts.ingest("models", [
        ...Object.entries(settings.defaults).map(([id, value]) => ({ id, value, version: value, label: labels[id] })),
        { id: "image_service", value: { endpoint: settings.image_service.endpoint, enabled: settings.image_service.enabled },
          version: settings.image_service.revision, label: labels.image_service },
      ]);
      const selected = byId("default-model-connection").value;
      byId("default-model-connection").replaceChildren(...settings.connections.filter(item => item.enabled).map(item => option(item.id, `${item.name} · ${item.backend}`)));
      if (settings.connections.some(item => item.id === selected && item.enabled)) byId("default-model-connection").value = selected;
      renderSettings();
      byId("media-settings-status").textContent = byId("image-settings-status").textContent = "";
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
      byId("media-settings-status").textContent = models.length ? "Compatible models are listed for each role. Choose models, then Save changes." : "This connection returned no models.";
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
  const changeImage = () => {
    if (settings) stage("image_service", { endpoint: byId("image-service-url").value.trim(), enabled: byId("image-service-enabled").checked });
  };
  byId("image-service-url").addEventListener("input", changeImage);
  byId("image-service-enabled").addEventListener("change", changeImage);
  byId("image-service-save").addEventListener("submit", event => { event.preventDefault(); changeImage(); });
  document.addEventListener("klaude-view", () => {
    if (active()) load();
    else { generation += 1; reading?.abort(); catalogReading?.abort(); catalogGeneration += 1; loadingCatalog = false; }
  });
  document.addEventListener("klaude-operations", event => {
    if (SettingsDrafts.category("models").saving) return;
    if (active() && event.detail.some(item => ["defaults-save", "image-settings-save", "defaults-recover", "image-settings-recover"].includes(item.kind) && ["completed", "failed", "unknown"].includes(item.state))) {
      // Reload only when an operation changes, preserving unsaved form edits.
      const revision = JSON.stringify(event.detail.filter(item => item.kind.startsWith("defaults-") || item.kind.startsWith("image-settings-")).map(item => [item.request_id, item.state]));
      if (revision !== lastOperations) { lastOperations = revision; load(); }
    }
  });
  let lastOperations = "";
  document.addEventListener("klaude-auth-reset", () => {
    generation += 1; catalogGeneration += 1; reading?.abort(); catalogReading?.abort(); loadingCatalog = false;
    settings = null; models = []; ready = undefined; lastOperations = "";
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
  let cached = null, expiryTimer = null, tracked = null, outcome = null, fullResult = null, publishedSuggestions = "";
  let tagSelection = null;
  const tagKey = value => value.trim().replace(/\s+/gu, " ").toLocaleLowerCase();
  const fullDialog = byId("vision-full-review");
  const manager = () => window.BrowserManagement;
  const active = () => authenticated && currentView === "library" && artifactDialog.open && image;
  const running = () => Boolean(image && tracked?.artifact === image.id && ["accepted", "running", "cancelling"].includes(tracked.state));
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
    if (state === "loading" && window.MaterialLoading) target.append(MaterialLoading.create({ size: "small" }));
    target.append(document.createTextNode(text));
    renderPresentation();
  }
  function renderPresentation() {
    const analysis = latestResult("analysis"), state = byId("vision-status").dataset.state;
    const working = running() || Boolean(data?.pending && data.pending.state !== "unknown") || state === "loading";
    byId("artifact-vision").dataset.state = working ? "loading" : ["error", "expired"].includes(state) ? state : analysis ? "complete" : "empty";
    byId("artifact-vision").dataset.hasReview = String(Boolean(analysis));
    byId("vision-latest").hidden = !analysis;
    byId("vision-empty").hidden = Boolean(analysis) || working;
    byId("vision-empty").querySelector("h3").textContent = state === "expired" ? "Review expired" : "Understand this image";
    byId("vision-empty").querySelector("p").textContent = state === "expired" ? "Ask again for a new review of this image." :
      "Ask Klaude to describe this image or explain its visible details.";
    byId("vision-question-label").textContent = analysis ? "Ask another question" : "Ask about this image";
    byId("vision-suggest").textContent = latestResult("tags") ? "Generate new tag suggestions" : "Generate tag suggestions";
  }
  function renderStatus() {
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
    const blocked = !image || !latest?.media_management || Boolean(data?.pending) ||
      manager().busy(`vision:${image?.id}`) || manager().busy(`vision-save:${image?.id}`);
    for (const input of byId("vision-analyze").querySelectorAll("input, textarea, button")) input.disabled = blocked;
    const results = byId("vision-results"), count = tagSelection?.selected.size || 0;
    for (const button of results.querySelectorAll("button")) button.disabled = blocked;
    const save = results.querySelector(".vision-tags-save"), clear = results.querySelector(".vision-tags-clear");
    if (save) {
      save.disabled = blocked || !count;
      save.textContent = saving?.artifact === image?.id ? saving.state === "unknown" ? "Save unconfirmed" : "Saving…" : `Save ${count} ${count === 1 ? "tag" : "tags"}`;
      save.setAttribute("aria-busy", String(Boolean(saving && saving.artifact === image?.id)));
      clear.disabled = blocked || !count;
      results.querySelector(".vision-tag-count").textContent = `${count} selected`;
      for (const chip of results.querySelectorAll(".tag-filter-chip")) {
        const selected = Boolean(tagSelection?.selected.has(chip.dataset.tag));
        chip.setAttribute("aria-pressed", String(selected));
        chip.querySelector(".icon").toggleAttribute("hidden", !selected);
      }
    }
    byId("vision-cancel").hidden = !data?.pending?.cancellable;
    byId("vision-cancel").disabled = data?.pending?.state === "cancelling";
    byId("vision-suggest").disabled = blocked;
    byId("vision-analyze").setAttribute("aria-busy", String(Boolean(data?.pending) || running()));
    renderPresentation();
  }
  function review(draft) {
    if (!image) return;
    const target = image, epoch = authEpoch;
    const applying = draft.operation === "vision-tags-apply";
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
        reopen().catch(domainError);
      },
      onDiscard: result => {
        outcome = result.uncertain ? { text: "Image request unconfirmed. Check Activity before trying again.", state: "error" } : null;
        reopen().catch(domainError);
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
    for (const id of ["vision-answer", "vision-review-metadata", "vision-copy", "vision-expand"]) byId(id).hidden = !analysis;
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
        node.append(domainText("h3", "Tag suggestions"), metadata(item));
        const form = document.createElement("form"); form.className = "vision-tag-selector";
        const group = domainText("div", "", "tag-chip-list");
        group.setAttribute("role", "group"); group.setAttribute("aria-label", "Suggested tags");
        const seen = new Set([...(image.tags || []), ...(image.ai_tags || [])].map(tagKey));
        for (const tag of item.tags) {
          if (seen.has(tagKey(tag))) continue;
          seen.add(tagKey(tag));
          const chip = domainButton("", () => {
            if (tagSelection.selected.has(tag)) tagSelection.selected.delete(tag);
            else tagSelection.selected.add(tag);
            renderBusy();
          }, "tag-filter-chip");
          chip.dataset.tag = tag; chip.setAttribute("aria-pressed", "false");
          chip.append(libraryIcon("check"), domainText("span", tag));
          group.append(chip);
        }
        const count = domainText("span", "0 selected", "vision-tag-count"); count.setAttribute("role", "status");
        const actions = domainText("div", "", "tag-selection-actions");
        actions.append(count, domainButton("Clear selection", () => { tagSelection.selected.clear(); renderBusy(); }, "quiet vision-tags-clear"));
        const save = domainButton("Save 0 tags", () => form.requestSubmit(), "vision-tags-save");
        form.append(domainText("p", group.childElementCount ? "Select tags to add to this file." : "These suggestions are already on this file.", "muted"), group, actions, save);
        form.addEventListener("submit", event => {
          event.preventDefault();
          if (!save.disabled && tagSelection.selected.size)
            review({ operation: "vision-tags-apply", result: item.id, selected: [...tagSelection.selected] });
        });
        node.append(form);
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
      data = result;
      if (previous && !latestResult("analysis")) outcome = { text: expires(previous) <= Date.now() ? "The previous review expired. Ask again for a new review." : "The previous review is no longer available. Ask again for a new review.", state: "expired" };
      if (tracked?.artifact === image.id && result.items.some(item => item.id === tracked.request_id)) {
        outcome = { text: tracked.kind === "vision-tags" ? "Tag suggestions ready. Select tags, then review before saving." : "Image review ready.", state: "success" };
        tracked = null;
      }
      remember(); renderResults(); renderStatus(); scheduleExpiry();
    } catch (error) {
      if (current === generation && active() && error.name !== "AbortError") {
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
    if (value && !same) cached = null;
    if (data?.items.some(item => item.kind === "analysis") && !latestResult("analysis"))
      outcome = { text: "The previous review expired. Ask again for a new review.", state: "expired" };
    byId("vision-copy").disabled = byId("vision-full-copy").disabled = false;
    renderResults(); status();
    byId("vision-cancel").hidden = true;
    if (value && !latest?.media_management) status("Restart the Web UI host and reload to use image analysis.", "error");
    else if (value) {
      renderStatus(); scheduleExpiry();
      if (!data) status("Loading AI Review…", "loading");
      setTimeout(() => { if (image === value) load(); }, 0);
    }
    renderBusy();
  }
  function start(operation) {
    if (!image || byId("vision-submit").disabled) return;
    for (const id of ["vision-context", "vision-output"]) {
      if (!byId(id).checkValidity()) { byId("vision-advanced").open = true; byId(id).reportValidity(); return; }
    }
    if (operation === "vision-analyze" && !byId("vision-question").reportValidity()) return;
    review({ operation, target: image.id, revision: image.revision, context: Number(byId("vision-context").value),
      output_tokens: Number(byId("vision-output").value), ...(operation === "vision-analyze" ? { question: byId("vision-question").value } : {}) });
  }
  byId("vision-analyze").addEventListener("submit", event => { event.preventDefault(); start("vision-analyze"); });
  byId("vision-suggest").addEventListener("click", () => start("vision-tags"));
  byId("vision-empty-icon").append(libraryIcon("sparkles"));
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
  byId("vision-cancel").addEventListener("click", async () => {
    if (!data?.pending) return;
    byId("vision-cancel").disabled = true;
    try { await domainRequest("/api/v1/library/cancel", "POST", { request_id: data.pending.request_id }); await load(); }
    catch (error) { domainError(error, "vision-status"); renderBusy(); }
  });
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
    saving = tracked = tagSelection = null; select(null); cached = data = outcome = null;
    byId("vision-analyze").reset(); byId("vision-advanced").open = false;
  });
  return { select, renderBusy };
})();
