"use strict";

// Same-origin adapter for shared Library services. Untrusted names, previews and
// knowledge snippets are always DOM text; downloaded documents never execute.
let librarySection = readNavigationChoice("library-section",
  ["files", "knowledge", "document", "research", "media", "archive"], "files");
// Preserve old tab selections as filters when a saved browser tab is upgraded.
let fileKind = readNavigationChoice("file-kind", ["all", "document", "research", "media"], "all");
let fileStatus = readNavigationChoice("file-status", ["saved", "archived"], "saved");
if (!["files", "knowledge"].includes(librarySection)) {
  fileKind = librarySection === "archive" ? "all" : librarySection;
  fileStatus = librarySection === "archive" ? "archived" : "saved";
  librarySection = "files";
  saveNavigationChoice("library-section", librarySection);
  saveNavigationChoice("file-kind", fileKind);
  saveNavigationChoice("file-status", fileStatus);
}
byId("artifact-kind").value = fileKind;
byId("artifact-status").value = fileStatus;
let libraryOffset = 0;
let sourceOffset = 0;
let skillsOffset = 0;
let knowledgeQuery = "";
const LIBRARY_PAGE_SIZE = 20;
const domainPageSizes = { library: 20, sources: 20, skills: 20 };
const domainGrids = { library: "library-items", sources: "source-items", skills: "skill-items" };
let gridResizeTimer = null;
let libraryLoad = 0;
let skillsLoad = 0;
let sourcesLoad = 0;
let artifactLoad = 0;
let tabCountsLoad = 0;
let legacyTabCounts = false;
let skillsSearchTimer = null;
let installedSkills = [];
let selectedArtifact = null;
let managementReview = null;
let operationSignature = "";
let operationPollBusy = false;
const reviewDialog = byId("domain-review");
const artifactDialog = byId("artifact-detail");
const legacyPageRoutes = new Set();
const compactDomainPages = window.matchMedia("(max-width: 560px)");

function domainText(tag, text, className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}
function domainButton(label, action, className = "quiet") {
  const button = domainText("button", label, className);
  button.type = "button";
  button.addEventListener("click", action);
  return button;
}
function domainError(error, target = "library-status") {
  if (error.name === "AbortError" || error.authEpoch !== undefined && error.authEpoch !== authEpoch) return;
  if (error.status === 401) { showLocalAccess(); return; }
  byId(target).textContent = error.message || String(error);
}
async function domainRequest(path, method = "GET", body) {
  const epoch = authEpoch;
  const result = path === "/api/v1/library/submit" && method === "POST" ?
    await controlledRequest(path, body) : await jsonRequest(path, method, body);
  if (!authenticated || epoch !== authEpoch) throw new DOMException("Signed out", "AbortError");
  return result;
}
async function domainPage(path, parameters, resolveTotal = true) {
  // Static assets update while an older host may still own a running turn.
  // Adapt its bounded inventories until that host can be restarted safely.
  const params = new URLSearchParams(parameters);
  if (legacyPageRoutes.has(path)) {
    params.delete("offset");
    if (path === "/api/v1/integrations/skills") params.delete("query");
  }
  let data;
  try {
    data = await domainRequest(`${path}?${params}`);
  } catch (error) {
    if (error.authEpoch !== undefined && error.authEpoch !== authEpoch) throw error;
    if (error.status !== 400 || legacyPageRoutes.has(path) ||
        !["/api/v1/library/knowledge", "/api/v1/integrations/skills"].includes(path)) throw error;
    legacyPageRoutes.add(path);
    return domainPage(path, parameters, resolveTotal);
  }
  if (data.page_size === undefined) {
    const key = data.hits ? "hits" : "items";
    let items = data[key];
    const inventory = path === "/api/v1/integrations/skills" ||
      path === "/api/v1/library/knowledge" && !parameters.query;
    if (path === "/api/v1/integrations/skills" && parameters.query) {
      const needle = parameters.query.toLocaleLowerCase();
      items = items.filter((item) => `${item.name} ${item.description} ${item.library}`.toLocaleLowerCase().includes(needle));
    }
    const offset = Number(parameters.offset || 0);
    const total = inventory ? items.length : data.total ??
      (!data.more && (items.length || offset === 0) ? offset + items.length : null);
    const knownTotal = total ?? (items.length ? offset + items.length + Number(Boolean(data.more)) : 0);
    if (inventory) items = items.slice(offset);
    data = { ...data, [key]: items.slice(0, LIBRARY_PAGE_SIZE),
      more: items.length > LIBRARY_PAGE_SIZE || !inventory && Boolean(data.more),
      limited: inventory && Boolean(data.more), page_size: LIBRARY_PAGE_SIZE,
      total, known_total: knownTotal };
  }
  // Older hosts expose lookahead rather than a count. Locate their terminal
  // batch with bounded exponential/binary probes, without restarting active work.
  if (resolveTotal && data.total == null && data.more && !legacyPageRoutes.has(path)) {
    let low = Number(parameters.offset || 0);
    let high = null;
    let step = 100;
    for (let attempt = 0; attempt < 32; attempt++) {
      const probe = high === null ? Math.min(1000000, low + step) :
        Math.floor((low + high) / (2 * LIBRARY_PAGE_SIZE)) * LIBRARY_PAGE_SIZE;
      if (probe <= low) break;
      const tail = await domainPage(path, { ...parameters, offset: probe }, false);
      if (tail.total != null) { data.total = tail.total; break; }
      if ((tail.items || tail.hits).length) { low = probe; step *= 2; }
      else high = probe;
    }
  }
  return data;
}
function measureDomainPageSize(prefix) {
  let grid = byId(domainGrids[prefix]);
  // Sources share the Library grid width, including while their section loads.
  if (!grid.getClientRects().length && prefix === "sources") grid = byId("library-items");
  if (!grid.getClientRects().length) return domainPageSizes[prefix];
  const tracks = getComputedStyle(grid).gridTemplateColumns;
  const columns = tracks === "none" ? 1 : tracks.trim().split(/\s+/).length;
  // Keep pages near twenty cards, in complete rows, with at most two read batches.
  return Math.min(40, columns * Math.max(1, Math.round(LIBRARY_PAGE_SIZE / columns)));
}
function syncDomainPageSize(prefix) {
  const size = measureDomainPageSize(prefix);
  if (size !== domainPageSizes[prefix]) {
    domainPageSizes[prefix] = size;
    // Keep the former first item on the newly sized page instead of resetting.
    if (prefix === "library") libraryOffset = Math.floor(libraryOffset / size) * size;
    else if (prefix === "skills") skillsOffset = Math.floor(skillsOffset / size) * size;
    else sourceOffset = Math.floor(sourceOffset / size) * size;
  }
  return size;
}
async function gridPage(path, parameters, pageSize) {
  // Compose existing bounded reads so new assets also work with a running host.
  const data = await domainPage(path, parameters);
  const key = data.hits ? "hits" : "items";
  const items = data[key].slice(0, pageSize);
  let more = data[key].length > pageSize || Boolean(data.more);
  let tail = data;
  if (items.length < pageSize && more && items.length) {
    tail = await domainPage(path, { ...parameters, offset: Number(parameters.offset || 0) + items.length }, false);
    const remaining = pageSize - items.length;
    items.push(...tail[key].slice(0, remaining));
    more = tail[key].length > remaining || Boolean(tail.more);
  }
  return { ...data, [key]: items, more, page_size: pageSize,
    total: tail.total ?? data.total,
    known_total: Math.max(data.known_total || 0, tail.known_total || 0) };
}
const countedTabs = [...document.querySelectorAll("[data-count-key]")];
for (const button of countedTabs) button.dataset.label = button.textContent;

