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
  byId("models-defaults").addEventListener("click", () => {
    showView("settings", { section: "models" });
    const heading = byId('model-default-heading'); heading.tabIndex = -1;
    heading.focus({preventScroll: true}); heading.scrollIntoView({block: 'start'});
  });
  byId('models-manage-connections').addEventListener('click', () => { showView('settings', {section: 'models'}); const heading = byId('model-connections-heading'); heading.tabIndex = -1; heading.focus({preventScroll:true}); heading.scrollIntoView({block:'start'}); });
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
  const busy = kind => !settings || settings.management_allowed === false || SettingsDrafts.locked("models") || Boolean(settings.pending[kind]) || manager().busy(`media-${kind}`);
  const labels = { chat: "Startup chat", utility: "Utility", research: "Research", vision: "Vision",
    fallbacks: "Utility fallbacks", vision_fallbacks: "Vision fallbacks", output_tokens: "Utility output tokens", vision_enabled: "Vision image input", image_service: "Image generation service" };
  SettingsDrafts.register("models", {
    panel: "models-settings", status: "media-settings-status", render: renderSettings, changed: renderBusy,
    refresh: () => load(false, true), blocked: () => !settings || settings.management_allowed === false || Object.keys(settings.pending).length > 0,
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
      ...choices.map(item => option(item.id, `${item.name}${item.roles[role] === null ? " · Capability unknown" : ""}`)));
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
        const controls = domainText("div", "", "settings-controls");
        controls.append(select, RoleModelPicker.decorate(select, `${field === "fallbacks" ? "Utility" : "Vision"} fallback ${index + 1}`, field === "fallbacks" ? "utility" : "vision", settings.connections));
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
  let imageTestResult = null, imageTestBusy = false;
  const changeImage = () => {
    imageTestResult = null;
    if (settings) stage("image_service", { endpoint: byId("image-service-url").value.trim(), enabled: byId("image-service-enabled").checked });
  };
  byId('image-service-test').addEventListener('click', async () => {
    const endpoint = byId('image-service-url').value.trim(), epoch = authEpoch;
    imageTestBusy = true; renderBusy();
    imageTestResult = {endpoint, message: 'Testing image service…'};
    byId('image-settings-status').textContent = imageTestResult.message;
    try {
      const result = await domainRequest('/api/v1/settings/models/image-test', 'POST', {endpoint});
      if (epoch !== authEpoch || !active() || byId('image-service-url').value.trim() !== endpoint) return;
      imageTestResult = {endpoint, message: `Service reached. Model: ${result.model}. Width ${result.limits.min_width}–${result.limits.max_width}, height ${result.limits.min_height}–${result.limits.max_height}. No image was generated.`};
      byId('image-settings-status').textContent = imageTestResult.message;
    } catch (error) { if (epoch === authEpoch && active()) { imageTestResult = {endpoint, message: error.message}; byId('image-settings-status').textContent = error.message; } }
    finally { if (epoch === authEpoch) { imageTestBusy = false; renderBusy(); } }
  });
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
window.ModelStoreUI = (() => {
  const sections = ['discover', 'charts', 'categories', 'installed', 'downloads', 'connections'];
  const labels = ['Discover', 'Top charts', 'Categories', 'Installed', 'Downloads', 'Connections'];
  const categories = ['Coding', 'Reasoning', 'Vision', 'General-purpose', 'Lightweight'];
  let section = 'discover', category = '', catalog = null, connections = [], endpoint = '', inventory = null;
  let liveCatalog = null, liveSerial = 0, liveReading = null, searchTimer = null, detailReading = '', liveLoading = false;
  const liveDetails = new Map();
  const hub = () => section === 'charts' || byId('store-source').value === 'huggingface';
  let jobs = [], serial = 0, allowed = false, pending = false, timer = null, reading = null, busyRead = false;
  const active = () => authenticated && currentView === 'models';
  const supported = () => latest?.model_store === true;
  const restartMessage = 'Restart the WebUI host, then reload this page to use Model Store. Configured models remain available in Connections.';
  const dialog = byId('store-detail'), downloadDialog = byId('store-download-dialog');
  let detail = '', variant = '', returnFocusId = '', inventoryRead = 0, installedPage = 1, observedCapability;
  const message = text => { byId('store-status').textContent = text; };
  const urlState = () => {
    const p = new URLSearchParams(location.search);
    section = sections.includes(p.get('models-section')) ? p.get('models-section') : 'discover';
    category = categories.includes(p.get('models-category')) ? p.get('models-category') : '';
    byId('store-query').value = (p.get('models-query') || '').slice(0, 200);
    detail = (p.get('models-detail') || '').slice(0, 200);
    byId('store-source').value = p.get('models-source') === 'huggingface' ? 'huggingface' : 'curated';
    byId('store-sort').value = p.get('models-sort') === 'lastModified' ? 'lastModified' : 'downloads';
  };
  function navigate(next, cat = '', id = '', replace = false) {
    section = next; category = cat; detail = id;
    if (next === 'categories' && cat) byId('store-source').value = 'curated';
    const url = new URL(location.href);
    for (const [key, value] of Object.entries({'models-section': section, 'models-category': category,
      'models-detail': detail, 'models-query': byId('store-query').value, 'models-source': byId('store-source').value, 'models-sort': byId('store-sort').value})) {
      if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
    }
    history[replace ? 'replaceState' : 'pushState'](history.state, '', url.pathname + url.search + url.hash);
    render();
    if (section === 'downloads') loadJobs();
    if (hub() && ['discover','charts','categories'].includes(section)) loadLive();
  }
  function icon(name, size = 32) {
    const node = domainText('span', '', 'model-brand-icon'); node.setAttribute('aria-hidden', 'true');
    setModelBrandIcon(node, name, 'ollama', {appearance: 'color', size}); return node;
  }
  function link(label, url) {
    const a = domainText('a', label); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a;
  }
  function openDetail(id, trigger) {
    returnFocusId = trigger?.dataset.storeModel || id; variant = ''; navigate(section, category, id);
  }
  function restoreDetailFocus() {
    const target = [...byId('store-content').querySelectorAll('[data-store-model]')].find(node => node.dataset.storeModel === returnFocusId);
    (target || byId('store-query')).focus();
  }
  function modelRow(item, featured = false) {
    const button = domainButton('', () => openDetail(item.id, button), featured ? 'store-feature quiet' : 'store-row quiet');
    button.dataset.storeModel = item.id;
    const content = domainText('span', '', 'store-card-content');
    content.append(domainText('small', featured ? item.categories[0] : item.publisher, 'store-eyebrow'),
      domainText('strong', item.name), domainText('span', item.summary, 'muted'));
    if (item.modified) content.append(domainText('small', `Updated ${item.modified}`, 'muted'));
    if (Number.isInteger(item.downloads)) content.append(domainText('small', `${item.downloads.toLocaleString()} Hub downloads`, 'muted'));
    button.append(icon(item.id, featured ? 48 : 32), content, domainText('span', 'View', 'store-cta'));
    return button;
  }
  function filtered() {
    const query = byId('store-query').value.trim().toLocaleLowerCase();
    if (hub()) return liveCatalog?.models || [];
    return (catalog?.models || []).filter(item => (!category || item.categories.includes(category)) &&
      `${item.name} ${item.summary} ${item.categories.join(' ')} ${item.capabilities.join(' ')}`.toLocaleLowerCase().includes(query));
  }
  function renderDetail() {
    const item = liveDetails.get(detail) || catalog?.models.find(item => item.id === detail) || liveCatalog?.models?.find(item => item.id === detail);
    const local = inventory?.models?.find(item => item.name === detail);
    if (detail.startsWith('hf:') && !item && !local) {
      byId('store-detail-title').textContent = 'Model details'; byId('store-detail-body').replaceChildren(domainText('p', 'Loading model details…'));
      if (!dialog.open) dialog.showModal(); if (detailReading !== detail) loadLiveDetail(detail); return;
    }
    if (!detail || (!item && !local)) { if (dialog.open) dialog.close(); return; }
    if (item && !item.variants.length) {
      byId('store-detail-title').textContent = item.name;
      const body = byId('store-detail-body'); body.replaceChildren(domainText('p', item.detailLoaded ? item.error || 'No supported top-level GGUF files are available. Split files and projector-only files are not offered by this integration.' : 'Loading exact GGUF files…'), link('Read model card and license', item.source_url));
      if (!dialog.open) dialog.showModal();
      if (!item.detailLoaded && detailReading !== detail) loadLiveDetail(detail);
      return;
    }
    const variants = item?.variants || [{tag: local.name, ...local}];
    if (!variants.some(v => v.tag === variant)) variant = variants[0].tag;
    byId('store-detail-title').textContent = item?.name || local.name;
    const body = byId('store-detail-body'); body.replaceChildren();
    body.append(icon(detail, 48), domainText('p', item?.summary || 'Installed on the selected Ollama server.'));
    if (item) body.append(domainText('p', `${item.publisher} · ${item.license || 'License not specified; read the model card'}`), link('Official model & license', item.source_url),
      domainText('p', item.capabilities.length ? `Catalog capabilities: ${item.capabilities.join(', ')}. Checked ${catalog.verified}; activation checks the installed variant again.` : 'Tool, Vision and Thinking support are not verified. Activation checks the installed variant.', 'muted'));
    const label = domainText('label', 'Variant'); const select = document.createElement('select'); select.id = 'store-variant';
    for (const v of variants) select.append(new Option(v.name || v.tag, v.tag));
    select.value = variant; select.disabled = pending; label.append(select); body.append(label);
    select.addEventListener('change', () => { variant = select.value; renderDetail(); byId('store-variant').focus(); });
    const metadata = variants.find(v => v.tag === variant);
    const installed = inventory?.models?.find(row => row.name === variant);
    body.append(domainText('p', `${metadata.parameters || 'Parameters unknown'} · ${metadata.quantization || 'Quantization unknown'} · ${installed?.size != null ? fileSize(installed.size) : metadata.size != null ? fileSize(metadata.size) : metadata.size_label || 'Size unknown'}`),
      domainText('p', 'Context limit and device fit: not verified. Runtime memory also depends on context and concurrency; download size is not a RAM requirement.', 'muted'));
    if (metadata.source_url) body.append(link('Exact variant details', metadata.source_url));
    const endpointLabel = connections.find(c => c.id === endpoint)?.name || 'No enabled native Ollama endpoint';
    body.append(domainText('p', `Destination: ${endpointLabel}`));
    const actions = domainText('div', '', 'management-actions');
    if (installed) {
      const use = domainButton('Use model', async () => {
        if (pending) return; pending = true; renderDetail();
        try { await chooseRuntime('model', latest.model_providers ? `ollama@${endpoint}/${variant}` : variant, {onError: error => message(error.message)}); }
        finally { pending = false; renderDetail(); }
      });
      use.disabled = pending || (!latest.model_providers && endpoint !== 'default-ollama') || runtimeChoiceInFlight || Boolean(latest?.active_turn_id) || Boolean(latest?.queue?.length);
      const remove = domainButton('Delete model', () => review('model-delete', variant), 'quiet danger');
      remove.disabled = !canWrite(); actions.append(use, remove);
    } else {
      const get = domainButton('Get', () => review('model-pull', variant)); get.disabled = !canWrite() || !inventory?.models || inventory.stale;
      actions.append(get);
    }
    body.append(actions, domainText('p', byId('store-status').textContent, 'domain-status'));
    if (!allowed) body.append(domainText('p', 'Downloads and deletion require an admin account.', 'muted'));
    if (!inventory?.models) body.append(domainText('p', 'Refresh the selected endpoint to verify installed models before downloading.', 'muted'));
    if (!dialog.open) dialog.showModal();
  }
  const canWrite = () => supported() && allowed && endpoint && !pending && !latest?.active_turn_id && !latest?.queue?.length &&
    !jobs.some(job => ['accepted', 'running', 'cancelling', 'unknown'].includes(job.state));
  async function review(operation, model, manual = false) {
    if (!canWrite()) return;
    pending = true; const epoch = authEpoch, selectedEndpoint = endpoint;
    try {
      const opened = await prepareChange({operation, connection: endpoint, model}, {
        current: () => active() && epoch === authEpoch && selectedEndpoint === endpoint && (manual ? downloadDialog.open : variant === model && dialog.open),
        beforeOpen: () => { detail = ''; dialog.close(); downloadDialog.close(); navigate('downloads'); },
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
    try { await domainRequest(path, 'POST', {request_id: id}); }
    catch (error) { if (epoch === authEpoch) message(error.message); }
    finally { if (epoch === authEpoch) { pending = false; await loadJobs(); } }
  }
  function renderJobs(target) {
    if (!jobs.length) target.append(domainText('p', 'No model downloads or deletions yet.', 'muted'));
    for (const job of jobs) {
      const row = domainText('article', '', 'management-row');
      const state = {accepted: 'Queued', running: 'Downloading', completed: 'Complete', failed: 'Failed',
        cancelled: 'Cancelled', cancelling: 'Stopping request', unknown: 'Outcome unknown'}[job.state] || job.state;
      const content = domainText('div', '', 'management-content');
      content.append(domainText('strong', job.model), domainText('small', connections.find(c => c.id === job.connection)?.name || job.connection, 'muted'), domainText('p', `${job.kind === 'model-delete' ? 'Deletion' : 'Download'} · ${state}`));
      if (job.message) content.append(domainText('p', job.message, 'muted'));
      if (job.progress?.stage && ['running','cancelling'].includes(job.state)) {
        content.append(domainText('p', job.progress.stage));
        if (Number.isFinite(job.progress.total) && job.progress.total > 0 && Number.isFinite(job.progress.completed)) {
          content.append(domainText('p', `Current file: ${fileSize(job.progress.completed)} / ${fileSize(job.progress.total)}`));
          const progress = document.createElement('progress'); progress.max = job.progress.total; progress.value = job.progress.completed;
          progress.setAttribute('aria-label', 'Current file download'); content.append(progress);
        }
      }
      const actions = domainText('div', '', 'management-actions');
      if (job.cancellable && job.kind === 'model-pull') actions.append(domainButton('Cancel request', () => jobAction('/api/v1/models/cancel', job.request_id)));
      if (job.state === 'unknown') {
        content.append(domainText('p', 'Remote transfer or cleanup is unconfirmed. Check the exact installed state without restarting the download.', 'muted'));
        actions.append(domainButton('Check outcome', () => jobAction('/api/v1/models/reconcile', job.request_id)));
      }
      for (const b of actions.children) b.disabled = pending || !allowed;
      row.append(content, actions); target.append(row);
    }
  }
  function render() {
    if (!active()) return;
    for (const b of byId('store-sections').children) {
      b.setAttribute('aria-pressed', String(b.dataset.section === section));
      b.disabled = !supported() && b.dataset.section !== 'connections';
    }
    byId('models-configured').hidden = section !== 'connections';
    byId('store-content').hidden = section === 'connections';
    byId('store-search').hidden = ['connections','downloads','charts'].includes(section);
    byId('store-endpoint-label').hidden = section === 'connections';
    byId('store-download-open').disabled = !canWrite() || !inventory?.models || inventory.stale;
    byId('store-discovery-filters').hidden = ['connections','downloads'].includes(section);
    byId('store-source').disabled = !latest?.model_store_catalog || section === 'installed' || section === 'charts';
    byId('store-sort').disabled = !hub() || section === 'installed' || section === 'charts';
    byId('store-size').disabled = section !== 'installed';
    const target = byId('store-content'); target.replaceChildren();
    byId('store-installed-pages').hidden = section !== 'installed' || !supported();
    if (!supported()) {
      allowed = false; dialog.close(); downloadDialog.close();
      byId('store-search').hidden = true; byId('store-endpoint-label').hidden = true; byId('store-discovery-filters').hidden = true;
      message(restartMessage);
      if (section !== 'connections') target.append(domainText('p', 'Model Store needs the updated host.', 'muted'));
      return;
    }
    if (section === 'connections') { renderDetail(); return; }
    if (section === 'downloads') renderJobs(target);
    else if (section === 'installed') {
      target.append(domainText('h2', 'Installed models'));
      if (inventory?.checked_at) target.append(domainText('p', `Last checked ${new Date(inventory.checked_at * 1000).toLocaleString()}${inventory.stale ? ' · Cached; server unavailable' : ''}`, 'muted'));
      const query = byId('store-query').value.trim().toLocaleLowerCase();
      const sizeLimit = byId('store-size').value;
      const rows = (inventory?.models || []).filter(row => row.name.toLocaleLowerCase().includes(query) && (sizeLimit === 'all' || Number.isFinite(row.size) && row.size <= Number(sizeLimit) * 1e9));
      if (!rows.length) target.append(domainText('p', inventory?.models ? 'No matching installed models.' : 'Installed inventory unavailable. Choose an enabled native Ollama endpoint and refresh.', 'muted'));
      installedPage = Math.max(1, Math.min(installedPage, Math.ceil(rows.length / 20)));
      for (const row of rows.slice((installedPage - 1) * 20, installedPage * 20)) {
        const b = domainButton('', () => openDetail(row.name, b), 'store-row quiet');
        b.dataset.storeModel = row.name;
        b.append(icon(row.name), domainText('strong', row.name), domainText('span', `${row.parameters || 'Parameters unknown'} · ${row.size != null ? fileSize(row.size) : 'Size unknown'}`, 'muted'), domainText('span', 'Manage', 'store-cta')); target.append(b);
      }
      updateDomainPager('store-installed', (installedPage - 1) * 20, {
        items: rows.slice((installedPage - 1) * 20, installedPage * 20),
        total: rows.length, page_size: 20, more: installedPage * 20 < rows.length,
      });
      byId('store-installed-pages').hidden = rows.length <= 20;
    } else if (hub() && ['discover','charts','categories'].includes(section)) {
      target.append(domainText('h2', section === 'charts' ? 'Top GGUF models on Hugging Face' : byId('store-sort').value === 'lastModified' ? 'Recently updated GGUF models' : 'GGUF models to explore'));
      target.append(domainText('p', 'Public queries are sent to Hugging Face. Download counts describe Hub repositories, not Ollama usage. Capabilities and device fit are not inferred.', 'muted'));
      if (!latest?.model_store_catalog) target.append(domainText('p', 'Restart the WebUI host and reload to browse the live catalog.', 'muted'));
      else {
        if (liveCatalog?.checked_at) target.append(domainText('p', `${liveCatalog.stale ? 'Cached' : 'Checked'} ${new Date(liveCatalog.checked_at * 1000).toLocaleString()} · up to 20 results`, 'muted'));
        if (liveCatalog?.error) target.append(domainText('p', liveCatalog.error, 'domain-status'));
        if (liveLoading) target.append(domainText('p', 'Loading catalog…', 'muted'));
        const rows = (liveCatalog?.models || []).filter(item => section !== 'charts' || Number.isInteger(item.downloads));
        rows.forEach((item, index) => { const row = modelRow(item); if (section === 'charts') row.prepend(domainText('span', String(index + 1), 'store-rank')); target.append(row); });
        if (!liveLoading && !rows.length) target.append(domainText('p', 'No matching catalog models. Curated and Installed models remain available.', 'muted'));
      }
    } else {
      if (!catalog) target.append(domainText('p', 'Loading curated models…', 'muted'));
      else {
        target.append(domainText('p', `Curated collection · verified ${catalog.verified} · available offline. Tags and sizes can change.`, 'muted'));
        const matches = filtered();
        if (section === 'discover' && !category && !byId('store-query').value) {
          const features = domainText('div', '', 'store-features');
          for (const item of matches) features.append(modelRow(item, true));
          target.append(features, domainText('h2', 'Models to explore'));
        } else target.append(domainText('h2', category || (section === 'categories' ? 'Explore by category' : 'Search results')));
        if (section === 'categories' || section === 'discover') {
          const tiles = domainText('div', '', 'store-categories');
          for (const name of categories) {
            const b = domainButton(name, () => navigate('categories', name), 'secondary');
            b.setAttribute('aria-pressed', String(name === category)); tiles.append(b);
          }
          if (category) tiles.append(domainButton('All categories', () => navigate('categories'), 'quiet'));
          target.append(tiles);
        }
        for (const item of matches) target.append(modelRow(item));
        if (!matches.length) target.append(domainText('p', 'No matches in the curated collection. Browse more models on Ollama.', 'muted'));
        target.append(link('Browse all models on Ollama', 'https://ollama.com/search'));
      }
    }
    renderDetail();
  }
  async function loadLive(force = false) {
    if (!active() || !latest?.model_store_catalog || !hub()) return;
    const current = ++liveSerial, epoch = authEpoch;
    liveReading?.abort(); liveReading = new AbortController(); liveLoading = true; render();
    const parameters = new URLSearchParams({source: 'huggingface', query: byId('store-query').value.trim(), sort: section === 'charts' ? 'downloads' : byId('store-sort').value, refresh: force ? '1' : '0'});
    try {
      const result = await domainRequest(`/api/v1/models/store?${parameters}`, 'GET', undefined, {signal: liveReading.signal});
      if (!active() || current !== liveSerial || epoch !== authEpoch) return;
      liveCatalog = result;
    } catch (error) { if (active() && current === liveSerial && epoch === authEpoch && error.name !== 'AbortError') liveCatalog = {...liveCatalog, error: error.message, stale: true}; }
    finally { if (current === liveSerial && epoch === authEpoch) { liveLoading = false; render(); } }
  }
  async function loadLiveDetail(id) {
    const epoch = authEpoch; detailReading = id;
    try {
      const result = await domainRequest(`/api/v1/models/store/detail?id=${encodeURIComponent(id)}`);
      if (!active() || epoch !== authEpoch || detail !== id) return;
      const base = liveCatalog?.models?.find(item => item.id === id) || {id, name: id.slice(3), source_url: 'https://huggingface.co/' + id.slice(3)};
      liveDetails.set(id, {...base, ...result, variants: result.variants || [], detailLoaded: true});
      while (liveDetails.size > 20) liveDetails.delete(liveDetails.keys().next().value);
      renderDetail();
    } catch (error) { if (active() && epoch === authEpoch && detail === id) { byId('store-detail-body').replaceChildren(domainText('p', error.message)); } }
    finally { if (detailReading === id) detailReading = ''; }
  }
  async function loadInventory() {
    if (!endpoint) { inventory = null; render(); return; }
    const selected = endpoint, epoch = authEpoch, read = ++inventoryRead;
    try {
      const result = await domainRequest(`/api/v1/models/installed?connection=${encodeURIComponent(selected)}`);
      if (!active() || selected !== endpoint || epoch !== authEpoch || read !== inventoryRead) return;
      if (result.models === null) throw Error(result.error || 'Installed models unavailable');
      inventory = result; message(result.stale ? 'Showing cached installed models; refresh when the server is available.' : '');
    } catch (error) {
      if (!active() || selected !== endpoint || epoch !== authEpoch || read !== inventoryRead) return;
      if (inventory) inventory = {...inventory, stale: true};
      message(`${error.message} Curated discovery remains available.`);
    }
    render();
  }
  async function loadJobs() {
    if (!active() || !supported() || busyRead) return;
    busyRead = true; const epoch = authEpoch;
    try {
      const result = await domainRequest('/api/v1/models/downloads');
      if (!active() || epoch !== authEpoch) return;
      const completed = jobs.some(old => ['running','accepted','unknown'].includes(old.state) && result.items.some(j => j.request_id === old.request_id && j.state === 'completed'));
      jobs = result.items; allowed = result.management_allowed;
      if (completed) loadInventory();
      if (section === 'downloads') render();
    } catch (error) { if (active() && epoch === authEpoch) message(error.message); }
    finally { busyRead = false; }
  }
  async function load() {
    if (!supported()) { render(); return; }
    const id = ++serial, epoch = authEpoch; reading?.abort(); reading = new AbortController();
    const current = () => active() && serial === id && epoch === authEpoch;
    const results = await Promise.allSettled([
      domainRequest('/api/v1/models/store', 'GET', undefined, {signal: reading.signal}),
      domainRequest('/api/v1/models/connections', 'GET', undefined, {signal: reading.signal})]);
    if (!current()) return;
    if (results[0].status === 'fulfilled') { catalog = results[0].value; allowed = catalog.management_allowed; }
    else message('Curated catalog unavailable. Installed models can still be refreshed.');
    if (results[1].status === 'fulfilled') {
      connections = results[1].value.connections.filter(c => c.backend === 'ollama' && c.source === 'Local' && c.enabled);
      if (!connections.some(c => c.id === endpoint)) { endpoint = connections[0]?.id || ''; inventory = null; }
      const select = byId('store-endpoint'); select.replaceChildren(...connections.map(c => new Option(c.name, c.id)));
      if (!connections.length) select.append(new Option('No native Ollama endpoint configured', ''));
      select.value = endpoint;
    }
    render(); await Promise.allSettled([loadInventory(), loadJobs(), ...(hub() ? [loadLive()] : [])]);
  }
  sections.forEach((name, i) => { const b = domainButton(labels[i], () => navigate(name), 'quiet'); b.dataset.section = name; byId('store-sections').append(b); });
  byId('store-sections').addEventListener('keydown', event => {
    const buttons = [...byId('store-sections').children], index = buttons.indexOf(document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : event.key === 'ArrowRight' ? (index + 1) % buttons.length : event.key === 'ArrowLeft' ? (index + buttons.length - 1) % buttons.length : null;
    if (index >= 0 && next !== null) { event.preventDefault(); buttons[next].focus(); buttons[next].click(); }
  });
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
  byId('store-query').addEventListener('input', () => { installedPage = 1; if (hub()) { clearTimeout(searchTimer); searchTimer = setTimeout(() => navigate(section, category, '', true), 350); } else navigate(section, category, '', true); });
  byId('store-endpoint').addEventListener('change', () => { endpoint = byId('store-endpoint').value; installedPage = 1; inventory = null; detail = ''; loadInventory(); });
  byId('store-download-open').addEventListener('click', () => { if (!byId('store-download-open').disabled) { byId('store-download-status').textContent = ''; downloadDialog.showModal(); byId('store-download-tag').focus(); } });
  byId('store-download-close').addEventListener('click', () => downloadDialog.close());
  downloadDialog.addEventListener('close', () => byId('store-download-open').focus());
  byId('store-download-form').addEventListener('submit', event => { event.preventDefault(); review('model-pull', byId('store-download-tag').value.trim(), true); });
  byId('store-source').addEventListener('change', () => { category = ''; liveCatalog = null; navigate(section, '', '', true); });
  byId('store-sort').addEventListener('change', () => { liveCatalog = null; navigate(section, category, '', true); });
  byId('store-size').addEventListener('change', () => { installedPage = 1; render(); });
  byId('models-refresh').addEventListener('click', async () => { await load(); if (hub()) loadLive(true); });
  byId('store-detail-close').addEventListener('click', () => { navigate(section, category); restoreDetailFocus(); });
  dialog.addEventListener('cancel', event => { event.preventDefault(); navigate(section, category); restoreDetailFocus(); });
  document.addEventListener('klaude-view', () => {
    clearInterval(timer); timer = null;
    if (active()) { urlState(); render(); load(); if (supported()) timer = setInterval(loadJobs, 2000); }
    else { serial++; reading?.abort(); liveReading?.abort(); clearTimeout(searchTimer); dialog.close(); downloadDialog.close(); }
  });
  document.addEventListener('klaude-snapshot', () => {
    const capability = supported();
    if (observedCapability === capability) return;
    observedCapability = capability;
    if (!active()) return;
    clearInterval(timer); timer = null;
    render(); load();
    if (capability) timer = setInterval(loadJobs, 2000);
  });
  window.addEventListener('popstate', () => { if (active()) { urlState(); render(); } });
  document.addEventListener('klaude-auth-reset', () => {
    clearInterval(timer); clearTimeout(searchTimer); liveSerial++; liveReading?.abort(); liveDetails.clear(); liveCatalog = null; serial++; reading?.abort(); dialog.close(); downloadDialog.close(); byId('store-download-tag').value = ''; catalog = inventory = null; jobs = []; connections = [];
    byId('store-installed-pages').hidden = true;
    byId('store-installed-numbers').replaceChildren(); byId('store-installed-page').textContent = ''; installedPage = 1;
    endpoint = detail = variant = ''; observedCapability = undefined; pending = false; allowed = false; byId('store-query').value = ''; byId('store-content').replaceChildren(); byId('store-detail-body').replaceChildren(); message('');
  });
  return {render};
})();

window.RoleModelPicker = (() => {
  const dialog = byId('role-model-picker');
  let target = '', role = '', entries = [], pending = null, serial = 0, page = 1, epoch;
  const valid = () => dialog.open && authenticated && epoch === authEpoch && currentView === 'settings' && settingsSection === 'models';
  function close() { dialog.close(); }
  function select(reference, label) {
    if (!valid()) return;
    const field = byId(target);
    if (!field) return close();
    if (![...field.options].some(option => option.value === reference)) field.add(new Option(label, reference));
    field.value = reference; field.dispatchEvent(new Event('change')); close();
  }
  function render() {
    if (!valid()) return;
    const query = byId('role-picker-query').value.trim().toLocaleLowerCase();
    const matches = entries.filter(entry => `${entry.name} ${entry.id}`.toLocaleLowerCase().includes(query));
    page = Math.max(1, Math.min(page, Math.ceil(matches.length / 20)));
    const rows = matches.slice((page - 1) * 20, page * 20);
    byId('role-picker-items').replaceChildren(...rows.map(entry => {
      const row = domainButton('', () => select(entry.id, entry.name), 'store-row quiet');
      const icon = domainText('span', '', 'model-brand-icon'); setModelBrandIcon(icon, entry.id, '', {size: 32});
      const content = domainText('span', '', 'store-card-content');
      content.append(domainText('strong', entry.name), domainText('small', entry.id, 'muted'),
        domainText('small', entry.roles[role] === null ? 'Role capability not verified' : 'Compatible with this role', 'muted'));
      row.append(icon, content); row.setAttribute('aria-pressed', String(byId(target)?.value === entry.id)); return row;
    }));
    if (!rows.length) byId('role-picker-items').append(domainText('p', 'No matching models in this connection.', 'muted'));
    updateDomainPager('role-picker', (page - 1) * 20, {items: rows, total: matches.length, page_size: 20, more: page * 20 < matches.length});
    byId('role-picker-pages').hidden = matches.length <= 20;
  }
  async function load() {
    const id = ++serial, selected = byId('role-picker-connection').value;
    pending?.abort(); pending = new AbortController(); page = 1; entries = [];
    if (!selected) { byId('role-picker-status').textContent = 'Add and enable a model connection first.'; render(); return; }
    byId('role-picker-status').textContent = 'Loading models…'; render();
    try {
      const result = await domainRequest(`/api/v1/models/catalog?connection=${encodeURIComponent(selected)}&purpose=defaults`, 'GET', undefined, {signal: pending.signal});
      if (!valid() || serial !== id) return;
      entries = result.models.filter(entry => entry.roles?.[role] !== false);
      byId('role-picker-status').textContent = 'Saving remains separate. Unknown capability labels are not a guarantee of provider support.'; render();
    } catch (error) { if (valid() && serial === id && error.name !== 'AbortError') byId('role-picker-status').textContent = error.message; }
  }
  function decorate(select, label, roleName, connections) {
    const button = domainButton('', () => {
      target = select.id; role = roleName; epoch = authEpoch;
      byId('role-picker-title').textContent = `Choose ${label.toLocaleLowerCase()} model`;
      byId('role-picker-query').value = '';
      byId('role-picker-connection').replaceChildren(...connections.filter(c => c.enabled).map(c => new Option(`${c.name} · ${c.backend}`, c.id)));
      const identity = select.value.split('/')[0].split('@')[1];
      if ([...byId('role-picker-connection').options].some(option => option.value === identity)) byId('role-picker-connection').value = identity;
      dialog.showModal(); byId('role-picker-query').focus(); load();
    }, 'secondary model-choice-button');
    button.id = select.id + '-picker'; button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-label', `Choose ${label.toLocaleLowerCase()} model`);
    const describe = () => { button.textContent = select.selectedOptions[0]?.textContent || 'Unset'; button.title = select.value || 'Unset'; };
    select.addEventListener('change', describe); describe();
    select.hidden = true;
    queueMicrotask(() => { const fieldLabel = document.querySelector(`label[for="${select.id}"]`); if (fieldLabel) fieldLabel.htmlFor = button.id; });
    return button;
  }
  byId('role-picker-close').append(libraryIcon('close'));
  byId('role-picker-close').addEventListener('click', close);
  byId('role-picker-unset').addEventListener('click', () => select('', 'Unset'));
  byId('role-picker-query').addEventListener('input', () => { page = 1; render(); });
  byId('role-picker-connection').addEventListener('change', load);
  for (const [action, delta] of [['previous', -1], ['next', 1]]) {
    byId(`role-picker-${action}`).append(libraryIcon(action));
    byId(`role-picker-${action}`).addEventListener('click', () => { page += delta; render(); });
  }
  byId('role-picker-numbers').addEventListener('click', event => { const b = event.target.closest('[data-page]'); if (b) { page = Number(b.dataset.page); render(); } });
  dialog.addEventListener('close', () => { serial++; pending?.abort(); entries = []; byId('role-picker-items').replaceChildren(); byId(target + '-picker')?.focus(); });
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
  function render() {
    byId('model-connection-add').disabled = locked();
    const container = byId('model-settings-connections'); container.replaceChildren();
    if (!data) return;
    for (const item of data.connections) {
      const node = domainText('article', '', 'management-row');
      const content = domainText('div', '', 'management-content');
      content.append(domainText('h3', item.name), domainText('p', `${item.backend} · ${item.source} routing · ${item.enabled ? 'Enabled' : 'Disabled'}`, 'muted'));
      if (item.url) content.append(domainText('p', item.url, 'model-connection-address'));
      content.append(domainText('small', item.credential_set ? 'Credential saved' : 'No saved credential', 'muted'));
      const actions = domainText('div', '', 'management-actions');
      const inUse = currentConnection() === item.id;
      const test = domainButton('Test', async () => {
        if (pending) return; pending = true; render(); const epoch = authEpoch;
        try { const result = await domainRequest('/api/v1/settings/model-connections/test', 'POST', {connection: item.id, revision: item.revision}); if (epoch === authEpoch && active()) message(result.message); }
        catch (error) { if (epoch === authEpoch && active()) message(error.message); }
        finally { if (epoch === authEpoch) { pending = false; render(); } }
      });
      test.disabled = locked(); actions.append(test);
      if (item.backend !== 'openai_codex') actions.append(domainButton('Edit', () => open('edit', item)));
      actions.append(domainButton(item.enabled ? 'Disable' : 'Enable', () => review({operation: 'model-connection-enabled', connection: item.id, revision: item.revision, enabled: !item.enabled})));
      if (item.credential_editable) actions.append(domainButton('Credential', () => open('credential', item)));
      actions.append(domainButton('Remove', () => review({operation: 'model-connection-remove', connection: item.id, revision: item.revision}), 'quiet danger'));
      for (const button of actions.children) if (button !== test) button.disabled = locked() || inUse;
      if (inUse) content.append(domainText('small', 'Current conversation connection. Select another model before changing it.', 'muted'));
      node.append(content, actions); container.append(node);
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
        beforeOpen: () => { if (dialog.open) dialog.close(); },
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
  byId('model-connection-add').addEventListener('click', () => open('add'));
  byId('model-connections-refresh').addEventListener('click', load);
  byId('model-connection-close').append(libraryIcon('close'));
  byId('model-connection-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { formVersion++; byId('model-credential-value').value = ''; byId('model-connection-add').focus(); });
  document.addEventListener('klaude-view', () => { if (active()) load(); else { serial++; read?.abort(); dialog.close(); } });
  document.addEventListener('klaude-snapshot', () => { if (active() && !data && !loading && latest?.model_settings) load(); });
  document.addEventListener('klaude-operations', event => {
    if (!active()) return;
    const relevant = event.detail.filter(item => item.kind.startsWith('model-connection-'));
    const signature = JSON.stringify(relevant.map(item => [item.request_id, item.state]));
    if (signature !== lastOperations) { lastOperations = signature; load(); BrowserMedia.load(true); }
  });
  document.addEventListener('klaude-auth-reset', () => { serial++; read?.abort(); data = null; pending = false; lastOperations = ''; dialog.close(); byId('model-connection-form').reset(); byId('model-settings-connections').replaceChildren(); byId('model-connections-recovery').replaceChildren(); message(''); });
})();
