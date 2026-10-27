"use strict";

/* BEGIN MD3 TABS: python3 scripts/bundle_webui_tabs.py */
/* material@3.2.4 | MIT | Copyright 2025 floor */
window.KlaudeMD3Tabs = (() => {
const DEFAULT_CONFIG = {
    widthStrategy: 'auto',
    fixedWidth: 40,
    visible: true,
    prefix: 'mtrl',
    variant: 'primary',
};
const PRIMARY_HEIGHT = 3;
const SECONDARY_HEIGHT = 2;
const PRIMARY_INSET = 2;
const MIN_LENGTH = 24;
const createTabIndicator = (config = {}) => {
    const mergedConfig = { ...DEFAULT_CONFIG, ...config };
    const prefix = mergedConfig.prefix || 'mtrl';
    const element = document.createElement('div');
    element.className = `${prefix}-tabs__indicator`;
    const anchorSupport = () => {
        const host = (element.ownerDocument.defaultView ?? globalThis);
        const supports = host.CSS?.supports;
        return typeof supports === 'function' ? supports('anchor-name', 'none') : null;
    };
    const anchor = anchorSupport();
    const strategy = mergedConfig.widthStrategy ?? 'auto';
    const custom = mergedConfig.animationDuration !== undefined || mergedConfig.animationTiming !== undefined;
    const motion = (property) => `${property} ${mergedConfig.animationDuration ?? 250}ms ${mergedConfig.animationTiming ?? 'cubic-bezier(0.4, 0, 0.2, 1)'}`;
    const transition = custom ? `${motion(anchor === false ? 'transform' : 'left')}, ${motion('width')}` : '';
    element.style.transition = transition;
    element.style.height = `${mergedConfig.height ?? (mergedConfig.variant === 'secondary' ? SECONDARY_HEIGHT : PRIMARY_HEIGHT)}px`;
    if (anchor === false)
        element.style.width = `${mergedConfig.fixedWidth}px`;
    if (strategy !== 'auto')
        element.classList.add(`${prefix}-tabs__indicator--${strategy}`);
    if (strategy === 'fixed' || strategy === 'content') {
        element.style.setProperty(`--${prefix}-tabs-indicator-width`, `${mergedConfig.fixedWidth || 40}px`);
    }
    if (mergedConfig.visible === false) {
        element.style.opacity = '0';
    }
    if (mergedConfig.color) {
        element.style.backgroundColor = mergedConfig.color;
    }
    let currentTab = null;
    const calculateWidth = (tab) => {
        if (mergedConfig.widthStrategy === 'auto') {
            if (mergedConfig.variant === 'secondary') {
                return tab.element.offsetWidth;
            }
            const textElement = tab.element.querySelector(`.${prefix}-button__text`);
            if (textElement) {
                return Math.max(textElement.getBoundingClientRect().width - 2 * PRIMARY_INSET, MIN_LENGTH);
            }
            return Math.max(tab.element.offsetWidth / 2, 30);
        }
        switch (mergedConfig.widthStrategy) {
            case 'dynamic':
                return Math.max(tab.element.offsetWidth / 2, 30);
            case 'content':
                const text = tab.element.querySelector(`.${prefix}-button__text`);
                if (text) {
                    return Math.max(text.clientWidth, 30);
                }
                return mergedConfig.fixedWidth || 40;
            case 'fixed':
            default:
                return mergedConfig.fixedWidth || 40;
        }
    };
    const getTabPosition = (tabElement) => {
        const scrollContainer = tabElement.parentElement;
        if (!scrollContainer) {
            console.error('Tab has no parent element, cannot position indicator');
            return { left: 0, width: tabElement.offsetWidth };
        }
        const tabRect = tabElement.getBoundingClientRect();
        const containerRect = scrollContainer.getBoundingClientRect();
        return {
            left: tabRect.left - containerRect.left,
            width: tabRect.width
        };
    };
    const calculatePosition = (tab, indicatorWidth) => {
        const { left, width: tabWidth } = getTabPosition(tab.element);
        if (mergedConfig.variant !== 'secondary' &&
            (mergedConfig.widthStrategy === 'auto' || mergedConfig.widthStrategy === 'content')) {
            const textElement = tab.element.querySelector(`.${prefix}-button__text`);
            if (textElement) {
                const textRect = textElement.getBoundingClientRect();
                const tabRect = tab.element.getBoundingClientRect();
                const textLeft = textRect.left - tabRect.left;
                return {
                    left: left + textLeft + (textRect.width - indicatorWidth) / 2
                };
            }
        }
        if (indicatorWidth < tabWidth) {
            return {
                left: left + ((tabWidth - indicatorWidth) / 2)
            };
        }
        return { left };
    };
    const moveToTab = (tab, immediate = false) => {
        if (!tab || !tab.element) {
            console.error('Invalid tab or tab has no element');
            return;
        }
        currentTab = tab;
        if (anchor !== false) {
            if (anchor === true && immediate) {
                element.style.transition = 'none';
                void element.offsetHeight;
                element.style.transition = transition;
            }
            return;
        }
        const width = calculateWidth(tab);
        const { left } = calculatePosition(tab, width);
        if (immediate) {
            element.style.transition = 'none';
            element.offsetHeight;
        }
        element.style.width = `${width}px`;
        element.style.transform = `translateX(${left}px)`;
        if (immediate) {
            setTimeout(() => {
                element.style.transition = transition;
            }, 10);
        }
    };
    const update = () => {
        if (currentTab) {
            moveToTab(currentTab, true);
        }
    };
    const show = () => {
        element.style.opacity = '1';
    };
    const hide = () => {
        element.style.opacity = '0';
    };
    const setColor = (color) => {
        element.style.backgroundColor = color;
    };
    const destroy = () => {
        if (element.parentNode) {
            element.parentNode.removeChild(element);
        }
        currentTab = null;
    };
    return {
        element,
        moveToTab,
        show,
        hide,
        setColor,
        update,
        destroy
    };
};

return Object.freeze({ createTabIndicator });
})();
/* END MD3 TABS */

"use strict";

// Same-origin adapter for shared Library services. Untrusted names, previews and
// knowledge snippets are always DOM text; downloaded documents never execute.
let librarySection = readNavigationChoice("library-section",
  ["files", "outputs", "knowledge", "document", "research", "media", "archive"], "files");