function renderTabCounts(counts = {}) {
  // File kinds are disjoint. Only show the aggregate when every part is known.
  const files = [counts.document, counts.media, counts.research];
  if (files.every((count) => Number.isSafeInteger(count?.total) && count.total >= 0)) {
    counts = { ...counts, files: { total: files.reduce((sum, count) => sum + count.total, 0),
      limited: files.some((count) => count.limited) } };
  }
  for (const button of countedTabs) {
    const count = counts[button.dataset.countKey];
    const total = count?.total;
    const label = domainText("span", button.dataset.label);
    if (Number.isSafeInteger(total) && total >= 0) {
      const badge = domainText("span", `${total.toLocaleString()}${count.limited ? "+" : ""}`, "tab-count");
      button.replaceChildren(badge, document.createTextNode(" "), label);
    } else button.replaceChildren(label);
  }
}
async function readTabCounts() {
  if (!legacyTabCounts) {
    try { return await domainRequest("/api/v1/library/counts"); }
    catch (error) {
      if (error.status !== 404 || error.authEpoch !== undefined && error.authEpoch !== authEpoch) throw error;
      legacyTabCounts = true;
    }
  }
  // Older running hosts can still supply inventory totals. MCP has no older
  // browser read route, so leave its count unknown rather than inventing zero.
  const reads = [
    ["knowledge", "/api/v1/library/knowledge", {}],
    ["document", "/api/v1/library/items", { kind: "document" }],
    ["research", "/api/v1/library/items", { kind: "research" }],
    ["media", "/api/v1/library/items", { kind: "media" }],
    ["archive", "/api/v1/library/items", { kind: "all", archived: "true" }],
    ["skills", "/api/v1/integrations/skills", {}],
  ];
  const results = await Promise.allSettled(reads.map(async ([name, path, params]) => {
    const result = await domainPage(path, { ...params, offset: 0 });
    return [name, { total: result.total, limited: result.limited }];
  }));
  return Object.fromEntries(results.filter((result) => result.status === "fulfilled")
    .map((result) => result.value));
}
async function loadTabCounts() {
  const load = ++tabCountsLoad;
  const finishes = countedTabs.map((button) => beginLoading(button, {
    kind: "count", prepend: true, preserve: Boolean(button.querySelector(".tab-count")),
  }));
  try {
    const counts = await readTabCounts();
    if (load === tabCountsLoad) renderTabCounts(counts);
  } catch (error) {
    if (load !== tabCountsLoad || error.name === "AbortError" ||
        error.authEpoch !== undefined && error.authEpoch !== authEpoch) return;
    if (!countedTabs.some((button) => button.querySelector(".tab-count"))) renderTabCounts();
    if (error.status === 401) showLocalAccess();
  }
  finally { finishes.forEach((finish) => finish()); }
}

