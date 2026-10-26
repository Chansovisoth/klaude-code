"use strict";

// Browse the existing configured catalog; selection uses the same fenced runtime
// action as the composer. Connection definitions and secrets stay host-owned.
window.BrowserModelsUI = (() => {
  let connections = [], catalog = [], selected = "", catalogConnection = "";
  let reading = null, generation = 0, loading = false, choosing = "", page = 1;
  let ready;
  const pageSize = 20;
  const active = () => authenticated && currentView === "settings" && settingsSection === "models" && byId("models-configured").open;
  const backendLabel = value => ({ ollama: "Ollama", openai_compatible: "OpenAI compatible", openai_codex: "OpenAI Codex", openai_api: "OpenAI", openrouter: "OpenRouter", gemini_api: "Google", deepseek: "DeepSeek", anthropic: "Anthropic" }[value] || value);
  function render() {
    if (!active() || !latest) return;
    byId("models-current-name").textContent = latest.requires_model_selection ? "Choose a model" : latest.model;
    byId("models-current-name").title = latest.model_ref || latest.model;
    byId("models-current-status").textContent = choosing ? "Changing model…" : latest.active_turn_id || latest.queue?.length ?
      "Models can be changed when this conversation is idle." : latest.requires_model_selection ? "Select a model to start chatting." : "";
    byId("configured-models-refresh").disabled = loading;
    byId("configured-models-refresh").setAttribute("aria-busy", String(loading));
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
  decorateDisclosure(byId("models-configured").querySelector("summary"));
  byId("models-configured").open = readNavigationChoice("configured-catalog", ["open", "closed"], "closed") === "open";
  byId("models-configured").addEventListener("toggle", () => {
    saveNavigationChoice("configured-catalog", byId("models-configured").open ? "open" : "closed");
    if (active()) load(); else { generation++; reading?.abort(); loading = false; }
  });
  byId("models-previous").append(libraryIcon("previous"));
  byId("models-next").append(libraryIcon("next"));
  byId("configured-models-refresh").addEventListener("click", () => load());
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
    connections = []; catalog = []; selected = catalogConnection = ""; ready = undefined; page = 1; byId("models-configured").open = false; saveNavigationChoice("configured-catalog", "closed");
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
  const sections = ['discover', 'installed', 'downloads'];
  const labels = ['Discover', 'Installed', 'Downloads'];
  const categories = ['Coding', 'Reasoning', 'Vision', 'General-purpose', 'Lightweight'];
  let section = 'discover', collection = '', category = '', catalog = null, connections = [], endpoint = '', inventory = null;
  let liveCatalog = null, livePage = 1, liveSerial = 0, liveReading = null, searchTimer = null, detailReading = '', liveLoading = false;
  const liveDetails = new Map();
  const hub = () => collection === 'charts' || byId('store-source').value === 'huggingface';
  const liveLanding = () => hub() && !byId('store-query').value.trim() && !category && !collection && byId('store-sort').value === 'downloads';
  let popularCatalog = null, recentCatalog = null, popularReading = null, popularSerial = 0;
  let jobs = [], observedTransfers = [], jobsLoaded = false, serial = 0, allowed = false, pending = false, timer = null, reading = null, busyRead = false;
  const downloadBars = new Map();
  function removeDownloadBar(key) { const bar = downloadBars.get(key); bar?.destroy?.(); bar?.element.remove(); downloadBars.delete(key); }
  function clearDownloadBars() { for (const key of downloadBars.keys()) removeDownloadBar(key); }
  const active = () => authenticated && currentView === 'models';
  const supported = () => latest?.model_store === true;
  const restartMessage = 'Restart the WebUI host, then reload this page to use Model Store. Connection settings remain available in Settings → Models.';
  const dialog = byId('store-detail'), downloadDialog = byId('store-download-dialog');
  const storeFilterMenus = ['store-source','store-sort','store-capability','store-size'].map(id => createTrailingFilterChip(byId(id))).filter(Boolean);
  const closeStoreFilters = () => storeFilterMenus.forEach(menu => menu.close());
  const downloadInfo = byId('store-download-info');
  let downloadInfoKey = '', downloadInfoSource = '', downloadInfoError = '';
  let variantPageSelection = '';
  let shownDetail = '', detailSignature = '', variantPage = 1;
  let browseContext = null, detailsOpen = new Set();
  let detail = '', variant = '', returnFocusId = '', inventoryRead = 0, installedPage = 1, observedCapability;
  const message = text => { byId('store-status').textContent = text; };
  const urlState = () => {
    const p = new URLSearchParams(location.search);
    const oldSection = p.get('models-section');
    if (oldSection === 'connections') {
      const url = new URL(location.href); for (const key of [...url.searchParams.keys()]) if (key.startsWith('models-')) url.searchParams.delete(key);
      url.searchParams.set('view','settings'); url.searchParams.set('settings','models');
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
      showView('settings', {section:'models', restore:true}); return false;
    }
    section = sections.includes(oldSection) ? oldSection : 'discover';
    collection = oldSection === 'charts' || p.get('models-collection') === 'charts' ? 'charts' : '';
    category = categories.includes(p.get('models-category')) ? p.get('models-category') : '';
    byId('store-query').value = (p.get('models-query') || '').slice(0, 200);
    detail = (p.get('models-detail') || '').slice(0, 200);
    variant = (p.get('models-variant') || '').slice(0, 200);
    const saved = history.state?.klaudeStoreBrowse;
    if (saved && typeof saved.scroll === 'number') { browseContext = saved; installedPage = Math.max(1, Math.min(1000, Number(saved.page) || 1)); returnFocusId = typeof saved.focus === 'string' ? saved.focus : ''; }
    byId('store-source').value = p.get('models-source') === 'offline' || category || ['tools','vision','thinking'].includes(p.get('models-capability')) ? 'curated' : 'huggingface';
    byId('store-sort').value = p.get('models-sort') === 'lastModified' ? 'lastModified' : 'downloads';
    livePage = Math.max(1, Math.min(500, Number(p.get('models-page')) || 1));
    byId('store-size').value = ['8','16','32'].includes(p.get('models-size')) ? p.get('models-size') : 'all';
    byId('store-capability').value = ['tools','vision','thinking'].includes(p.get('models-capability')) ? p.get('models-capability') : 'all';
    return true;
  };
  function navigate(next, cat = '', id = '', replace = false, group = collection) {
    const enteringDiscover = next === 'discover' && section !== next;
    if (next !== section) { collection = ''; category = ''; livePage = 1; }
    if (group !== collection) livePage = 1;
    section = next; category = cat; detail = id; collection = section === 'discover' ? group : '';
    if (cat) { collection = ''; byId('store-source').value = 'curated'; }
    const url = new URL(location.href);
    for (const [key, value] of Object.entries({'models-section': section, 'models-category': category,
      'models-collection': collection, 'models-page': livePage > 1 ? String(livePage) : '', 'models-detail': detail, 'models-variant': detail ? variant : '', 'models-query': byId('store-query').value,
      'models-source': byId('store-source').value === 'curated' ? 'offline' : 'huggingface', 'models-sort': byId('store-sort').value,
      'models-size': byId('store-size').value, 'models-capability': byId('store-capability').value})) {
      if (value && value !== 'all') url.searchParams.set(key, value); else url.searchParams.delete(key);
    }
    history[replace ? 'replaceState' : 'pushState'](history.state, '', url.pathname + url.search + url.hash);
    render();
    if (section === 'downloads') loadJobs();
    if (section === 'discover' && liveLanding()) loadPopular(enteringDiscover);
    else if (section === 'discover' && hub()) loadLive(enteringDiscover);
  }
  function icon(name, size = 32) {
    const node = domainText('span', '', 'model-brand-icon'); node.setAttribute('aria-hidden', 'true');
    setModelBrandIcon(node, name, 'ollama', {appearance: 'color', size}); return node;
  }
  function link(label, url) {
    const a = domainText('a', label); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer'; return a;
  }
  function openDetail(id, trigger) {
    returnFocusId = trigger?.dataset.storeModel || id;
    browseContext = {scroll:byId('models-view').scrollTop, focus:returnFocusId, page:installedPage, section, url:location.href};
    history.replaceState({...history.state, klaudeStoreBrowse:browseContext}, '', location.href);
    message(''); variant = ''; variantPageSelection = ''; variantPage = 1; detailsOpen.clear(); detailSignature = '';
    navigate(section, category, id);
  }
  function restoreDetailFocus() {
    const target = [...byId('store-content').querySelectorAll('[data-store-model]')].find(node => node.dataset.storeModel === returnFocusId);
    (target || byId('store-query')).focus({preventScroll:true});
  }
  function sectionHeading(title, action = '', onClick = null) {
    const header = domainText('div', '', 'store-section-heading');
    header.append(domainText('h2', title));
    if (action) header.append(domainButton(action, onClick, 'quiet'));
    return header;
  }
  function runtimeBadge() {
    const runtime = domainText('span', '', 'store-runtime-badge');
    const runtimeIcon = domainText('span', '', 'model-brand-icon store-runtime-icon');
    runtimeIcon.setAttribute('aria-hidden', 'true');
    window.AIIcons?.setPlatformIcon(runtimeIcon, 'ollama', {size:16});
    const server = connections.find(connection => connection.id === endpoint);
    const runtimeLabel = connections.length > 1 && server ? `Ollama · ${server.name}` : 'Ollama';
    runtime.append(runtimeIcon, domainText('span', runtimeLabel));
    runtime.title = server ? `Install via Ollama on ${server.name}` : 'Install via Ollama. Configure a server in Model settings.';
    runtime.setAttribute('aria-label', runtime.title);
    return runtime;
  }
  function modelTask(item) {
    if (!item || typeof item.id !== 'string') return '';
    // Older hosts put the Hub pipeline tag in summary; retain that metadata too.
    const known = new Set(['text-generation','text2text-generation','text-to-speech','text-to-audio','text-to-image','text-to-video','image-text-to-text','image-to-text','image-to-image','image-to-video','automatic-speech-recognition','audio-text-to-text','feature-extraction','sentence-similarity','image-classification','object-detection','visual-question-answering']);
    const source = [item, ...(popularCatalog?.models || []), ...(recentCatalog?.models || []), ...(liveCatalog?.models || [])].find(row => row && row.id === item.id && (row.task || known.has(row.summary)));
    const task = source?.task || (known.has(source?.summary) ? source.summary : '');
    return /^[a-z][a-z0-9-]{0,79}$/.test(task) ? task.charAt(0).toUpperCase() + task.slice(1) : '';
  }
  function modelRow(item, rank = 0) {
    const button = domainButton('', () => openDetail(item.id, button), 'store-row quiet');
    button.dataset.storeModel = item.id;
    const content = domainText('span', '', 'store-card-content');
    content.append(domainText('strong', item.name));
    const purpose = Number.isInteger(item.downloads) ? `${item.downloads.toLocaleString()} Hub downloads` : item.categories?.join(' · ') || item.publisher || item.summary;
    if (Number.isInteger(item.downloads)) {
      const downloads = domainText('small', '', 'store-download-count muted');
      downloads.title = purpose; downloads.setAttribute('aria-label', purpose);
      downloads.append(libraryIcon('download'), domainText('span', item.downloads.toLocaleString()));
      content.append(downloads);
    } else content.append(domainText('small', purpose, 'muted'));
    const task = modelTask(item);
    if (task) content.append(domainText('small', task, 'store-task-label muted'));
    content.append(runtimeBadge());

    if (item.modified && byId('store-sort').value === 'lastModified') content.append(domainText('small', `Updated ${item.modified}`, 'muted'));
    if (rank) { button.classList.add('store-ranked-row'); button.append(domainText('span', String(rank), 'store-rank')); }
    const installed = inventory?.models?.some(local => item.variants?.some(v => v.tag === local.name));
    button.append(icon(item.id, 40), content, domainText('span', installed ? 'Installed' : 'View', 'store-cta'));
    button.title = `${item.name} · ${item.summary || purpose}`;
    return button;
  }
  function modelGrid(items, ranked = false) {
    const grid = domainText('div', '', 'store-model-grid');
    items.forEach((item, index) => grid.append(modelRow(item, ranked ? index + 1 : 0)));
    return grid;
  }
  function filtered() {
    const query = byId('store-query').value.trim().toLocaleLowerCase(), capability = byId('store-capability').value;
    return (catalog?.models || []).filter(item => (!category || item.categories.includes(category)) &&
      (capability === 'all' || item.capabilities.includes(capability)) &&
      `${item.name} ${item.summary} ${item.categories.join(' ')} ${item.capabilities.join(' ')}`.toLocaleLowerCase().includes(query));
  }
  function emptyState(target, title, description, icon) {
    collectionEmpty(target, title, description, icon); target.classList.add('is-empty');
    target.querySelector('.collection-empty').setAttribute('role', 'status');
  }
  function settingsLink(target) {
    target.append(domainButton('Open model settings', () => {
      showView('settings', {section:'models'}); byId('model-connections-heading').scrollIntoView({block:'start'});
    }, 'quiet'));
  }
  function detailSection(title, identity) {
    const node = domainText('section', '', 'model-detail-section');
    const heading = domainText('h2', title); heading.id = identity;
    node.setAttribute('aria-labelledby', identity); node.append(heading); return node;
  }
  function focusVariants() {
    const group = byId('store-variants-section');
    group.scrollIntoView({block:'start', behavior:'instant'});
    (group.querySelector('input:checked') || group.querySelector('input') || group.querySelector('h2')).focus({preventScroll:true});
  }
  function selectVariant(tag) {
    variant = tag;
    const url = new URL(location.href); url.searchParams.set('models-variant', tag);
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    renderDetail();
  }
  function renderDetail() {
    if (!active() || !detail || dialog.hidden) return;
    const item = liveDetails.get(detail) || catalog?.models.find(item => item.id === detail) || liveCatalog?.models?.find(item => item.id === detail) || popularCatalog?.models?.find(item => item.id === detail) || recentCatalog?.models?.find(item => item.id === detail);
    const local = inventory?.models?.find(item => item.name === detail);
    const variants = item?.variants || (local ? [{tag:local.name,...local}] : []);
    const loading = detail.startsWith('hf:') && !item?.detailLoaded;
    if (!variants.some(row => row.tag === variant) && !loading && (item || local || catalog)) variant = local ? local.name : '';
    const selectedIndex = variants.findIndex(row => row.tag === variant);
    if (variant && selectedIndex >= 0 && variantPageSelection !== variant) { variantPage = Math.floor(selectedIndex / 20) + 1; variantPageSelection = variant; }
    const metadata = variants.find(row => row.tag === variant);
    const installed = metadata && inventory?.models?.find(row => row.name === variant);
    const destination = connections.find(c => c.id === endpoint)?.name || '';
    const current = Boolean(installed && !latest?.requires_model_selection && (latest?.model_ref === `ollama@${endpoint}/${variant}` || endpoint === 'default-ollama' && [variant,`ollama/${variant}`].includes(latest?.model_ref || latest?.model)));
    const useAllowed = Boolean(installed && !inventory.stale && !current && !pending && !runtimeChoiceInFlight && !latest?.active_turn_id && !latest?.queue?.length && (latest?.model_providers || endpoint === 'default-ollama'));
    const signature = JSON.stringify([detail,variant,variantPage,item,modelTask(item),local,inventory?.stale,inventory?.checked_at,connections,endpoint,pending,allowed,latest?.active_turn_id,latest?.queue?.length,jobs.map(job=>job.state),canWrite(),useAllowed,current,byId('store-status').textContent]);
    if (signature === detailSignature) return;
    detailSignature = signature;
    const focused = document.activeElement, focusId = dialog.contains(focused) ? focused.id : '';
    const focusPage = focused?.closest('#store-variants-pages') ? focused.dataset.page : '';
    for (const disclosure of dialog.querySelectorAll('details')) {
      if (disclosure.open) detailsOpen.add(disclosure.id); else detailsOpen.delete(disclosure.id);
    }
    const body = byId('store-detail-body'); body.replaceChildren();
    const identity = domainText('header', '', 'model-detail-identity'); identity.id = 'store-detail-identity';
    const logo = domainText('div', '', 'model-detail-logo'); logo.append(icon(item?.id || detail, 88));
    const summary = domainText('div', '', 'model-detail-summary');
    const title = domainText('h1', item?.name || local?.name || detail); title.id = 'store-detail-title'; title.tabIndex = -1;
    const byline = domainText('p', '', 'model-detail-byline muted');
    if (item?.publisher) {
      byline.append(document.createTextNode('By '));
      if (detail.startsWith('hf:')) {
        const author = link(item.publisher, `https://huggingface.co/${encodeURIComponent(item.publisher)}`);
        author.setAttribute('aria-label', `Open ${item.publisher} author profile in a new tab`);
        byline.append(author);
      } else byline.append(document.createTextNode(item.publisher));
    } else byline.textContent = destination ? `Installed on ${destination}` : 'Model details';
    summary.append(title, byline);
    summary.append(runtimeBadge());
    if (item?.stale) summary.append(domainText('p', 'Cached metadata', 'model-detail-source muted'));
    const actionArea = domainText('div', '', 'model-detail-actions');
    const install = domainButton(current ? 'Current model' : 'Use model', async () => {
      if (!installed) { focusVariants(); return; }
      if (installed) {
        if (!useAllowed) return; pending = true; renderDetail();
        try { await chooseRuntime('model', latest.model_providers ? `ollama@${endpoint}/${variant}` : variant, {onError:error => message(error.message)}); }
        finally { pending = false; renderDetail(); }
      }
    }, installed ? 'model-detail-install' : 'secondary model-detail-choose'); install.id = 'store-detail-install';
    install.disabled = installed ? !useAllowed : !variants.length;
    if (installed) actionArea.append(install);
    let blocker = '';
    if (loading) blocker = 'Loading exact variants…';
    else if (!variants.length) blocker = item?.error || 'No supported variants are available.';
    else if (!endpoint) blocker = 'Choose an enabled native Ollama connection in Model settings.';
    else if (!allowed && !installed) blocker = 'Installation requires an admin account.';
    else if (latest?.active_turn_id || latest?.queue?.length) blocker = 'Finish the conversation and queue before model work.';
    else if (!inventory?.models || inventory.stale) blocker = 'Refresh the native endpoint to verify its installed inventory.';
    else if (!canWrite() && !installed) blocker = 'Model work is active or unconfirmed. Check Downloads.';

    if (byId('store-status').textContent && !inventory?.stale) blocker = byId('store-status').textContent;
    const notice = domainText('p', blocker, 'model-detail-blocker muted'); notice.id = 'store-detail-blocker'; notice.setAttribute('role','status'); actionArea.append(notice);
    if (jobs.some(job => ['accepted','running','cancelling','unknown'].includes(job.state))) actionArea.append(domainButton('View downloads', () => navigate('downloads'), 'quiet'));
    if (!endpoint) settingsLink(actionArea);
    else if (!inventory?.models || inventory.stale) actionArea.append(domainButton('Refresh inventory', () => loadInventory(), 'quiet'));
    if (item?.error && detail.startsWith('hf:')) actionArea.append(domainButton('Retry source details', () => { liveDetails.delete(detail); detailSignature = ''; loadLiveDetail(detail); }, 'quiet'));
    identity.append(logo,summary,actionArea); body.append(identity);
    if (item?.source_url) {
      const cardLink = link('', item.source_url); cardLink.className = 'icon-button quiet model-card-link';
      cardLink.setAttribute('aria-label', 'Open model card in a new tab'); cardLink.title = 'Open model card in a new tab';
      cardLink.append(libraryIcon('openNew')); summary.append(cardLink);
    }
    const stats = domainText('dl', '', 'model-detail-stats'); stats.id = 'store-detail-stats';
    const size = metadata ? installed?.size != null ? fileSize(installed.size) : metadata.size != null ? fileSize(metadata.size) : metadata.size_label || 'Unknown' : 'Choose variant';
    const capabilities = item?.capabilities?.length ? item.capabilities.join(' · ') : 'Unknown';
    const facts = [];
    const task = modelTask(item);
    if (task) facts.push(['Task', task]);
    if (Number.isInteger(item?.downloads)) facts.push(['Hub downloads', new Intl.NumberFormat(undefined, {notation:'compact', maximumFractionDigits:1}).format(item.downloads)]);
    if (variants.length) facts.push(['Available variants', String(variants.length)]);
    if (metadata?.parameters) facts.push(['Parameters', metadata.parameters]);
    if (detail.startsWith('hf:') && variants.length) facts.push(['Format', 'GGUF']);
    if (item?.license) facts.push(['License', item.license]);
    for (const [label,value] of facts) {
      const stat = domainText('div', '', 'model-detail-stat'), term = domainText('dt', label);
      if (label === 'Hub downloads') {
        term.replaceChildren(libraryIcon('download'), domainText('span','Hub downloads','visually-hidden'));
        term.title = 'Hugging Face downloads';
      }
      stat.append(term,domainText('dd',value)); stats.append(stat);
    }
    stats.hidden = !facts.length;
    body.append(stats);
    const reading = domainText('div', '', 'model-detail-reading');
    const about = detailSection('About this model','store-detail-about');
    const description = item?.summary || (local ? 'This exact model is installed on the selected native Ollama endpoint.' : 'Source metadata is not available for this model.');
    if (description.length > 360) {
      const preview = domainText('p',description.slice(0,360) + '…'); about.append(preview);
      const more = domainText('details', '', 'model-about-more'); more.id = 'store-detail-more'; more.open = detailsOpen.has(more.id);
      const summary = domainText('summary',''), label = domainText('span',more.open ? 'Show less' : 'Show more'); summary.id = 'store-detail-more-summary'; summary.append(label);
      more.append(decorateDisclosure(summary),domainText('p',description)); preview.hidden = more.open;
      more.addEventListener('toggle', () => { preview.hidden = more.open; label.textContent = more.open ? 'Show less' : 'Show more'; }); about.append(more);
    } else about.append(domainText('p',description));
    const genericAbout = modelTask(item).toLowerCase() === description || ['Community GGUF model. Capabilities and device fit are not verified.', 'Community GGUF. Read its model card and choose an exact file.'].includes(description);
    if (!genericAbout) reading.append(about);
    const variantSection = detailSection('Choose your download','store-variants-heading'); variantSection.id = 'store-variants-section'; variantSection.querySelector('h2').tabIndex = -1;
    const variantCount = domainText('p', loading ? 'Finding available files…' : `${variants.length} ${variants.length === 1 ? 'file' : 'files'} available`, 'model-variant-count muted');
    variantCount.id = 'store-variant-count'; variantSection.append(variantCount);
    if (connections.length > 1) {
      const label = domainText('label','Download to'), select = document.createElement('select'); select.id = 'store-detail-endpoint';
      select.replaceChildren(...connections.map(c=>new Option(c.name,c.id))); select.value = endpoint; select.disabled = pending;
      select.addEventListener('change', () => changeEndpoint(select.value)); label.append(select); variantSection.append(label);
    } else if (destination) variantSection.append(domainText('p',`Download to ${destination}`,'model-download-destination muted'));
    const fieldset = document.createElement('fieldset'); fieldset.id = 'store-variant-list'; fieldset.className = 'model-variant-list'; fieldset.setAttribute('aria-describedby','store-variant-count');
    const legend = domainText('legend','Exact variant'); legend.className = 'visually-hidden'; fieldset.append(legend);
    variantPage = Math.max(1,Math.min(variantPage,Math.ceil(variants.length / 20) || 1));
    variants.slice((variantPage - 1)*20,variantPage*20).forEach((row,index) => {
      const label = domainText('label','','model-variant-row');
      const input = document.createElement('input'); input.type = 'radio'; input.name = 'store-variant'; input.value = row.tag; input.checked = variant === row.tag; input.disabled = pending;
      input.id = `store-variant-${(variantPage - 1)*20+index}`;
      input.addEventListener('change', () => { if (input.checked) selectVariant(row.tag); });
      const copy = domainText('span','','model-variant-copy'); copy.append(domainText('strong',row.name || row.tag)); label.title = row.tag;
      const actual = inventory?.models?.find(local=>local.name===row.tag);
      const info = [row.quantization, row.parameters].filter(Boolean);
      if (info.length) copy.append(domainText('small',info.join(' · '),'muted'));
      const state = domainText('span', '', 'model-variant-state');
      state.append(domainText('strong', actual?.size != null ? fileSize(actual.size) : row.size != null ? fileSize(row.size) : row.size_label || 'Size unknown'));
      if (actual || input.checked) state.append(domainText('small',actual ? inventory.stale ? 'Cached' : 'Installed' : 'Selected'));
      label.append(input,copy,state); fieldset.append(label);
    });
    variantSection.append(fieldset);
    let variantFooter = null;
    if (variants.length && !installed) {
      const downloadLabel = metadata && size !== 'Unknown' ? `Download · ${size}` : 'Download';
      const choose = domainButton(variant ? downloadLabel : 'Choose variant', () => {
        if (!variant) focusVariants(); else review('model-pull', variant);
      }, 'model-detail-install');
      choose.id = 'store-variant-install';
      choose.disabled = variant ? !canWrite() || !inventory?.models || inventory.stale : false;
      if (variant) choose.prepend(libraryIcon('download'));
      variantFooter = domainText('div', '', 'model-variant-footer');
      variantFooter.append(choose);
    }
    if (!variants.length) variantSection.append(domainText('p',loading ? 'Loading supported exact files…' : item?.error || 'No supported single-file variants are available. Open the source to inspect alternatives.','muted'));
    if (variants.length > 20) {
      const nav = domainText('nav','','pagination'); nav.id = 'store-variants-pages'; nav.setAttribute('aria-label','Variant pages');
      for (const [name,delta] of [['previous',-1],['next',1]]) {
        const button = domainButton('', () => { variantPage += delta; renderDetail(); },'quiet'); button.id = `store-variants-${name}`; button.setAttribute('aria-label',`${name} variant page`); button.append(libraryIcon(name));
        if (name === 'next') { const numbers = domainText('span','','page-numbers'); numbers.id = 'store-variants-numbers'; numbers.addEventListener('click',event=>{const button=event.target.closest('button[data-page]');if(button){variantPage=Number(button.dataset.page);renderDetail();}});nav.append(numbers); }
        nav.append(button);
      }
      const status = domainText('span','','visually-hidden'); status.id = 'store-variants-page'; status.setAttribute('role','status'); nav.append(status);variantSection.append(nav);
    }
    if (variantFooter) variantSection.append(variantFooter);
    reading.append(variantSection);
    const details = detailSection('Details','store-model-details');
    const disclosure = (id,title,text) => {
      const node = document.createElement('details'); node.id = id; node.className = 'model-detail-disclosure'; node.open = detailsOpen.has(id);
      const summary = domainText('summary',title); summary.id = `${id}-summary`;
      node.append(decorateDisclosure(summary),domainText('p',text)); return node;
    };
    if (variant) details.append(disclosure('store-exact-variant','Exact model reference',variant));
    details.append(disclosure('store-compatibility','Compatibility and technical information',`${metadata?.parameters || 'Parameter count unknown'}. Context and device fit are not verified. Runtime memory depends on context and concurrency; download size is not a RAM requirement. ${item?.capabilities?.length ? 'Dated catalog declarations: ' + capabilities + '. Activation checks the installed variant again.' : 'Tool use, image input and Thinking are not verified for this exact variant.'}`));
    details.append(disclosure('store-source-license','Source and license',`${item?.checked_at ? 'Source checked ' + new Date(item.checked_at * 1000).toLocaleString() + '. ' : ''}${item?.license ? 'Catalog license: ' + item.license + '. Inspect the source and exact artifact terms.' : 'License is unknown. Inspect the source terms before installation.'} ${detail.startsWith('hf:') ? 'Only top-level single-file GGUF weights are offered. Split weights, projector-only files and subdirectory files are unsupported by this integration.' : catalog?.verified && item ? 'Curated source facts checked ' + catalog.verified + '.' : 'Source metadata is not recorded in the installed inventory.'}`));
    if (installed) {
      const remove = domainButton('Delete model',()=>review('model-delete',variant),'quiet danger'); remove.disabled = !canWrite() || inventory.stale; details.append(remove);
    }
    reading.append(details);
    const links = detailSection('Links','store-detail-links');
    if (metadata?.source_url) links.append(link('Exact variant source',metadata.source_url));
    if (!item?.source_url && !metadata?.source_url) links.append(domainText('p','No verified external source is recorded for this installed model.','muted'));
    if (links.querySelector('a, p')) reading.append(links); body.append(reading);
    if (variants.length > 20) updateDomainPager('store-variants',(variantPage-1)*20,{items:variants.slice((variantPage-1)*20,variantPage*20),total:variants.length,page_size:20,more:variantPage*20<variants.length});
    const previousFocus = (focusId ? byId(focusId) : null) || (focusPage ? byId('store-variants-numbers')?.querySelector(`[data-page="${focusPage}"]`) : null);
    previousFocus?.focus({preventScroll:true});
    if (loading && detailReading !== detail) loadLiveDetail(detail);
  }
  const canWrite = () => supported() && allowed && endpoint && !pending && !latest?.active_turn_id && !latest?.queue?.length &&
    !jobs.some(job => ['accepted', 'running', 'cancelling', 'unknown'].includes(job.state));
  async function review(operation, model, manual = false) {
    if (!canWrite()) return;
    pending = true; const epoch = authEpoch, selectedEndpoint = endpoint;
    try {
      const opened = await prepareChange({operation, connection: endpoint, model}, {
        downloadDestination: connections.find(connection => connection.id === endpoint)?.name || endpoint,
        current: () => active() && epoch === authEpoch && selectedEndpoint === endpoint && (manual ? downloadDialog.open : variant === model && !dialog.hidden),
        beforeOpen: () => { detail = ''; dialog.hidden = true; downloadDialog.close(); navigate('downloads'); },
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
    renderDownloadInfo();
    try {
      await domainRequest(path, 'POST', {request_id: id});
      if (path.endsWith('/reconcile')) loadInventory();
    }
    catch (error) { if (epoch === authEpoch) { openDownloadInfo('owned', id); downloadInfoError = error.message; renderDownloadInfo(); } }
    finally { if (epoch === authEpoch) { pending = false; await loadJobs(); } }
  }
  function downloadProgress(content, progress, label, key) {
    let bar = downloadBars.get(key);
    if (!Number.isFinite(progress?.total) || progress.total <= 0 || !Number.isFinite(progress.completed)) {
      removeDownloadBar(key); return;
    }
    const value = progress.completed / progress.total * 100;
    if (bar) { bar.setValue(value); return; }
    bar = MaterialProgress.create({thickness:'thin', value, label});
    bar.element.classList.add('model-download-progress'); bar.element.dataset.thickness = 'thin';
    downloadBars.set(key, bar); content.append(bar.element);
  }
  function downloadName(item) {
    if (item.source === 'ollama') return 'Ollama transfer';
    const model = item.model || 'Model download', tag = model.split(':').at(-1);
    return model.startsWith('hf.co/') && /\.gguf$/i.test(tag) ? tag : model.split('/').at(-1);
  }
  function downloadState(item) {
    if (item.source === 'ollama') return item.state === 'quiet' ? 'No recent activity' : 'Downloading';
    const stage = {'Checking manifest':'Preparing…', 'Preparing download':'Preparing…',
      'Downloading file':'Downloading', 'Verifying download':'Verifying…', 'Saving model':'Installing…', 'Complete':'Finishing…'};
    return {accepted:'Queued', running:item.kind === 'model-delete' ? 'Removing…' : stage[item.progress?.stage] || 'Downloading',
      completed:item.kind === 'model-delete' ? 'Removed' : 'Complete', failed:'Failed', cancelled:'Stopped',
      cancelling:'Stopping…', unknown:'Needs check'}[item.state] || item.state;
  }
  function infoRecord() {
    return downloadInfoSource === 'owned' ? jobs.find(job => job.request_id === downloadInfoKey)
      : observedTransfers.find(item => item.id === downloadInfoKey);
  }
  function openDownloadInfo(source, key) {
    if (!active() || section !== 'downloads' || detail) return;
    downloadInfoKey = key; downloadInfoSource = source; downloadInfoError = '';
    renderDownloadInfo();
    if (infoRecord()) { if (!downloadInfo.open) downloadInfo.showModal(); byId('store-download-info-close').focus(); }
  }
  function renderDownloadInfo() {
    if (!downloadInfoKey) return;
    const item = infoRecord();
    if (!item) { downloadInfo.close(); return; }
    const exactName = byId('store-download-info-name');
    if (exactName.textContent !== item.model) exactName.textContent = item.model;
    const metadata = byId('store-download-info-metadata'); metadata.replaceChildren();
    const rows = [['Status', downloadState(item)], ['Connection', connections.find(c => c.id === item.connection)?.name || item.connection]];
    if (item.kind === 'model-delete') rows.push(['Action', 'Remove model']);
    const progress = item.progress;
    if (Number.isFinite(progress?.total) && progress.total > 0 && Number.isFinite(progress.completed))
      rows.push(['Current file', `${fileSize(progress.completed)} / ${fileSize(progress.total)}`]);
    for (const [label, value] of rows) metadata.append(domainText('dt', label), domainText('dd', value));
    let note = downloadInfoError || item.message || '';
    if (downloadInfoSource === 'observed') note = item.source === 'ollama'
      ? 'Detected from local file activity. The model name, exact progress and final outcome are unavailable. Manage the transfer in the client that started it.'
      : 'Started in another Klaude client. Manage the download there.';
    else if (item.state === 'unknown') note = [note, 'The server has not confirmed the result. Check status before starting another model operation.'].filter(Boolean).join(' ');
    const message = byId('store-download-info-note');
    if (message.textContent !== note) message.textContent = note;
    message.hidden = !note;
    const check = byId('store-download-info-check'), remove = byId('store-download-info-remove');
    check.hidden = downloadInfoSource !== 'owned' || item.state !== 'unknown'; check.disabled = pending || !allowed;
    remove.hidden = downloadInfoSource !== 'owned' || item.cancellable || item.dismissed || !latest?.model_download_dismissal || !['completed','failed','cancelled','unknown'].includes(item.state);
    remove.disabled = pending || !allowed;
    downloadInfo.querySelector('.dialog-actions').hidden = check.hidden && remove.hidden;
  }
  function downloadAction(label, glyph, action, key) {
    const button = domainButton('', action, 'quiet icon-button');
    button.setAttribute('aria-label', label); button.title = label; button.dataset.downloadAction = key;
    button.append(libraryIcon(glyph)); return button;
  }
  function renderJobs(target) {
    if (!jobs.length && !observedTransfers.length) {
      clearDownloadBars(); target.replaceChildren();
      emptyState(target, 'No downloads yet', '', 'download');
      target.querySelector('.collection-empty p')?.remove();
      target.append(domainButton('Discover models', () => { byId('store-query').value = ''; navigate('discover', '', '', false, ''); }, 'secondary'));
      renderDownloadInfo();
      return;
    }
    const existing = new Map([...target.querySelectorAll('.store-download-row')].map(row => [row.dataset.downloadId, row]));
    for (const child of [...target.children]) if (!child.classList.contains('store-download-row')) child.remove();
    const retained = new Set();
    let position = 0;
    for (const item of [...observedTransfers, ...jobs]) {
      const observed = !item.request_id;
      if (item.dismissed && item.state !== 'unknown') continue;
      const key = item.request_id || item.id, source = observed ? 'observed' : 'owned', name = downloadName(item);
      const row = existing.get(key) || domainText('article', '', 'store-download-row'); row.dataset.downloadId = key; retained.add(key);
      if (observed) row.classList.add('model-observed-transfer');
      if (item.dismissed) row.classList.add('model-dismissed-notice');
      row.setAttribute('aria-label', `${name}: ${downloadState(item)}`);
      const mark = domainText('div', '', 'store-download-icon'); mark.append(icon(item.model, 32));
      const content = domainText('div', '', 'store-download-content');
      const title = domainText('strong', name, 'store-download-name'); title.title = item.model;
      const progress = item.progress;
      const bytes = ['running','cancelling'].includes(item.state) && Number.isFinite(progress?.total) && progress.total > 0 && Number.isFinite(progress.completed);
      const status = domainText('span', bytes ? `${fileSize(progress.completed)} / ${fileSize(progress.total)}` : downloadState(item), 'store-download-status');
      status.dataset.state = item.state; content.append(title, status);
      const actions = domainText('div', '', 'store-download-actions');
      if (!observed && item.cancellable && item.kind === 'model-pull' && ['accepted','running'].includes(item.state))
        actions.append(downloadAction('Stop download', 'close', () => jobAction('/api/v1/models/cancel', key), 'stop'));
      else if (!observed && item.state === 'unknown')
        actions.append(downloadAction('Check download status', 'refresh', () => jobAction('/api/v1/models/reconcile', key), 'check'));
      else if (!observed && !item.cancellable && ['completed','failed','cancelled'].includes(item.state) && latest?.model_download_dismissal)
        actions.append(downloadAction('Remove download', 'close', () => jobAction('/api/v1/models/dismiss', key), 'remove'));
      for (const button of actions.children) button.disabled = pending || !allowed;
      const info = downloadAction('Download details', 'info', () => openDownloadInfo(source, key), 'info');
      info.id = `store-download-info-${source}-${key}`; info.setAttribute('aria-haspopup', 'dialog');
      actions.append(info);
      if (existing.has(key)) {
        row.querySelector('.store-download-icon').replaceWith(mark);
        row.querySelector('.store-download-content').replaceWith(content);
        row.querySelector('.store-download-actions').replaceWith(actions);
      } else row.append(mark, content, actions);
      if (['running','cancelling'].includes(item.state)) downloadProgress(row, progress, `Current file progress for ${name}`, key);
      else { removeDownloadBar(key); }
      if (target.children[position] !== row) target.insertBefore(row, target.children[position] || null);
      position++;

    }
    for (const [key, row] of existing) if (!retained.has(key)) { removeDownloadBar(key); row.remove(); }
    renderDownloadInfo();
  }
  function render() {
    if (!active()) return;
    const before = shownDetail || (!dialog.hidden ? '__visible' : ''), focused = document.activeElement, key = focused?.dataset?.storeModel;
    const fullPage = Boolean(detail && supported());
    if (fullPage || section !== 'downloads') downloadInfo.close();
    if (fullPage) clearDownloadBars();
    byId('models-view').classList.toggle('has-model-detail', fullPage);
    byId('models-view').querySelector(':scope > .view-heading').hidden = fullPage;
    byId('store-sections').hidden = fullPage; byId('store-panel').hidden = fullPage;
    dialog.hidden = !fullPage;
    byId('models-view').setAttribute('aria-labelledby', fullPage ? 'store-detail-title' : 'models-title');
    if (fullPage) renderDetail(); else renderContent();
    shownDetail = fullPage ? detail : '';
    if (shownDetail && before !== shownDetail) {
      byId('models-view').scrollTop = 0;
      byId('store-detail-title')?.focus({preventScroll:true});
    } else if (!shownDetail && before) {
      detailSignature = '';
      const sameSection = !browseContext?.section || browseContext.section === section;
      const restore = () => {
        byId('models-view').scrollTop = sameSection ? Math.max(0, Number(browseContext?.scroll) || 0) : 0;
        if (sameSection) restoreDetailFocus();
      };
      restore(); requestAnimationFrame(() => { if (active() && !detail) restore(); });
    } else if (key && dialog.hidden && !byId('store-content').contains(focused)) {
      const row = [...byId('store-content').querySelectorAll('[data-store-model]')].find(node => node.dataset.storeModel === key);
      row?.focus({preventScroll:true});
    }
  }
  function renderStoreCounts() {
    const counts = {
      installed: inventory?.models?.length,
      downloads: jobsLoaded ? observedTransfers.length + jobs.filter(job => !job.dismissed || job.state === 'unknown').length : undefined,
    };
    for (const name of ['installed', 'downloads']) {
      const button = byId(`store-tab-${name}`), total = counts[name];
      let badge = button.querySelector('.tab-count');
      if (!Number.isSafeInteger(total)) { badge?.remove(); continue; }
      if (!badge) { badge = domainText('span', '', 'tab-count'); button.prepend(badge); }
      const text = total.toLocaleString();
      if (badge.textContent !== text) badge.textContent = text;
    }
  }
  function renderContent() {
    if (!active()) return;
    const focusedRow = document.activeElement?.closest('.store-download-row');
    const downloadFocus = focusedRow ? {key:focusedRow.dataset.downloadId, action:document.activeElement.dataset.downloadAction} : null;
    if (section !== 'downloads') clearDownloadBars();
    renderStoreCounts();
    for (const button of byId('store-sections').children) {
      const selected = button.dataset.section === section;
      button.setAttribute('aria-pressed', String(selected));
      button.disabled = !supported();
    }
    byId('store-panel').setAttribute('aria-labelledby', `store-tab-${section}`);
    byId('store-search-row').hidden = section === 'downloads' || !supported();
    byId('store-query').placeholder = section === 'installed' ? 'Search installed models…' : 'Search models or a use case…';
    byId('store-endpoint-label').hidden = !supported() || connections.length < 2 || section === 'discover' || section === 'downloads' && !jobs.length;
    byId('store-download-open').disabled = !canWrite() || !inventory?.models || inventory.stale;
    byId('store-source').disabled = !latest?.model_store_catalog || section !== 'discover' || collection === 'charts';
    byId('store-sort').disabled = section !== 'discover' || !hub() || collection === 'charts';
    byId('store-capability').disabled = section !== 'discover' || hub();
    byId('store-size').disabled = section !== 'installed';
    byId('store-filter-chips').hidden = section === 'downloads' || !supported();
    for (const id of ['store-source','store-sort','store-capability','store-size']) {
      const select = byId(id), field = select.closest('.file-filter-field, label');
      field.hidden = section === 'installed' ? id !== 'store-size' : id === 'store-size' || id === 'store-capability' && hub();
    }
    storeFilterMenus.forEach(menu => menu.sync());
    const target = byId('store-content'); if (section !== 'downloads' || !supported()) target.replaceChildren(); target.classList.remove('is-empty');
    byId('store-installed-pages').hidden = section !== 'installed' || !supported();
    if (!supported()) {
      allowed = false; dialog.hidden = true; downloadDialog.close(); closeStoreFilters(); message(restartMessage);
      emptyState(target, 'Model Store needs the updated host', 'Restart the host and reload this page.', 'models'); settingsLink(target); return;
    }
    if (section === 'downloads') {
      renderJobs(target); renderDetail();
      if (downloadFocus && !downloadInfo.open) {
        const row = [...target.querySelectorAll('.store-download-row')].find(row => row.dataset.downloadId === downloadFocus.key);
        (row?.querySelector(`[data-download-action="${downloadFocus.action}"]`) || row?.querySelector('[data-download-action=info]') || byId('store-tab-downloads')).focus({preventScroll:true});
      }
      return;
    }
    if (section === 'installed') {
      if (inventory?.checked_at) target.append(domainText('p', `${inventory.stale ? 'Cached · ' : ''}Checked ${new Date(inventory.checked_at * 1000).toLocaleString()}`, 'store-source-note muted'));
      const query = byId('store-query').value.trim().toLocaleLowerCase(), sizeLimit = byId('store-size').value;
      const rows = (inventory?.models || []).filter(row => row.name.toLocaleLowerCase().includes(query) && (sizeLimit === 'all' || Number.isFinite(row.size) && row.size <= Number(sizeLimit) * 1e9));
      if (!rows.length) {
        emptyState(target, inventory?.models ? query || sizeLimit !== 'all' ? 'No matching models' : 'No installed models' : 'Installed models unavailable', inventory?.models ? 'Discover a model or adjust your search and filters.' : 'Check an enabled native Ollama connection in Model settings, then refresh.', 'models');
        if (!endpoint || !inventory?.models) settingsLink(target);
      }
      installedPage = Math.max(1, Math.min(installedPage, Math.ceil(rows.length / 20)));
      for (const row of rows.slice((installedPage - 1) * 20, installedPage * 20)) {
        const button = domainButton('', () => openDetail(row.name, button), 'store-row quiet'); button.dataset.storeModel = row.name;
        const copy = domainText('span', '', 'store-card-content');
        copy.append(domainText('strong', row.name), domainText('small', `${row.parameters || 'Parameters unknown'} · ${row.size != null ? fileSize(row.size) : 'Size unknown'}`, 'muted'));
        button.append(icon(row.name, 40), copy, domainText('span', 'Manage', 'store-cta')); target.append(button);
      }
      updateDomainPager('store-installed', (installedPage - 1) * 20, {items:rows.slice((installedPage - 1) * 20, installedPage * 20), total:rows.length, page_size:20, more:installedPage * 20 < rows.length});
      byId('store-installed-pages').hidden = rows.length <= 20;
      renderDetail(); return;
    }
    const landing = liveLanding();
    if (landing) {
      byId('store-live-pages').hidden = true;
      const popular = (popularCatalog?.models || []).filter(item => Number.isInteger(item.downloads));
      target.append(sectionHeading('Popular models', 'See all', () => navigate('discover', '', '', false, 'charts')));
      target.append(domainText('p', 'By Hugging Face downloads' + (popularCatalog?.stale ? ' · Cached' : ''), 'store-source-note muted'));
      if (popular.length) target.append(modelGrid(popular, true));
      else target.append(domainText('p', popularCatalog?.error ? 'Catalog unavailable. Try Refresh.' : latest?.model_store_catalog ? 'Loading models…' : 'Update the host to explore more models.', 'muted'));
      const popularIds = new Set(popular.map(item => item.id));
      const recent = (recentCatalog?.models || []).filter(item => !popularIds.has(item.id));
      if (recent.length) {
        target.append(sectionHeading('Recently updated', 'See all', () => {
          byId('store-source').value = 'huggingface'; byId('store-sort').value = 'lastModified';
          navigate('discover', '', '', false, '');
        }), modelGrid(recent));
        if (recentCatalog.stale) target.append(domainText('p', 'Cached collection', 'store-source-note muted'));
      }
      if (!popular.length && popularCatalog?.error) {
        target.append(sectionHeading('Available offline'), modelGrid(catalog?.models || []));
      }

    } else {
      const back = sectionHeading(category || (!hub() ? 'Offline collection' : collection === 'charts' ? 'Top GGUF models' : hub() && byId('store-sort').value === 'lastModified' ? 'Recently updated' : 'Search results'), 'Discover', () => {
        byId('store-query').value = ''; byId('store-source').value = 'huggingface'; byId('store-sort').value = 'downloads'; byId('store-capability').value = 'all'; navigate('discover', '', '', false, '');
      }); target.append(back);
      if (hub()) {
        target.append(domainText('p', 'Hugging Face public catalog · repository downloads, not Ollama usage. Capabilities and device fit are not verified.', 'store-source-note muted'));
        if (liveCatalog?.checked_at) target.append(domainText('p', `${liveCatalog.stale ? 'Cached' : 'Checked'} ${new Date(liveCatalog.checked_at * 1000).toLocaleString()} · up to 20 results`, 'store-source-note muted'));
        if (liveCatalog?.error) target.append(domainText('p', liveCatalog.error, 'domain-status'));
        const rows = (liveCatalog?.models || []).filter(item => collection !== 'charts' || Number.isInteger(item.downloads));
        target.append(modelGrid(rows, collection === 'charts'));
        if (collection === 'charts' || byId('store-sort').value === 'lastModified') renderLivePager(liveCatalog);
        else byId('store-live-pages').hidden = true;
        if (liveLoading) target.append(domainText('p', 'Loading catalog…', 'muted'));
        else if (!rows.length) target.append(domainText('p', 'No matching catalog models. Curated and Installed remain available.', 'muted'));
      } else {
        const matches = filtered(); matches.forEach(item => target.append(modelRow(item)));
        if (!matches.length) emptyState(target, 'No matching curated models', 'Try another use case or choose the Hugging Face catalog in Filters.', 'models');
      }
    }
    renderDetail();
  }
  async function loadPopular(force = false) {
    if (!active() || !latest?.model_store_catalog || popularReading) return;
    const id = ++popularSerial, epoch = authEpoch, request = new AbortController(); popularReading = request;
    try {
      await Promise.allSettled(['downloads', 'lastModified'].map(async sort => {
        let result;
        try {
          const url = `/api/v1/models/store?source=huggingface&sort=${sort}`;
          const previous = sort === 'downloads' ? popularCatalog : recentCatalog;
          if (!previous && force) {
            const cached = await domainRequest(`${url}&refresh=0`, 'GET', undefined, {signal:request.signal});
            if (!active() || epoch !== authEpoch || id !== popularSerial) return;
            if (sort === 'downloads') popularCatalog = cached; else recentCatalog = cached;
            render();
          }
          result = await domainRequest(`${url}&refresh=${force ? '1' : '0'}`, 'GET', undefined, {signal:request.signal});
        } catch (error) {
          if (error.name === 'AbortError') return;
          const previous = sort === 'downloads' ? popularCatalog : recentCatalog;
          result = {...previous, error:error.message, stale:true};
        }
        if (!active() || epoch !== authEpoch || id !== popularSerial) return;
        if (sort === 'downloads') popularCatalog = result; else recentCatalog = result;
        render();
      }));
    } finally { if (popularReading === request) popularReading = null; }
  }

  function renderLivePager(data) {
    const rows = data?.models || [];
    const pager = byId('store-live-pages');
    pager.setAttribute('aria-label', byId('store-sort').value === 'lastModified' ? 'Recently updated model pages' : 'Top GGUF model pages');
    if (!data || !rows.length) { pager.hidden = true; return; }
    pager.hidden = false;
    const known = (livePage - 1) * 20 + rows.length + Number(Boolean(data.more));
    updateDomainPager('store-live', (livePage - 1) * 20, {
      items: rows, total: known, page_size: 20, more: Boolean(data.more),
    });
    byId('store-live-page').textContent = `Page ${livePage}`;
  }
  function moveLivePage(next) {
    if (next < 1 || next > 500 || next === livePage) return;
    livePage = next; liveCatalog = null;
    const url = new URL(location.href);
    if (livePage > 1) url.searchParams.set('models-page', String(livePage));
    else url.searchParams.delete('models-page');
    history.pushState(history.state, '', url.pathname + url.search + url.hash);
    loadLive();
  }
  byId('store-live-previous').append(libraryIcon('previous'));
  byId('store-live-next').append(libraryIcon('next'));
  byId('store-live-numbers').addEventListener('click', event => {
    const button = event.target.closest('button[data-page]');
    if (button) moveLivePage(Number(button.dataset.page));
  });
  byId('store-live-previous').addEventListener('click', () => moveLivePage(livePage - 1));
  byId('store-live-next').addEventListener('click', () => moveLivePage(livePage + 1));
  async function loadLive(force = false) {
    if (!active() || !latest?.model_store_catalog || section !== 'discover' || !hub()) return;
    const current = ++liveSerial, epoch = authEpoch;
    liveReading?.abort(); liveReading = new AbortController(); liveLoading = true; render();
    const parameters = new URLSearchParams({source: 'huggingface', query: byId('store-query').value.trim(), sort: collection === 'charts' ? 'downloads' : byId('store-sort').value, page: livePage, refresh: force ? '1' : '0'});
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
      const base = liveCatalog?.models?.find(item => item.id === id) || popularCatalog?.models?.find(item => item.id === id) || recentCatalog?.models?.find(item => item.id === id) || {id, name: id.slice(3), source_url: 'https://huggingface.co/' + id.slice(3)};
      liveDetails.set(id, {...base, ...result, task:result.task || base.task || '', summary:result.summary === 'Community GGUF model. Capabilities and device fit are not verified.' ? base.summary || result.summary : result.summary || base.summary, variants: result.variants || [], detailLoaded: true});
      while (liveDetails.size > 20) liveDetails.delete(liveDetails.keys().next().value);
      renderDetail();
    } catch (error) { if (active() && epoch === authEpoch && detail === id) { liveDetails.set(id, {id, name:id.slice(3), publisher:id.slice(3).split('/')[0], summary:'Community GGUF model.', source_url:'https://huggingface.co/' + id.slice(3), capabilities:[], variants:[], detailLoaded:true, error:error.message}); detailSignature = ''; renderDetail(); } }
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
      jobs = result.items; observedTransfers = result.observed || []; jobsLoaded = true; allowed = result.management_allowed; renderStoreCounts();
      if (completed) loadInventory();
      if (section === 'downloads') render(); else if (detail) renderDetail();
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
    render(); await Promise.allSettled([loadInventory(), loadJobs(), ...(section === 'discover' && hub() && !liveLanding() ? [loadLive(true)] : []), ...(section === 'discover' && liveLanding() ? [loadPopular(true)] : [])]);
  }
  for (const id of ['store-download-info-close', 'store-download-close']) byId(id).append(libraryIcon('close'));
  byId('store-download-info-close').addEventListener('click', () => downloadInfo.close());
  byId('store-download-info-check').addEventListener('click', () => jobAction('/api/v1/models/reconcile', downloadInfoKey));
  byId('store-download-info-remove').addEventListener('click', () => jobAction('/api/v1/models/dismiss', downloadInfoKey));
  downloadInfo.addEventListener('close', () => {
    const origin = byId(`store-download-info-${downloadInfoSource}-${downloadInfoKey}`);
    downloadInfoKey = downloadInfoSource = downloadInfoError = '';
    byId('store-download-info-name').textContent = ''; byId('store-download-info-metadata').replaceChildren();
    byId('store-download-info-note').textContent = '';
    if (active() && section === 'downloads' && !detail) (origin || byId('store-tab-downloads')).focus({preventScroll:true});
  });
  downloadInfo.addEventListener('click', event => {
    if (event.target !== downloadInfo) return;
    const rect = downloadInfo.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) downloadInfo.close();
  });
  sections.forEach((name, i) => { const b = domainButton(labels[i], () => navigate(name, '', '', false, ''), ''); b.replaceChildren(domainText('span', labels[i])); b.dataset.section = name; b.id = `store-tab-${name}`; b.setAttribute('aria-pressed', String(name === section)); b.setAttribute('aria-controls','store-panel'); byId('store-sections').append(b); });
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
  byId('store-query').addEventListener('input', () => { installedPage = 1; livePage = 1; if (section === 'discover' && hub()) { clearTimeout(searchTimer); searchTimer = setTimeout(() => navigate(section, category, '', true), 350); } else navigate(section, category, '', true); });
  function changeEndpoint(value) { endpoint = value; byId('store-endpoint').value = value; byId('store-download-destination').textContent = connections.find(c => c.id === endpoint)?.name || ''; installedPage = 1; inventory = null; loadInventory(); }
  byId('store-endpoint').addEventListener('change', () => changeEndpoint(byId('store-endpoint').value));
  byId('store-download-open').append(libraryIcon('plus'));
  byId('store-download-open').addEventListener('click', () => { if (!byId('store-download-open').disabled) { closeStoreFilters(); byId('store-download-status').textContent = ''; byId('store-download-destination').textContent = connections.find(c => c.id === endpoint)?.name || ''; const picker = byId('store-download-endpoint'); picker.replaceChildren(...connections.map(c => new Option(c.name,c.id))); picker.value = endpoint; byId('store-download-endpoint-label').hidden = connections.length < 2; downloadDialog.showModal(); byId('store-download-tag').focus(); } });
  byId('store-download-endpoint').addEventListener('change', () => changeEndpoint(byId('store-download-endpoint').value));
  byId('store-download-close').addEventListener('click', () => downloadDialog.close());
  downloadDialog.addEventListener('close', () => byId('store-download-open').focus());
  byId('store-download-form').addEventListener('submit', event => { event.preventDefault(); review('model-pull', byId('store-download-tag').value.trim(), true); });
  byId('store-source').addEventListener('change', () => { category = ''; livePage = 1; liveCatalog = null; navigate(section, '', '', true, ''); });
  byId('store-sort').addEventListener('change', () => { livePage = 1; liveCatalog = null; navigate(section, category, '', true); });
  byId('store-size').addEventListener('change', () => { installedPage = 1; navigate(section, category, '', true); });
  byId('store-capability').addEventListener('change', () => navigate(section, category, '', true));
  byId('models-refresh').addEventListener('click', () => load());
  byId('store-detail-back').prepend(libraryIcon('previous'));
  byId('store-detail-back').addEventListener('click', () => {
    if (browseContext?.url && history.length > 1) history.back();
    else navigate(section, category, '', true);
  });
  document.addEventListener('klaude-view', () => {
    clearInterval(timer); timer = null;
    if (active()) { if (urlState() === false) return; render(); load(); if (supported()) timer = setInterval(loadJobs, 2000); }
    else { clearDownloadBars(); serial++; reading?.abort(); liveReading?.abort(); clearTimeout(searchTimer); popularSerial++; popularReading?.abort(); popularReading = null; dialog.hidden = true; downloadDialog.close(); closeStoreFilters(); downloadInfo.close(); }
  });
  document.addEventListener('klaude-snapshot', () => {
    const capability = supported();
    if (observedCapability === capability) { if (active() && detail) renderDetail(); return; }
    observedCapability = capability;
    if (!active()) return;
    clearInterval(timer); timer = null;
    render(); load();
    if (capability) timer = setInterval(loadJobs, 2000);
  });
  window.addEventListener('popstate', () => { if (active() && urlState() !== false) { render(); if (liveLanding()) loadPopular(); else if (hub()) loadLive(); } });
  document.addEventListener('klaude-auth-reset', () => {
    downloadInfo.close(); downloadInfoKey = downloadInfoSource = downloadInfoError = '';
    clearDownloadBars();
    shownDetail = detailSignature = variantPageSelection = ''; browseContext = null; detailsOpen.clear();
    clearInterval(timer); clearTimeout(searchTimer); popularSerial++; popularReading?.abort(); popularReading = null; popularCatalog = recentCatalog = null; closeStoreFilters(); byId('store-live-pages').hidden = true; livePage = 1; liveSerial++; liveReading?.abort(); liveDetails.clear(); liveCatalog = null; serial++; reading?.abort(); dialog.hidden = true; downloadDialog.close(); byId('store-download-tag').value = ''; catalog = inventory = null; jobs = []; connections = [];
    observedTransfers = []; jobsLoaded = false; renderStoreCounts();
    byId('store-installed-pages').hidden = true;
    byId('store-installed-numbers').replaceChildren(); byId('store-installed-page').textContent = ''; installedPage = 1;
    endpoint = detail = variant = collection = category = ''; observedCapability = undefined; pending = false; allowed = false; byId('store-query').value = ''; byId('store-content').replaceChildren(); byId('store-detail-body').replaceChildren(); message('');
  });
  function restoreFromLocation() {
    if (!active() || urlState() === false) return;
    render();
    if (detail && supported() && detail.startsWith('hf:') &&
        !liveDetails.has(detail) && detailReading !== detail) loadLiveDetail(detail);
  }
  return {render, restoreFromLocation};
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
        beforeOpen: () => { byId('model-credential-value').value = ''; if (dialog.open) dialog.close(); },
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