let integrationSection = readNavigationChoice("integration-section", ["skills", "knowledge", "connections"], "skills");
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
let contextPreviewOrigin = null;
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
let skillsState = "all";
let skillsLocationPage = null;
let knowledgeQuery = "";
let knowledgeSource = "";
const knowledgeSourceNames = new Map();
let knowledgeChunkPage = null;
let knowledgeChunkRead = null;
let knowledgeReaderIndex = 0;
let knowledgeDeletePending = null;
let knowledgeOrigin = null;
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
let knowledgeSearchTimer = null;
let fileSearchTimer = null;
let skillsRead = null;
let installedSkills = [];
let detailSkill = null;
let skillReviewPending = false;
const skillChanges = new Map();
const domainRefreshes = new Map();
let selectedArtifact = null;
let managementReview = null;
let operationSignature = null;
let operationPollBusy = false;
const reviewDialog = byId("domain-review");
const artifactDialog = byId("artifact-detail");
const importDialog = byId("artifact-import-panel");
const integrationAddDialog = byId("integration-add-panel");
let integrationAddGeneration = 0;
let integrationAddSection = null;
const integrationAddForms = {
  skills: { form: "skill-import", title: "Import a Skill" },
  knowledge: { form: "knowledge-learn", title: "Add to Knowledge" },
  connections: { form: "connection-add", title: "Add an MCP connection" },
};
const skillDialog = byId("skill-detail");
let importGeneration = 0;
let droppedImports = null;
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
function reconcileRows(container, rows) {
  const previous = new Map([...container.children].map(row => [row.dataset.rowKey, row]));
  const keep = new Set();
  rows.forEach((row, index) => {
    const old = previous.get(row.dataset.rowKey);
    const next = old?.dataset.rowSignature === row.dataset.rowSignature ? old : row;
    keep.add(next);
    if (container.children[index] !== next) container.insertBefore(next, container.children[index] || null);
  });
  for (const row of [...container.children]) if (!keep.has(row)) row.remove();
}
function collectionEmpty(container, title, description, icon = "file", followup = "") {
  const empty = domainText("section", "", "collection-empty");
  empty.append(libraryIcon(icon), domainText("h2", title), domainText("p", description, "muted"));
  if (followup) empty.append(domainText("p", followup, "muted"));
  container.replaceChildren(empty);
}
function collectionRow(key, title, metadata, icon, action, signature) {
  const row = domainText("article", "", "library-card collection-row");
  row.dataset.rowKey = key;
  row.dataset.rowSignature = signature;
  const open = domainButton("", action, "collection-open");
  open.setAttribute("aria-description", metadata);
  const artwork = domainText("span", "", "collection-icon");
  artwork.append(libraryIcon(icon));
  const text = domainText("span", "", "collection-content");
  const name = domainText("span", title, "collection-title"); name.title = title;
  text.append(name, domainText("span", metadata, "collection-metadata"));
  open.append(artwork, text, libraryIcon("next"));
  row.append(open);
  return row;
}
function countLabel(count, singular) {
  return count == null ? `${singular[0].toUpperCase() + singular.slice(1)} count unavailable` :
    `${count.toLocaleString()} ${singular}${count === 1 ? "" : "s"}`;
}
async function refreshDomain(prefix) {
  if (domainRefreshes.has(prefix)) return;
  const button = byId(prefix === "library" ? "library-refresh" : "skills-refresh");
  const token = { timer: null, indicator: null };
  domainRefreshes.set(prefix, token);
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  token.timer = setTimeout(() => {
    if (domainRefreshes.get(prefix) !== token || !window.MaterialLoadingCircle) return;
    token.indicator = MaterialLoadingCircle.create({ size: "small" });
    button.prepend(token.indicator);
  }, 120);
  if (prefix === "library") { clearTimeout(fileSearchTimer); filePages.clear(); artifactDetails.clear(); }
  try {
    await Promise.allSettled([prefix === "library" ? loadLibrary() : loadIntegrationSection(), loadTabCounts()]);
  } finally {
    clearTimeout(token.timer); token.indicator?.remove();
    if (domainRefreshes.get(prefix) === token) {
      domainRefreshes.delete(prefix);
      button.disabled = false;
      button.setAttribute("aria-busy", "false");
    }
  }
}
function activeDomainStatus() {
  if (currentView === "settings") return "memory-status";
  return currentView === "integrations" ? `${integrationSection}-status` : "library-status";
}
function domainError(error, target = activeDomainStatus()) {
  if (error.name === "AbortError" || error.authEpoch !== undefined && error.authEpoch !== authEpoch) return;
  if (error.status === 401) { showLocalAccess(); return; }
  window.KlaudeToast.show(error.message || String(error), { variant: "error" });
  if (target === activeDomainStatus() || ["connections-status", "skills-status", "knowledge-status"].includes(target)) {
    byId(target).textContent = "";
    return;
  }
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
    if (error.status === 400 && path === "/api/v1/integrations/skills" && parameters.state)
      throw new Error("Restart Web UI and reload to filter Skills by status.");
    if (error.status !== 400 || legacyPageRoutes.has(path) ||
        !["/api/v1/library/knowledge", "/api/v1/integrations/skills"].includes(path)) throw error;
    legacyPageRoutes.add(path);
    return domainPage(path, parameters, resolveTotal, options);
  }
  if (data.page_size === undefined) {
    const key = data.hits ? "hits" : "items";
    const allSkills = path === "/api/v1/integrations/skills" ? data[key] : null;
    let items = data[key];
    const inventory = path === "/api/v1/integrations/skills" ||
      path === "/api/v1/library/knowledge" && !parameters.query;
    if (path === "/api/v1/integrations/skills" && parameters.query) {
      const needle = parameters.query.toLocaleLowerCase();
      items = items.filter((item) => `${item.name} ${item.description} ${item.library}`.toLocaleLowerCase().includes(needle));
    }
    if (path === "/api/v1/integrations/skills" && parameters.state)
      items = items.filter(item => item.enabled === (parameters.state === "enabled"));
    const offset = Number(parameters.offset || 0);
    const total = inventory ? items.length : data.total ??
      (!data.more && (items.length || offset === 0) ? offset + items.length : null);
    const knownTotal = total ?? (items.length ? offset + items.length + Number(Boolean(data.more)) : 0);
    const counts = allSkills ? {
      all: allSkills.length,
      enabled: allSkills.filter(item => item.enabled).length,
      disabled: allSkills.filter(item => !item.enabled).length,
      limited: Boolean(data.more),
    } : undefined;
    if (inventory) items = items.slice(offset);
    data = { ...data, [key]: items.slice(0, LIBRARY_PAGE_SIZE),
      more: items.length > LIBRARY_PAGE_SIZE || !inventory && Boolean(data.more),
      limited: inventory && Boolean(data.more), ...(counts ? { counts } : {}), page_size: LIBRARY_PAGE_SIZE,
      total, known_total: knownTotal };
  } else if (path === "/api/v1/integrations/skills" && parameters.state && data.state !== parameters.state) {
    throw new Error("Restart Web UI and reload to filter Skills by status.");
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
  if (["knowledge", "sources"].includes(prefix)) return 20;
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
function artifactImage(item, expanded = false, source = "") {
  const img = document.createElement("img");
  img.draggable = false;
  img.alt = item.name;
  img.loading = "lazy";
  img.decoding = "async";
  img.classList.add("image-pending");
  img.setAttribute("aria-busy", "true");
  img.addEventListener("load", () => {
    img.classList.remove("image-pending");
    img.setAttribute("aria-busy", "false");
  }, { once: true });
  img.src = source || (latest && latest.library_images !== true ? artifactUrl(item, true) :
    "/api/v1/library/image?" + new URLSearchParams({
    id: item.id, revision: item.revision, size: expanded ? "preview" : "thumbnail",
  }));
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
  openNew: "M14 4h6v6m0-6-9 9M18 13v6H5V6h6",
  sidebar: "M3 3h18v18H3ZM15 3v18",
  search: "M15 15a7 7 0 1 1 0-10 7 7 0 0 1 0 10Zm0 0 6 6",
  options: "M4 7h16M4 17h16M8 4v6m8 4v6",
  disclosure: "M8.7 4.8a1.5 1.5 0 0 0-2.3 1.3v11.8a1.5 1.5 0 0 0 2.3 1.3l9.4-5.9a1.5 1.5 0 0 0 0-2.6L8.7 4.8Z",
  close: "m6 6 12 12M6 18 18 6",
  more: "M12 4a1 1 0 1 0 0 2 1 1 0 0 0 0-2M12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2M12 18a1 1 0 1 0 0 2 1 1 0 0 0 0-2",
  download: "M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4",
  copy: "M9 9h11v11H9ZM5 15H3V3h12v2", check: "m5 12 4 4L19 6",
  laptop: "M4 4h16v12H4ZM4 16l-2 4h20l-2-4M9 18h6",
  smartphone: "M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2ZM10 5h4M11 19h2",
  fit: "M3 9V3h6m6 0h6v6M3 15v6h6m6 0h6v-6M8 8h8v8H8z",
  plus: "M12 5v14M5 12h14", minus: "M5 12h14",
  link: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2",
  tags: "M3 3h7l11 11-7 7L3 10V3Zm4 4h.01",
  sparkles: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3ZM20 2v4m-2-2h4",
  info: "M12 16v-4m0-4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  trash: "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7",
  knowledge: "M12 5C8 2 4 3 2 4v15c4-2 7-1 10 1 3-2 6-3 10-1V4c-2-1-6-2-10 1Zm0 0v15",
  skill: "M4 8h4V5a2 2 0 0 1 4 0v3h6v4h2a2 2 0 0 1 0 4h-2v5H4v-5h2a2 2 0 0 0 0-4H4V8Z",
  connection: "M8 3v5m8-5v5M6 8h12v4a6 6 0 0 1-12 0V8Zm6 10v3",
  account: "M20 21v-2a8 8 0 0 0-16 0v2M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  chat: "M4 4h16v12H8l-4 4V4ZM8 8h8M8 12h5",
  vision: "M2 12s3-7 10-7 10 7 10 7-3 7-10 7S2 12 2 12ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
  theme: "M12 3a9 9 0 0 0 0 18h1a2.5 2.5 0 0 0 0-5h-.5a1.5 1.5 0 0 1 0-3H17a4 4 0 0 0 4-4c0-3.3-4-6-9-6ZM7 10h.01M9 6.5h.01M14 6.5h.01M17 9h.01",
  agent: "M12 3v4M5 7h14v13H5ZM2 11v5m20-5v5M9 11h.01M15 11h.01M9 16h6",
  models: "m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5",
  clock: "M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  memory: "M12 18V5M15 13a4.17 4.17 0 0 1-3-4 4.17 4.17 0 0 1-3 4M17.598 6.5A3 3 0 1 0 12 5a3 3 0 1 0-5.598 1.5M17.997 5.125a4 4 0 0 1 2.526 5.77M18 18a4 4 0 0 0 2-7.464M20.303 16.369A4 4 0 1 1 12 18M6.003 5.125a4 4 0 0 0-2.526 5.77M6 18a4 4 0 0 1-2-7.464M3.697 16.369A4 4 0 1 0 12 18",
  tools: "m14 6 4 4 3-3a6 6 0 0 1-8 7L6 21l-3-3 7-7a6 6 0 0 1 7-8l-3 3Z",
  shield: "M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7l-9-4Zm-4 9 3 3 5-6",
  web: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3a18 18 0 0 0 0 18 18 18 0 0 0 0-18Z",
};
function libraryIcon(type) {
  if (type === "refresh") return byId("refresh-sessions").querySelector("svg").cloneNode(true);
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
function decorateDisclosure(summary) {
  if (summary.classList.contains("rounded-disclosure")) return summary;
  summary.classList.add("rounded-disclosure");
  const icon = libraryIcon("disclosure"); icon.classList.add("disclosure-indicator");
  summary.prepend(icon);
  return summary;
}
for (const summary of document.querySelectorAll("details:not(.model-menu, .agent-activity) > summary")) decorateDisclosure(summary);
for (const button of document.querySelectorAll("[data-refresh-icon]")) button.append(libraryIcon("refresh"));
for (const node of document.querySelectorAll("#settings-sections [data-settings], #settings-view [data-settings-icon]")) {
  node.prepend(libraryIcon(node.dataset.settingsIcon || node.dataset.settings));
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
  if (!Number.isFinite(size) || size < 0) return "Size unknown";
  if (size > 0 && size < 10_000) return "<0.01 MB";
  const gigabytes = size >= 1_000_000_000;
  const value = gigabytes ? size / 1_000_000_000 : Math.min(size / 1_000_000, 999.99);
  return `${value.toLocaleString(undefined, {maximumFractionDigits:2})} ${gigabytes ? "GB" : "MB"}`;
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
  url.searchParams.delete("view");
  // The full Library always spans conversations; only Context Library has scope.
  url.searchParams.delete("files-scope");
  url.searchParams.delete("session"); url.searchParams.delete("message");
  for (const key of [...url.searchParams.keys()])
    if (["integrations", "settings", "sources-page"].includes(key) || key.startsWith("knowledge-") || key.startsWith("skills-")) url.searchParams.delete(key);
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
  else if (["skills", "knowledge", "connections"].includes(query.get("integrations"))) integrationSection = query.get("integrations");
  else return;
  if (integrationSection === "skills") {
    byId("skills-query").value = (query.get("skills-q") || "").slice(0, 200);
    skillsState = ["enabled", "disabled"].includes(query.get("skills-state")) ? query.get("skills-state") : "all";
    const page = Number(query.get("skills-page") || 1);
    skillsLocationPage = Number.isSafeInteger(page) && page > 0 && page <= 50001 ? page : 1;
    return;
  }
  if (integrationSection !== "knowledge") return;
  const library = (query.get("knowledge-library") || "").slice(0, 160);
  knowledgeSource = library ? (query.get("knowledge-source") || "").slice(0, 8192) : "";
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
  url.searchParams.delete("view");
  url.searchParams.delete("session"); url.searchParams.delete("message");
  for (const key of [...url.searchParams.keys()])
    if (["library", "settings", "sources-page"].includes(key) || key.startsWith("files-") || key.startsWith("knowledge-") || key.startsWith("skills-")) url.searchParams.delete(key);
  url.searchParams.set("integrations", integrationSection);
  if (integrationSection === "knowledge") {
    const state = { "knowledge-library": byId("knowledge-library").value,
      "knowledge-source": knowledgeSource,
      "knowledge-q": knowledgeQuery, "knowledge-page": String(knowledgeLocationPage ?? Math.floor(knowledgeOffset / domainPageSizes.knowledge) + 1),
      "sources-page": String(sourceLocationPage ?? Math.floor(sourceOffset / domainPageSizes.sources) + 1) };
    for (const [key, value] of Object.entries(state)) if (value) url.searchParams.set(key, value);
  } else if (integrationSection === "skills") {
    const query = byId("skills-query").value;
    if (query) url.searchParams.set("skills-q", query);
    if (skillsState !== "all") url.searchParams.set("skills-state", skillsState);
    url.searchParams.set("skills-page", String(skillsLocationPage ?? Math.floor(skillsOffset / domainPageSizes.skills) + 1));
  }
  const next = url.pathname + url.search;
  if (next !== location.pathname + location.search) history[replace ? "replaceState" : "pushState"](history.state, "", next);
}
function renderIntegrationSection() {
  if (integrationAddDialog.open && integrationAddSection !== integrationSection) integrationAddDialog.close();
  byId("skills-panel").hidden = integrationSection !== "skills";
  byId("knowledge-panel").hidden = integrationSection !== "knowledge";
  byId("connections-panel").hidden = integrationSection !== "connections";
  for (const button of byId("integration-sections").querySelectorAll("[data-integration]"))
    button.setAttribute("aria-pressed", String(button.dataset.integration === integrationSection));
  renderSkillsFilter();
}
function renderSkillsFilter() {
  for (const button of byId("skills-state-filter").children)
    button.setAttribute("aria-pressed", String(button.dataset.skillState === skillsState));
}
function renderSkillsCounts(counts = {}) {
  for (const state of ["all", "enabled", "disabled"]) {
    const node = byId("skills-state-filter").querySelector(`[data-skill-count="${state}"]`);
    if (!node) continue;
    const total = counts[state];
    const known = Number.isSafeInteger(total) && total >= 0;
    node.textContent = known ? `${total}${counts.limited ? "+" : ""}` : "—";
    const label = node.parentElement.querySelector(".filter-chip-label").textContent;
    node.closest("button").setAttribute("aria-label", known ?
      `${label} Skills, ${total}${counts.limited ? " or more" : ""}` : `${label} Skills, count unavailable`);
  }
}
async function readSkillsCounts(options = {}) {
  const states = ["all", "enabled", "disabled"];
  const results = await Promise.all(states.map(state => domainPage(
    "/api/v1/integrations/skills",
    { offset: 0, ...(state === "all" ? {} : { state }) }, true, options)));
  const counts = Object.fromEntries(states.map((state, index) => [state,
    results[index].total ?? results[index].known_total ?? null]));
  return { ...counts, limited: results.some(result => result.limited) };
}
function loadIntegrationSection() {
  renderIntegrationSection();
  if (integrationSection === "connections") return window.BrowserManagement?.loadConnections();
  return integrationSection === "knowledge" ? loadKnowledge() : loadSkills();
}
function stopIntegrationReads() {
  knowledgeRead?.abort(); sourceRead?.abort(); skillsRead?.abort();
  knowledgeChunkRead?.abort();
  byId("knowledge-chunk-reader").close();
  knowledgeLoad += 1; sourcesLoad += 1; skillsLoad += 1;
  clearTimeout(skillsSearchTimer);
  clearTimeout(knowledgeSearchTimer);
  for (const id of ["knowledge-items", "source-items", "skill-items"]) cancelLoading(byId(id));
}
// Native selects remain the state/event seam and the fallback for older browsers.
// The same adapter supplies all three Library dropdown chips.
function createTrailingFilterChip(select) {
  if (typeof HTMLElement.prototype.showPopover !== "function") return null;
  const original = select.closest("label"), name = original.firstChild.textContent.trim();
  const field = domainText("div", "", "file-filter-field");
  if (original.classList.contains("file-sort-field")) field.classList.add("file-sort-field");
  let closeOnClick = false;
  const trigger = domainButton("", () => {
    if (closeOnClick) { closeOnClick = false; close(); return; }
    open();
  }, "filter-chip library-filter-chip");
  trigger.id = `${select.id}-chip`;
  trigger.setAttribute("aria-haspopup", "menu"); trigger.setAttribute("aria-expanded", "false");
  const face = domainText("span", "", "filter-chip-face");
  const label = domainText("span", "", "filter-chip-label");
  const arrow = libraryIcon("disclosure"); arrow.classList.add("filter-chip-menu-arrow");
  face.append(label, arrow); trigger.append(face);
  const menu = domainText("div", "", "message-menu library-filter-menu");
  menu.id = `${select.id}-menu`; menu.setAttribute("popover", "auto");
  menu.setAttribute("role", "menu"); menu.setAttribute("aria-label", name);
  trigger.setAttribute("aria-controls", menu.id);
  original.replaceWith(field); select.hidden = true; select.setAttribute("aria-label", name);
  field.append(select, trigger); document.body.append(menu);
  const showing = () => menu.matches(":popover-open");
  function close(focus = false) {
    if (showing()) menu.hidePopover();
    trigger.setAttribute("aria-expanded", "false");
    if (focus) trigger.focus({ preventScroll: true });
  }
  function sync() {
    const selected = select.selectedOptions[0];
    label.textContent = selected?.textContent || name;
    trigger.setAttribute("aria-label", `${name}: ${label.textContent}`);
    trigger.title = `${name}: ${label.textContent}`;
    trigger.disabled = select.disabled;
    trigger.dataset.filterActive = String(select.value !== select.options[0]?.value);
  }
  function position() {
    if (!showing()) return;
    const viewport = window.visualViewport;
    const left = (viewport?.offsetLeft || 0) + 8, top = (viewport?.offsetTop || 0) + 8;
    const right = left + (viewport?.width || innerWidth) - 16;
    const bottom = top + (viewport?.height || innerHeight) - 16;
    menu.style.maxHeight = `${bottom - top}px`;
    const anchor = trigger.getBoundingClientRect(), row = field.parentElement.getBoundingClientRect();
    if (anchor.bottom <= top || anchor.top >= bottom || anchor.right <= row.left || anchor.left >= row.right) {
      close(); return;
    }
    const bounds = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(left, Math.min(anchor.left, right - bounds.width))}px`;
    const y = anchor.bottom + 4 + bounds.height <= bottom ? anchor.bottom + 4 :
      anchor.top - bounds.height - 4;
    menu.style.top = `${Math.max(top, Math.min(y, bottom - bounds.height))}px`;
  }
  function open(last = false) {
    if (showing()) { close(); return; }
    search = ""; typedAt = 0;
    menu.replaceChildren(...[...select.options].map(option => {
      const item = domainButton("", () => {
        close(true);
        if (select.value === option.value) return;
        select.value = option.value; sync(); select.dispatchEvent(new Event("change", { bubbles: true }));
      }, "message-action");
      item.setAttribute("role", "menuitemradio"); item.tabIndex = -1;
      item.setAttribute("aria-checked", String(option.selected));
      item.disabled = option.disabled; item.dataset.value = option.value;
      const check = libraryIcon("check"); check.classList.add("filter-menu-check");
      item.append(check, domainText("span", option.textContent));
      return item;
    }));
    menu.showPopover(); trigger.setAttribute("aria-expanded", "true"); position();
    const enabled = [...menu.querySelectorAll("button:not(:disabled)")];
    (last ? enabled.at(-1) : menu.querySelector('[aria-checked="true"]:not(:disabled)') || enabled[0])?.focus({ preventScroll: true });
  }
  trigger.addEventListener("keydown", event => {
    if (!["ArrowDown", "ArrowUp"].includes(event.key)) return;
    event.preventDefault(); open(event.key === "ArrowUp");
  });
  trigger.addEventListener("pointerdown", () => { closeOnClick = showing(); });
  let search = "", typedAt = 0;
  menu.addEventListener("keydown", event => {
    const items = [...menu.querySelectorAll("button:not(:disabled)")];
    const index = items.indexOf(document.activeElement);
    let next;
    if (event.key === "ArrowDown") next = (index + 1) % items.length;
    if (event.key === "ArrowUp") next = (index - 1 + items.length) % items.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = items.length - 1;
    if (next !== undefined) { event.preventDefault(); items[next]?.focus(); }
    if (event.key === "Escape") { event.preventDefault(); close(true); }
    if (event.key === "Tab") close(true);
    if (event.key.length === 1 && event.key !== " " && !event.ctrlKey && !event.metaKey && !event.altKey) {
      search = Date.now() - typedAt < 700 && search !== event.key ? search + event.key : event.key;
      typedAt = Date.now();
      const ordered = [...items.slice(index + 1), ...items.slice(0, index + 1)];
      const match = ordered.find(item => item.textContent.toLocaleLowerCase().startsWith(search.toLocaleLowerCase()));
      if (match) { event.preventDefault(); match.focus(); }
    }
    event.stopPropagation();
  });
  menu.addEventListener("toggle", () => trigger.setAttribute("aria-expanded", String(showing())));
  select.addEventListener("change", sync);
  window.addEventListener("resize", position);
  window.visualViewport?.addEventListener("resize", position);
  window.visualViewport?.addEventListener("scroll", position);
  document.addEventListener("scroll", event => {
    if (menu.contains(event.target)) return;
    position();
  }, true);
  document.addEventListener("klaude-view", () => close());
  document.addEventListener("klaude-auth-reset", () => close());
  sync();
  return { sync, close };
}
const libraryFilterMenus = ["artifact-kind", "artifact-status", "artifact-sort"]
  .map(id => createTrailingFilterChip(byId(id))).filter(Boolean);

function renderFileToolbar() {
  for (const button of byId("file-view-modes").children) button.setAttribute("aria-pressed", String(button.dataset.fileView === fileView));
  const outputs = librarySection === "outputs";
  byId("generated-tools").hidden = !outputs;
  if (outputs) window.BrowserManagement?.loadJobs();
  byId("file-add").hidden = outputs;
  byId("image-add").hidden = !outputs;
  if (!outputs && currentView === "library") byId("image-generate-panel").close();
  byId("artifact-query").placeholder = outputs ? "Search generated files…" : "Search uploads…";
  byId("artifact-filter").querySelector(".file-search-label span").textContent = outputs ? "Find generated files" : "Find uploads";
  const available = latest?.library_images === true;
  const gallery = byId("file-view-modes").querySelector('[data-file-view="gallery"]');
  gallery.disabled = Boolean(latest) && !available;
  gallery.title = gallery.disabled ? "Restart Web UI after the active reply to enable Gallery" : "Gallery view";
  for (const option of byId("artifact-sort").options) option.disabled =
    Boolean(latest) && !available && !["newest", "oldest", "name"].includes(option.value);
  for (const menu of libraryFilterMenus) menu.sync();
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
function createFileTile(item, onOpen) {
  const card = domainText("article", "", "library-card file-item");
  card.dataset.fileId = item.id;
  const open = domainButton("", () => onOpen(open), "file-open");
  open.setAttribute("aria-label", `Open ${item.name}`);
  open.title = item.name;
  const art = domainText("span", "", "file-artwork");
  art.setAttribute("aria-hidden", "true");
  art.append(canPreviewImage(item) ? artifactImage(item) : fileIcon(item));
  const [type, label] = fileType(item);
  open.setAttribute("aria-description", `${label}, ${fileSize(item.size)}, added ${fileDate(item.created)}`);
  card.dataset.fileType = type;
  const detail = domainText("span", "", "file-name-group");
  detail.append(domainText("span", item.name, "file-name"),
    domainText("span", `${label} · ${fileSize(item.size)}`, "file-secondary"));
  const date = domainText("time", fileDate(item.created), "file-added");
  date.dateTime = new Date(item.created * 1000).toISOString();
  date.title = `Added ${new Date(item.created * 1000).toLocaleString()}`;
  open.append(art, detail, domainText("span", label, "file-type"),
    domainText("span", fileSize(item.size), "file-size"), date);
  card.append(open);
  return { card, open };
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
    const { card } = createFileTile(item, open => {
      imageSequence = data.items.filter(isLibraryImage);
      imageSequenceOffset = libraryOffset;
      imageSequenceTotal = fileView === "gallery" ? data.total : imageSequence.length;
      previewOrigin = open;
      previewOriginId = item.id;
      previewScroll = byId("library-view").scrollTop;
      openArtifact(item.id).catch((error) => domainError(error));
    });
    nodes.push(card);
  }
  grid.replaceChildren(...nodes);
}

async function loadLibrary() {
  clearTimeout(fileSearchTimer);
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
    const searching = Boolean(byId("artifact-query").value.trim());
    const filtered = fileKind !== "all" || fileStatus !== "saved";
    const title = searching ? "No files match this search" : filtered ? "No files match these filters" :
      fileView === "gallery" ? "No images yet" : section === "outputs" ? "No generated files yet" : "No uploads yet";
    if (!data.items.length) {
      collectionEmpty(grid, title, searching || filtered ?
        "Try another search or change the type and status filters." : fileView === "gallery" ?
          "Supported images appear here. Try List or Grid to see other files." : section === "outputs" ?
            "Research reports and generated images created in the CLI appear here." : "Add a file to get started.",
        fileView === "gallery" ? "image" : "file");
      grid.firstChild.classList.add("library-empty");
      grid.firstChild.setAttribute("role", "status");
    }
    byId("library-status").textContent = "";
    updateDomainPager("library", offset, data);
    grid.dataset.contentKey = key;
    rememberLibraryLocation(true);
  } catch (error) {
    if (load === libraryLoad && error.name !== "AbortError") {
      finish();
      if (!grid.children.length) collectionEmpty(grid, "Files could not be loaded", "Use Refresh to try again.");
      domainError(error);
    }
  }
  finally { finish(); }
}

function knowledgeLocation(library, source = "", keepQuery = false) {
  knowledgeRead?.abort(); sourceRead?.abort();
  knowledgeLoad++; sourcesLoad++;
  const select = byId("knowledge-library");
  const sameLibrary = select.value === library;
  if (library && ![...select.options].some(option => option.value === library)) {
    const option = domainText("option", library); option.value = library; select.append(option);
  }
  select.value = library;
  byId("learn-library").value = library;
  knowledgeSource = source;
  knowledgeOffset = 0;
  if (!sameLibrary) sourceOffset = 0;
  knowledgeLocationPage = sourceLocationPage = null;
  if (!keepQuery) { knowledgeQuery = ""; byId("knowledge-query").value = ""; }
  rememberIntegrationLocation();
  loadKnowledge();
  byId("knowledge-title").focus({ preventScroll: true });
}
const knowledgeWide = matchMedia("(min-width: 1000px)");
byId("knowledge-sources").open = knowledgeWide.matches;
knowledgeWide.addEventListener("change", () => { byId("knowledge-sources").open = knowledgeWide.matches; });
function knowledgeHeading(summary = null) {
  const library = byId("knowledge-library").value;
  const crumbs = byId("knowledge-breadcrumbs");
  crumbs.hidden = !library;
  crumbs.replaceChildren();
  if (library) {
    crumbs.append(domainButton("All knowledge", () => knowledgeLocation(""), "quiet"),
      domainText("span", "›", "muted"));
    if (knowledgeSource) crumbs.append(domainButton(library, () => knowledgeLocation(library), "quiet"),
      domainText("span", "›", "muted"), domainText("span", knowledgeSourceNames.get(knowledgeSource) || knowledgeSource, "knowledge-current"));
    else crumbs.append(domainText("span", library, "knowledge-current"));
    crumbs.lastChild.setAttribute("aria-current", "page");
  }
  byId("knowledge-heading").hidden = !library && !knowledgeQuery;
  byId("knowledge-title").textContent = library || (knowledgeQuery ? "Search results" : "");
  byId("knowledge-query").placeholder = knowledgeSource ? "Search this source…" : library ? "Search this knowledge…" : "Search all knowledge…";
  byId("knowledge-search-label").textContent = knowledgeSource ? "Search chunk text in this source" : library ?
    "Search sources and chunk text in this knowledge" : "Search libraries, sources and chunk text";
  byId("knowledge-delete").hidden = !library;
  byId("knowledge-delete").disabled = Boolean(knowledgeDeletePending);
  byId("knowledge-delete").textContent = knowledgeDeletePending?.unknown ? "Unconfirmed" : knowledgeDeletePending ? "Deleting…" : knowledgeSource ? "Delete source" : "Delete knowledge";
  byId("knowledge-content-title").hidden = !library && !knowledgeQuery;
  byId("knowledge-browser").classList.toggle("has-library", Boolean(library));
  if (summary) byId("knowledge-summary").textContent = library ?
    `${countLabel(summary.sources, "source")} · ${countLabel(summary.chunks, "chunk")}` :
    knowledgeQuery ? "Matches in library names, sources and indexed text" : "";
}
async function knowledgeRequest(path, parameters, options = {}) {
  try { return await domainRequest(`${path}?${new URLSearchParams(parameters)}`, "GET", undefined, options); }
  catch (error) {
    if (error.status === 404) throw new Error("Use Refresh to try again.");
    throw error;
  }
}
function highlightKnowledge(node, text, query) {
  if (!query) { node.textContent = text; return; }
  // All indexed content stays inert, including HTML and FTS/regex syntax.
  let start = 0, position;
  const lower = text.toLocaleLowerCase(), needle = query.toLocaleLowerCase();
  while ((position = lower.indexOf(needle, start)) >= 0) {
    node.append(document.createTextNode(text.slice(start, position)), domainText("mark", text.slice(position, position + query.length)));
    start = position + query.length;
  }
  node.append(document.createTextNode(text.slice(start)));
}
function knowledgeChunkCard(item, index) {
  const row = domainText("article", "", "knowledge-chunk library-card");
  const button = domainButton("", () => openKnowledgeChunk(index, button), "knowledge-chunk-open");
  const meta = domainText("span", `${item.library} · ${countLabel(item.characters, "character")}`, "collection-metadata");
  const name = domainText("span", item.source_name || item.source || "Indexed text", "knowledge-chunk-source");
  const preview = domainText("span", "", "knowledge-chunk-preview");
  highlightKnowledge(preview, item.text, knowledgeQuery);
  const read = domainText("span", "Read chunk", "knowledge-read-label"); read.append(libraryIcon("next"));
  button.setAttribute("aria-label", `Read chunk from ${item.source_name || item.source || item.library}`);
  button.append(meta, name, preview, read);
  row.append(button);
  if (!byId("knowledge-library").value || !knowledgeSource) {
    row.append(domainButton("View source", () => knowledgeLocation(item.library, item.source, true), "quiet knowledge-source-link"));
  }
  return row;
}
async function loadKnowledge() {
  if (!authenticated || currentView !== "integrations" || integrationSection !== "knowledge") return;
  knowledgeRead?.abort(); knowledgeRead = new AbortController();
  const signal = knowledgeRead.signal, library = byId("knowledge-library").value;
  if (knowledgeLocationPage !== null) { knowledgeOffset = (knowledgeLocationPage - 1) * 20; knowledgeLocationPage = null; }
  const load = ++knowledgeLoad, offset = knowledgeOffset, grid = byId("knowledge-items");
  const key = JSON.stringify([library, knowledgeSource, knowledgeQuery, offset]);
  knowledgeHeading();
  byId("knowledge-sources").hidden = !library;
  sourceRead?.abort(); sourcesLoad++;
  if (byId("source-items").dataset.library !== library) {
    byId("source-items").replaceChildren();
    byId("sources-pages").hidden = true;
  }
  if (grid.dataset.contentKey !== key) byId("knowledge-pages").hidden = true;
  const finish = beginLoading(grid, { kind: "rows", count: 4, preserve: grid.dataset.contentKey === key, label: "Loading Knowledge…" });
  byId("knowledge-status").textContent = "";
  try {
    const data = await knowledgeRequest("/api/v1/library/knowledge/contents", {
      library, source: knowledgeSource, query: knowledgeQuery, offset }, { signal });
    if (load !== knowledgeLoad) return;
    if (!data.items.length && offset > 0) {
      knowledgeOffset = Math.max(0, Math.ceil(data.total / 20) - 1) * 20;
      return loadKnowledge();
    }
    knowledgeHeading(data.summary);
    knowledgeChunkPage = data.mode === "chunks" ? data : null;
    if (data.available === false) {
      collectionEmpty(grid, "Knowledge index needs an update", "Use the CLI to update this older index, then refresh Knowledge.", "knowledge");
    } else if (!data.items.length) {
      collectionEmpty(grid, knowledgeQuery ? "No matching text" : library ? "No indexed chunks" : "No knowledge yet",
        knowledgeQuery ? "Try another word or clear the search to browse everything." : library ?
          "This knowledge may have been deleted or replaced. Return to All knowledge or add a source." :
          "Add a URL or text file to create a library you can browse and search.", "knowledge");
      const action = library ? domainButton("All knowledge", () => knowledgeLocation(""), "secondary") :
        domainButton("Add to Knowledge", () => byId("integration-add-knowledge").click(), "secondary");
      if (!knowledgeQuery) grid.firstChild.append(action);
    } else if (data.mode === "libraries") {
      knowledgeChunkPage = null;
      reconcileRows(grid, data.items.map(item => {
        const card = collectionRow(item.id, item.id,
          `${countLabel(item.sources, "source")} · ${countLabel(item.chunks, "chunk")}`, "knowledge",
          () => knowledgeLocation(item.id), JSON.stringify(item));
        card.classList.add("knowledge-card"); card.firstChild.setAttribute("aria-label", `Explore library ${item.id}`);
        return card;
      }));
    } else {
      knowledgeChunkPage = data;
      grid.replaceChildren(...data.items.map(knowledgeChunkCard));
      byId("knowledge-content-title").textContent = knowledgeQuery ? `${countLabel(data.total, "matching chunk")}` :
        knowledgeSource ? `${countLabel(data.total, "chunk")} in this source` : "All chunks";
    }
    updateDomainPager("knowledge", offset, data);
    if (data.total <= 20) byId("knowledge-pages").hidden = true;
    grid.dataset.contentKey = key;
    rememberIntegrationLocation(true);
    finish();
    if (library) await loadKnowledgeSources();
  } catch (error) {
    if (load === knowledgeLoad && error.name !== "AbortError") {
      domainError(error, "knowledge-status");
      if (grid.dataset.contentKey !== key) collectionEmpty(grid, "Knowledge could not be loaded",
        "Use Refresh to try again.", "knowledge",
        "Restart Web UI after the active reply, then reload to browse knowledge chunks.");
    }
  } finally { finish(); }
}
async function openKnowledgeChunk(index, origin = null, page = knowledgeChunkPage) {
  if (!page?.items[index]) return;
  const dialog = byId("knowledge-chunk-reader"), item = page.items[index];
  knowledgeChunkRead?.abort(); knowledgeChunkRead = new AbortController();
  const signal = knowledgeChunkRead.signal;
  knowledgeReaderIndex = index;
  if (origin) knowledgeOrigin = origin;
  dialog.knowledgePage = page;
  byId("knowledge-chunk-title").textContent = `Chunk ${page.offset + index + 1}`;
  byId("knowledge-chunk-source").textContent = `${item.library} · ${item.source_name || item.source}`;
  byId("knowledge-chunk-status").textContent = "Loading chunk…";
  byId("knowledge-chunk-text").replaceChildren();
  byId("knowledge-chunk-copy").disabled = true;
  byId("knowledge-chunk-previous").disabled = page.offset + index === 0;
  byId("knowledge-chunk-next").disabled = page.offset + index + 1 >= page.total;
  byId("knowledge-chunk-position").textContent = `${page.offset + index + 1} of ${page.total}`;
  if (!dialog.open) {
    dialog.showModal();
    byId("knowledge-chunk-title").focus({ preventScroll: true });
  }
  try {
    const data = await knowledgeRequest("/api/v1/library/knowledge/contents", {
      library: item.library, source: item.source, chunk: item.id }, { signal });
    if (signal.aborted || !dialog.open || !authenticated) return;
    highlightKnowledge(byId("knowledge-chunk-text"), data.item.text, knowledgeQuery);
    byId("knowledge-chunk-text").scrollTop = 0;
    byId("knowledge-chunk-copy").disabled = false;
    byId("knowledge-chunk-status").textContent = data.item.truncated ? "Showing the first 65,536 characters of this oversized chunk." :
      countLabel(data.item.characters, "character");
  } catch (error) { if (!signal.aborted && dialog.open) domainError(error, "knowledge-chunk-status"); }
}
async function stepKnowledgeChunk(direction) {
  const dialog = byId("knowledge-chunk-reader"), page = dialog.knowledgePage;
  if (!page) return;
  let index = knowledgeReaderIndex + direction;
  if (index >= 0 && index < page.items.length) return openKnowledgeChunk(index, null, page);
  knowledgeChunkRead?.abort(); knowledgeChunkRead = new AbortController();
  const signal = knowledgeChunkRead.signal;
  byId("knowledge-chunk-previous").disabled = byId("knowledge-chunk-next").disabled = true;
  byId("knowledge-chunk-status").textContent = "Loading chunk…";
  try {
    const data = await knowledgeRequest("/api/v1/library/knowledge/contents", {
      library: byId("knowledge-library").value, source: knowledgeSource, query: knowledgeQuery,
      offset: page.offset + direction * 20 }, { signal });
    if (signal.aborted || !dialog.open || !authenticated) return;
    if (!data.items.length) throw new Error("Knowledge changed; close this reader and refresh.");
    await openKnowledgeChunk(direction > 0 ? 0 : data.items.length - 1, null, data);
    if (!dialog.open || !authenticated) return;
    const control = byId(direction > 0 ? "knowledge-chunk-next" : "knowledge-chunk-previous");
    (control.disabled ? byId("knowledge-chunk-title") : control).focus({ preventScroll: true });
  } catch (error) { if (!signal.aborted && dialog.open) domainError(error, "knowledge-chunk-status"); }
}
byId("knowledge-chunk-copy").addEventListener("click", async () => {
  const copied = await window.ChatMarkdown?.copyText(byId("knowledge-chunk-text").textContent, byId("knowledge-chunk-reader"));
  if (byId("knowledge-chunk-reader").open) byId("knowledge-chunk-status").textContent = copied ? "Chunk copied." : "Select the chunk text to copy it.";
});
byId("knowledge-chunk-close").append(libraryIcon("close"));
byId("knowledge-chunk-close").addEventListener("click", () => byId("knowledge-chunk-reader").close());
byId("knowledge-chunk-previous").addEventListener("click", () => stepKnowledgeChunk(-1));
byId("knowledge-chunk-next").addEventListener("click", () => stepKnowledgeChunk(1));
byId("knowledge-chunk-reader").addEventListener("close", () => {
  knowledgeChunkRead?.abort();
  byId("knowledge-chunk-text").replaceChildren();
  byId("knowledge-chunk-source").textContent = "";
  byId("knowledge-chunk-reader").knowledgePage = null;
  if (knowledgeOrigin?.isConnected && authenticated) knowledgeOrigin.focus({ preventScroll: true });
  knowledgeOrigin = null;
});
byId("knowledge-delete").addEventListener("click", async () => {
  if (knowledgeDeletePending || reviewDialog.open) return;
  const library = byId("knowledge-library").value, source = knowledgeSource, epoch = authEpoch;
  if (!library) return;
  const pending = { library, source }; knowledgeDeletePending = pending; knowledgeHeading();
  const current = () => authenticated && epoch === authEpoch && currentView === "integrations" &&
    integrationSection === "knowledge" && library === byId("knowledge-library").value && source === knowledgeSource;
  try {
    await prepareChange({ operation: "knowledge-delete", library, source }, {
      current,
      onAccepted: operation => { pending.request_id = operation.request_id; pending.library = library; pending.source = source; },
      onDiscard: review => {
        if (review.uncertain) pending.request_id = review.request_id;
        else if (knowledgeDeletePending === pending) knowledgeDeletePending = null;
        knowledgeHeading();
      },
    });
    if (!current() && !pending.request_id && knowledgeDeletePending === pending) knowledgeDeletePending = null;
  } catch (error) {
    if (knowledgeDeletePending === pending) knowledgeDeletePending = null;
    if (current()) domainError(error, "knowledge-status");
  } finally { knowledgeHeading(); }
});
document.addEventListener("klaude-operations", event => {
  const pending = knowledgeDeletePending;
  if (!pending?.request_id) return;
  const operation = event.detail.find(item => item.request_id === pending.request_id);
  if (!operation || !["completed", "failed", "unknown"].includes(operation.state)) return;
  if (operation.state === "unknown") {
    pending.unknown = true;
    knowledgeHeading();
    byId("knowledge-delete").disabled = true;
    byId("knowledge-status").textContent = "";
    return;
  }
  knowledgeDeletePending = null;
  if (!authenticated || currentView !== "integrations" || integrationSection !== "knowledge") return;
  if (operation.state === "completed" && byId("knowledge-library").value === pending.library) {
    knowledgeLocation(pending.source ? pending.library : "");
  } else {
    knowledgeHeading();
    if (operation.state === "failed") {
      byId("knowledge-status").textContent = "";
    }
  }
});

function sourceLanguage(item) {
  const extension = item.filename.split(".").pop().toLowerCase();
  return ({ html: "html", htm: "html", xml: "xml", svg: "xml", css: "css",
    js: "js", mjs: "js", cjs: "js", ts: "ts", py: "py", json: "json",
    sh: "sh", bash: "bash", sql: "sql", yml: "yaml", yaml: "yaml", toml: "toml",
    diff: "diff", patch: "diff", md: "markdown", markdown: "markdown" })[extension] || "text";
}
function numberedSource(source, language) {
  const pre = domainText("pre", "", "artifact-text");
  const code = domainText("code", "", "source-code");
  const highlighted = document.createElement("code");
  if (window.ChatMarkdown?.highlight) ChatMarkdown.highlight(highlighted, source, language);
  else highlighted.textContent = source;
  let line, number = 0;
  const nextLine = () => {
    const row = domainText("span", "", "source-line");
    const gutter = domainText("span", "", "source-line-number");
    gutter.dataset.number = String(++number); gutter.setAttribute("aria-hidden", "true");
    line = domainText("span", "", "source-line-text");
    row.append(gutter, line); code.append(row);
  };
  nextLine();
  const walker = document.createTreeWalker(highlighted, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const text = walker.currentNode, ancestors = [];
    for (let parent = text.parentElement; parent !== highlighted; parent = parent.parentElement) ancestors.unshift(parent);
    for (const part of text.data.split(/(\r\n|\r|\n)/)) {
      if (/^(\r\n|\r|\n)$/.test(part)) {
        const ending = domainText("span", part, "source-line-ending");
        ending.setAttribute("aria-hidden", "true"); line.append(ending); nextLine();
      } else if (part) {
        let parent = line;
        for (const ancestor of ancestors) { const span = ancestor.cloneNode(false); parent.append(span); parent = span; }
        parent.append(document.createTextNode(part));
      }
    }
  }
  pre.append(code); return pre;
}

// Presentation and gestures remain local to the existing native file dialog.
const artifactViewer = (() => {
  const preview = byId("artifact-preview"), panel = byId("artifact-information");
  const menu = byId("artifact-menu"), more = byId("artifact-more");
  const phone = matchMedia("(max-width: 850px)");
  const inspectorTabs = byId("inspector-tabs"), inspectorScroll = panel.querySelector(".preview-information-scroll");
  const inspectorIndicator = window.KlaudeMD3Tabs.createTabIndicator({ variant: "primary", widthStrategy: "auto" });
  inspectorIndicator.element.setAttribute("aria-hidden", "true");
  const inspectorDivider = document.createElement("div");
  inspectorDivider.className = "mtrl-tabs__divider"; inspectorDivider.setAttribute("aria-hidden", "true");
  inspectorTabs.append(inspectorDivider, inspectorIndicator.element);
  const indicatorElement = inspectorIndicator.element;
  indicatorElement.style.left = "0px";
  indicatorElement.style.transition = "transform 450ms cubic-bezier(0.2, 0, 0, 1), width 450ms cubic-bezier(0.2, 0, 0, 1)";
  let inspectorIndicatorReady = false;
  function positionInspectorIndicator(selected, immediate = false) {
    const label = selected?.querySelector(".mtrl-button__text");
    if (!label) return;
    const width = Math.max(24, label.offsetWidth - 4);
    const left = selected.offsetLeft + label.offsetLeft + (label.offsetWidth - width) / 2;
    if (immediate) indicatorElement.style.transition = "none";
    indicatorElement.style.width = `${width}px`;
    indicatorElement.style.transform = `translateX(${left}px)`;
    if (immediate) requestAnimationFrame(() => {
      indicatorElement.style.transition = "transform 450ms cubic-bezier(0.2, 0, 0, 1), width 450ms cubic-bezier(0.2, 0, 0, 1)";
    });
  }
  new ResizeObserver(() => positionInspectorIndicator(inspectorTabs.querySelector("[aria-selected='true']"), true)).observe(inspectorTabs);
  document.fonts?.ready.then(() => positionInspectorIndicator(inspectorTabs.querySelector("[aria-selected='true']"), true));
  let inspectorTab = "details", inspectorArtifact = null;
  const inspectorScrolls = { details: 0, "ai-review": 0 };
  function selectInspector(tab, focus = false) {
    const selected = byId(`inspector-tab-${tab}`);
    if (!selected || selected.disabled) return;
    inspectorScrolls[inspectorTab] = inspectorScroll.scrollTop;
    inspectorTab = tab;
    for (const button of inspectorTabs.querySelectorAll("[role='tab']")) {
      const active = button === selected;
      button.setAttribute("aria-selected", String(active)); button.tabIndex = active ? 0 : -1;
      button.classList.toggle("mtrl-tab--active", active);
      byId(button.getAttribute("aria-controls")).hidden = !active;
    }
    positionInspectorIndicator(selected, !inspectorIndicatorReady);
    inspectorIndicatorReady = true;
    inspectorScroll.scrollTop = inspectorScrolls[tab];
    if (focus) selected.focus({ preventScroll: true });
  }
  for (const tab of inspectorTabs.querySelectorAll("[role='tab']"))
    tab.addEventListener("click", () => selectInspector(tab.dataset.inspector));
  inspectorTabs.addEventListener("keydown", event => {
    const tabs = [...inspectorTabs.querySelectorAll("[role='tab']")].filter(tab => !tab.disabled);
    const index = tabs.indexOf(document.activeElement);
    if (index < 0) return;
    const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
      event.key === "ArrowRight" ? (index + 1) % tabs.length :
        event.key === "ArrowLeft" ? (index - 1 + tabs.length) % tabs.length : null;
    if (next !== null) { event.preventDefault(); selectInspector(tabs[next].dataset.inspector, true); }
  });
  document.addEventListener("klaude-auth-reset", () => {
  knowledgeSource = ""; knowledgeChunkPage = null; knowledgeDeletePending = null; knowledgeOrigin = null;
    selectInspector("details"); inspectorArtifact = null;
    inspectorScrolls.details = inspectorScrolls["ai-review"] = 0;
  });
  let item = null, draftTags = [], editingTags = false, allTags = false;
  const removedAITags = new Set();
  let editingSource = false, suggestedTags = [], suggestionsSignature = "";
  const metadataChanges = new Map();
  const normalizeTag = value => value.trim().replace(/\s+/gu, " ");
  const tagKey = value => normalizeTag(value).toLocaleLowerCase();
  const retainedAITags = () => (item?.ai_tags || []).filter(tag => !removedAITags.has(tag));
  const tagsChanged = () => removedAITags.size > 0 || JSON.stringify(draftTags) !== JSON.stringify(item?.tags || []);
  const metadataKey = operation => `${item?.id}:${operation}`;
  const metadataBusy = () => [...metadataChanges.values()].some(change => change.target === item?.id);
  function editorStatus(operation) {
    const target = byId(operation === "tags" ? "artifact-tags-status" : "artifact-source-status");
    target.textContent = "";
    target.dataset.state = "";
  }
  function editorControls() {
    const busy = metadataBusy();
    for (const id of ["artifact-source-form", "artifact-tags"]) {
      byId(id).setAttribute("aria-busy", String(busy));
      for (const control of byId(id).querySelectorAll("input,button")) control.disabled = busy;
    }
    byId("artifact-source-input").disabled = busy;
    byId("artifact-source-edit").disabled = busy || latest?.library_source_links !== true;
    const sourcePlaceholder = byId("artifact-source").querySelector(".inspector-source-placeholder");
    if (sourcePlaceholder) sourcePlaceholder.disabled = busy || latest?.library_source_links !== true;
    byId("artifact-tags-edit").disabled = busy;
    byId("artifact-tags-save").disabled = busy || !editingTags || !tagsChanged();
  }
  async function saveMetadata(operation, value) {
    if (!item || metadataBusy() || reviewDialog.open) return;
    if (operation === "tags" && removedAITags.size && latest?.library_ai_tag_edit !== true) {
      editorStatus("tags", "Restart the Web UI host and reload to save AI tag removals. Your draft is kept.", true);
      return;
    }
    const key = metadataKey(operation), target = item, epoch = authEpoch;
    const change = { operation, target: target.id, phase: "preparing", request_id: null };
    metadataChanges.set(key, change);
    if (operation !== "source_link") editorStatus(operation, "Saving…");
    editorControls();
    const current = () => authenticated && epoch === authEpoch && item === target && artifactDialog.open;
    const canCommitMetadata = () => authenticated && epoch === authEpoch && metadataChanges.get(key) === change;
    try {
      const opened = await submitDirectChange({ operation, target: target.id, revision: target.revision, value,
        ...(operation === "tags" && removedAITags.size ? { remove_ai_tags: [...removedAITags] } : {}),
      }, {
        current: canCommitMetadata,
        onSubmitting: receipt => {
          change.phase = "submitting"; change.request_id = receipt.request_id;
          if (current()) editorControls();
        },
        onAccepted: receipt => {
          change.phase = "accepted"; change.request_id ||= receipt.request_id;
          if (current()) { if (operation !== "source_link") editorStatus(operation, "Saving…"); editorControls(); }
        },
        onDiscard: review => {
          if (epoch !== authEpoch) return;
          if (review.uncertain) { change.phase = "unknown"; change.request_id = review.request_id; }
          else metadataChanges.delete(key);
          if (current()) {
            editorStatus(operation, review.uncertain ? "Save unconfirmed. Your draft is kept; check Activity before trying again." :
              review.uncertain === false ? "Save failed. Your draft is kept." : "Save cancelled. Your draft is kept.", Boolean(review.uncertain !== undefined));
            editorControls();
          }
        },
      });
      if (!opened && metadataChanges.get(key) === change) metadataChanges.delete(key);
    } catch (error) {
      metadataChanges.delete(key);
      if (current()) editorStatus(operation, `${error.message || "Could not save."} Your draft is kept.`, true);
    } finally { if (current()) editorControls(); }
  }
  document.addEventListener("klaude-operations", async event => {
    for (const [key, change] of metadataChanges) {
      const receipt = event.detail.find(operation => operation.request_id === change.request_id);
      if (!receipt || change.phase === "refreshing" || !["completed", "failed", "cancelled", "unknown"].includes(receipt.state)) continue;
      if (receipt.state === "unknown") {
        change.phase = "unknown";
        if (item?.id === change.target) { editorStatus(change.operation, "Save unconfirmed. Your draft is kept; check Activity before trying again.", true); editorControls(); }
        continue;
      }
      if (receipt.state === "completed") artifactDetails.delete(change.target);
      if (!authenticated || item?.id !== change.target || !artifactDialog.open) { metadataChanges.delete(key); continue; }
      if (receipt.state !== "completed") {
        metadataChanges.delete(key); editorStatus(change.operation, "Could not save. Your draft is kept. The file may have changed; reopen it to inspect the current version.", true); editorControls(); continue;
      }
      change.phase = "refreshing";
      const epoch = authEpoch;
      try {
        const result = await domainRequest(`/api/v1/library/item?${new URLSearchParams({ id: change.target })}`);
        metadataChanges.delete(key);
        if (epoch !== authEpoch || item?.id !== change.target || !artifactDialog.open) continue;
        item = result.item; selectedArtifact = item;
        artifactDetails.set(item.id, { time: Date.now(), data: result });
        if (change.operation === "tags") { editingTags = false; byId("artifact-tag-new").value = ""; }
        else editingSource = false;
        if (!editingTags) { draftTags = [...item.tags]; removedAITags.clear(); }
        renderSource(); renderTags(); renderMenu();
        byId("artifact-download").href = artifactUrl(item);
        window.BrowserVision?.select(canPreviewImage(item) && !item.archived ? item : null);
        editorStatus(change.operation, "Saved."); editorControls();
      } catch (error) {
        change.phase = "unknown";
        if (epoch === authEpoch && item?.id === change.target) editorStatus(change.operation, "Save completed, but the updated file could not be read. Your draft is kept; reopen the file to inspect it.", true);
      }
    }
  });
  document.addEventListener("klaude-vision-suggestions", event => {
    const result = event.detail;
    suggestedTags = result && item && result.artifact === item.id && result.revision === item.revision ? result.tags : [];
    renderTagSuggestions();
  });
  document.addEventListener("klaude-auth-reset", () => {
  knowledgeSource = ""; knowledgeChunkPage = null; knowledgeDeletePending = null; knowledgeOrigin = null; metadataChanges.clear(); suggestedTags = []; editingSource = false; });
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
    if (phone.matches && state !== "closed") state = "full";
    if (state === "closed") closeMenu();
    artifactDialog.dataset.details = state;
    panel.inert = state === "closed";
    byId("image-details").hidden = state !== "closed";
    byId("preview-sidebar-toggle").setAttribute("aria-expanded", String(state !== "closed"));
    byId("image-details").setAttribute("aria-expanded", String(state !== "closed"));
    byId("image-details").setAttribute("aria-label", state === "closed" ? "Show file details" : "Hide file details");
    byId("image-details").title = state === "closed" ? "Show file details" : "Hide file details";
    byId("preview-sheet-handle").setAttribute("aria-label", phone.matches && state !== "closed" ? "Close file inspector" : "Expand file details");
    byId("preview-sheet-scrim").hidden = !phone.matches || state === "closed";
    artifactDialog.querySelector(".preview-main").inert = phone.matches && state !== "closed";
    if (focus && state === "closed") byId("image-details").focus({ preventScroll: true });
    else if (focus) {
      const previousFocus = document.activeElement;
      requestAnimationFrame(() => {
        if (artifactDialog.open && artifactDialog.dataset.details !== "closed" && document.activeElement === previousFocus)
          byId("preview-sheet-handle").focus({ preventScroll: true });
      });
    }
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
    byId("image-zoom-value").setAttribute("aria-label", `${Math.round(scale * 100)}% zoom. Fit image to screen`);
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
    byId("image-zoom-value").setAttribute("aria-label", "100% zoom. Fit image to screen");
    transform();
  }
  function review(operation, value) {
    if (!item) return;
    const target = item;
    closeMenu();
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
      menu.append(button);
    }
  }
  function renderTags() {
    byId("artifact-tag-new").setCustomValidity("");
    if (!byId("artifact-tag-new").value) byId("artifact-tag-new").style.width = "";
    const combined = [...draftTags.map(tag => ({ tag, manual: true })),
      ...retainedAITags().map(tag => ({ tag, manual: false }))];
    byId("artifact-tag-count").textContent = `(${combined.length})`;
    byId("artifact-tags-input").value = draftTags.join(", ");
    byId("artifact-tag-editor").hidden = !editingTags;
    byId("artifact-tags-edit").hidden = editingTags;
    byId("artifact-tags-edit").textContent = combined.length ? "Edit tags" : "+ Add tags";
    const shown = editingTags || allTags ? combined : combined.slice(0, 8);
    byId("artifact-tag-items").replaceChildren(...shown.map(({ tag, manual }) => {
      const chip = domainText("span", "", `preview-tag input-chip${manual ? "" : " tag-generated"}`);
      chip.title = manual ? "Manual tag" : "AI tag";
      const face = domainText("span", "", "filter-chip-face");
      face.append(domainText("span", tag, "input-chip-label")); chip.append(face);
      if (editingTags) {
        const remove = domainButton("", () => {
          if (manual) draftTags = draftTags.filter(value => value !== tag);
          else removedAITags.add(tag);
          editorStatus("tags"); renderTags(); byId("artifact-tag-new").focus();
        }, "icon-button");
        remove.setAttribute("aria-label", `Remove tag ${tag}`);
        remove.append(libraryIcon("close")); chip.append(remove);
      }
      return chip;
    }));
    byId("artifact-tag-draft").hidden = !editingTags;
    if (!combined.length && !editingTags) byId("artifact-tag-items").append(domainText("p", "No tags yet.", "muted"));
    const moreTags = byId("artifact-tags-more");
    moreTags.hidden = editingTags || combined.length <= 8;
    moreTags.textContent = allTags ? "Show less" : `Show all ${combined.length} tags`;
    moreTags.setAttribute("aria-expanded", String(allTags));
    renderTagSuggestions(); editorControls();
  }
  function renderTagSuggestions() {
    const offered = suggestedTags.filter(tag => ![...draftTags, ...retainedAITags()].some(existing => tagKey(existing) === tagKey(tag)));
    const signature = JSON.stringify([editingTags, offered]);
    if (signature === suggestionsSignature) return;
    suggestionsSignature = signature;
    byId("artifact-tag-suggestions").hidden = !editingTags || !offered.length;
    byId("artifact-tag-suggestion-list").replaceChildren(...offered.map(tag => {
      const button = domainButton("", () => addTag(tag), "filter-chip tag-suggestion");
      const face = domainText("span", `+ ${tag}`, "filter-chip-face"); button.append(face);
      button.setAttribute("aria-label", `Add suggested tag ${tag}`); return button;
    }));
    editorControls();
  }
  function addTag(suggestion) {
    const input = byId("artifact-tag-new");
    if (metadataBusy()) return false;
    const values = [...draftTags];
    for (const value of (typeof suggestion === "string" ? suggestion : input.value).split(",").map(normalizeTag).filter(Boolean))
      if (![...values, ...retainedAITags()].some(tag => tagKey(tag) === tagKey(value))) values.push(value);
    if (values.length > 20 || values.some(value => Array.from(value).length > 40 || /[\x00-\x1f\x7f-\x9f]/.test(value))) {
      editorStatus("tags");
      input.setCustomValidity("Use up to 20 printable tags of at most 40 characters."); input.reportValidity(); return false;
    }
    editorStatus("tags"); input.setCustomValidity(""); draftTags = values;
    if (typeof suggestion !== "string") input.value = "";
    renderTags(); return true;
  }
  function resizeSourceEditor() {
    const input = byId("artifact-source-input");
    input.style.height = "auto"; input.style.height = `${input.scrollHeight}px`;
  }
  function editSource() {
    editingSource = true; editorStatus("source_link");
    byId("artifact-source-input").value = item.source_url || "";
    renderSource();
    resizeSourceEditor();
    byId("artifact-source-input").focus();
  }
  function renderSource() {
    const source = byId("artifact-source");
    source.replaceChildren(); source.hidden = editingSource;
    byId("artifact-source-form").hidden = !editingSource;
    byId("artifact-source-edit").hidden = editingSource;
    byId("artifact-source-edit").textContent = item?.source_url ? "Edit source" : "+ Add source";
    if (editingSource) {
      byId("artifact-source-edit").title = latest?.library_source_links === true ? "" : "Restart the WebUI host to edit source links";
      editorControls();
      return;
    }
    if (item.source_url) {
      const note = domainText("p", "", "muted inspector-source-note");
      for (const part of item.source_url.split(/(https?:\/\/[^\s<>"']+)/giu)) {
        let url;
        try {
          url = new URL(part);
          if (!/^https?:\/\//i.test(part) || !["http:", "https:"].includes(url.protocol) || !url.hostname || url.username || url.password || url.port === "0" || /[\s\\]/u.test(part)) url = null;
        } catch { url = null; }
        if (!url) { note.append(document.createTextNode(part)); continue; }
        const link = domainText("a", part, "inspector-source-reference");
        link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
        link.title = part; note.append(link);
      }
      source.append(note);
    } else {
      const placeholder = domainButton("No source link added.", editSource, "inspector-source-placeholder");
      placeholder.setAttribute("aria-label", "Add source notes or a link");
      source.append(placeholder);
    }
    byId("artifact-source-edit").title = latest?.library_source_links === true ? "" : "Restart the WebUI host to edit source links";
    editorControls();
  }
  function renderTextControls(text, source = "", markdown = false) {
    const controls = byId("preview-text-controls");
    controls.replaceChildren();
    controls.hidden = !text;
    if (!text) return;
    let mode = "source";
    let renderedMarkdown = null;
    const showMode = value => {
      mode = value;
      if (mode === "preview") {
        renderedMarkdown ||= ChatMarkdown.renderDocument(source);
        preview.replaceChildren(renderedMarkdown);
      } else preview.replaceChildren(text);
      preview.scrollTop = preview.scrollLeft = 0;
      for (const button of controls.querySelectorAll("[data-mode]")) button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
      preview.setAttribute("aria-label", mode === "preview" ? "Markdown preview" : "File source preview");
    };
    if (markdown && window.ChatMarkdown?.renderDocument) {
      const modes = domainText("div", "", "preview-wrap-options");
      modes.setAttribute("role", "group"); modes.setAttribute("aria-label", "Markdown view");
      for (const [value, label] of [["preview", "Preview"], ["source", "Source"]]) {
        const button = domainButton(label, () => showMode(value));
        button.dataset.mode = value; button.id = `artifact-mode-${value}`;
        button.setAttribute("aria-controls", "artifact-preview");
        button.setAttribute("aria-pressed", String(value === mode)); modes.append(button);
      }
      controls.append(modes);
    }
    const wrapping = domainText("div", "", "preview-wrap-options");
    wrapping.setAttribute("role", "group");
    wrapping.setAttribute("aria-label", "Line wrapping");
    const setWrap = value => {
      text.dataset.wrap = String(value);
      preview.dataset.wrap = String(value);
      for (const button of wrapping.children) button.setAttribute("aria-pressed", String(button.dataset.wrap === text.dataset.wrap));
      if (value) preview.scrollLeft = 0;
    };
    for (const [value, label, id] of [[true, "Wrap", "artifact-wrap"], [false, "No wrap", "artifact-no-wrap"]]) {
      const button = domainButton(label, () => setWrap(value));
      button.id = id; button.dataset.wrap = String(value);
      button.setAttribute("aria-controls", "artifact-preview");
      wrapping.append(button);
    }
    setWrap(true);
    let copying = false;
    const copy = domainButton("", async () => {
      if (copying) return;
      copying = true;
      copy.setAttribute("aria-busy", "true");
      const success = await ChatMarkdown.copyText(source, artifactDialog);
      if (!copy.isConnected || !artifactDialog.open) return;
      copying = false;
      copy.removeAttribute("aria-busy");
      copy.replaceChildren(libraryIcon(success ? "check" : "copy"), domainText("span", success ? "Copied" : "Copy"));
      notice(success ? "Preview text copied." : "Copy unavailable. Select the preview text and copy it using your browser.");
      if (success) setTimeout(() => {
        if (copy.isConnected) copy.replaceChildren(libraryIcon("copy"), domainText("span", "Copy"));
      }, 1800);
    }, "quiet preview-copy-button");
    copy.id = "artifact-copy";
    copy.title = "Copy preview text";
    copy.setAttribute("aria-label", "Copy preview text");
    copy.append(libraryIcon("copy"), domainText("span", "Copy"));
    controls.append(wrapping, copy);
    if (markdown && window.ChatMarkdown?.renderDocument) showMode("preview");
  }
  function render(data) {
    const chat = data.chat_attachment === true;
    item = data.item; editingTags = allTags = editingSource = false; draftTags = [...item.tags]; removedAITags.clear();
    suggestedTags = []; editorStatus("tags"); editorStatus("source_link");
    const image = canPreviewImage(item);
    artifactDialog.classList.toggle("is-image", image);
    byId("artifact-detail-title").textContent = item.name;
    byId("artifact-detail-title").title = item.name;
    const language = sourceLanguage(item);
    byId("artifact-subtitle").textContent = `${chat ? "Chat attachment" : librarySection === "outputs" ? "Generated" : "Uploads"} · ${image ? "Image" : language === "text" ? fileType(item)[1] : language.toUpperCase()} · ${fileSize(item.size)}`;
    const source = typeof data.source_text === "string" ? data.source_text : data.lines.join("\n");
    const readable = !image && !data.fallback && (typeof data.source_text === "string" || data.lines.length > 0);
    const nodes = image ? [artifactImage(item, true, data.preview_url)] : readable ? [numberedSource(source, language)] :
      [domainText("p", "Preview unavailable for this file type. Download the original file to open it.", "preview-unavailable")];
    preview.replaceChildren(...nodes);
    const truncated = data.source_truncated ?? data.truncated;
    byId("preview-truncation").textContent = !image && truncated ? "Preview truncated. Download for the complete file." : "";
    byId("preview-source-note").textContent = data.thumbnail_only ? "Only a thumbnail was retained for this older attachment." :
      data.extracted ? "Extracted text preview. Download the original document for its layout." :
        !image && data.source_sanitized ? "Unsafe control characters or invalid text were replaced in this preview. Download preserves the original bytes." : "";
    renderTextControls(readable ? nodes[0] : null, source, language === "markdown");
    preview.querySelector("img")?.addEventListener("load", transform, { once: true });
    resetZoom();
    const rows = [["Filename", item.filename], ["Type", fileType(item)[1]], ["MIME type", item.mime], ["Size", `${fileSize(item.size)} (${item.size.toLocaleString()} bytes)`],
      ...(item.width && item.height ? [["Dimensions", `${item.width.toLocaleString()} × ${item.height.toLocaleString()} px`]] : []),
      ...(Number.isFinite(item.created) ? [[chat ? "Sent" : "Added", new Date(item.created * 1000).toLocaleString()]] : []),
      ...(item.archived ? [["Status", "Archived"]] : [])];
    byId("artifact-metadata").replaceChildren(...rows.flatMap(([label, value]) => [domainText("dt", label), domainText("dd", value)]));
    panel.querySelector(".preview-source").hidden = chat;
    panel.querySelector(".preview-tags-section").hidden = chat;
    inspectorTabs.hidden = chat; more.hidden = chat;
    if (!chat) { renderSource(); renderTags(); renderMenu(); }
    else menu.replaceChildren();
    byId("inspector-tab-ai-review").disabled = chat || !image || item.archived;
    byId("inspector-tab-ai-review").title = image && !item.archived ? "" : "AI Review is available for saved images.";
    if (inspectorArtifact !== item.id) {
      inspectorArtifact = item.id; inspectorScrolls.details = inspectorScrolls["ai-review"] = 0;
      inspectorScroll.scrollTop = 0;
    }
    selectInspector(!chat && image && !item.archived ? inspectorTab : "details");
    window.BrowserVision?.select(!chat && image && !item.archived ? item : null);
    byId("artifact-learn").hidden = chat || !latest?.profile_management || image || item.archived || item.size > 2 * 1024 * 1024;
    byId("artifact-learn-library").value = byId("knowledge-library").value || "";
    byId("artifact-tags").hidden = chat;
    byId("image-toolbar").hidden = false;
    byId("image-lens").hidden = !image;
    byId("artifact-download").hidden = chat && !data.download_url;
    artifactDialog.querySelector(".preview-zoom-controls").hidden = !image;
    byId("artifact-download").href = chat ? data.download_url || "" : artifactUrl(item);
    byId("artifact-download").download = item.filename;
    byId("artifact-actions").replaceChildren();
    preview.setAttribute("aria-label", image ? "Image preview" : language === "markdown" ? "Markdown preview" : "File source preview");
    more.disabled = chat; notice("");
  }
  function begin(image, opening) {
    window.BrowserLens?.reset();
    window.BrowserVision?.select(null);
    item = null; closeMenu(); resetZoom(); notice("");
    renderTextControls(null);
    byId("artifact-subtitle").textContent = "";
    byId("preview-truncation").textContent = ""; byId("preview-source-note").textContent = "";
    preview.scrollTop = preview.scrollLeft = 0;
    if (document.activeElement === more) preview.focus({ preventScroll: true });
    more.disabled = true;
    artifactDialog.classList.toggle("is-image", Boolean(image));
    byId("artifact-metadata").replaceChildren(); byId("artifact-source").replaceChildren();
    byId("artifact-source-form").hidden = true;
    editingSource = false; suggestedTags = []; editorStatus("tags"); editorStatus("source_link");
    byId("artifact-learn").hidden = true;
    byId("artifact-tag-new").value = "";
    byId("artifact-tag-new").setCustomValidity("");
    byId("artifact-tag-count").textContent = "";
    byId("image-toolbar").hidden = true;
    if (opening) { setDetails(phone.matches ? "closed" : "partial"); }
  }
  for (const [id, icon] of [["artifact-close", "close"], ["artifact-more", "more"], ["image-zoom-out", "minus"], ["image-zoom-in", "plus"], ["artifact-download", "download"], ["image-details", "info"], ["preview-sidebar-toggle", "sidebar"]]) byId(id).append(libraryIcon(icon));
  byId("image-details").append(domainText("span", "Details"));
  byId("image-zoom-in").onclick = () => zoom(scale * 1.5);
  byId("image-zoom-out").onclick = () => zoom(scale / 1.5);
  byId("image-zoom-value").onclick = resetZoom;
  byId("image-details").onclick = () => setDetails(artifactDialog.dataset.details === "closed" ? "partial" : "closed", true);
  byId("preview-sidebar-toggle").onclick = () => setDetails("closed", true);
  byId("preview-sheet-scrim").onclick = () => setDetails("closed", true);
  byId("preview-sheet-handle").onclick = event => { if (event.detail && sheetStart === undefined) return; setDetails(phone.matches ? "closed" : artifactDialog.dataset.details === "full" ? "partial" : "full", true); };
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
  byId("artifact-source-title").prepend(libraryIcon("link"));
  byId("artifact-tags-title").prepend(libraryIcon("tags"));
  byId("artifact-tag-add").append(libraryIcon("plus"));
  byId("artifact-tags-edit").onclick = () => { editingTags = true; draftTags = [...item.tags]; removedAITags.clear(); editorStatus("tags"); renderTags(); byId("artifact-tag-new").focus(); };
  byId("artifact-tags-cancel").onclick = () => { editingTags = false; draftTags = [...item.tags]; removedAITags.clear(); byId("artifact-tag-new").value = ""; editorStatus("tags"); renderTags(); byId("artifact-tags-edit").focus(); };
  byId("artifact-tags-more").onclick = () => { allTags = !allTags; renderTags(); };
  byId("artifact-tag-add").onclick = addTag;
  byId("artifact-tag-new").addEventListener("input", event => { event.target.setCustomValidity(""); event.target.style.width = `${Math.max(3, Math.min(24, Array.from(event.target.value).length + 1))}ch`; editorStatus("tags"); });
  byId("artifact-tag-new").addEventListener("blur", () => { if (editingTags && byId("artifact-tag-new").value.trim()) addTag(); });
  byId("artifact-tag-new").addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); addTag(); } });
  byId("artifact-source-edit").onclick = editSource;
  byId("artifact-source-input").addEventListener("input", event => { event.target.setCustomValidity(""); resizeSourceEditor(); editorStatus("source_link"); editorControls(); });
  const commitSourceLink = () => {
    const input = byId("artifact-source-input"), value = input.value.trim();
    if (!item || !editingSource || metadataBusy()) return;
    if (value === (item.source_url || "")) {
      editingSource = false; renderSource(); return;
    }
    if (Array.from(value).length > 2048 || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/u.test(value)) return;
    saveMetadata("source_link", value);
  };
  byId("artifact-source-input").addEventListener("keydown", event => {
    if (event.key === "Escape") {
      event.preventDefault(); event.stopPropagation(); editingSource = false; byId("artifact-source-input").value = item?.source_url || "";
      editorStatus("source_link"); renderSource(); byId("artifact-source-edit").focus();
    } else if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault(); commitSourceLink();
    }
  });
  byId("artifact-source-input").addEventListener("blur", commitSourceLink);
  byId("artifact-source-form").addEventListener("submit", event => {
    event.preventDefault(); commitSourceLink();
  });
  byId("artifact-learn").addEventListener("submit", event => {
    event.preventDefault();
    if (!item) return;
    const draft = { operation: "artifact-learn", target: item.id, revision: item.revision, library: byId("artifact-learn-library").value.trim() };
    artifactDialog.close();
    prepareChange(draft).catch(error => domainError(error));
  });
  byId("artifact-tags").addEventListener("submit", event => {
    event.preventDefault();
    if (!item || !editingTags || !addTag() || !tagsChanged()) return;
    saveMetadata("tags", draftTags.join(", "));
  });
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
  preview.addEventListener("dblclick", event => { if (artifactDialog.classList.contains("is-image")) event.preventDefault(); });
  preview.addEventListener("wheel", event => { if (!preview.querySelector("img") || !event.ctrlKey) return; event.preventDefault(); zoom(scale * Math.exp(-event.deltaY * .01), event.clientX, event.clientY); }, { passive: false });
  artifactDialog.addEventListener("cancel", event => {
    if (more.getAttribute("aria-expanded") === "true") { event.preventDefault(); closeMenu(true); }
    else if (editingTags) { event.preventDefault(); byId("artifact-tags-cancel").click(); }
    else if (phone.matches && artifactDialog.dataset.details !== "closed") { event.preventDefault(); setDetails("closed", true); }
  });
  artifactDialog.addEventListener("keydown", event => {
    if (event.key === "Escape" && editingTags) {
      event.preventDefault(); event.stopPropagation(); byId("artifact-tags-cancel").click(); return;
    }
    if (event.key !== "Escape" || !phone.matches || artifactDialog.dataset.details === "closed") return;
    event.preventDefault(); event.stopPropagation(); setDetails("closed", true);
  });
  return { begin, render, reset: () => { closeMenu(); resetZoom(); renderTextControls(null);
    window.BrowserVision?.select(null);
    for (const id of ["artifact-subtitle", "preview-truncation", "preview-source-note"]) byId(id).textContent = "";
    item = null; draftTags = []; removedAITags.clear(); byId("artifact-source-input").value = ""; byId("artifact-tag-new").value = ""; byId("artifact-source-form").hidden = true; byId("artifact-learn-library").value = ""; byId("artifact-learn").hidden = true; setDetails("closed"); },
    key: event => {
      if (event.target.closest(".preview-information, #artifact-menu") || !preview.querySelector("img")) return false;
      if (["+", "=", "-", "0", "f", "F"].includes(event.key)) { event.preventDefault(); if (["0", "f", "F"].includes(event.key)) resetZoom(); else zoom(scale * (event.key === "-" ? 1 / 1.5 : 1.5)); return true; }
      if (scale > 1 && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) { event.preventDefault(); panX += event.key === "ArrowLeft" ? 60 : event.key === "ArrowRight" ? -60 : 0; panY += event.key === "ArrowUp" ? 60 : event.key === "ArrowDown" ? -60 : 0; transform(); return true; }
      return false;
    } };
})();

async function openArtifact(id, { origin = null, item = null } = {}) {
  delete artifactDialog.dataset.chatAttachment;
  artifactRead?.abort(); artifactRead = new AbortController();
  const load = ++artifactLoad, opening = !artifactDialog.open;
  if (opening) contextPreviewOrigin = origin;
  const known = item || imageSequence.find(item => item.id === id) || filePage?.items.find(item => item.id === id);
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
    if (error.name !== "AbortError") preview.replaceChildren(domainText("p", error.message || "Could not load this item.", "preview-unavailable"));
    if (error.status === 401) showLocalAccess();
  } finally { finish(); }
}
async function openChatAttachment({ session, message, file, descriptor, origin, created }) {
  if (!authenticated || latest?.session_id !== session || !/^stored:[1-9]\d{0,18}$/.test(message)) return;
  if (latest.attachment_content !== true && descriptor.artifact_id)
    return openArtifact(descriptor.artifact_id, { origin });
  artifactRead?.abort(); artifactRead = new AbortController();
  const load = ++artifactLoad, opening = !artifactDialog.open;
  contextPreviewOrigin = origin; artifactDialog.dataset.chatAttachment = session;
  selectedArtifact = null;
  artifactViewer.begin(descriptor.image, opening);
  byId("artifact-detail-title").textContent = descriptor.name;
  byId("artifact-detail-title").title = descriptor.name;
  byId("artifact-actions").replaceChildren(); byId("artifact-tags").hidden = true;
  byId("image-navigation").hidden = true;
  const preview = byId("artifact-preview");
  const finish = beginLoading(preview, { kind: "detail", count: 1, preserve: false, label: "Loading attachment…" });
  if (opening) artifactDialog.showModal();
  const url = view => "/api/v1/chat/attachments/content?" + new URLSearchParams({ session, message, file, view });
  try {
    let data;
    if (latest.attachment_content === true) {
      data = await domainRequest(url("info"), "GET", undefined, { signal: artifactRead.signal });
      data.preview_url = descriptor.image ? url("image") : "";
      data.download_url = data.thumbnail_only ? "" : url("download");
    } else if (descriptor.image && descriptor.preview) {
      data = { item: { ...descriptor, filename: descriptor.name, width: 128, height: 128 }, lines: [], thumbnail_only: true,
        preview_url: "/api/v1/chat/attachments/preview?" + new URLSearchParams({ session, message, file }) };
    } else throw new Error("Restart Web UI and reload to preview attached files.");
    if (load !== artifactLoad || !artifactDialog.open || latest?.session_id !== session) return;
    data.chat_attachment = true;
    data.item = { ...data.item, id: `chat:${session}:${message}:${file}`, revision: 0,
      name: descriptor.name, filename: descriptor.name, kind: descriptor.image ? "media" : "document",
      tags: [], ai_tags: [], archived: false, created };
    artifactViewer.render(data);
  } catch (error) {
    if (load !== artifactLoad || !artifactDialog.open || latest?.session_id !== session) return;
    if (error.name !== "AbortError") preview.replaceChildren(domainText("p", error.message || "Could not load this attachment.", "preview-unavailable"));
    if (error.status === 401) showLocalAccess();
  } finally { finish(); }
}
document.addEventListener("klaude-chat-session-changed", () => {
  if (artifactDialog.open && artifactDialog.dataset.chatAttachment) artifactDialog.close();
});
byId("artifact-close").addEventListener("click", () => artifactDialog.close());
artifactDialog.addEventListener("close", () => {
  if (artifactDialog.open) return;
  artifactLoad += 1; selectedArtifact = null; artifactRead?.abort(); artifactViewer.reset();
  byId("image-navigation").hidden = true;
  cancelLoading(byId("artifact-preview")); byId("artifact-preview").replaceChildren();
  for (const card of document.querySelectorAll(".file-selected")) { card.classList.remove("file-selected"); card.querySelector("button")?.removeAttribute("aria-current"); }
  const contextOrigin = contextPreviewOrigin; contextPreviewOrigin = null;
  delete artifactDialog.dataset.chatAttachment;
  if (contextOrigin && authenticated) {
    (contextOrigin.isConnected && !contextOrigin.closest("[inert], [hidden]") ? contextOrigin :
      contextOrigin.closest("#inspector") ? byId("inspector-toggle") : byId("prompt")).focus({ preventScroll: true });
  } else if (authenticated && currentView === "library") {
    byId("library-view").scrollTop = previewScroll;
    if (!previewOrigin?.isConnected) previewOrigin = [...document.querySelectorAll(".file-item")].find(card => card.dataset.fileId === previewOriginId)?.querySelector("button");
    (previewOrigin || byId("library-refresh")).focus({ preventScroll: true });
  }
});

function updateImageNavigation() {
  if (contextPreviewOrigin) { byId("image-navigation").hidden = true; return; }
  const index = imageSequence.findIndex(item => item.id === selectedArtifact?.id);
  const image = selectedArtifact && isLibraryImage(selectedArtifact);
  byId("image-navigation").hidden = !image;
  const paged = fileView === "gallery";
  byId("image-position").textContent = index >= 0 ?
    `${(paged ? imageSequenceOffset : 0) + index + 1} / ${imageSequenceTotal}` : image ? "Image preview" : "";
  byId("image-previous").disabled = previewNavigation || index < 0 ||
    index === 0 && (!paged || imageSequenceOffset === 0);
  byId("image-next").disabled = previewNavigation || index < 0 ||
    index === imageSequence.length - 1 && (!paged || imageSequenceOffset + imageSequence.length >= imageSequenceTotal);
}
async function nextImage(direction) {
  if (contextPreviewOrigin) return;
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
artifactDialog.addEventListener("keydown", event => {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) || event.altKey || event.ctrlKey || event.metaKey) return;
  if (artifactViewer.key(event) || event.target.closest(".preview-information, #artifact-menu")) return;
  if (byId("image-navigation").hidden) return;
  if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
    const direction = event.key === "ArrowRight" ? "next" : "previous";
    if (!byId(`image-${direction}`).disabled) { event.preventDefault(); nextImage(direction === "next" ? 1 : -1); }
  }
});

async function loadKnowledgeSources() {
  sourceRead?.abort(); sourceRead = new AbortController();
  const signal = sourceRead.signal, library = byId("knowledge-library").value;
  const load = ++sourcesLoad;
  if (!library) { byId("knowledge-sources").hidden = true; return; }
  if (sourceLocationPage !== null) { sourceOffset = (sourceLocationPage - 1) * 20; sourceLocationPage = null; }
  const offset = sourceOffset, grid = byId("source-items"), key = JSON.stringify([library, offset]);
  const finish = beginLoading(grid, { kind: "rows", count: 3, preserve: grid.dataset.contentKey === key, label: "Loading sources…" });
  byId("knowledge-sources").hidden = false;
  byId("knowledge-all-sources").setAttribute("aria-pressed", String(!knowledgeSource));
  try {
    const data = await knowledgeRequest("/api/v1/library/knowledge/sources", { library, offset }, { signal });
    if (load !== sourcesLoad || !authenticated || currentView !== "integrations" || integrationSection !== "knowledge" || library !== byId("knowledge-library").value) return;
    if (!data.items.length && offset > 0) { sourceOffset = Math.max(0, Math.ceil(data.total / 20) - 1) * 20; return loadKnowledgeSources(); }
    reconcileRows(grid, data.items.map(source => {
      knowledgeSourceNames.set(source.id, source.source_name || source.id);
      while (knowledgeSourceNames.size > 100) knowledgeSourceNames.delete(knowledgeSourceNames.keys().next().value);
      const card = collectionRow(source.id, source.source_name || source.id, countLabel(source.chunks, "chunk"), "text",
        () => knowledgeLocation(library, source.id), JSON.stringify([source, source.id === knowledgeSource]));
      card.classList.add("source-row");
      card.firstChild.setAttribute("aria-pressed", String(source.id === knowledgeSource));
      card.firstChild.title = source.id;
      for (const managed of source.refresh || []) {
        const refresh = domainButton("", () => prepareChange({ operation: "knowledge-refresh",
          library, source: managed.id, source_identity: managed.identity }).catch(error => domainError(error, "knowledge-status")),
        "icon-button quiet refresh-button");
        const label = `Review refresh for ${managed.id}`;
        refresh.setAttribute("aria-label", label); refresh.title = label; refresh.append(libraryIcon("refresh"));
        card.append(refresh);
      }
      return card;
    }));
    byId("knowledge-all-sources").textContent = `All sources · ${data.summary.chunks.toLocaleString()} chunks`;
    updateDomainPager("sources", offset, data);
    if (data.total <= 20) byId("sources-pages").hidden = true;
    grid.dataset.contentKey = key; grid.dataset.library = library;
    knowledgeHeading();
    rememberIntegrationLocation(true);
  } catch (error) { if (load === sourcesLoad && error.name !== "AbortError") domainError(error, "knowledge-status"); }
  finally { finish(); }
}
byId("knowledge-all-sources").addEventListener("click", () => knowledgeLocation(byId("knowledge-library").value));
byId("sources-next").addEventListener("click", () => { sourceOffset += 20; rememberIntegrationLocation(); loadKnowledgeSources(); });
byId("sources-previous").addEventListener("click", () => { sourceOffset = Math.max(0, sourceOffset - 20); rememberIntegrationLocation(); loadKnowledgeSources(); });
byId("knowledge-library").addEventListener("change", () => knowledgeLocation(byId("knowledge-library").value));
function searchKnowledge() {
  clearTimeout(knowledgeSearchTimer);
  if (!authenticated || currentView !== "integrations" || integrationSection !== "knowledge") return;
  knowledgeQuery = byId("knowledge-query").value.trim();
  knowledgeOffset = 0; knowledgeLocationPage = null;
  rememberIntegrationLocation(); loadKnowledge();
}
byId("knowledge-search").addEventListener("submit", event => { event.preventDefault(); searchKnowledge(); });
byId("knowledge-query").addEventListener("input", () => {
  clearTimeout(knowledgeSearchTimer); knowledgeRead?.abort(); knowledgeLoad++;
  knowledgeSearchTimer = setTimeout(searchKnowledge, 250);
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
function discardStagedUpload(upload_id, epoch = authEpoch) {
  // This existing owner-scoped route accepts a staged upload independently of a chat selection.
  if (authenticated && epoch === authEpoch) jsonRequest("/api/v1/chat/attachments/discard", "POST",
    { upload_id }).catch(() => {});
}
async function prepareChange(draft, { current = () => true, beforeOpen = () => {}, onAccepted, onDiscard, filename = "", downloadDestination = "" } = {}) {
  const result = await domainRequest("/api/v1/library/review", "POST", { draft });
  if (!current()) {
    domainRequest("/api/v1/library/discard", "POST", { review_id: result.review_id }).catch(() => {});
    return;
  }
  managementReview = { ...result, request_id: requestId(), onAccepted, onDiscard };
  const destructive = ["delete", "model-delete", "model-connection-remove", "skill-delete", "memory-delete", "mcp-remove", "session-delete", "knowledge-delete"].includes(draft.operation);
  const ai = ["vision-analyze", "vision-tags"].includes(draft.operation), tags = draft.operation === "vision-tags";
  const download = draft.operation === "model-pull";
  reviewDialog.classList.toggle("model-download-confirmation", download);
  reviewDialog.classList.toggle("ai-confirmation", ai);
  byId("domain-review-title").textContent = download ? "Download model?" : ai ? tags ? "Suggest image tags?" : "Review image?" : destructive ?
    draft.operation === "knowledge-delete" ? draft.source ? "Delete this source?" : "Delete this knowledge?" : draft.operation === "delete" ? "Delete file permanently?" : "Remove this item?" : "Review change";
  byId("domain-review-confirm").textContent = download ? "Download" : ai ? tags ? "Suggest tags" : "Review image" : destructive ? "Delete permanently" : "Confirm";
  byId("domain-review-confirm").classList.toggle("danger", destructive);
  byId("domain-review-summary").textContent = download ? "" : ai ? tags ? "Klaude will analyze this image and suggest tags for you to review." :
    "Klaude will analyze this image to answer your question." : result.summary;
  byId("domain-review-target").hidden = !ai && !download;
  byId("domain-review-target").textContent = ai ? filename : "";
  byId("domain-review-target").title = ai ? filename : "";
  if (download) {
    const target = byId("domain-review-target"), rows = document.createElement("dl");
    const model = String(draft.model || ""), split = model.startsWith("hf.co/") ? model.lastIndexOf(":") : -1;
    const fields = split > 0 ? [["Model", model.slice(0, split)], ["File", model.slice(split + 1)]] : [["Model", model]];
    fields.push(["Server", downloadDestination || draft.connection]);
    for (const [label, value] of fields) {
      const term = document.createElement("dt"), description = document.createElement("dd");
      term.textContent = label; description.textContent = value; rows.append(term, description);
    }
    target.replaceChildren(rows);
  }
  byId("domain-review-notice").hidden = !ai;
  byId("domain-review-notice").textContent = ai ? "Image data will be sent to the configured model provider(s). Provider charges may apply." +
    (tags ? " Suggested tags are not saved automatically." : "") : "";
  byId("domain-review-technical").hidden = !ai && !download;
  byId("domain-review-technical").querySelector("summary").textContent = download ? "More details" : "Technical details";
  byId("domain-review-technical").open = false;
  byId("domain-review-technical-summary").textContent = ai || download ? result.summary : "";
  byId("domain-review-status").textContent = ai || download ? "" : "Changes begin only after confirmation. Accepted work continues if you leave this page.";
  byId("domain-review-confirm").disabled = false;
  beforeOpen();
  reviewDialog.showModal();
  byId("domain-review-cancel").focus();
  return managementReview;
}

async function submitDirectChange(draft, { current = () => true, onSubmitting, onAccepted, onDiscard } = {}) {
  if (!["skill-enabled", "mcp-enable", "mcp-disable", "session-rename", "source_link", "tags", "vision-tags", "vision-analyze"].includes(draft.operation))
    throw new Error("This action requires confirmation");
  // The click, inline commit, or rename submission is the owner's action. Keep exact snapshot,
  // revision checks and durable submission without opening a confirmation dialog.
  const prepared = await domainRequest("/api/v1/library/review", "POST", { draft });
  const discard = () => domainRequest("/api/v1/library/discard", "POST", { review_id: prepared.review_id }).catch(() => {});
  if (!current()) { discard(); return; }
  const receipt = { ...prepared, request_id: requestId() };
  onSubmitting?.(receipt);
  try {
    const operation = await domainRequest("/api/v1/library/submit", "POST", {
      review_id: receipt.review_id, request_id: receipt.request_id,
    });
    receipt.accepted = true;
    onAccepted?.(operation);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    receipt.uncertain = error.status === undefined || error.status >= 500;
    if (!receipt.uncertain) { discard(); throw error; }
    // A lost acknowledgement may already have changed storage. Preserve its
    // request ID and pending lock; polling can resolve the original receipt.
    onDiscard?.(receipt);
  }
  await loadOperations();
  return receipt;
}

reviewDialog.addEventListener("close", () => {
  const old = managementReview;
  managementReview = null;
  if (old && authenticated && !old.accepted) {
    domainRequest("/api/v1/library/discard", "POST", { review_id: old.review_id }).catch(() => {});
    old.onDiscard?.(old);
  }
});
byId("domain-review-confirm").addEventListener("click", async () => {
  if (!managementReview || !latest) return;
  const review = managementReview;
  const epoch = authEpoch;
  const sourceSession = latest.session_id;
  const current = () => managementReview === review && authenticated && epoch === authEpoch;
  byId("domain-review-confirm").disabled = true;
  try {
    const operation = await domainRequest("/api/v1/library/submit", "POST", {
      review_id: review.review_id, request_id: review.request_id,
    });
    review.accepted = true;
    review.onAccepted?.(operation);
    if (current()) {
      reviewDialog.close();
      for (const id of ["artifact-file", "learn-file", "skill-file"]) byId(id).value = "";
      const target = activeDomainStatus();
      byId(target).textContent = `Accepted · ${operation.kind}. Track progress in Activity.`;
      if (operation.session_id && operation.session_id !== sourceSession) {
        showView("chat");
        toggleSessions(false);
        await snapshot().catch(showError);
        if (authenticated && epoch === authEpoch) {
          rememberLinkedSession();
          await refreshSessions().catch(showError);
        }
      }
    }
    await loadOperations();
  } catch (error) {
    review.uncertain = error.status === undefined || error.status >= 500;
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
    const epoch = authEpoch, generation = integrationAddGeneration, importVersion = importGeneration;
    const current = () => epoch === authEpoch && authenticated && (statusId !== "integration-add-status" ||
      integrationAddDialog.open && generation === integrationAddGeneration) &&
      (id !== "artifact-import" || importVersion === importGeneration && importDialog.open);
    button.disabled = true;
    byId(statusId).textContent = "Preparing review…";
    try { await action(); if (current()) byId(statusId).textContent = "Ready for review."; }
    catch (error) { if (current()) domainError(error, statusId); }
    finally { button.disabled = false; }
  });
}
bindUploadForm("artifact-import", async () => {
  const generation = importGeneration, epoch = authEpoch, batch = droppedImports;
  const current = () => importDialog.open && generation === importGeneration &&
    authenticated && epoch === authEpoch && currentView === "library" && librarySection === "files";
  if (!current()) return;
  const upload_id = await uploadForReview(byId("artifact-file").files[0]);
  if (!current()) { discardStagedUpload(upload_id, epoch); return; }
  if (current()) await prepareChange({ operation: "import", upload_id }, {
    current, beforeOpen: () => {
      if (batch) {
        batch.reviewing = true;
        byId("domain-review-status").textContent = `File ${batch.index + 1} of ${batch.files.length}. Each file is imported only after confirmation. Cancel stops the remaining files.`;
      }
      importDialog.close();
    },
    onAccepted: operation => {
      if (batch) { batch.accepted = true; batch.receipt = operation; }
    },
    onDiscard: () => { if (droppedImports === batch) droppedImports = null; },
  });
}, "artifact-import-status");

function cancelDroppedImports() {
  if (droppedImports?.waiting) {
    byId("artifact-file").disabled = false;
    byId("artifact-import").querySelector('button[type="submit"]').disabled = false;
  }
  droppedImports = null; importGeneration++;
}
function nextDroppedImport(batch) {
  if (droppedImports !== batch || !authenticated || batch.epoch !== authEpoch ||
      batch.generation !== importGeneration || currentView !== "library" || librarySection !== "files") return;
  if (batch.index >= batch.files.length) { droppedImports = null; importDialog.close(); return; }
  const transfer = new DataTransfer();
  transfer.items.add(batch.files[batch.index]);
  byId("artifact-file").files = transfer.files;
  batch.reviewing = batch.accepted = false;
  byId("artifact-import-status").textContent = "";
  if (!importDialog.open) importDialog.showModal();
  byId("artifact-import").requestSubmit();
}
function advanceDroppedImport(batch) {
  if (droppedImports !== batch || !batch.waiting) return;
  if (!importDialog.open) { cancelDroppedImports(); return; }
  const state = batch.receipt?.state;
  if (!["completed", "failed", "cancelled", "unknown"].includes(state)) return;
  byId("artifact-file").disabled = false;
  byId("artifact-import").querySelector('button[type="submit"]').disabled = false;
  batch.waiting = false;
  if (state === "completed") { batch.index++; nextDroppedImport(batch); }
  else {
    droppedImports = null;
    byId("artifact-import-status").textContent = "Import did not complete. Remaining files were stopped. Check Activity before trying again.";
  }
}
importDialog.addEventListener("close", () => {
  if (!importDialog.open && droppedImports && !droppedImports.reviewing) cancelDroppedImports();
});
byId("artifact-file").addEventListener("change", cancelDroppedImports);
reviewDialog.addEventListener("close", () => {
  const batch = droppedImports;
  if (!reviewDialog.open && batch?.reviewing && batch.accepted) {
    batch.reviewing = false; batch.waiting = true;
    // All imports share a backend resource. Wait for its terminal receipt before
    // offering the next independent confirmation; admission alone does not release it.
    byId("artifact-file").disabled = true;
    byId("artifact-import").querySelector('button[type="submit"]').disabled = true;
    byId("artifact-import-status").textContent = `Importing file ${batch.index + 1} of ${batch.files.length}… Close to stop the remaining files; this accepted import will continue.`;
    if (!importDialog.open) importDialog.showModal();
    advanceDroppedImport(batch);
  }
});
document.addEventListener("klaude-operations", event => {
  const batch = droppedImports;
  if (!batch?.receipt) return;
  const receipt = event.detail.find(item => item.request_id === batch.receipt.request_id);
  if (receipt) { batch.receipt = receipt; advanceDroppedImport(batch); }
});
window.FileDropUI?.register({
  active: () => currentView === "library" && librarySection === "files",
  state: () => {
    const allowed = !byId("artifact-import").querySelector('button[type="submit"]').disabled;
    return { allowed, title: allowed ? "Drop files into Uploads" : "An import is being prepared",
      detail: allowed ? "Keep documents and images in your private Library." : "Wait for the current file to finish preparing.",
      note: "32 MiB per file · Review each import" };
  },
  receive: files => {
    if (files.length > 20) throw new Error("Drop up to 20 files at a time.");
    if (files.some(file => !file.size || file.size > 32 * 1024 * 1024))
      throw new Error("Choose nonempty files up to 32 MiB each.");
    const batch = { files, index: 0, epoch: authEpoch, generation: ++importGeneration };
    droppedImports = batch;
    nextDroppedImport(batch);
  },
  reject: message => { byId("library-status").textContent = message; },
});
bindUploadForm("knowledge-learn", async () => {
  const context = integrationAddContext("knowledge");
  if (!context.current()) return;
  const library = byId("learn-library").value;
  const source = byId("learn-url").value.trim();
  const file = byId("learn-file").files[0];
  if (source && file) throw new Error("Choose a URL or a text file, then review it separately.");
  if (file) {
    const upload_id = await uploadForReview(file, 2 * 1024 * 1024);
    if (context.current()) await prepareChange({ operation: "knowledge-upload", upload_id, library }, context);
  } else await prepareChange({ operation: "knowledge-url", library, source }, context);
}, "integration-add-status");
bindUploadForm("skill-import", async () => {
  const context = integrationAddContext("skills");
  if (!context.current()) return;
  const name = byId("skill-name").value, library = byId("skill-library").value;
  const upload_id = await uploadForReview(byId("skill-file").files[0], 2 * 1024 * 1024);
  if (context.current()) await prepareChange({ operation: "skill-import", upload_id, name, library }, context);
}, "integration-add-status");

async function loadSkills() {
  clearTimeout(skillsSearchTimer);
  skillsRead?.abort(); skillsRead = new AbortController();
  const pageSize = syncDomainPageSize("skills");
  if (skillsLocationPage !== null) {
    skillsOffset = Math.min(skillsLocationPage - 1, Math.floor(1000000 / pageSize)) * pageSize;
    skillsLocationPage = null;
  }
  const load = ++skillsLoad;
  const offset = skillsOffset;
  const query = byId("skills-query").value;
  const state = skillsState;
  const grid = byId("skill-items");
  const key = JSON.stringify([query, state, offset]);
  if (grid.dataset.contentKey !== key) byId("skills-pages").hidden = true;
  const finish = beginLoading(grid, { kind: "rows", count: Math.min(6, pageSize),
    preserve: grid.dataset.contentKey === key, label: "Loading Skills…" });
  byId("skills-status").textContent = "";
  try {
    const data = await gridPage("/api/v1/integrations/skills", { query, offset, ...(state === "all" ? {} : { state }) }, pageSize, { signal: skillsRead.signal });
    if (load !== skillsLoad) return;
    if (!data.items.length && offset > 0) {
      skillsOffset = Math.max(0, offset - pageSize);
      return loadSkills();
    }
    let counts = data.counts;
    if (!counts) {
      try { counts = await readSkillsCounts({ signal: skillsRead.signal }); }
      catch (error) {
        if (error.name === "AbortError" || load !== skillsLoad) return;
        counts = {};
      }
      if (load !== skillsLoad) return;
    }
    installedSkills = data.items;
    renderSkillsCounts(counts);
    renderSkills();
    grid.dataset.contentKey = key;
    updateDomainPager("skills", offset, data);
    rememberIntegrationLocation(true);
    const noMatch = state === "all" ? "No Skills match this search" : `No ${state} Skills match this search`;
    const noItems = state === "all" ? "No installed Skills" : `No ${state} Skills`;
    byId("skills-status").textContent = "";
    if (!data.items.length) collectionEmpty(grid, query ? noMatch : noItems,
      query ? "Try another name or description." : state === "all" ? "Import a package to get started." : "Try All or another status filter.", "skill");
  } catch (error) { if (load === skillsLoad) domainError(error, "skills-status"); }
  finally { finish(); }
}
function renderSkills() {
  const nodes = installedSkills.map((skill) => {
    const row = collectionRow(skill.name, skill.name, skill.enabled ? "Enabled" : "Disabled",
      "skill", () => openSkill(skill), JSON.stringify(skill));
    row.classList.add("skill-card", "integration-card");
    row.firstChild.setAttribute("aria-label", `Details for ${skill.name}`);
    row.firstChild.setAttribute("aria-description", `${skill.description || "No description provided."} ${skill.enabled ? "Enabled" : "Disabled"}.`);
    const text = row.querySelector(".collection-content");
    text.insertBefore(domainText("span", skill.description || "No description provided.", "collection-description"), text.lastChild);
    const toggle = domainButton("", () => changeSkill(skill, "skill-enabled"), "skill-toggle integration-toggle");
    toggle.setAttribute("role", "switch");
    toggle.setAttribute("aria-checked", String(skill.enabled));
    toggle.setAttribute("aria-label", `Enable ${skill.name}`);
    toggle.title = skill.enabled ? `Disable ${skill.name}` : `Enable ${skill.name}`;
    toggle.append(domainText("span", "", "skill-switch-track integration-switch-track"));
    row.append(toggle, domainText("span", "", "skill-row-status integration-row-status"));
    return row;
    });
  reconcileRows(byId("skill-items"), nodes);
  updateSkillStates();
  if (skillDialog.open) {
    const current = installedSkills.find(skill => skill.name === detailSkill?.name);
    if (current) { detailSkill = current; renderSkillDetails(); }
  }
}
function updateSkillStates() {
  const skillsByName = new Map(installedSkills.map(skill => [skill.name, skill]));
  for (const row of byId("skill-items").querySelectorAll(".skill-card")) {
    const name = row.dataset.rowKey, pending = skillChanges.has(name);
    const skill = skillsByName.get(name);
    if (!skill) continue;
    const label = skill.enabled ? "Enabled" : "Disabled";
    const metadata = row.querySelector(".collection-metadata");
    metadata.textContent = label;
    row.firstChild.setAttribute("aria-description", `${skill.description || "No description provided."} ${label}.`);
    const toggle = row.querySelector(".skill-toggle");
    toggle.disabled = pending || skillReviewPending;
    toggle.setAttribute("aria-busy", String(pending));
    row.querySelector(".skill-row-status").textContent = "";
  }
  if (skillDialog.open) renderSkillDetails();
}
function renderSkillDetails() {
  if (!detailSkill) return;
  const skill = detailSkill;
  byId("skill-detail-title").textContent = skill.name;
  byId("skill-detail-description").textContent = skill.description || "No description provided.";
  const metadata = byId("skill-detail-metadata");
  metadata.replaceChildren();
  for (const [label, value] of [["Status", skill.enabled ? "Enabled" : "Disabled"],
    ["Installation", skill.source_label], ["Indexed files", skill.indexed_file_count], ["Knowledge library", skill.library]]) {
    if (value !== undefined && value !== null) metadata.append(domainText("dt", label), domainText("dd", String(value)));
  }
  byId("skill-detail-status").textContent = "";
  byId("skill-detail-change").textContent = skill.enabled ? "Disable" : "Enable";
  for (const id of ["skill-detail-change", "skill-detail-delete"]) byId(id).disabled = skillChanges.has(skill.name) || skillReviewPending;
}
function openSkill(skill) {
  detailSkill = skill; renderSkillDetails(); skillDialog.showModal();
}
async function changeSkill(skill, operation) {
  if (skillChanges.has(skill.name) || skillReviewPending || reviewDialog.open) return;
  const direct = operation === "skill-enabled";
  const epoch = authEpoch, state = { phase: direct ? "preparing" : "review", operation };
  skillChanges.set(skill.name, state);
  skillReviewPending = true; updateSkillStates();
  const current = () => authenticated && epoch === authEpoch && skillChanges.get(skill.name) === state;
  const mayOpenReview = () => current() && currentView === "integrations" && integrationSection === "skills";
  try {
    await (direct ? submitDirectChange : prepareChange)({ operation, name: skill.name, identity: skill.identity,
      expected_enabled: skill.enabled, ...(operation === "skill-enabled" ? { enabled: !skill.enabled } : {}) }, {
      current: mayOpenReview,
      beforeOpen: () => { if (skillDialog.open) skillDialog.close(); },
      onSubmitting: receipt => {
        if (!current()) return;
        state.phase = "submitting"; state.request_id = receipt.request_id; updateSkillStates();
      },
      onAccepted: (operation) => {
        if (!current()) return;
        state.phase = "accepted"; state.request_id = operation.request_id; updateSkillStates();
      },
      onDiscard: (review) => {
        if (!current()) return;
        if (review.uncertain) { state.phase = "unknown"; state.request_id = review.request_id; }
        else skillChanges.delete(skill.name);
        updateSkillStates();
      },
    });
    if (current() && !mayOpenReview() && ["preparing", "review"].includes(state.phase)) skillChanges.delete(skill.name);
  } catch (error) {
    if (current()) {
      skillChanges.delete(skill.name);
      domainError(error, "skills-status");
    }
  } finally {
    if (epoch === authEpoch) { skillReviewPending = false; updateSkillStates(); }
  }
}
byId("skill-detail-close").append(libraryIcon("close"));
byId("skill-detail-close").addEventListener("click", () => skillDialog.close());
byId("skill-detail-change").addEventListener("click", () => changeSkill(detailSkill, "skill-enabled"));
byId("skill-detail-delete").addEventListener("click", () => changeSkill(detailSkill, "skill-delete"));
async function loadOperations() {
  if (operationPollBusy || !authenticated) return;
  operationPollBusy = true;
  const finish = beginLoading(byId("domain-operations"), { kind: "rows", count: 3, label: "Loading operations…" });
  try {
    const data = await domainRequest("/api/v1/library/operations");
    let skillSettled = false;
    for (const [name, pending] of skillChanges) {
      const operation = data.items.find(item => item.request_id === pending.request_id);
      if (!operation || !["completed", "failed", "unknown"].includes(operation.state)) continue;
      if (operation.state === "unknown") pending.phase = "unknown";
      else {
        skillChanges.delete(name); skillSettled = true;
      }
    }
    updateSkillStates();
    document.dispatchEvent(new CustomEvent("klaude-operations", { detail: data.items }));
    const signature = data.items.map((item) => `${item.request_id}:${item.state}`).join("|");
    const render = signature !== operationSignature;
    const changed = operationSignature !== null && signature !== operationSignature;
    operationSignature = signature;
    if (render) byId("domain-operations").replaceChildren(...data.items.map((item) => {
      const node = domainText("article", "", "operation-row");
      const status = item.state === "unknown" ? "Unconfirmed · local reconciliation required; do not resubmit" :
        item.state === "failed" ? "Rejected · reload and review the current item" : item.state;
      node.append(domainText("strong", item.kind.replaceAll("-", " ")), domainText("span", status),
        domainText("small", item.request_id, "muted"));
      if (window.MaterialLoadingCircle && ["accepted", "running", "cancelling"].includes(item.state)) {
        node.dataset.working = "true";
        node.prepend(MaterialLoadingCircle.create({ size: "medium" }));
      }
      return node;
    }));
    if (render && !data.items.length) byId("domain-operations").append(domainText("p", "No Library or integration operations yet.", "muted"));
    if (skillSettled || changed && data.items.some((item) => ["completed", "failed", "unknown"].includes(item.state))) {
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
byId("library-refresh").addEventListener("click", () => refreshDomain("library"));
for (const button of byId("file-view-modes").children) {
  button.append(libraryIcon(button.dataset.fileView));
  button.addEventListener("click", () => {
    fileView = button.dataset.fileView;
    if (fileView === "gallery") libraryOffset = 0;
    rememberLibraryLocation(); loadLibrary();
  });
}
byId("file-add").append(libraryIcon("plus"));
function integrationAddContext(section) {
  const generation = integrationAddGeneration, epoch = authEpoch;
  return {
    current: () => authenticated && epoch === authEpoch && currentView === "integrations" &&
      integrationSection === section && integrationAddSection === section && integrationAddDialog.open &&
      generation === integrationAddGeneration,
    beforeOpen: () => integrationAddDialog.close(),
  };
}
for (const button of document.querySelectorAll("[data-integration-add]")) {
  button.append(libraryIcon("plus"));
  button.addEventListener("click", () => {
    const section = button.dataset.integrationAdd;
    if (!authenticated || currentView !== "integrations" || integrationSection !== section || reviewDialog.open) return;
    integrationAddGeneration += 1; integrationAddSection = section;
    byId("integration-add-title").textContent = integrationAddForms[section].title;
    byId("integration-add-status").textContent = "";
    for (const panel of integrationAddDialog.querySelectorAll("[data-integration-form]"))
      panel.hidden = panel.dataset.integrationForm !== section;
    const form = byId(integrationAddForms[section].form);
    form.reset();
    if (section === "knowledge") byId("learn-library").value = byId("knowledge-library").value;
    integrationAddDialog.showModal();
    form.querySelector("input").focus();
  });
}
byId("integration-add-close").append(libraryIcon("close"));
byId("integration-add-close").addEventListener("click", () => integrationAddDialog.close());
integrationAddDialog.addEventListener("close", () => {
  if (integrationAddDialog.open) return;
  integrationAddGeneration += 1; integrationAddSection = null;
  for (const item of Object.values(integrationAddForms)) byId(item.form).reset();
  byId("integration-add-status").textContent = "";
});
byId("file-add").addEventListener("click", () => {
  cancelDroppedImports();
  byId("artifact-import-status").textContent = "";
  importDialog.showModal();
  byId("artifact-file").focus();
});
byId("artifact-import-close").append(libraryIcon("close"));
byId("artifact-import-close").addEventListener("click", () => importDialog.close());
byId("skills-refresh").addEventListener("click", () => refreshDomain("integrations"));
for (const button of byId("integration-sections").querySelectorAll("[data-integration]")) {
  button.addEventListener("click", () => {
    if (integrationSection === button.dataset.integration) return;
    stopIntegrationReads();
    integrationSection = button.dataset.integration;
    renderIntegrationSection(); rememberIntegrationLocation(); loadIntegrationSection();
  });
}
byId("skills-query").addEventListener("input", () => {
  skillsOffset = 0; skillsLocationPage = null;
  skillsLoad += 1; skillsRead?.abort();
  clearTimeout(skillsSearchTimer);
  skillsSearchTimer = setTimeout(() => { rememberIntegrationLocation(); loadSkills(); }, 200);
});
for (const button of byId("skills-state-filter").children) button.addEventListener("click", () => {
  if (skillsState === button.dataset.skillState) return;
  skillsState = button.dataset.skillState;
  skillsOffset = 0; skillsLocationPage = null;
  renderSkillsFilter(); rememberIntegrationLocation(); loadSkills();
});
byId("skills-filter").addEventListener("submit", (event) => {
  event.preventDefault(); skillsOffset = 0; skillsLocationPage = null;
  rememberIntegrationLocation(); loadSkills();
});
byId("skills-previous").addEventListener("click", () => { skillsOffset = Math.max(0, skillsOffset - domainPageSizes.skills); rememberIntegrationLocation(); loadSkills(); });
byId("skills-next").addEventListener("click", () => { skillsOffset += domainPageSizes.skills; rememberIntegrationLocation(); loadSkills(); });
for (const button of document.querySelectorAll("#library-sections button")) {
  button.addEventListener("click", () => {
    if (librarySection === button.dataset.section) return;
    cancelDroppedImports(); importDialog.close(); window.FileDropUI?.reset();
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
byId("artifact-filter").addEventListener("submit", (event) => {
  event.preventDefault(); clearTimeout(fileSearchTimer);
  libraryOffset = 0; rememberLibraryLocation(); loadLibrary();
});
byId("artifact-query").addEventListener("input", () => {
  clearTimeout(fileSearchTimer); fileRead?.abort(); libraryLoad += 1;
  fileSearchTimer = setTimeout(() => {
    libraryOffset = 0; rememberLibraryLocation(); loadLibrary();
  }, 200);
});
document.addEventListener('klaude-chat-session-changed', () => {
  filePages.clear();
});
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
    else if (prefix === "skills") { skillsOffset = offset; rememberIntegrationLocation(); loadSkills(); }
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
      if (prefix in domainPageSizes && measureDomainPageSize(prefix) !== domainPageSizes[prefix]) loadIntegrationSection();
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
    cancelDroppedImports(); importDialog.close();
    clearTimeout(fileSearchTimer);
    fileRead?.abort();
    libraryLoad += 1; cancelLoading(byId("library-items"));
  }
  if (event.detail === "integrations") {
    restoreIntegrationLocation(); renderIntegrationSection(); rememberIntegrationLocation(true); loadIntegrationSection();
  } else { stopIntegrationReads(); integrationAddDialog.close(); }
  if (authenticated && !["library", "integrations"].includes(event.detail)) {
    const url = new URL(location.href);
    for (const key of [...url.searchParams.keys()])
      if (["library", "integrations", "sources-page"].includes(key) || key.startsWith("files-") || key.startsWith("knowledge-") || key.startsWith("skills-")) url.searchParams.delete(key);
    history.replaceState(history.state, "", url.pathname + url.search + url.hash);
  }
  if (["library", "integrations", "activity"].includes(event.detail)) loadOperations();
});
document.addEventListener("klaude-auth-reset", () => {
  knowledgeSource = ""; knowledgeChunkPage = null; knowledgeDeletePending = null; knowledgeOrigin = null;
  knowledgeSourceNames.clear();
  cancelDroppedImports();
  integrationAddGeneration += 1; integrationAddDialog.close();
  clearTimeout(fileSearchTimer);
  for (const token of domainRefreshes.values()) {
    clearTimeout(token.timer); token.indicator?.remove();
  }
  domainRefreshes.clear();
  for (const id of ["library-refresh", "skills-refresh"]) {
    byId(id).disabled = false; byId(id).setAttribute("aria-busy", "false");
  }
  skillChanges.clear(); skillReviewPending = false; detailSkill = null;
  skillDialog.close();
  for (const id of ["skill-detail-title", "skill-detail-description", "skill-detail-metadata", "skill-detail-status"]) byId(id).replaceChildren();
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
  skillsLocationPage = null;
  skillsState = "all"; renderSkillsFilter();
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
  renderSkillsCounts({ all: 0, enabled: 0, disabled: 0 });
  selectedArtifact = null;
  managementReview = null;
  operationSignature = null;
  reviewDialog.close();
  artifactDialog.close();
  importDialog.close();
  for (const id of ["library-items", "knowledge-items", "skill-items", "source-items", "artifact-preview", "artifact-actions", "domain-operations"]) byId(id).replaceChildren();
  for (const id of ["artifact-metadata", "artifact-source", "artifact-tag-items", "artifact-menu"]) byId(id).replaceChildren();
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
  for (const menu of libraryFilterMenus) menu.sync();
  byId("artifact-import-status").textContent = "";
  byId("knowledge-query").value = "";
  byId("knowledge-library").replaceChildren();
  byId("knowledge-breadcrumbs").replaceChildren();
  byId("knowledge-heading").hidden = true;
  byId("knowledge-summary").textContent = "";
  byId("knowledge-title").textContent = "";
  byId("knowledge-content-title").textContent = "Chunks";
  byId("knowledge-chunk-status").textContent = "";
  byId("knowledge-chunk-title").textContent = "Chunk";
  byId("knowledge-chunk-position").textContent = "";
  byId("learn-library").value = ""; byId("learn-url").value = "";
  byId("domain-review-summary").textContent = "";
  byId("domain-review-target").textContent = "";
  byId("domain-review-notice").textContent = "";
  byId("domain-review-technical-summary").textContent = "";
  byId("domain-review-technical").open = false;
  byId("domain-review-status").textContent = "";
  byId("artifact-detail-title").textContent = "Saved item";
  byId("library-status").textContent = "";
  byId("skills-status").textContent = "";
  byId("knowledge-status").textContent = "";
});
window.addEventListener("popstate", () => {
  integrationAddDialog.close();
  if (!authenticated) return;
  if (artifactDialog.open) artifactDialog.close();
  if (skillDialog.open) skillDialog.close();
  const query = new URLSearchParams(location.search);
  if (query.get("library") === "knowledge" || ["skills", "knowledge", "connections"].includes(query.get("integrations"))) {
    restoreIntegrationLocation();
    if (currentView !== "integrations") showView("integrations", { restore: true });
    else { renderIntegrationSection(); rememberIntegrationLocation(true); loadIntegrationSection(); }
  } else if (["files", "outputs"].includes(query.get("library"))) {
    restoreLibraryLocation();
    if (currentView !== "library") showView("library", { restore: true }); else loadLibrary();
  } else {
    const view = viewNames.includes(query.get("view")) ? query.get("view") : "chat";
    if (currentView !== view) showView(view, { restore: true });
    else if (view === "settings") showSettingsSection(query.get("settings") || settingsSection, { restore: true });
  }
});
setInterval(() => {
  if (authenticated && (["library", "integrations", "activity", "settings"].includes(currentView) || window.BrowserManagement?.hasPending()) && !document.hidden) loadOperations();
}, 2000);