function artifactUrl(item, inline = false) {
  return "/api/v1/library/content?" + new URLSearchParams({
    id: item.id, revision: item.revision, ...(inline ? { inline: "1" } : {}),
  });
}
function canPreviewImage(item) {
  return ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(item.mime) &&
    item.width > 0 && item.height > 0 && Math.max(item.width, item.height) <= 4096 &&
    item.width * item.height <= 4000000 && item.size <= 8 * 1024 * 1024;
}
function artifactImage(item) {
  const img = document.createElement("img");
  img.alt = item.name;
  img.loading = "lazy";
  img.decoding = "async";
  img.classList.add("image-pending");
  img.setAttribute("aria-busy", "true");
  img.addEventListener("load", () => {
    img.classList.remove("image-pending");
    img.setAttribute("aria-busy", "false");
  }, { once: true });
  img.src = artifactUrl(item, true);
  img.addEventListener("error", () => img.replaceWith(domainText("p", "Preview unavailable. Open the item to download it.", "muted")), { once: true });
  return img;
}
function renderDomainPageNumbers(prefix, current, last) {
  const start = Math.max(2, Math.min(current - 1, last - 3));
  const pages = last <= (compactDomainPages.matches ? 5 : 7) ?
    Array.from({ length: last }, (_, index) => index + 1) :
    [1, start, start + 1, start + 2, last];
  const numbers = byId(`${prefix}-numbers`);
  numbers.dataset.current = current;
  numbers.dataset.last = last;
  const focused = numbers.contains(document.activeElement) ? document.activeElement.dataset.page : null;
  const buttons = [];
  let previous = 0;
  for (const page of pages) {
    if (page > previous + 1) {
      const gap = domainText("span", "···", "page-gap");
      gap.setAttribute("aria-hidden", "true");
      buttons.push(gap);
    }
    const button = domainText("button", page);
    button.type = "button";
    button.dataset.page = page;
    button.setAttribute("aria-label", `Page ${page}`);
    if (page === current) button.setAttribute("aria-current", "page");
    buttons.push(button);
    previous = page;
  }
  numbers.replaceChildren(...buttons);
  if (focused) (numbers.querySelector(`[data-page="${focused}"]`) ||
    numbers.querySelector("[aria-current='page']"))?.focus({ preventScroll: true });
}
function updateDomainPager(prefix, offset, data) {
  const pageSize = data.page_size;
  const current = offset / pageSize + 1;
  const count = (data.items || data.hits).length;
  const known = data.total ?? data.known_total ?? offset + count + Number(Boolean(data.more));
  const last = Math.max(current, Math.ceil(known / pageSize));
  renderDomainPageNumbers(prefix, current, last);
  byId(`${prefix}-pages`).hidden = count === 0 && offset === 0;
  byId(`${prefix}-previous`).disabled = offset === 0;
  byId(`${prefix}-next`).disabled = !data.more;
  byId(`${prefix}-page`).textContent = `Page ${current}${data.total == null ? "" : ` of ${last}`}`;
}

