"use strict";

window.ChatAttachmentsUI = (() => {
  const dialog = byId("attach-dialog");
  const list = byId("chat-attachments");
  const status = byId("attach-status");
  let selected = [];
  let jobs = 0;
  let generation = 0;
  let offset = 0;
  let read = 0;
  let rendered = "";
  const messageCards = new WeakMap();

  function fileType(item) {
    const extension = item.name.split(".").pop().toUpperCase();
    if (item.image) return "Image";
    if (item.mime === "application/pdf" || extension === "PDF") return "PDF";
    return /^[A-Z0-9]{1,8}$/.test(extension) && item.name.includes(".") ? extension : "File";
  }
  function fileCard(item, previewURL = "") {
    const type = fileType(item);
    const card = document.createElement("div");
    card.className = "attachment-card";
    card.setAttribute("role", "listitem");
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
    files.forEach((item, index) => cards.append(fileCard(item, item.preview ? previewURL({
      session, message: message.id, file: index,
    }) : "")));
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
        remove.textContent = "×";
        remove.setAttribute("aria-label", `Remove ${item.name}`);
        remove.disabled = pending;
        remove.addEventListener("click", () => {
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
      jobs ? "Preparing attachment…" : waiting ?
      "Files are ready. Send when the current reply finishes." :
      selected.some(item => item.truncated) ? "Long file text is truncated to 32,000 characters." : "";
    byId("chat-attachment-status").textContent = label;
    byId("chat-attachment-status").hidden = !label;
    byId("send").disabled = pending || jobs > 0 || Boolean(waiting);
    byId("steer").disabled = pending || jobs > 0 || Boolean(selected.length);
    byId("attach-file").disabled = pending || !available;
    byId("attach-file").title = available ? "Attach file" :
      "Restart Web UI, then reload to enable attachments";
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
      if (selected.length >= 4 || selected.filter(file => file.image).length + Number(item.image) > 2 ||
          selected.reduce((sum, file) => sum + file.size, 0) + item.size > 32 * 1024 * 1024) {
        discard(item.id);
        throw new Error("Attach up to four files, including two images, within 32 MiB.");
      }
      selected.push(item);
      status.textContent = `${item.name} attached${item.truncated ? " · Text truncated" : ""}`;
    } finally { jobs--; refresh(); }
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
    const context = generation, epoch = authEpoch, session = latest?.session_id;
    for (const file of files) {
      if (context !== generation || epoch !== authEpoch || session !== latest?.session_id) return;
      try {
        if (selected.length >= 4) throw new Error("Attach up to four files per message.");
        if (!file.size || file.size > 32 * 1024 * 1024) throw new Error("Choose a nonempty file up to 32 MiB.");
        jobs++;
        refresh();
        let upload;
        try {
          const response = await fetch("/api/v1/uploads", { method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/octet-stream", "X-Klaude-CSRF": csrf,
              "X-Klaude-Filename": file.name.replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 100) }, body: file });
          upload = await response.json();
          if (!response.ok) throw new Error(upload.error?.message || "Upload failed");
        } finally { jobs--; refresh(); }
        if (context !== generation || epoch !== authEpoch || session !== latest?.session_id) {
          if (authenticated && epoch === authEpoch) jsonRequest("/api/v1/chat/attachments/discard",
            "POST", { upload_id: upload.id }).catch(() => {});
          return;
        }
        await attach({ upload_id: upload.id }, context);
      } catch (error) {
        if (context === generation && epoch === authEpoch) status.textContent = error.message;
        break;
      }
    }
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
        const detail = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = item.name;
        const meta = document.createElement("p");
        meta.className = "muted";
        meta.textContent = `${item.mime} · ${(item.size / 1024).toFixed(1)} KiB`;
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
        row.append(detail, button);
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
    if (dialog.open) dialog.close();
    byId("attach-library-items").replaceChildren();
    refresh();
  }
  document.addEventListener("klaude-auth-reset", clear);
  document.addEventListener("klaude-chat-session-changed", clear);
  refresh();
  return Object.freeze({ ids: () => selected.map(item => item.id), preparing: () => jobs > 0,
    clear, refresh, renderMessage });
})();
