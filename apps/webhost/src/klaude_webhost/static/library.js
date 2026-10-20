"use strict";

// Same-origin adapter for shared Library services. Untrusted names, previews and
// knowledge snippets are always DOM text; downloaded documents never execute.
let librarySection = readNavigationChoice("library-section",
  ["files", "outputs", "knowledge", "document", "research", "media", "archive"], "files");
let integrationSection = readNavigationChoice("integration-section", ["skills", "knowledge"], "skills");
if (librarySection === "knowledge") {
  librarySection = "files"; integrationSection = "knowledge";
  saveNavigationChoice("library-section", librarySection);
  saveNavigationChoice("integration-section", integrationSection);
  if (readNavigationChoice("page", viewNames, "chat") === "library") saveNavigationChoice("page", "integrations");
}
// Preserve old tab selections as filters when a saved browser tab is upgraded.
let fileKind = readNavigationChoice("file-kind", ["all", "document", "research", "media"], "all");
let fileStatus = readNavigationChoice("file-status", ["saved", "archived"], "saved");
let fileView = readNavigationChoice("file-view", ["list", "grid", "gallery"], "grid");
const fileSorts = ["newest", "oldest", "name", "name_desc", "largest", "smallest", "type"];
const FILE_PAGE_SIZE = 24;
let filePage = null;
let fileRead = null;
const filePages = new Map();
const artifactDetails = new Map();
let imageSequence = [];
let imageSequenceOffset = 0;
let imageSequenceTotal = 0;
let previewOrigin = null;
let previewOriginId = "";
let previewScroll = 0;
let previewNavigation = false;
let libraryImageCapability;
let librarySourceCapability;
if (librarySection === "research" || librarySection === "files" && fileKind === "research") {
  librarySection = "outputs";
  saveNavigationChoice("output-kind", "document");
  saveNavigationChoice("file-kind", "all");
  saveNavigationChoice("output-status", fileStatus);
  saveNavigationChoice("library-section", librarySection);
}
if (!["files", "outputs"].includes(librarySection)) {
  fileKind = librarySection === "archive" ? "all" : librarySection;
  fileStatus = librarySection === "archive" ? "archived" : "saved";
  librarySection = "files";
  saveNavigationChoice("library-section", librarySection);
  saveNavigationChoice("file-kind", fileKind);
  saveNavigationChoice("file-status", fileStatus);
}
if (librarySection === "outputs") {
  fileKind = normalizeFileKind(readNavigationChoice("output-kind", ["all", "document", "research", "media"], "all"));
  saveNavigationChoice("output-kind", fileKind);
  fileStatus = readNavigationChoice("output-status", ["saved", "archived"], "saved");
}
const artifactLocations = new Map();
function normalizeFileKind(kind) {
  if (kind === "research") return "document";
  return ["all", "document", "media"].includes(kind) ? kind : "all";
}
function configureArtifactKinds() {
  const choices = [["all", "All types"], ["document", "Documents"], ["media", "Media"]];
  byId("artifact-kind").replaceChildren(...choices.map(([value, label]) => {
    const option = domainText("option", label); option.value = value; return option;
  }));
}
configureArtifactKinds();
byId("artifact-kind").value = fileKind;
byId("artifact-status").value = fileStatus;
let libraryOffset = 0;
let knowledgeOffset = 0;
let knowledgeLoad = 0;
let knowledgeRead = null;
let sourceRead = null;
let knowledgeLocationPage = null;
let sourceLocationPage = null;
let sourceOffset = 0;
let skillsOffset = 0;
let knowledgeQuery = "";
const LIBRARY_PAGE_SIZE = 20;
const domainPageSizes = { library: 24, knowledge: 20, sources: 20, skills: 20 };
const domainGrids = { library: "library-items", knowledge: "knowledge-items", sources: "source-items", skills: "skill-items" };
let gridResizeTimer = null;
let libraryLoad = 0;
let skillsLoad = 0;
let sourcesLoad = 0;
let artifactLoad = 0;
let artifactRead = null;
let tabCountsLoad = 0;
let legacyTabCounts = false;
let skillsSearchTimer = null;
let installedSkills = [];
let selectedArtifact = null;
let managementReview = null;
let operationSignature = null;
let operationPollBusy = false;
const reviewDialog = byId("domain-review");
const artifactDialog = byId("artifact-detail");
const importDialog = byId("artifact-import-panel");
let importGeneration = 0;
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
function activeDomainStatus() {
  return currentView === "integrations" ? `${integrationSection}-status` : "library-status";
}
function domainError(error, target = activeDomainStatus()) {
  if (error.name === "AbortError" || error.authEpoch !== undefined && error.authEpoch !== authEpoch) return;
  if (error.status === 401) { showLocalAccess(); return; }
  byId(target).textContent = error.message || String(error);
}
async function domainRequest(path, method = "GET", body, options = {}) {
  const epoch = authEpoch;
  const result = path === "/api/v1/library/submit" && method === "POST" ?
    await controlledRequest(path, body) : await jsonRequest(path, method, body, options);
  if (!authenticated || epoch !== authEpoch) throw new DOMException("Signed out", "AbortError");
  return result;
}
async function domainPage(path, parameters, resolveTotal = true, options = {}) {
  // Static assets update while an older host may still own a running turn.
  // Adapt its bounded inventories until that host can be restarted safely.
  const params = new URLSearchParams(parameters);
  if (legacyPageRoutes.has(path)) {
    params.delete("offset");
    if (path === "/api/v1/integrations/skills") params.delete("query");
  }
  let data;
  try {
    data = await domainRequest(`${path}?${params}`, "GET", undefined, options);
  } catch (error) {
    if (error.authEpoch !== undefined && error.authEpoch !== authEpoch) throw error;
    if (error.status !== 400 || legacyPageRoutes.has(path) ||
        !["/api/v1/library/knowledge", "/api/v1/integrations/skills"].includes(path)) throw error;
    legacyPageRoutes.add(path);
    return domainPage(path, parameters, resolveTotal, options);
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
      const tail = await domainPage(path, { ...parameters, offset: probe }, false, options);
      if (tail.total != null) { data.total = tail.total; break; }
      if ((tail.items || tail.hits).length) { low = probe; step *= 2; }
      else high = probe;
    }
  }
  return data;
}
function measureDomainPageSize(prefix) {
  if (prefix === "library") return FILE_PAGE_SIZE;
  let grid = byId(domainGrids[prefix]);
  // Sources share the Knowledge grid width, including while their section loads.
  if (!grid.getClientRects().length && prefix === "sources") grid = byId("knowledge-items");
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
    else if (prefix === "knowledge") knowledgeOffset = Math.floor(knowledgeOffset / size) * size;
    else if (prefix === "skills") skillsOffset = Math.floor(skillsOffset / size) * size;
    else sourceOffset = Math.floor(sourceOffset / size) * size;
  }
  return size;
}
async function gridPage(path, parameters, pageSize, options = {}) {
  // Compose existing bounded reads so new assets also work with a running host.
  const data = await domainPage(path, parameters, true, options);
  const key = data.hits ? "hits" : "items";
  const items = data[key].slice(0, pageSize);
  let more = data[key].length > pageSize || Boolean(data.more);
  let tail = data;
  if (items.length < pageSize && more && items.length) {
    tail = await domainPage(path, { ...parameters, offset: Number(parameters.offset || 0) + items.length }, false, options);
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
  // Uploads/output counts come from the same provenance filter as their inventories.
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
    ...(latest?.library_artifact_sources ? [
      ["files", "/api/v1/library/items", { kind: "all", source: "input" }],
      ["outputs", "/api/v1/library/items", { kind: "all", source: "output" }],
    ] : []),
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
  if (!isLibraryImage(item)) return false;
  if (latest && latest.library_images !== true) return item.width > 0 && item.height > 0 &&
    Math.max(item.width, item.height) <= 4096 && item.width * item.height <= 4000000 &&
    item.size <= 8 * 1024 * 1024;
  return item.size <= 32 * 1024 * 1024;
}
function isLibraryImage(item) {
  return ["image/png", "image/jpeg", "image/webp", "image/gif"].includes(item.mime);
}
function artifactImage(item, expanded = false) {
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
  img.src = latest && latest.library_images !== true ? artifactUrl(item, true) :
    "/api/v1/library/image?" + new URLSearchParams({
    id: item.id, revision: item.revision, size: expanded ? "preview" : "thumbnail",
  });
  img.addEventListener("error", () => {
    const fallback = domainText("span", "Preview unavailable", "image-fallback");
    fallback.append(fileIcon(item));
    img.replaceWith(fallback);
  }, { once: true });
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

const fileIconPaths = {
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6",
  text: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M8 13h8M8 17h5",
  code: "m8 7-5 5 5 5m8-10 5 5-5 5m-3-14-2 18",
  image: "M3 3h18v18H3ZM3 16l6-6 5 5 3-3 4 4M7 7h.01",
  video: "M3 5h13v14H3Zm13 5 5-3v10l-5-3",
  audio: "M9 18V5l11-2v13M9 8l11-2M9 18a3 3 0 1 1-3-3c1.7 0 3 1.3 3 3Zm11-2a3 3 0 1 1-3-3c1.7 0 3 1.3 3 3Z",
  archive: "M4 3h16v4H4Zm1 4v14h14V7M10 11h4M10 14h4M10 17h4",
  folder: "M3 6h7l2 2h9v12H3ZM3 6V4h7l2 2",
  list: "M8 5h13M8 12h13M8 19h13M3 5h.01M3 12h.01M3 19h.01",
  grid: "M3 3h7v7H3Zm11 0h7v7h-7ZM3 14h7v7H3Zm11 0h7v7h-7Z",
  gallery: "M3 3h18v18H3ZM3 16l6-6 5 5 3-3 4 4M7 7h.01",
  previous: "m15 5-7 7 7 7", next: "m9 5 7 7-7 7",
  expand: "M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5",
  search: "M15 15a7 7 0 1 1 0-10 7 7 0 0 1 0 10Zm0 0 6 6",
  options: "M4 7h16M4 17h16M8 4v6m8 4v6",
  close: "m6 6 12 12M6 18 18 6",
  more: "M12 4a1 1 0 1 0 0 2 1 1 0 0 0 0-2M12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2M12 18a1 1 0 1 0 0 2 1 1 0 0 0 0-2",
  download: "M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4",
  fit: "M3 9V3h6m6 0h6v6M3 15v6h6m6 0h6v-6M8 8h8v8H8z",
  plus: "M12 5v14M5 12h14", minus: "M5 12h14",
  info: "M12 16v-4m0-4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  trash: "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7",
};
function libraryIcon(type) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.7");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(svg.namespaceURI, "path");
  path.setAttribute("d", fileIconPaths[type] || fileIconPaths.file);
  svg.append(path);
  return svg;
}
function fileType(item) {
  const extension = item.filename.split(".").pop().toLowerCase();
  if (isLibraryImage(item)) return ["image", "Image"];
  if (item.kind === "research") return ["text", "Report"];
  if (item.mime === "application/pdf" || extension === "pdf") return ["pdf", "PDF"];
  if (item.mime.startsWith("video/")) return ["video", "Video"];
  if (item.mime.startsWith("audio/")) return ["audio", "Audio"];
  if (["zip", "7z", "rar", "tar", "gz", "bz2", "xz"].includes(extension)) return ["archive", "Archive"];
  if (["py", "js", "ts", "tsx", "jsx", "json", "html", "css", "rs", "go", "c", "cpp", "sh", "yaml", "toml", "sql"].includes(extension)) return ["code", extension.toUpperCase()];
  if (item.mime.startsWith("text/") || ["doc", "docx", "odt", "rtf"].includes(extension)) return ["text", "Document"];
  return ["file", "File"];
}
function fileIcon(item) {
  const [type] = fileType(item);
  const icon = domainText("span", "", `file-icon file-icon-${type}`);
  icon.setAttribute("aria-hidden", "true");
  icon.append(libraryIcon(type === "pdf" ? "text" : type));
  if (type === "pdf") icon.append(domainText("span", "PDF", "file-icon-badge"));
  return icon;
}
function fileSize(size) {
  return size < 1024 ? `${size} B` : size < 1024 * 1024 ? `${(size / 1024).toFixed(1)} KiB` : `${(size / 1024 / 1024).toFixed(1)} MiB`;
}
function fileDate(created, options = { year: "numeric", month: "short", day: "numeric" }) {
  return new Date(created * 1000).toLocaleDateString(undefined, options);
}
function fileParameters(offset = libraryOffset) {
  // Generated documents retain the existing Research record kind and reviewed actions.
  return { kind: librarySection === "outputs" && fileKind === "document" ? "research" : fileKind,
    archived: String(fileStatus === "archived"), offset,
    source: librarySection === "outputs" ? "output" : "input",
    query: byId("artifact-query").value, sort: byId("artifact-sort").value,
    ...(fileView === "gallery" ? { images: "1" } : {}) };
}
async function readFilePage(offset, signal) {
  if (latest && latest.library_artifact_sources !== true) throw new Error(
    "Restart Web UI after the active reply to separate your Uploads from Generated.");
  const params = fileParameters(offset), key = JSON.stringify(params);
  const cached = filePages.get(key);
  if (cached && Date.now() - cached.time < 30000) return cached.data;
  const data = await gridPage("/api/v1/library/items", params, FILE_PAGE_SIZE, { signal });
  if (signal?.aborted) throw new DOMException("Obsolete inventory", "AbortError");
  filePages.set(key, { time: Date.now(), data });
  while (filePages.size > 8) filePages.delete(filePages.keys().next().value);
  return data;
}
function restoreLibraryLocation() {
  const query = new URLSearchParams(location.search);
  if (!["files", "outputs"].includes(query.get("library"))) return;
  librarySection = query.get("library");
  if (librarySection === "files" && query.get("files-type") === "research") librarySection = "outputs";
  fileView = ["list", "grid", "gallery"].includes(query.get("files-view")) ? query.get("files-view") : fileView;
  fileKind = normalizeFileKind(query.get("files-type"));
  fileStatus = query.get("files-status") === "archived" ? "archived" : "saved";
  configureArtifactKinds();
  byId("artifact-kind").value = fileKind;
  byId("artifact-status").value = fileStatus;
  byId("artifact-query").value = (query.get("files-q") || "").slice(0, 200);
  byId("artifact-sort").value = fileSorts.includes(query.get("files-sort")) ? query.get("files-sort") : "newest";
  const page = Number(query.get("files-page") || 1);
  libraryOffset = Number.isSafeInteger(page) && page > 0 && page <= 41667 ? (page - 1) * FILE_PAGE_SIZE : 0;
}
function rememberLibraryLocation(replace = false) {
  if (!authenticated || currentView !== "library") return;
  const url = new URL(location.href);
  url.searchParams.delete("session"); url.searchParams.delete("message");
  for (const key of [...url.searchParams.keys()])
    if (key === "integrations" || key.startsWith("knowledge-") || key === "sources-page") url.searchParams.delete(key);
  url.searchParams.set("library", librarySection);
  const state = { "files-view": fileView, "files-type": fileKind, "files-status": fileStatus,
    "files-sort": byId("artifact-sort").value, "files-q": byId("artifact-query").value,
    "files-page": String(Math.floor(libraryOffset / FILE_PAGE_SIZE) + 1) };
  for (const [key, value] of Object.entries(state)) {
    if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
  }
  const next = url.pathname + url.search;
  if (next !== location.pathname + location.search) history[replace ? "replaceState" : "pushState"](
    { ...history.state, klaudeLibrary: true }, "", next);
  saveNavigationChoice("file-view", fileView);
  saveNavigationChoice("library-section", librarySection);
  const prefix = librarySection === "outputs" ? "output" : "file";
  saveNavigationChoice(`${prefix}-kind`, fileKind); saveNavigationChoice(`${prefix}-status`, fileStatus);
}
function restoreIntegrationLocation() {
  const query = new URLSearchParams(location.search);
  if (query.get("library") === "knowledge") integrationSection = "knowledge";
  else if (["skills", "knowledge"].includes(query.get("integrations"))) integrationSection = query.get("integrations");
  else return;
  if (integrationSection !== "knowledge") return;
  const library = (query.get("knowledge-library") || "").slice(0, 80);
  const select = byId("knowledge-library");
  if (library && ![...select.options].some(option => option.value === library)) {
    const option = domainText("option", library); option.value = library; select.append(option);
  }
  select.value = library;
  byId("learn-library").value = library;
  knowledgeQuery = (query.get("knowledge-q") || "").slice(0, 200);
  byId("knowledge-query").value = knowledgeQuery;
  const page = Number(query.get("knowledge-page") || 1);
  knowledgeLocationPage = Number.isSafeInteger(page) && page > 0 && page <= 50001 ? page : 1;
  const sourcePage = Number(query.get("sources-page") || 1);
  sourceLocationPage = Number.isSafeInteger(sourcePage) && sourcePage > 0 && sourcePage <= 50001 ? sourcePage : 1;
}
function rememberIntegrationLocation(replace = false) {
  if (!authenticated || currentView !== "integrations") return;
  saveNavigationChoice("integration-section", integrationSection);
  const url = new URL(location.href);
  url.searchParams.delete("session"); url.searchParams.delete("message");
  for (const key of [...url.searchParams.keys()])
    if (key === "library" || key.startsWith("files-") || key.startsWith("knowledge-") || key === "sources-page") url.searchParams.delete(key);
  url.searchParams.set("integrations", integrationSection);
  if (integrationSection === "knowledge") {
    const state = { "knowledge-library": byId("knowledge-library").value,
      "knowledge-q": knowledgeQuery, "knowledge-page": String(knowledgeLocationPage ?? Math.floor(knowledgeOffset / domainPageSizes.knowledge) + 1),
      "sources-page": String(sourceLocationPage ?? Math.floor(sourceOffset / domainPageSizes.sources) + 1) };
    for (const [key, value] of Object.entries(state)) if (value) url.searchParams.set(key, value);
  }
  const next = url.pathname + url.search;
  if (next !== location.pathname + location.search) history[replace ? "replaceState" : "pushState"](history.state, "", next);
}
function renderIntegrationSection() {
  byId("skills-panel").hidden = integrationSection !== "skills";
  byId("knowledge-panel").hidden = integrationSection !== "knowledge";
  for (const button of byId("integration-sections").querySelectorAll("[data-integration]"))
    button.setAttribute("aria-pressed", String(button.dataset.integration === integrationSection));
}
function loadIntegrationSection() {
  renderIntegrationSection();
  if (integrationSection === "knowledge") loadKnowledge(); else loadSkills();
}
function stopIntegrationReads() {
  knowledgeRead?.abort(); sourceRead?.abort();
  knowledgeLoad += 1; sourcesLoad += 1; skillsLoad += 1;
  clearTimeout(skillsSearchTimer);
  for (const id of ["knowledge-items", "source-items", "skill-items"]) cancelLoading(byId(id));
}
function renderFileToolbar() {
  for (const button of byId("file-view-modes").children) button.setAttribute("aria-pressed", String(button.dataset.fileView === fileView));
  const options = byId("file-options-toggle");
  const sortLabel = byId("artifact-sort").selectedOptions[0].textContent;
  options.title = `Filters and sort · ${sortLabel}`;
  options.setAttribute("aria-description", sortLabel);
  const crumbs = byId("file-breadcrumbs");
  const outputs = librarySection === "outputs";
  byId("file-add").hidden = outputs;
  byId("artifact-query").placeholder = outputs ? "Search generated files…" : "Search uploads…";
  byId("artifact-filter").querySelector(".file-search-label span").textContent = outputs ? "Find generated files" : "Find uploads";
  byId("file-search-submit").setAttribute("aria-label", outputs ? "Search generated files" : "Search uploads");
  byId("file-search-submit").title = outputs ? "Search generated files" : "Search uploads";
  const root = domainButton("Library", () => {
    fileKind = "all"; fileStatus = "saved"; libraryOffset = 0;
    byId("artifact-kind").value = "all"; byId("artifact-status").value = "saved";
    byId("artifact-query").value = "";
    rememberLibraryLocation(); loadLibrary();
  });
  const current = domainText("span", outputs ? "Generated" : "Uploads");
  current.title = current.textContent;
  current.setAttribute("aria-current", "location");
  crumbs.replaceChildren(root, libraryIcon("next"), current);
  const available = latest?.library_images === true;
  const gallery = byId("file-view-modes").querySelector('[data-file-view="gallery"]');
  gallery.disabled = Boolean(latest) && !available;
  gallery.title = gallery.disabled ? "Restart Web UI after the active reply to enable Gallery" : "Gallery view";
  for (const option of byId("artifact-sort").options) option.disabled =
    Boolean(latest) && !available && !["newest", "oldest", "name"].includes(option.value);
}
function refreshLibraryCapabilities() {
  if (!latest || libraryImageCapability === (latest.library_images === true) &&
      librarySourceCapability === (latest.library_artifact_sources === true)) return;
  const previous = libraryImageCapability;
  libraryImageCapability = latest.library_images === true;
  librarySourceCapability = latest.library_artifact_sources === true;
  if (currentView === "library" &&
      (previous !== undefined || !libraryImageCapability || !librarySourceCapability)) loadLibrary();
}
function renderFileItems(data) {
  filePage = data;
  const grid = byId("library-items");
  grid.classList.add("file-browser");
  grid.dataset.view = fileView;
  const signature = JSON.stringify([fileView, byId("artifact-sort").value,
    latest ? latest.library_images === true : null,
    data.items.map(item => [item.id, item.revision])]);
  if (grid.dataset.filesRendered === signature && grid.querySelector(".file-item")) return;
  grid.dataset.filesRendered = signature;
  const nodes = [];
  const grouped = fileView === "gallery" && ["newest", "oldest"].includes(byId("artifact-sort").value);
  if (fileView === "list") {
    const header = domainText("div", "", "file-list-header");
    for (const [label, sort] of [["Name", "name"], ["Type", "type"], ["Size", "largest"], ["Added", "newest"]]) {
      const button = domainButton(label, () => {
        const current = byId("artifact-sort").value;
        byId("artifact-sort").value = current === sort ? ({ name: "name_desc", newest: "oldest", largest: "smallest" }[sort] || sort) : sort;
        libraryOffset = 0; rememberLibraryLocation(); loadLibrary();
      });
      if (byId("artifact-sort").value === sort) button.append(document.createTextNode(" ↓"));
      header.append(button);
    }
    nodes.push(header);
  }
  let previousMonth = "";
  for (const item of data.items) {
    if (grouped) {
      const month = fileDate(item.created, { month: "long", year: "numeric" });
      if (month !== previousMonth) {
        const heading = domainText("h2", month, "gallery-month");
        heading.append(domainText("span", librarySection === "outputs" ? "Saved to Generated" : "Added to Uploads", "muted"));
        nodes.push(heading); previousMonth = month;
      }
    }
    const card = domainText("article", "", "library-card file-item");
    card.dataset.fileId = item.id;
    const open = domainButton("", () => {
      imageSequence = data.items.filter(isLibraryImage);
      imageSequenceOffset = libraryOffset;
      imageSequenceTotal = fileView === "gallery" ? data.total : imageSequence.length;
      previewOrigin = open;
      previewOriginId = item.id;
      previewScroll = byId("library-view").scrollTop;
      openArtifact(item.id).catch((error) => domainError(error));
    }, "file-open");
    open.setAttribute("aria-label", `Open ${item.name}`);
    open.title = item.name;
    const art = domainText("span", "", "file-artwork");
    art.append(canPreviewImage(item) ? artifactImage(item) : fileIcon(item));
    const name = domainText("span", item.name, "file-name");
    const [type, label] = fileType(item);
    open.setAttribute("aria-description", `${label}, ${fileSize(item.size)}, added ${fileDate(item.created)}`);
    card.dataset.fileType = type;
    const detail = domainText("span", "", "file-name-group");
    detail.append(name, domainText("span", `${label} · ${fileSize(item.size)}`, "file-secondary"));
    const date = domainText("time", fileDate(item.created), "file-added");
    date.dateTime = new Date(item.created * 1000).toISOString();
    date.title = `Added ${new Date(item.created * 1000).toLocaleString()}`;
    open.append(art, detail, domainText("span", label, "file-type"),
      domainText("span", fileSize(item.size), "file-size"), date);
    card.append(open);
    nodes.push(card);
  }
  grid.replaceChildren(...nodes);
}

async function loadLibrary() {
  if (latest && latest.library_images !== true) {
    if (fileView === "gallery") fileView = "grid";
    if (!["newest", "oldest", "name"].includes(byId("artifact-sort").value))
      byId("artifact-sort").value = "newest";
  }
  fileRead?.abort();
  fileRead = new AbortController();
  const signal = fileRead.signal;
  const pageSize = syncDomainPageSize("library");
  for (const button of document.querySelectorAll("#library-sections button")) {
    button.setAttribute("aria-pressed", String(button.dataset.section === librarySection));
  }
  const load = ++libraryLoad;
  const section = librarySection;
  const offset = libraryOffset;
  byId("library-view").dataset.section = section;
  byId("library-items").classList.add("file-browser");
  byId("library-items").dataset.view = fileView;
  renderFileToolbar();
  byId("artifact-tools").hidden = false;
  const grid = byId("library-items");
  const key = JSON.stringify([section, fileKind, fileStatus, offset,
    byId("artifact-query").value, byId("artifact-sort").value, fileView]);
  if (grid.dataset.contentKey !== key) byId("library-pages").hidden = true;
  const finish = beginLoading(grid, { kind: fileView === "list" ? "rows" : "cards", count: Math.min(6, pageSize),
    preserve: grid.dataset.contentKey === key, artwork: true, label: "Loading library…" });
  byId("library-status").textContent = "";
  try {
    const data = await readFilePage(offset, signal);
    if (load !== libraryLoad) return;
    if (!data.items.length && offset > 0) {
      libraryOffset = Math.max(0, offset - pageSize);
      return loadLibrary();
    }
    renderFileItems(data);
    let emptyMessage = data.items.length ? "" :
      byId("artifact-query").value ? "No files match this search and filters." : fileStatus === "archived" ?
        "No archived files match this type." : librarySection === "outputs" ?
          "No generated files match this type. Research reports and generated images created in the CLI appear here." : "No uploads match this type. Add a file to get started.";
    if (fileView === "gallery") emptyMessage = data.items.length ?
      "" : "No supported images match this search and filters.";
    if (section === "outputs" && emptyMessage) {
      const empty = domainText("p", emptyMessage, "domain-status library-empty");
      empty.setAttribute("role", "status");
      grid.replaceChildren(empty);
    } else byId("library-status").textContent = emptyMessage;
    updateDomainPager("library", offset, data);
    grid.dataset.contentKey = key;
    rememberLibraryLocation(true);
  } catch (error) { if (load === libraryLoad) domainError(error); }
  finally { finish(); }
}

async function loadKnowledge() {
  if (!authenticated || currentView !== "integrations" || integrationSection !== "knowledge") return;
  if (!byId("knowledge-items").getClientRects().length) { requestAnimationFrame(loadKnowledge); return; }
  knowledgeRead?.abort(); knowledgeRead = new AbortController();
  const signal = knowledgeRead.signal;
  const pageSize = syncDomainPageSize("knowledge");
  if (knowledgeLocationPage !== null) {
    knowledgeOffset = Math.min(knowledgeLocationPage - 1, Math.floor(1000000 / pageSize)) * pageSize;
    knowledgeLocationPage = null;
  }
  const load = ++knowledgeLoad, offset = knowledgeOffset;
  const grid = byId("knowledge-items");
  const key = JSON.stringify([byId("knowledge-library").value, knowledgeQuery, offset]);
  if (grid.dataset.contentKey !== key) byId("knowledge-pages").hidden = true;
  if (byId("source-items").dataset.library !== byId("knowledge-library").value)
    byId("knowledge-sources").hidden = true;
  const finish = beginLoading(grid, { kind: "cards", count: Math.min(6, pageSize),
    preserve: grid.dataset.contentKey === key, label: "Loading Knowledge…" });
  byId("knowledge-status").textContent = "";
  try {
    if (knowledgeQuery) {
      const data = await gridPage("/api/v1/library/knowledge", {
        library: byId("knowledge-library").value, query: knowledgeQuery, offset }, pageSize, { signal });
      if (load !== knowledgeLoad) return;
      if (!data.hits.length && offset > 0) {
        knowledgeOffset = Math.max(0, offset - pageSize);
        return loadKnowledge();
      }
      byId("knowledge-items").replaceChildren(...data.hits.map((hit) => {
        const card = domainText("article", "", "library-card knowledge-hit");
        card.append(domainText("h3", hit.source), domainText("pre", hit.text));
        return card;
      }));
      updateDomainPager("knowledge", offset, data);
      byId("knowledge-status").textContent = data.hits.length ? "" : "No indexed text matches.";
      grid.dataset.contentKey = key;
      rememberIntegrationLocation(true);
      finish();
      await loadKnowledgeSources();
      return;
    }
    const data = await gridPage("/api/v1/library/knowledge", { offset }, pageSize, { signal });
    if (load !== knowledgeLoad) return;
    if (!data.items.length && offset > 0) {
      knowledgeOffset = Math.max(0, offset - pageSize);
      return loadKnowledge();
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
          rememberIntegrationLocation();
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
    byId("knowledge-items").replaceChildren(...nodes);
    updateDomainPager("knowledge", offset, data);
    byId("knowledge-status").textContent = data.items.length ?
      data.limited ? "Inventory limited to 1,000." : "" :
      "No knowledge yet. Learn a URL or text file to create your first library.";
    grid.dataset.contentKey = key;
    rememberIntegrationLocation(true);
    finish();
    await loadKnowledgeSources();
  } catch (error) { if (load === knowledgeLoad) domainError(error, "knowledge-status"); }
  finally { finish(); }
}

// Presentation and gestures remain local to the existing native file dialog.
const artifactViewer = (() => {
  const preview = byId("artifact-preview"), panel = byId("artifact-information");
  const menu = byId("artifact-menu"), more = byId("artifact-more");
  const phone = matchMedia("(max-width: 850px)");
  let item = null, draftTags = [], editingTags = false, allTags = false;
  let scale = 1, panX = 0, panY = 0, gesture = null, pinch = null, lastTap = null;
  const pointers = new Map();
  const notice = text => { byId("preview-status").textContent = text; };
  function closeMenu(focus = false) {
    if (typeof menu.hidePopover === "function") {
      if (menu.matches(":popover-open")) menu.hidePopover();
    } else menu.hidden = true;
    more.setAttribute("aria-expanded", "false");
    if (focus && artifactDialog.open) more.focus();
  }
  function setDetails(state, focus = false) {
    if (state !== "closed") artifactDialog.classList.remove("image-expanded");
    artifactDialog.dataset.details = state;
    panel.inert = state === "closed";
    byId("image-details").setAttribute("aria-expanded", String(state !== "closed"));
    byId("image-details").setAttribute("aria-label", state === "closed" ? "Show file details" : "Hide file details");
    byId("preview-sheet-handle").setAttribute("aria-label", state === "full" ? "Partially expand file details" : "Expand file details");
    byId("preview-sheet-scrim").hidden = !phone.matches || state === "closed";
    artifactDialog.querySelector(".preview-main").inert = phone.matches && state !== "closed";
    if (focus && state === "closed") byId("image-details").focus({ preventScroll: true });
    else if (focus) requestAnimationFrame(() => {
      if (artifactDialog.open && artifactDialog.dataset.details !== "closed")
        byId("preview-sheet-close").focus({ preventScroll: true });
    });
  }
  function transform() {
    const image = preview.querySelector("img");
    if (!image) return;
    const width = preview.clientWidth, height = preview.clientHeight;
    const ratio = image.naturalWidth / image.naturalHeight;
    if (ratio > 0) {
      const fitWidth = Math.min(width, height * ratio), fitHeight = fitWidth / ratio;
      const maxX = Math.max(0, (fitWidth * scale - width) / 2);
      const maxY = Math.max(0, (fitHeight * scale - height) / 2);
      panX = Math.max(-maxX, Math.min(maxX, panX));
      panY = Math.max(-maxY, Math.min(maxY, panY));
    }
    image.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
    preview.dataset.zoom = String(scale);
    byId("image-zoom-value").textContent = `${Math.round(scale * 100)}%`;
    byId("image-zoom-in").disabled = scale >= 8;
    byId("image-zoom-out").disabled = scale <= 1;
  }
  function zoom(value, clientX, clientY) {
    const next = Math.max(1, Math.min(8, value));
    const rect = preview.getBoundingClientRect();
    const x = clientX === undefined ? 0 : clientX - rect.left - rect.width / 2;
    const y = clientY === undefined ? 0 : clientY - rect.top - rect.height / 2;
    panX = x - (x - panX) * next / scale;
    panY = y - (y - panY) * next / scale;
    scale = next;
    if (scale === 1) panX = panY = 0;
    transform();
  }
  function resetZoom() {
    scale = 1; panX = panY = 0; pointers.clear(); gesture = pinch = lastTap = null;
    preview.dataset.zoom = "1";
    byId("image-zoom-value").textContent = "100%";
    transform();
  }
  function review(operation, value) {
    if (!item) return;
    const target = item;
    closeMenu();
    if (operation === "delete" && !target.archived) {
      notice("Archive this file before permanently deleting it.");
      more.focus();
      return;
    }
    artifactDialog.close();
    prepareChange({ operation, target: target.id, revision: target.revision,
      ...(value !== undefined ? { value } : {}) }).catch(error => domainError(error));
  }
  function renderMenu() {
    menu.replaceChildren();
    for (const [operation, label, icon] of [
      [item.archived ? "restore" : "archive", item.archived ? "Restore" : "Archive", "archive"],
      ["delete", "Delete", "trash"],
      ...(item.ai_tags?.length ? [["clear_ai_tags", "Clear AI tags", "close"]] : []),
    ]) {
      const button = domainButton("", () => review(operation), "message-action" + (operation === "delete" ? " danger" : ""));
      button.setAttribute("role", "menuitem");
      button.append(libraryIcon(icon), domainText("span", label));
      if (operation === "delete" && !item.archived) button.title = "Archive this file before permanent deletion";
      menu.append(button);
    }
  }
  function renderTags() {
    byId("artifact-tag-new").setCustomValidity("");
    const combined = [...draftTags.map(tag => ({ tag, manual: true })),
      ...(item?.ai_tags || []).map(tag => ({ tag, manual: false }))];
    byId("artifact-tag-count").textContent = `(${combined.length})`;
    byId("artifact-tags-input").value = draftTags.join(", ");
    byId("artifact-tag-editor").hidden = !editingTags;
    byId("artifact-tags-edit").hidden = editingTags;
    const shown = editingTags || allTags ? combined : combined.slice(0, 8);
    byId("artifact-tag-list").replaceChildren(...shown.map(({ tag, manual }) => {
      const chip = domainText("span", "", `preview-tag${manual ? "" : " tag-generated"}`);
      chip.title = manual ? "Manual tag" : "AI tag";
      chip.append(domainText("span", tag));
      if (editingTags && manual) {
        const remove = domainButton("", () => { draftTags = draftTags.filter(value => value !== tag); renderTags(); byId("artifact-tag-new").focus(); }, "icon-button");
        remove.setAttribute("aria-label", `Remove tag ${tag}`);
        remove.append(libraryIcon("close")); chip.append(remove);
      }
      return chip;
    }));
    if (!combined.length) byId("artifact-tag-list").append(domainText("p", "No tags yet.", "muted"));
    const moreTags = byId("artifact-tags-more");
    moreTags.hidden = editingTags || combined.length <= 8;
    moreTags.textContent = allTags ? "Show less" : `Show all ${combined.length} tags`;
    moreTags.setAttribute("aria-expanded", String(allTags));
  }
  function addTag() {
    const input = byId("artifact-tag-new");
    const values = [...new Set([...draftTags, ...input.value.split(",").map(value => value.trim()).filter(Boolean)])];
    if (values.length > 20 || values.some(value => value.length > 40 || /[\x00-\x1f\x7f-\x9f]/.test(value))) {
      input.setCustomValidity("Use up to 20 printable tags of at most 40 characters."); input.reportValidity(); return false;
    }
    input.setCustomValidity(""); draftTags = values; input.value = ""; renderTags(); return true;
  }
  function editSource() {
    byId("artifact-source-form").hidden = false;
    byId("artifact-source-input").value = item.source_url || "";
    byId("artifact-source-input").focus();
  }
  function renderSource() {
    const source = byId("artifact-source");
    source.replaceChildren(); byId("artifact-source-form").hidden = true;
    let url;
    try {
      url = new URL(item.source_url);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) url = null;
    } catch { url = null; }
    if (url) {
      const link = domainText("a", item.source_url);
      link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
      link.setAttribute("aria-label", `Open source link ${item.source_url}`); source.append(link);
      source.append(domainButton("Copy link", async () => {
        notice(await ChatMarkdown.copyText(item.source_url, artifactDialog) ? "Source link copied." : "Select the source link to copy it.");
      }));
    }
    const edit = domainButton(url ? "Edit link" : "+ Add source link", editSource);
    edit.disabled = latest?.library_source_links !== true;
    if (edit.disabled) edit.title = "Restart the WebUI host to edit source links";
    source.append(edit);
  }
  function render(data) {
    item = data.item; editingTags = allTags = false; draftTags = [...item.tags];
    const image = canPreviewImage(item);
    artifactDialog.classList.toggle("is-image", image);
    byId("artifact-detail-title").textContent = item.name;
    byId("artifact-detail-title").title = item.name;
    const nodes = image ? [artifactImage(item, true)] : [domainText("pre", data.lines.join("\n"), "artifact-text")];
    if (data.truncated) nodes.push(domainText("p", "Preview truncated. Download for the complete file.", "muted"));
    preview.replaceChildren(...nodes);
    preview.querySelector("img")?.addEventListener("load", transform, { once: true });
    resetZoom();
    const rows = [["Filename", item.filename], ["Type", `${fileType(item)[1]} · ${item.mime}`], ["Size", `${fileSize(item.size)} (${item.size.toLocaleString()} bytes)`],
      ...(item.width && item.height ? [["Dimensions", `${item.width.toLocaleString()} × ${item.height.toLocaleString()} px`]] : []),
      ...(Number.isFinite(item.created) ? [["Added", new Date(item.created * 1000).toLocaleString()]] : []),
      ...(item.archived ? [["Status", "Archived"]] : [])];
    byId("artifact-metadata").replaceChildren(...rows.flatMap(([label, value]) => [domainText("dt", label), domainText("dd", value)]));
    renderSource(); renderTags(); renderMenu();
    byId("artifact-tags").hidden = false;
    byId("image-toolbar").hidden = false;
    for (const id of ["image-fit", "image-expand", "artifact-download"]) byId(id).hidden = !image;
    artifactDialog.querySelector(".preview-zoom-controls").hidden = !image;
    byId("artifact-download").href = artifactUrl(item);
    byId("artifact-download").download = item.filename;
    byId("artifact-actions").replaceChildren();
    if (!image) {
      const download = domainText("a", "Download", "download-link");
      download.href = artifactUrl(item); download.download = item.filename;
      byId("artifact-actions").append(download);
    }
    more.disabled = false; notice("");
  }
  function begin(image, opening) {
    item = null; closeMenu(); resetZoom(); notice("");
    if (document.activeElement === more) preview.focus({ preventScroll: true });
    more.disabled = true;
    artifactDialog.classList.toggle("is-image", Boolean(image));
    byId("artifact-metadata").replaceChildren(); byId("artifact-source").replaceChildren();
    byId("artifact-source-form").hidden = true;
    byId("artifact-tag-new").value = "";
    byId("artifact-tag-new").setCustomValidity("");
    byId("artifact-tag-count").textContent = "";
    byId("image-toolbar").hidden = true;
    if (opening) { artifactDialog.classList.remove("image-expanded"); setDetails(phone.matches ? "closed" : "partial"); }
  }
  for (const [id, icon] of [["artifact-close", "previous"], ["artifact-more", "more"], ["image-zoom-out", "minus"], ["image-zoom-in", "plus"], ["image-fit", "fit"], ["artifact-download", "download"], ["image-details", "info"], ["preview-sheet-close", "close"]]) byId(id).append(libraryIcon(icon));
  byId("image-details").append(domainText("span", "Details"));
  byId("image-zoom-in").onclick = () => zoom(scale * 1.5);
  byId("image-zoom-out").onclick = () => zoom(scale / 1.5);
  byId("image-fit").onclick = resetZoom;
  byId("image-details").onclick = () => setDetails(artifactDialog.dataset.details === "closed" ? "partial" : "closed", true);
  byId("preview-sheet-close").onclick = byId("preview-sheet-scrim").onclick = () => setDetails("closed", true);
  byId("preview-sheet-handle").onclick = event => { if (event.detail && sheetStart === undefined) return; setDetails(artifactDialog.dataset.details === "full" ? "partial" : "full"); };
  let sheetStart;
  byId("preview-sheet-handle").addEventListener("pointerdown", event => { sheetStart = event.clientY; event.currentTarget.setPointerCapture(event.pointerId); });
  byId("preview-sheet-handle").addEventListener("pointerup", event => {
    if (sheetStart === undefined || Math.abs(event.clientY - sheetStart) < 35) return;
    event.preventDefault(); setDetails(event.clientY > sheetStart ? "closed" : "full", true); sheetStart = undefined;
  });
  phone.addEventListener("change", () => { if (artifactDialog.open) setDetails(phone.matches ? "closed" : "partial"); });
  new ResizeObserver(transform).observe(preview);
  more.onclick = () => {
    if (more.getAttribute("aria-expanded") === "true") { closeMenu(true); return; }
    if (typeof menu.showPopover === "function") menu.showPopover(); else menu.hidden = false;
    more.setAttribute("aria-expanded", "true");
    const rect = more.getBoundingClientRect(), bounds = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(rect.right - bounds.width, innerWidth - bounds.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(rect.bottom + 6, innerHeight - bounds.height - 8))}px`;
    menu.querySelector("button")?.focus();
  };
  if (typeof menu.showPopover !== "function") { menu.removeAttribute("popover"); menu.hidden = true; }
  menu.addEventListener("toggle", () => { if (!menu.matches(":popover-open")) more.setAttribute("aria-expanded", "false"); });
  menu.addEventListener("keydown", event => {
    const items = [...menu.querySelectorAll("[role=menuitem]")], index = items.indexOf(document.activeElement);
    let next;
    if (event.key === "ArrowDown") next = (index + 1) % items.length;
    if (event.key === "ArrowUp") next = (index - 1 + items.length) % items.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = items.length - 1;
    if (next !== undefined) { event.preventDefault(); items[next]?.focus(); }
    if (event.key === "Escape") { event.preventDefault(); closeMenu(true); }
    if (event.key === "Tab") closeMenu();
    event.stopPropagation();
  });
  document.addEventListener("click", event => { if (!menu.contains(event.target) && !more.contains(event.target)) closeMenu(); });
  byId("artifact-tags-edit").onclick = () => { editingTags = true; renderTags(); byId("artifact-tag-new").focus(); };
  byId("artifact-tags-cancel").onclick = () => { editingTags = false; draftTags = [...item.tags]; renderTags(); byId("artifact-tags-edit").focus(); };
  byId("artifact-tags-more").onclick = () => { allTags = !allTags; renderTags(); };
  byId("artifact-tag-add").onclick = addTag;
  byId("artifact-tag-new").addEventListener("input", event => event.target.setCustomValidity(""));
  byId("artifact-tag-new").addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); addTag(); } });
  byId("artifact-source-cancel").onclick = () => { byId("artifact-source-form").hidden = true; byId("artifact-source").querySelector("button:last-child")?.focus(); };
  byId("artifact-source-form").addEventListener("submit", event => { event.preventDefault(); review("source_link", byId("artifact-source-input").value); });
  byId("artifact-tags").addEventListener("submit", event => { event.preventDefault(); if (editingTags && !addTag()) return; review("tags", byId("artifact-tags-input").value); });
  preview.addEventListener("pointerdown", event => {
    if (!preview.querySelector("img") || event.button > 0) return;
    event.preventDefault(); preview.focus({ preventScroll: true });
    preview.setPointerCapture(event.pointerId); pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 1) gesture = { x: event.clientX, y: event.clientY, panX, panY, scale, time: performance.now(), multiple: false };
    if (pointers.size === 2) {
      gesture.multiple = true; const [a, b] = [...pointers.values()];
      pinch = { distance: Math.hypot(a.x - b.x, a.y - b.y), x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, scale, panX, panY };
    }
  });
  preview.addEventListener("pointermove", event => {
    if (!pointers.has(event.pointerId)) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.size === 2 && pinch?.distance > 0) {
      const [a, b] = [...pointers.values()], rect = preview.getBoundingClientRect();
      scale = Math.max(1, Math.min(8, pinch.scale * Math.hypot(a.x - b.x, a.y - b.y) / pinch.distance));
      panX = (a.x + b.x) / 2 - rect.left - rect.width / 2 - (pinch.x - rect.left - rect.width / 2 - pinch.panX) * scale / pinch.scale;
      panY = (a.y + b.y) / 2 - rect.top - rect.height / 2 - (pinch.y - rect.top - rect.height / 2 - pinch.panY) * scale / pinch.scale;
      transform();
    } else if (pointers.size === 1 && gesture && scale > 1 && !gesture.multiple) {
      panX = gesture.panX + event.clientX - gesture.x; panY = gesture.panY + event.clientY - gesture.y; transform();
    }
  });
  function endPointer(event) {
    if (!pointers.has(event.pointerId)) return;
    pointers.delete(event.pointerId);
    if (pointers.size) return;
    if (gesture && event.type === "pointerup" && !gesture.multiple) {
      const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y, now = performance.now();
      if (gesture.scale === 1 && scale === 1 && Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5 && now - gesture.time < 800) {
        lastTap = null; nextImage(dx < 0 ? 1 : -1);
      } else if (Math.hypot(dx, dy) < 10) {
        if (lastTap && now - lastTap.time < 350 && Math.hypot(event.clientX - lastTap.x, event.clientY - lastTap.y) < 25) {
          zoom(scale > 1 ? 1 : 2.5, event.clientX, event.clientY); lastTap = null;
        } else lastTap = { time: now, x: event.clientX, y: event.clientY };
      }
    }
    gesture = pinch = null;
  }
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) preview.addEventListener(type, endPointer);
  preview.addEventListener("dblclick", event => event.preventDefault());
  preview.addEventListener("wheel", event => { if (!preview.querySelector("img") || !event.ctrlKey) return; event.preventDefault(); zoom(scale * Math.exp(-event.deltaY * .01), event.clientX, event.clientY); }, { passive: false });
  artifactDialog.addEventListener("cancel", event => {
    if (more.getAttribute("aria-expanded") === "true") { event.preventDefault(); closeMenu(true); }
    else if (phone.matches && artifactDialog.dataset.details !== "closed") { event.preventDefault(); setDetails("closed", true); }
  });
  artifactDialog.addEventListener("keydown", event => {
    if (event.key !== "Escape" || !phone.matches || artifactDialog.dataset.details === "closed") return;
    event.preventDefault(); event.stopPropagation(); setDetails("closed", true);
  });
  return { begin, render, reset: () => { closeMenu(); resetZoom(); item = null; draftTags = []; byId("artifact-source-input").value = ""; byId("artifact-tag-new").value = ""; byId("artifact-source-form").hidden = true; setDetails("closed"); },
    toggleExpanded: () => { const expanded = !artifactDialog.classList.contains("image-expanded"); setDetails(expanded ? "closed" : "partial"); artifactDialog.classList.toggle("image-expanded", expanded); return expanded; },
    key: event => {
      if (event.target.closest(".preview-information, #artifact-menu") || !preview.querySelector("img")) return false;
      if (["+", "=", "-", "0", "f", "F"].includes(event.key)) { event.preventDefault(); if (["0", "f", "F"].includes(event.key)) resetZoom(); else zoom(scale * (event.key === "-" ? 1 / 1.5 : 1.5)); return true; }
      if (scale > 1 && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) { event.preventDefault(); panX += event.key === "ArrowLeft" ? 60 : event.key === "ArrowRight" ? -60 : 0; panY += event.key === "ArrowUp" ? 60 : event.key === "ArrowDown" ? -60 : 0; transform(); return true; }
      return false;
    } };
})();

async function openArtifact(id) {
  byId("artifact-close").title = librarySection === "outputs" ? "Back to Generated" : "Back to Uploads";
  artifactRead?.abort(); artifactRead = new AbortController();
  const load = ++artifactLoad, opening = !artifactDialog.open;
  const known = imageSequence.find(item => item.id === id) || filePage?.items.find(item => item.id === id);
  for (const card of document.querySelectorAll(".file-item")) {
    card.classList.toggle("file-selected", card.dataset.fileId === id);
    const button = card.querySelector("button");
    if (card.dataset.fileId === id) button.setAttribute("aria-current", "true"); else button.removeAttribute("aria-current");
  }
  const preview = byId("artifact-preview"); selectedArtifact = null;
  byId("artifact-detail-title").textContent = known?.name || "Item details";
  byId("artifact-detail-title").title = known?.name || "";
  byId("artifact-actions").replaceChildren(); byId("artifact-tags").hidden = true;
  byId("artifact-tags-input").value = ""; byId("image-navigation").hidden = true;
  artifactViewer.begin(known && canPreviewImage(known), opening);
  const finish = beginLoading(preview, { kind: "detail", count: 1, preserve: false, label: "Loading item preview…" });
  if (opening) artifactDialog.showModal();
  try {
    const cached = artifactDetails.get(id);
    const data = cached && Date.now() - cached.time < 30000 && (!known || known.revision === cached.data.item.revision) ? cached.data :
      await domainRequest(`/api/v1/library/item?${new URLSearchParams({ id })}`, "GET", undefined, { signal: artifactRead.signal });
    if (load !== artifactLoad || !artifactDialog.open) return;
    artifactDetails.set(id, { time: cached?.data === data ? cached.time : Date.now(), data });
    while (artifactDetails.size > 24) artifactDetails.delete(artifactDetails.keys().next().value);
    selectedArtifact = data.item; artifactViewer.render(data); updateImageNavigation();
  } catch (error) {
    if (load !== artifactLoad || !artifactDialog.open) return;
    if (error.name !== "AbortError") preview.textContent = error.message || "Could not load this item.";
    if (error.status === 401) showLocalAccess();
  } finally { finish(); }
}
byId("artifact-close").addEventListener("click", () => artifactDialog.close());
artifactDialog.addEventListener("close", () => {
  if (artifactDialog.open) return;
  artifactLoad += 1; selectedArtifact = null; artifactRead?.abort(); artifactViewer.reset();
  byId("image-navigation").hidden = true;
  artifactDialog.classList.remove("image-expanded");
  byId("image-expand").setAttribute("aria-pressed", "false");
  byId("image-expand").setAttribute("aria-label", "Expand image preview");
  cancelLoading(byId("artifact-preview")); byId("artifact-preview").replaceChildren();
  for (const card of document.querySelectorAll(".file-selected")) { card.classList.remove("file-selected"); card.querySelector("button")?.removeAttribute("aria-current"); }
  byId("library-view").scrollTop = previewScroll;
  if (authenticated && currentView === "library") {
    if (!previewOrigin?.isConnected) previewOrigin = [...document.querySelectorAll(".file-item")].find(card => card.dataset.fileId === previewOriginId)?.querySelector("button");
    (previewOrigin || byId("library-refresh")).focus({ preventScroll: true });
  }
});

function updateImageNavigation() {
  const index = imageSequence.findIndex(item => item.id === selectedArtifact?.id);
  const image = selectedArtifact && isLibraryImage(selectedArtifact);
  byId("image-navigation").hidden = !image;
  const paged = fileView === "gallery";
  byId("image-position").textContent = index >= 0 ?
    `${(paged ? imageSequenceOffset : 0) + index + 1} / ${imageSequenceTotal}` : image ? "Image preview" : librarySection === "outputs" ? "Generated" : "Uploads";
  byId("image-previous").disabled = previewNavigation || index < 0 ||
    index === 0 && (!paged || imageSequenceOffset === 0);
  byId("image-next").disabled = previewNavigation || index < 0 ||
    index === imageSequence.length - 1 && (!paged || imageSequenceOffset + imageSequence.length >= imageSequenceTotal);
}
async function nextImage(direction) {
  if (previewNavigation || !selectedArtifact) return;
  const index = imageSequence.findIndex(item => item.id === selectedArtifact.id);
  if (index < 0) return;
  // Loading disables navigation buttons. Keep keyboard focus on the stable
  // stage before that happens so the next arrow key still reaches the dialog.
  byId("artifact-preview").focus({ preventScroll: true });
  let target = imageSequence[index + direction];
  previewNavigation = true;
  updateImageNavigation();
  const epoch = authEpoch, selected = selectedArtifact.id;
  try {
    if (!target && fileView === "gallery") {
      const offset = imageSequenceOffset + direction * FILE_PAGE_SIZE;
      if (offset < 0 || offset >= imageSequenceTotal) return;
      const data = await readFilePage(offset);
      if (!authenticated || epoch !== authEpoch || !artifactDialog.open || selectedArtifact?.id !== selected) return;
      imageSequence = data.items;
      imageSequenceOffset = offset;
      imageSequenceTotal = data.total;
      target = direction > 0 ? imageSequence[0] : imageSequence.at(-1);
    }
    if (target) await openArtifact(target.id);
  } catch (error) {
    if (epoch === authEpoch && artifactDialog.open) domainError(error, "image-position");
  } finally { previewNavigation = false; updateImageNavigation(); }
}
for (const direction of ["previous", "next"]) {
  byId(`image-${direction}`).append(libraryIcon(direction));
  byId(`image-${direction}`).addEventListener("click", () => nextImage(direction === "next" ? 1 : -1));
}
byId("image-expand").append(libraryIcon("expand"));
byId("image-expand").addEventListener("click", () => {
  const expanded = artifactViewer.toggleExpanded();
  byId("image-expand").setAttribute("aria-pressed", String(expanded));
  byId("image-expand").setAttribute("aria-label", expanded ? "Reduce image preview" : "Expand image preview");
});
artifactDialog.addEventListener("keydown", event => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) || event.altKey || event.ctrlKey || event.metaKey || byId("image-navigation").hidden) return;
  if (artifactViewer.key(event) || event.target.closest(".preview-information, #artifact-menu")) return;
  if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
    const direction = event.key === "ArrowRight" ? "next" : "previous";
    if (!byId(`image-${direction}`).disabled) { event.preventDefault(); nextImage(direction === "next" ? 1 : -1); }
  }
});

async function loadKnowledgeSources() {
  sourceRead?.abort(); sourceRead = new AbortController();
  const pageSize = syncDomainPageSize("sources");
  if (sourceLocationPage !== null) {
    sourceOffset = Math.min(sourceLocationPage - 1, Math.floor(1000000 / pageSize)) * pageSize;
    sourceLocationPage = null;
  }
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
    const data = await gridPage("/api/v1/library/sources", { library, offset }, pageSize, { signal: sourceRead.signal });
    if (load !== sourcesLoad || currentView !== "integrations" || integrationSection !== "knowledge" || library !== byId("knowledge-library").value) return;
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
    rememberIntegrationLocation(true);
  } catch (error) {
    if (load === sourcesLoad) {
      if (!grid.querySelector(".library-card")) byId("knowledge-sources").hidden = true;
      throw error;
    }
  }
  finally { finish(); }
}
byId("sources-next").addEventListener("click", () => { sourceOffset += domainPageSizes.sources; rememberIntegrationLocation(); loadKnowledgeSources().catch((error) => domainError(error)); });
byId("sources-previous").addEventListener("click", () => { sourceOffset = Math.max(0, sourceOffset - domainPageSizes.sources); rememberIntegrationLocation(); loadKnowledgeSources().catch((error) => domainError(error)); });
byId("knowledge-library").addEventListener("change", () => {
  byId("learn-library").value = byId("knowledge-library").value;
  sourceOffset = 0;
  knowledgeQuery = "";
  byId("knowledge-query").value = "";
  knowledgeOffset = 0;
  rememberIntegrationLocation(); loadKnowledge();
});
byId("knowledge-search").addEventListener("submit", (event) => {
  event.preventDefault();
  const library = byId("knowledge-library").value;
  const query = byId("knowledge-query").value.trim();
  if (query && !library) { byId("knowledge-status").textContent = "Choose a library first."; return; }
  knowledgeQuery = query;
  knowledgeOffset = 0;
  rememberIntegrationLocation(); loadKnowledge();
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
async function prepareChange(draft, { current = () => true, beforeOpen = () => {} } = {}) {
  const result = await domainRequest("/api/v1/library/review", "POST", { draft });
  if (!current()) {
    domainRequest("/api/v1/library/discard", "POST", { review_id: result.review_id }).catch(() => {});
    return;
  }
  managementReview = { ...result, request_id: requestId() };
  byId("domain-review-title").textContent = draft.operation === "delete" ? "Delete file permanently?" : "Review change";
  byId("domain-review-confirm").textContent = draft.operation === "delete" ? "Delete permanently" : "Confirm";
  byId("domain-review-confirm").classList.toggle("danger", draft.operation === "delete");
  byId("domain-review-summary").textContent = result.summary;
  byId("domain-review-status").textContent = "Changes begin only after confirmation. Accepted work continues if you leave this page.";
  byId("domain-review-confirm").disabled = false;
  beforeOpen();
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
      const target = activeDomainStatus();
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
  const generation = importGeneration;
  const current = () => importDialog.open && generation === importGeneration;
  const upload_id = await uploadForReview(byId("artifact-file").files[0]);
  if (current()) await prepareChange({ operation: "import", upload_id }, {
    current, beforeOpen: () => importDialog.close(),
  });
}, "artifact-import-status");
bindUploadForm("knowledge-learn", async () => {
  const library = byId("learn-library").value;
  const source = byId("learn-url").value.trim();
  const file = byId("learn-file").files[0];
  if (source && file) throw new Error("Choose a URL or a text file, then review it separately.");
  if (file) {
    const upload_id = await uploadForReview(file, 2 * 1024 * 1024);
    await prepareChange({ operation: "knowledge-upload", upload_id, library });
  } else await prepareChange({ operation: "knowledge-url", library, source });
}, "knowledge-status");
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
    const changed = operationSignature !== null && signature !== operationSignature;
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
      filePages.clear(); artifactDetails.clear();
      if (currentView === "library") loadLibrary();
      if (currentView === "integrations") loadIntegrationSection();
    }
  } catch (error) { domainError(error); }
  finally { finish(); operationPollBusy = false; }
}

byId("nav-library").addEventListener("click", () => showView("library"));
byId("nav-integrations").addEventListener("click", () => showView("integrations"));
byId("library-refresh").addEventListener("click", () => { filePages.clear(); artifactDetails.clear(); loadLibrary(); loadTabCounts(); });
for (const button of byId("file-view-modes").children) {
  button.append(libraryIcon(button.dataset.fileView));
  button.addEventListener("click", () => {
    fileView = button.dataset.fileView;
    if (fileView === "gallery") libraryOffset = 0;
    rememberLibraryLocation(); loadLibrary();
  });
}
byId("file-search-submit").append(libraryIcon("search"));
byId("file-add").append(libraryIcon("plus"));
byId("file-add").addEventListener("click", () => {
  importGeneration += 1;
  byId("artifact-import-status").textContent = "";
  importDialog.showModal();
  byId("artifact-file").focus();
});
byId("artifact-import-close").append(libraryIcon("close"));
byId("artifact-import-close").addEventListener("click", () => importDialog.close());
byId("file-options-toggle").append(libraryIcon("options"));
byId("file-options-toggle").addEventListener("click", () => {
  const open = byId("artifact-filter").classList.toggle("options-open");
  byId("file-options-toggle").setAttribute("aria-expanded", String(open));
});
byId("artifact-filter").addEventListener("keydown", (event) => {
  if (event.key !== "Escape" || !byId("file-options-toggle").getClientRects().length ||
      !byId("artifact-filter").classList.contains("options-open")) return;
  event.preventDefault();
  byId("artifact-filter").classList.remove("options-open");
  byId("file-options-toggle").setAttribute("aria-expanded", "false");
  byId("file-options-toggle").focus();
});
byId("skills-refresh").addEventListener("click", () => { loadIntegrationSection(); loadTabCounts(); });
for (const button of byId("integration-sections").querySelectorAll("[data-integration]")) {
  button.addEventListener("click", () => {
    if (integrationSection === button.dataset.integration) return;
    stopIntegrationReads();
    integrationSection = button.dataset.integration;
    renderIntegrationSection(); rememberIntegrationLocation(); loadIntegrationSection();
  });
}
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
    if (librarySection === button.dataset.section) return;
    artifactLocations.set(librarySection, { kind: fileKind, status: fileStatus, view: fileView,
      query: byId("artifact-query").value, sort: byId("artifact-sort").value, offset: libraryOffset });
    if (librarySection !== button.dataset.section) byId("artifact-file").value = "";
    librarySection = button.dataset.section;
    saveNavigationChoice("library-section", librarySection);
    const saved = artifactLocations.get(librarySection);
    const prefix = librarySection === "outputs" ? "output" : "file";
    fileKind = normalizeFileKind(saved?.kind || readNavigationChoice(`${prefix}-kind`,
      ["all", "document", "research", "media"], "all"));
    fileStatus = saved?.status || readNavigationChoice(`${prefix}-status`, ["saved", "archived"], "saved");
    fileView = saved?.view || fileView;
    configureArtifactKinds();
    byId("artifact-kind").value = fileKind; byId("artifact-status").value = fileStatus;
    byId("artifact-query").value = saved?.query || "";
    byId("artifact-sort").value = saved?.sort || "newest";
    libraryOffset = saved?.offset || 0;
    for (const sibling of button.parentElement.children) sibling.setAttribute("aria-pressed", String(sibling === button));
    rememberLibraryLocation();
    loadLibrary();
  });
}
byId("artifact-filter").addEventListener("submit", (event) => { event.preventDefault(); libraryOffset = 0; rememberLibraryLocation(); loadLibrary(); });
byId("artifact-sort").addEventListener("change", () => { libraryOffset = 0; rememberLibraryLocation(); loadLibrary(); });
for (const id of ["artifact-kind", "artifact-status"]) {
  byId(id).addEventListener("change", () => {
    fileKind = byId("artifact-kind").value;
    fileStatus = byId("artifact-status").value;
    libraryOffset = 0;
    rememberLibraryLocation();
    loadLibrary();
  });
}
byId("library-previous").addEventListener("click", () => { libraryOffset = Math.max(0, libraryOffset - domainPageSizes.library); rememberLibraryLocation(); loadLibrary(); });
byId("library-next").addEventListener("click", () => { libraryOffset += domainPageSizes.library; rememberLibraryLocation(); loadLibrary(); });
byId("knowledge-previous").addEventListener("click", () => { knowledgeOffset = Math.max(0, knowledgeOffset - domainPageSizes.knowledge); rememberIntegrationLocation(); loadKnowledge(); });
byId("knowledge-next").addEventListener("click", () => { knowledgeOffset += domainPageSizes.knowledge; rememberIntegrationLocation(); loadKnowledge(); });
for (const prefix of Object.keys(domainGrids)) {
  byId(`${prefix}-numbers`).addEventListener("click", (event) => {
    const button = event.target.closest("button[data-page]");
    if (!button || button.hasAttribute("aria-current")) return;
    const offset = (Number(button.dataset.page) - 1) * domainPageSizes[prefix];
    if (prefix === "library") { libraryOffset = offset; rememberLibraryLocation(); loadLibrary(); }
    else if (prefix === "knowledge") { knowledgeOffset = offset; rememberIntegrationLocation(); loadKnowledge(); }
    else if (prefix === "skills") { skillsOffset = offset; loadSkills(); }
    else { sourceOffset = offset; rememberIntegrationLocation(); loadKnowledgeSources().catch((error) => domainError(error)); }
  });
}
compactDomainPages.addEventListener("change", () => {
  for (const prefix of Object.keys(domainGrids)) {
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
    } else if (currentView === "integrations") {
      const prefix = integrationSection;
      if (measureDomainPageSize(prefix) !== domainPageSizes[prefix]) loadIntegrationSection();
      else if (integrationSection === "knowledge" && byId("source-items").getClientRects().length &&
          measureDomainPageSize("sources") !== domainPageSizes.sources)
        loadKnowledgeSources().catch((error) => domainError(error));
    }
  }, 150);
});
for (const id of Object.values(domainGrids)) domainGridObserver.observe(byId(id));
document.addEventListener("klaude-view", (event) => {
  if (["library", "integrations"].includes(event.detail)) loadTabCounts();
  if (event.detail === "library") {
    if (new URLSearchParams(location.search).get("library") === "knowledge") { showView("integrations"); return; }
    restoreLibraryLocation(); rememberLibraryLocation(true); loadLibrary();
  } else {
    fileRead?.abort();
    libraryLoad += 1; cancelLoading(byId("library-items"));
  }
  if (event.detail === "integrations") {
    restoreIntegrationLocation(); renderIntegrationSection(); rememberIntegrationLocation(true); loadIntegrationSection();
  } else stopIntegrationReads();
  if (authenticated && !["library", "integrations"].includes(event.detail)) {
    const url = new URL(location.href);
    for (const key of [...url.searchParams.keys()])
      if (["library", "integrations", "sources-page"].includes(key) || key.startsWith("files-") || key.startsWith("knowledge-")) url.searchParams.delete(key);
    history.replaceState(history.state, "", url.pathname + url.search + url.hash);
  }
  if (["library", "integrations", "activity"].includes(event.detail)) loadOperations();
});
document.addEventListener("klaude-auth-reset", () => {
  stopIntegrationReads();
  fileRead?.abort(); artifactRead?.abort(); filePages.clear(); artifactDetails.clear(); filePage = null;
  libraryImageCapability = undefined;
  librarySourceCapability = undefined;
  artifactLocations.clear();
  imageSequence = []; imageSequenceTotal = 0; previewOrigin = null; previewOriginId = "";
  clearTimeout(gridResizeTimer);
  tabCountsLoad += 1;
  legacyTabCounts = false;
  renderTabCounts();
  libraryLoad += 1;
  skillsLoad += 1;
  sourcesLoad += 1;
  artifactLoad += 1;
  libraryOffset = knowledgeOffset = sourceOffset = skillsOffset = 0;
  knowledgeLocationPage = sourceLocationPage = null;
  knowledgeQuery = "";
  clearTimeout(skillsSearchTimer);
  legacyPageRoutes.clear();
  for (const prefix of Object.keys(domainGrids)) {
    const numbers = byId(`${prefix}-numbers`);
    numbers.replaceChildren();
    delete numbers.dataset.current;
    delete numbers.dataset.last;
    byId(`${prefix}-pages`).hidden = true;
  }
  installedSkills = [];
  selectedArtifact = null;
  managementReview = null;
  operationSignature = null;
  reviewDialog.close();
  artifactDialog.close();
  importDialog.close();
  for (const id of ["library-items", "knowledge-items", "skill-items", "source-items", "artifact-preview", "artifact-actions", "domain-operations"]) byId(id).replaceChildren();
  for (const id of ["artifact-metadata", "artifact-source", "artifact-tag-list", "artifact-menu"]) byId(id).replaceChildren();
  byId("artifact-tag-count").textContent = "";
  byId("artifact-tags-input").value = "";
  byId("artifact-source-input").value = "";
  byId("artifact-download").removeAttribute("href");
  byId("artifact-download").removeAttribute("download");
  byId("artifact-detail-title").removeAttribute("title");
  byId("image-position").textContent = "";
  byId("preview-status").textContent = "";
  for (const id of ["library-items", "knowledge-items", "skill-items", "source-items"]) delete byId(id).dataset.contentKey;
  delete byId("library-items").dataset.filesRendered;
  delete byId("source-items").dataset.library;
  for (const id of ["artifact-import", "knowledge-learn", "skill-import", "artifact-tags", "artifact-filter", "skills-filter"]) byId(id).reset();
  byId("artifact-kind").value = fileKind;
  byId("artifact-status").value = fileStatus;
  byId("artifact-filter").classList.remove("options-open");
  byId("file-options-toggle").setAttribute("aria-expanded", "false");
  byId("artifact-import-status").textContent = "";
  byId("knowledge-query").value = "";
  byId("knowledge-library").replaceChildren();
  byId("learn-library").value = ""; byId("learn-url").value = "";
  byId("domain-review-summary").textContent = "";
  byId("domain-review-status").textContent = "";
  byId("artifact-detail-title").textContent = "Saved item";
  byId("library-status").textContent = "";
  byId("skills-status").textContent = "";
  byId("knowledge-status").textContent = "";
});
window.addEventListener("popstate", () => {
  if (!authenticated) return;
  if (artifactDialog.open) artifactDialog.close();
  const query = new URLSearchParams(location.search);
  if (query.get("library") === "knowledge" || ["skills", "knowledge"].includes(query.get("integrations"))) {
    restoreIntegrationLocation();
    if (currentView !== "integrations") showView("integrations");
    else { renderIntegrationSection(); rememberIntegrationLocation(true); loadIntegrationSection(); }
  } else if (["files", "outputs"].includes(query.get("library"))) {
    restoreLibraryLocation();
    if (currentView !== "library") showView("library"); else loadLibrary();
  } else if (["library", "integrations"].includes(currentView)) showView("chat");
});
setInterval(() => {
  if (authenticated && ["library", "integrations", "activity"].includes(currentView) && !document.hidden) loadOperations();
}, 2000);