async function loadLibrary() {
  const pageSize = syncDomainPageSize("library");
  for (const button of document.querySelectorAll("#library-sections button")) {
    button.setAttribute("aria-pressed", String(button.dataset.section === librarySection));
  }
  const load = ++libraryLoad;
  const section = librarySection;
  const offset = libraryOffset;
  const knowledge = section === "knowledge";
  byId("artifact-tools").hidden = knowledge;
  byId("knowledge-tools").hidden = !knowledge;
  if (!knowledge || byId("source-items").dataset.library !== byId("knowledge-library").value) {
    byId("knowledge-sources").hidden = true;
  }
  const grid = byId("library-items");
  const key = JSON.stringify([section, fileKind, fileStatus, offset, knowledgeQuery, byId("knowledge-library").value,
    byId("artifact-query").value, byId("artifact-sort").value]);
  if (grid.dataset.contentKey !== key) byId("library-pages").hidden = true;
  const finish = beginLoading(grid, { kind: "cards", count: Math.min(6, pageSize),
    preserve: grid.dataset.contentKey === key, artwork: !knowledge, label: "Loading library…" });
  byId("library-status").textContent = "";
  try {
    if (knowledge) {
      if (knowledgeQuery) {
        const data = await gridPage("/api/v1/library/knowledge", {
          library: byId("knowledge-library").value, query: knowledgeQuery, offset }, pageSize);
        if (load !== libraryLoad) return;
        if (!data.hits.length && offset > 0) {
          libraryOffset = Math.max(0, offset - pageSize);
          return loadLibrary();
        }
        byId("library-items").replaceChildren(...data.hits.map((hit) => {
          const card = domainText("article", "", "library-card knowledge-hit");
          card.append(domainText("h3", hit.source), domainText("pre", hit.text));
          return card;
        }));
        updateDomainPager("library", offset, data);
        byId("library-status").textContent = data.hits.length ? "" : "No indexed text matches.";
        grid.dataset.contentKey = key;
        finish();
        await loadKnowledgeSources();
        return;
      }
      const data = await gridPage("/api/v1/library/knowledge", { offset }, pageSize);
      if (load !== libraryLoad) return;
      if (!data.items.length && offset > 0) {
        libraryOffset = Math.max(0, offset - pageSize);
        return loadLibrary();
      }
      const previous = byId("knowledge-library").value;
      byId("knowledge-library").replaceChildren(domainText("option", "Choose a library"));
      byId("knowledge-library").firstChild.value = "";
      const nodes = [];
      for (const item of data.items) {
        const option = domainText("option", item.id);
        option.value = item.id;
        byId("knowledge-library").append(option);
        const card = domainText("article", "", "library-card knowledge-card");
        card.append(domainText("span", "KNOWLEDGE", "eyebrow"), domainText("h2", item.id),
          domainText("p", `${item.sources ?? "Unknown"} sources · ${item.chunks ?? "Unknown"} chunks`, "muted"),
          domainButton("Explore library", () => {
            byId("knowledge-library").value = item.id;
            byId("learn-library").value = item.id;
            byId("knowledge-query").focus();
            sourceOffset = 0;
            loadKnowledgeSources().catch((error) => domainError(error));
          }));
        nodes.push(card);
      }
      if (previous && !data.items.some((item) => item.id === previous)) {
        const option = domainText("option", previous);
        option.value = previous;
        byId("knowledge-library").append(option);
      }
      byId("knowledge-library").value = previous;
      byId("library-items").replaceChildren(...nodes);
      updateDomainPager("library", offset, data);
      byId("library-status").textContent = data.items.length ?
        data.limited ? "Inventory limited to 1,000." : "" :
        "No knowledge yet. Learn a URL or text file to create your first library.";
      grid.dataset.contentKey = key;
      finish();
      await loadKnowledgeSources();
    } else {
      const params = { kind: fileKind,
        archived: String(fileStatus === "archived"), offset,
        query: byId("artifact-query").value, sort: byId("artifact-sort").value };
      const data = await gridPage("/api/v1/library/items", params, pageSize);
      if (load !== libraryLoad) return;
      if (!data.items.length && offset > 0) {
        libraryOffset = Math.max(0, offset - pageSize);
        return loadLibrary();
      }
      const cards = data.items.map((item) => {
        const card = domainText("article", "", "library-card");
        if (canPreviewImage(item)) card.append(artifactImage(item));
        else card.append(domainText("div", item.kind === "media" ? "Image" : item.kind === "research" ? "Report" : "File", "artifact-symbol"));
        card.append(domainText("h2", item.name),
          domainText("p", `${item.kind === "research" ? "Report" : item.kind === "media" ? "Media" : "Document"}${item.archived ? " · Archived" : ""} · ${(item.size / 1024).toFixed(1)} KiB`, "muted"));
        if (item.tags.length) card.append(domainText("p", item.tags.join(" · "), "artifact-tags"));
        card.append(domainButton("Open item", () => openArtifact(item.id).catch((error) => domainError(error))));
        return card;
      });
      byId("library-items").replaceChildren(...cards);
      byId("library-status").textContent = data.items.length ? "" :
        byId("artifact-query").value ? "No files match this search and filters." : fileStatus === "archived" ?
          "No archived files match this type." : fileKind === "research" ?
            "No saved reports. Research reports created in the CLI appear here." : "No saved files match this type. Add a file to get started.";
      updateDomainPager("library", offset, data);
      grid.dataset.contentKey = key;
    }
  } catch (error) { if (load === libraryLoad) domainError(error); }
  finally { finish(); }
}

async function openArtifact(id) {
  const load = ++artifactLoad;
  const preview = byId("artifact-preview");
  selectedArtifact = null;
  byId("artifact-detail-title").textContent = "Item details";
  byId("artifact-actions").replaceChildren();
  byId("artifact-tags").hidden = true;
  byId("artifact-tags-input").value = "";
  const finish = beginLoading(preview, { kind: "detail", count: 1, preserve: false, label: "Loading item preview…" });
  if (!artifactDialog.open) artifactDialog.showModal();
  try {
    const data = await domainRequest(`/api/v1/library/item?${new URLSearchParams({ id })}`);
    if (load !== artifactLoad || !artifactDialog.open) return;
    const item = data.item;
    selectedArtifact = item;
    byId("artifact-detail-title").textContent = item.name;
    const nodes = [domainText("p", `${item.mime} · ${item.size.toLocaleString()} bytes`, "muted")];
    if (canPreviewImage(item)) nodes.push(artifactImage(item));
    else nodes.push(domainText("pre", data.lines.join("\n"), "artifact-text"));
    if (data.truncated) nodes.push(domainText("p", "Preview truncated. Download for the complete file.", "muted"));
    if (item.ai_tags?.length) nodes.push(domainText("p", `AI tags: ${item.ai_tags.join(", ")}`, "muted"));
    byId("artifact-preview").replaceChildren(...nodes);
    byId("artifact-tags-input").value = item.tags.join(", ");
    const download = domainText("a", "Download", "download-link");
    download.href = artifactUrl(item);
    download.download = item.filename;
    const change = (operation, value) => {
      artifactDialog.close();
      prepareChange({ operation, target: item.id, revision: item.revision,
        ...(value !== undefined ? { value } : {}) }).catch((error) => domainError(error));
    };
    const actions = [download, domainButton(item.archived ? "Restore" : "Archive",
      () => change(item.archived ? "restore" : "archive"))];
    if (item.archived) actions.push(domainButton("Delete permanently", () => change("delete"), "danger"));
    if (item.ai_tags?.length) actions.push(domainButton("Clear AI tags", () => change("clear_ai_tags")));
    byId("artifact-actions").replaceChildren(...actions);
    byId("artifact-tags").hidden = false;
  } catch (error) {
    if (load !== artifactLoad || !artifactDialog.open) return;
    if (error.name !== "AbortError") preview.textContent = error.message || "Could not load this item.";
    if (error.status === 401) showLocalAccess();
  } finally { finish(); }
}
byId("artifact-close").addEventListener("click", () => artifactDialog.close());
artifactDialog.addEventListener("close", () => {
  if (artifactDialog.open) return;
  artifactLoad += 1;
  selectedArtifact = null;
  cancelLoading(byId("artifact-preview"));
});
byId("artifact-tags").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!selectedArtifact) return;
  const item = selectedArtifact;
  artifactDialog.close();
  prepareChange({ operation: "tags", target: item.id, revision: item.revision,
    value: byId("artifact-tags-input").value }).catch((error) => domainError(error));
});

async function loadKnowledgeSources() {
  const pageSize = syncDomainPageSize("sources");
  const library = byId("knowledge-library").value;
  const load = ++sourcesLoad;
  const offset = sourceOffset;
  if (!library) { cancelLoading(byId("source-items")); byId("knowledge-sources").hidden = true; return; }
  const grid = byId("source-items");
  const key = JSON.stringify([library, offset]);
  if (grid.dataset.contentKey !== key) byId("sources-pages").hidden = true;
  const finish = beginLoading(grid, { kind: "cards", count: 3,
    preserve: grid.dataset.contentKey === key, label: "Loading sources…" });
  byId("knowledge-sources").hidden = false;
  try {
    const data = await gridPage("/api/v1/library/sources", { library, offset }, pageSize);
    if (load !== sourcesLoad || librarySection !== "knowledge" || library !== byId("knowledge-library").value) return;
    if (!data.items.length && offset > 0) {
      sourceOffset = Math.max(0, offset - pageSize);
      return loadKnowledgeSources();
    }
    const cards = data.items.map((source) => {
      const card = domainText("article", "", "library-card");
      card.append(domainText("h3", source.id), domainText("p", source.url, "muted"),
        domainText("p", `${source.kind} · ${source.files} files`, "muted"),
        domainButton("Review refresh", () => prepareChange({ operation: "knowledge-refresh",
          library: source.library, source: source.id, source_identity: source.identity })
          .catch((error) => domainError(error))));
      return card;
    });
    byId("source-items").replaceChildren(...cards);
    byId("knowledge-sources").hidden = !data.items.length;
    updateDomainPager("sources", offset, data);
    grid.dataset.contentKey = key;
    grid.dataset.library = library;
  } catch (error) {
    if (load === sourcesLoad) {
      if (!grid.querySelector(".library-card")) byId("knowledge-sources").hidden = true;
      throw error;
    }
  }
  finally { finish(); }
}
byId("sources-next").addEventListener("click", () => { sourceOffset += domainPageSizes.sources; loadKnowledgeSources().catch((error) => domainError(error)); });
byId("sources-previous").addEventListener("click", () => { sourceOffset = Math.max(0, sourceOffset - domainPageSizes.sources); loadKnowledgeSources().catch((error) => domainError(error)); });
byId("knowledge-library").addEventListener("change", () => {
  byId("learn-library").value = byId("knowledge-library").value;
  sourceOffset = 0;
  knowledgeQuery = "";
  libraryOffset = 0;
  loadLibrary();
});
byId("knowledge-search").addEventListener("submit", (event) => {
  event.preventDefault();
  const library = byId("knowledge-library").value;
  const query = byId("knowledge-query").value.trim();
  if (query && !library) { byId("library-status").textContent = "Choose a library first."; return; }
  knowledgeQuery = query;
  libraryOffset = 0;
  loadLibrary();
});

async function uploadForReview(file, limit = 32 * 1024 * 1024) {
  if (!file || !file.size || file.size > limit) throw new Error(`Choose a nonempty file up to ${limit / 1024 / 1024} MiB.`);
  const epoch = authEpoch;
  const response = await fetch("/api/v1/uploads", { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/octet-stream", "X-Klaude-CSRF": csrf,
      "X-Klaude-Filename": file.name.replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 100) }, body: file });
  const data = await response.json();
  if (epoch !== authEpoch || !authenticated) throw new DOMException("Signed out", "AbortError");
  if (!response.ok) {
    const error = new Error(data.error?.message || "Upload failed");
    error.status = response.status;
    throw error;
  }
  return data.id;
}
async function prepareChange(draft) {
  const result = await domainRequest("/api/v1/library/review", "POST", { draft });
  managementReview = { ...result, request_id: requestId() };
  byId("domain-review-summary").textContent = result.summary;
  byId("domain-review-status").textContent = "Changes begin only after confirmation. Accepted work continues if you leave this page.";
  byId("domain-review-confirm").disabled = false;
  reviewDialog.showModal();
  byId("domain-review-cancel").focus();
}
reviewDialog.addEventListener("close", () => {
  const old = managementReview;
  managementReview = null;
  if (old && authenticated && !old.accepted) {
    domainRequest("/api/v1/library/discard", "POST", { review_id: old.review_id }).catch(() => {});
  }
});
byId("domain-review-confirm").addEventListener("click", async () => {
  if (!managementReview || !latest) return;
  const review = managementReview;
  const epoch = authEpoch;
  const current = () => managementReview === review && authenticated && epoch === authEpoch;
  byId("domain-review-confirm").disabled = true;
  try {
    const operation = await domainRequest("/api/v1/library/submit", "POST", {
      review_id: review.review_id, request_id: review.request_id,
    });
    review.accepted = true;
    if (current()) {
      reviewDialog.close();
      for (const id of ["artifact-file", "learn-file", "skill-file"]) byId(id).value = "";
      const target = currentView === "integrations" ? "skills-status" : "library-status";
      byId(target).textContent = `Accepted · ${operation.kind}. Track progress in Activity.`;
    }
    await loadOperations();
  } catch (error) {
    if (current() && error.name !== "AbortError") {
      if (error.status === 401) showLocalAccess();
      else byId("domain-review-status").textContent = `${error.message}. Check Activity if the connection was interrupted; retrying uses the same request ID.`;
    }
  } finally { if (current()) byId("domain-review-confirm").disabled = false; }
});

function bindUploadForm(id, action, statusId) {
  byId(id).addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = byId(id).querySelector('button[type="submit"]');
    if (button.disabled) return;
    button.disabled = true;
    byId(statusId).textContent = "Preparing review…";
    try { await action(); byId(statusId).textContent = "Ready for review."; }
    catch (error) { domainError(error, statusId); }
    finally { button.disabled = false; }
  });
}
bindUploadForm("artifact-import", async () => {
  const kind = byId("artifact-import-kind").value;
  const upload_id = await uploadForReview(byId("artifact-file").files[0]);
  await prepareChange({ operation: "import", upload_id, kind });
}, "library-status");
byId("artifact-import-kind").addEventListener("change", () => {
  byId("artifact-file").value = "";
  byId("artifact-file").accept = byId("artifact-import-kind").value === "media" ?
    "image/png,image/jpeg,image/webp,image/gif" : "";
});
bindUploadForm("knowledge-learn", async () => {
  const library = byId("learn-library").value;
  const source = byId("learn-url").value.trim();
  const file = byId("learn-file").files[0];
  if (source && file) throw new Error("Choose a URL or a text file, then review it separately.");
  if (file) {
    const upload_id = await uploadForReview(file, 2 * 1024 * 1024);
    await prepareChange({ operation: "knowledge-upload", upload_id, library });
  } else await prepareChange({ operation: "knowledge-url", library, source });
}, "library-status");
bindUploadForm("skill-import", async () => {
  const upload_id = await uploadForReview(byId("skill-file").files[0], 2 * 1024 * 1024);
  await prepareChange({ operation: "skill-import", upload_id,
    name: byId("skill-name").value, library: byId("skill-library").value });
}, "skills-status");

async function loadSkills() {
  clearTimeout(skillsSearchTimer);
  const pageSize = syncDomainPageSize("skills");
  const load = ++skillsLoad;
  const offset = skillsOffset;
  const query = byId("skills-query").value;
  const grid = byId("skill-items");
  const key = JSON.stringify([query, offset]);
  if (grid.dataset.contentKey !== key) byId("skills-pages").hidden = true;
  const finish = beginLoading(grid, { kind: "cards", count: Math.min(6, pageSize),
    preserve: grid.dataset.contentKey === key, label: "Loading Skills…" });
  byId("skills-status").textContent = "";
  try {
    const data = await gridPage("/api/v1/integrations/skills", { query, offset }, pageSize);
    if (load !== skillsLoad) return;
    if (!data.items.length && offset > 0) {
      skillsOffset = Math.max(0, offset - pageSize);
      return loadSkills();
    }
    installedSkills = data.items;
    renderSkills();
    grid.dataset.contentKey = key;
    updateDomainPager("skills", offset, data);
    byId("skills-status").textContent = data.items.length ?
      data.limited ? "Inventory limited to 1,000." : "" :
      query ? "No Skills match your search." : "No installed Skills. Import a package to get started.";
  } catch (error) { if (load === skillsLoad) domainError(error, "skills-status"); }
  finally { finish(); }
}
function renderSkills() {
  const nodes = installedSkills.map((skill) => {
      const card = domainText("article", "", "library-card skill-card");
      card.append(domainText("span", skill.enabled ? "ENABLED" : "DISABLED", "eyebrow"),
        domainText("h2", skill.name), domainText("p", skill.description || "No description provided."),
        domainText("p", `${skill.source_label} · ${skill.indexed_file_count} indexed files · ${skill.library}`, "muted"));
      const actions = domainText("div", "", "dialog-actions");
      const change = (operation, extra = {}) => prepareChange({ operation, name: skill.name,
        identity: skill.identity, expected_enabled: skill.enabled, ...extra }).catch((error) => domainError(error, "skills-status"));
      actions.append(domainButton(skill.enabled ? "Disable" : "Enable", () => change("skill-enabled", { enabled: !skill.enabled })),
        domainButton("Delete", () => change("skill-delete"), "danger"));
      card.append(actions);
      return card;
    });
  byId("skill-items").replaceChildren(...nodes);
}
async function loadOperations() {
  if (operationPollBusy || !authenticated) return;
  operationPollBusy = true;
  const finish = beginLoading(byId("domain-operations"), { kind: "rows", count: 3, label: "Loading operations…" });
  try {
    const data = await domainRequest("/api/v1/library/operations");
    const signature = data.items.map((item) => `${item.request_id}:${item.state}`).join("|");
    const changed = operationSignature && signature !== operationSignature;
    operationSignature = signature;
    byId("domain-operations").replaceChildren(...data.items.map((item) => {
      const node = domainText("article", "", "operation-row");
      const status = item.state === "unknown" ? "Unconfirmed · local reconciliation required; do not resubmit" :
        item.state === "failed" ? "Rejected · reload and review the current item" : item.state;
      node.append(domainText("strong", item.kind.replaceAll("-", " ")), domainText("span", status),
        domainText("small", item.request_id, "muted"));
      return node;
    }));
    if (!data.items.length) byId("domain-operations").append(domainText("p", "No Library or integration operations yet.", "muted"));
    if (changed && data.items.some((item) => ["completed", "failed", "unknown"].includes(item.state))) {
      loadTabCounts();
      if (currentView === "library") loadLibrary();
      if (currentView === "integrations") loadSkills();
    }
  } catch (error) { domainError(error, currentView === "integrations" ? "skills-status" : "library-status"); }
  finally { finish(); operationPollBusy = false; }
}

byId("nav-library").addEventListener("click", () => showView("library"));
byId("nav-integrations").addEventListener("click", () => showView("integrations"));
byId("library-refresh").addEventListener("click", () => { loadLibrary(); loadTabCounts(); });
byId("skills-refresh").addEventListener("click", () => { loadSkills(); loadTabCounts(); });
byId("skills-query").addEventListener("input", () => {
  skillsOffset = 0;
  skillsLoad += 1;
  clearTimeout(skillsSearchTimer);
  skillsSearchTimer = setTimeout(loadSkills, 200);
});
byId("skills-filter").addEventListener("submit", (event) => { event.preventDefault(); skillsOffset = 0; loadSkills(); });
byId("skills-previous").addEventListener("click", () => { skillsOffset = Math.max(0, skillsOffset - domainPageSizes.skills); loadSkills(); });
byId("skills-next").addEventListener("click", () => { skillsOffset += domainPageSizes.skills; loadSkills(); });
for (const button of document.querySelectorAll("#library-sections button")) {
  button.addEventListener("click", () => {
    if (librarySection !== button.dataset.section) byId("artifact-file").value = "";
    librarySection = button.dataset.section;
    saveNavigationChoice("library-section", librarySection);
    libraryOffset = 0;
    knowledgeQuery = "";
    for (const sibling of button.parentElement.children) sibling.setAttribute("aria-pressed", String(sibling === button));
    loadLibrary();
  });
}
byId("artifact-filter").addEventListener("submit", (event) => { event.preventDefault(); libraryOffset = 0; loadLibrary(); });
byId("artifact-sort").addEventListener("change", () => { libraryOffset = 0; loadLibrary(); });
for (const id of ["artifact-kind", "artifact-status"]) {
  byId(id).addEventListener("change", () => {
    fileKind = byId("artifact-kind").value;
    fileStatus = byId("artifact-status").value;
    saveNavigationChoice("file-kind", fileKind);
    saveNavigationChoice("file-status", fileStatus);
    libraryOffset = 0;
    loadLibrary();
  });
}
byId("library-previous").addEventListener("click", () => { libraryOffset = Math.max(0, libraryOffset - domainPageSizes.library); loadLibrary(); });
byId("library-next").addEventListener("click", () => { libraryOffset += domainPageSizes.library; loadLibrary(); });
for (const prefix of ["library", "skills", "sources"]) {
  byId(`${prefix}-numbers`).addEventListener("click", (event) => {
    const button = event.target.closest("button[data-page]");
    if (!button || button.hasAttribute("aria-current")) return;
    const offset = (Number(button.dataset.page) - 1) * domainPageSizes[prefix];
    if (prefix === "library") { libraryOffset = offset; loadLibrary(); }
    else if (prefix === "skills") { skillsOffset = offset; loadSkills(); }
    else { sourceOffset = offset; loadKnowledgeSources().catch((error) => domainError(error)); }
  });
}
compactDomainPages.addEventListener("change", () => {
  for (const prefix of ["library", "skills", "sources"]) {
    const numbers = byId(`${prefix}-numbers`);
    if (numbers.dataset.current) renderDomainPageNumbers(
      prefix, Number(numbers.dataset.current), Number(numbers.dataset.last));
  }
});
const domainGridObserver = new ResizeObserver(() => {
  if (!authenticated || !Object.keys(domainGrids).some((prefix) =>
    byId(domainGrids[prefix]).getClientRects().length &&
    measureDomainPageSize(prefix) !== domainPageSizes[prefix])) return;
  clearTimeout(gridResizeTimer);
  gridResizeTimer = setTimeout(() => {
    if (!authenticated) return;
    if (currentView === "library") {
      if (measureDomainPageSize("library") !== domainPageSizes.library) loadLibrary();
      else if (byId("source-items").getClientRects().length &&
          measureDomainPageSize("sources") !== domainPageSizes.sources) {
        loadKnowledgeSources().catch((error) => domainError(error));
      }
    } else if (currentView === "integrations" && measureDomainPageSize("skills") !== domainPageSizes.skills) {
      loadSkills();
    }
  }, 150);
});
for (const id of Object.values(domainGrids)) domainGridObserver.observe(byId(id));
document.addEventListener("klaude-view", (event) => {
  if (["library", "integrations"].includes(event.detail)) loadTabCounts();
  if (event.detail === "library") loadLibrary();
  if (event.detail === "integrations") loadSkills();
  if (["library", "integrations", "activity"].includes(event.detail)) loadOperations();
});
document.addEventListener("klaude-auth-reset", () => {
  clearTimeout(gridResizeTimer);
  tabCountsLoad += 1;
  legacyTabCounts = false;
  renderTabCounts();
  libraryLoad += 1;
  skillsLoad += 1;
  sourcesLoad += 1;
  artifactLoad += 1;
  libraryOffset = sourceOffset = skillsOffset = 0;
  knowledgeQuery = "";
  clearTimeout(skillsSearchTimer);
  legacyPageRoutes.clear();
  for (const prefix of ["library", "skills", "sources"]) {
    const numbers = byId(`${prefix}-numbers`);
    numbers.replaceChildren();
    delete numbers.dataset.current;
    delete numbers.dataset.last;
    byId(`${prefix}-pages`).hidden = true;
  }
  installedSkills = [];
  selectedArtifact = null;
  managementReview = null;
  operationSignature = "";
  reviewDialog.close();
  artifactDialog.close();
  for (const id of ["library-items", "skill-items", "source-items", "artifact-preview", "artifact-actions", "domain-operations"]) byId(id).replaceChildren();
  for (const id of ["library-items", "skill-items", "source-items"]) delete byId(id).dataset.contentKey;
  delete byId("source-items").dataset.library;
  for (const id of ["artifact-import", "knowledge-learn", "skill-import", "artifact-tags", "artifact-filter", "skills-filter"]) byId(id).reset();
  byId("artifact-kind").value = fileKind;
  byId("artifact-status").value = fileStatus;
  byId("artifact-file").accept = "";
  byId("artifact-import-panel").open = false;
  byId("knowledge-query").value = "";
  byId("knowledge-library").replaceChildren();
  byId("domain-review-summary").textContent = "";
  byId("domain-review-status").textContent = "";
  byId("artifact-detail-title").textContent = "Saved item";
  byId("library-status").textContent = "";
  byId("skills-status").textContent = "";
});
setInterval(() => {
  if (authenticated && ["library", "integrations", "activity"].includes(currentView) && !document.hidden) loadOperations();
}, 2000);
