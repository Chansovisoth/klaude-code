"use strict";

// Crop directly on the image, or search the full image.
window.BrowserLens = (() => {
  const overlay = byId("lens-overlay"), canvas = byId("lens-canvas"), context = canvas.getContext("2d");
  const stage = overlay.parentElement, trigger = byId("image-lens"), search = byId("lens-search");
  const status = byId("lens-status"), selection = byId("lens-selection");
  let source = null, crop = null, drag = null, prepared = null, timer = null;
  let owner = null, session = "", epoch = 0, generation = 0, preparation = 0, imageRect = null;
  const active = () => !overlay.hidden;
  const current = () => active() && authenticated && artifactDialog.open &&
    selectedArtifact === owner && latest?.session_id === session && authEpoch === epoch;
  function normalize() {
    if (!source || !crop) return;
    crop.x = Math.max(0, Math.min(source.width - 1, Math.round(crop.x)));
    crop.y = Math.max(0, Math.min(source.height - 1, Math.round(crop.y)));
    crop.width = Math.max(1, Math.min(source.width - crop.x, Math.round(crop.width)));
    crop.height = Math.max(1, Math.min(source.height - crop.y, Math.round(crop.height)));
  }
  function announce() {
    if (crop) selection.textContent = "Selection: left " + crop.x + ", top " + crop.y + ", " +
      crop.width + " by " + crop.height + " pixels.";
  }
  function draw() {
    if (!source || !current()) return;
    const bounds = stage.getBoundingClientRect(), ratio = Math.min(devicePixelRatio || 1, 2);
    const width = Math.max(1, bounds.width), height = Math.max(1, bounds.height);
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const scale = Math.min(width / source.width, height / source.height);
    imageRect = { x: (width - source.width * scale) / 2, y: (height - source.height * scale) / 2,
      width: source.width * scale, height: source.height * scale, scale };
    const image = imageRect;
    context.clearRect(0, 0, width, height);
    context.drawImage(source, image.x, image.y, image.width, image.height);
    const x = image.x + crop.x * scale, y = image.y + crop.y * scale;
    const w = crop.width * scale, h = crop.height * scale;
    context.fillStyle = "rgba(0,0,0,.48)";
    context.fillRect(image.x, image.y, image.width, image.height);
    context.drawImage(source, crop.x, crop.y, crop.width, crop.height, x, y, w, h);
    context.strokeStyle = getComputedStyle(stage).getPropertyValue("--primary").trim();
    context.lineWidth = 2;
    context.strokeRect(x, y, w, h);
    context.fillStyle = context.strokeStyle;
    for (const [hx, hy] of [[x,y],[x+w,y],[x,y+h],[x+w,y+h]]) {
      context.beginPath(); context.arc(hx, hy, 4, 0, Math.PI * 2); context.fill();
    }
  }
  function prepare(submitOnReady = false) {
    const ticket = ++preparation, version = generation;
    if (!source || !current()) return;
    const area = { ...crop }, output = document.createElement("canvas");
    output.width = area.width; output.height = area.height;
    output.getContext("2d").drawImage(source, area.x, area.y, area.width, area.height,
      0, 0, area.width, area.height);
    if (submitOnReady) {
      const encoded = output.toDataURL("image/png").split(",")[1];
      const binary = atob(encoded), bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      if (bytes.length > 8 * 1024 * 1024) { status.textContent = "Choose a smaller area to search."; return; }
      prepared = { file: new File([bytes], "lens-image.png", { type: "image/png" }),
        width: area.width, height: area.height };
      search.disabled = false; submitSearch(); return;
    }
    output.toBlob(blob => {
      if (ticket !== preparation || version !== generation || !current()) return;
      if (!blob || blob.size > 8 * 1024 * 1024) {
        status.textContent = "Choose a smaller area to search."; return;
      }
      prepared = { file: new File([blob], "lens-image.png", { type: "image/png" }),
        width: area.width, height: area.height };
      search.disabled = false;
    }, "image/png");
  }
  function changed(immediate = false) {
    normalize(); prepared = null; search.disabled = true; preparation += 1;
    clearTimeout(timer); status.textContent = ""; draw();
    if (immediate) prepare(); else timer = setTimeout(prepare, 100);
  }
  function reset(focus = false) {
    generation += 1; preparation += 1; clearTimeout(timer);
    overlay.hidden = true; stage.classList.remove("lens-active"); trigger.setAttribute("aria-pressed", "false");
    source = crop = drag = prepared = owner = imageRect = null;
    canvas.width = canvas.height = 1; search.disabled = true;
    byId("lens-upload-file").value = ""; status.textContent = ""; selection.textContent = "";
    if (focus && artifactDialog.open && authenticated && !trigger.hidden) trigger.focus({ preventScroll: true });
  }
  trigger.addEventListener("click", () => {
    if (active()) { reset(true); return; }
    const image = byId("artifact-preview").querySelector("img");
    if (!authenticated || !selectedArtifact || !image?.naturalWidth) return;
    byId("image-zoom-value").click();
    owner = selectedArtifact; session = latest.session_id; epoch = authEpoch; generation += 1;
    source = document.createElement("canvas");
    const scale = Math.min(1, 2048 / Math.max(image.naturalWidth, image.naturalHeight));
    source.width = Math.max(1, Math.round(image.naturalWidth * scale));
    source.height = Math.max(1, Math.round(image.naturalHeight * scale));
    source.getContext("2d").drawImage(image, 0, 0, source.width, source.height);
    crop = { x: 0, y: 0, width: source.width, height: source.height };
    overlay.hidden = false; stage.classList.add("lens-active"); trigger.setAttribute("aria-pressed", "true");
    changed(true); announce(); canvas.focus({ preventScroll: true });
  });
  search.prepend(libraryIcon("search"));
  byId("lens-cancel").append(libraryIcon("close"));
  byId("lens-cancel").addEventListener("click", () => reset(true));
  function point(event) {
    const bounds = canvas.getBoundingClientRect();
    return { x: Math.max(0, Math.min(source.width, (event.clientX - bounds.left - imageRect.x) / imageRect.scale)),
      y: Math.max(0, Math.min(source.height, (event.clientY - bounds.top - imageRect.y) / imageRect.scale)) };
  }
  canvas.addEventListener("pointerdown", event => {
    if (!current() || event.button !== 0 || !imageRect) return;
    const bounds = canvas.getBoundingClientRect();
    const vx = event.clientX - bounds.left, vy = event.clientY - bounds.top;
    if (vx < imageRect.x || vy < imageRect.y || vx > imageRect.x + imageRect.width ||
        vy > imageRect.y + imageRect.height) return;
    event.preventDefault(); canvas.focus({ preventScroll: true });
    const p = point(event), tolerance = 16 / imageRect.scale;
    const corner = [["nw",crop.x,crop.y],["ne",crop.x+crop.width,crop.y],
      ["sw",crop.x,crop.y+crop.height],["se",crop.x+crop.width,crop.y+crop.height]]
      .find(([,x,y]) => Math.abs(p.x-x)<=tolerance && Math.abs(p.y-y)<=tolerance)?.[0];
    const full = crop.x===0 && crop.y===0 && crop.width===source.width && crop.height===source.height;
    const inside = p.x>crop.x && p.x<crop.x+crop.width && p.y>crop.y && p.y<crop.y+crop.height;
    drag = { start: p, original: { ...crop }, kind: corner || (!full && inside ? "move" : "new"),
      pointer: event.pointerId, clientX: event.clientX, clientY: event.clientY, moved: false };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", event => {
    if (!drag || !current() || drag.pointer !== event.pointerId) return;
    if (Math.hypot(event.clientX-drag.clientX,event.clientY-drag.clientY)<3 && !drag.moved) return;
    drag.moved = true;
    const p = point(event), old = drag.original;
    if (drag.kind === "move") {
      crop = { ...old, x: Math.max(0,Math.min(source.width-old.width,old.x+p.x-drag.start.x)),
        y: Math.max(0,Math.min(source.height-old.height,old.y+p.y-drag.start.y)) };
    } else {
      const opposite = drag.kind === "new" ? drag.start : {
        x: drag.kind.includes("w") ? old.x+old.width : old.x,
        y: drag.kind.includes("n") ? old.y+old.height : old.y };
      crop = { x: Math.min(p.x,opposite.x), y: Math.min(p.y,opposite.y),
        width: Math.abs(p.x-opposite.x), height: Math.abs(p.y-opposite.y) };
    }
    changed();
  });
  function endDrag(event) {
    if (!drag || drag.pointer !== event.pointerId) return;
    const submit = event.type === "pointerup" && drag.moved;
    if (event.type === "pointercancel") crop = drag.original;
    drag = null; changed(); announce();
    if (submit) { clearTimeout(timer); prepare(true); }
  }
  for (const type of ["pointerup","pointercancel","lostpointercapture"]) canvas.addEventListener(type,endDrag);
  canvas.addEventListener("keydown", event => {
    if (!current()) return;
    if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); search.click(); return; }
    if (event.key === "Home") {
      event.preventDefault(); event.stopPropagation();
      crop = { x:0,y:0,width:source.width,height:source.height }; changed(); announce(); return;
    }
    if (!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    const horizontal = ["ArrowLeft","ArrowRight"].includes(event.key);
    const amount = ["ArrowLeft","ArrowUp"].includes(event.key) ? -1 : 1;
    if (event.shiftKey) crop[horizontal ? "width" : "height"] += amount;
    else {
      const key = horizontal ? "x" : "y", limit = horizontal ? source.width-crop.width : source.height-crop.height;
      crop[key] = Math.max(0,Math.min(limit,crop[key]+amount));
    }
    changed(); announce();
  });
  artifactDialog.addEventListener("keydown", event => {
    if (active() && event.key === "Escape") {
      event.preventDefault(); event.stopImmediatePropagation(); reset(true);
    }
  }, true);
  function submitSearch() {
    if (!current() || !prepared || search.disabled) return;
    const form = byId("lens-upload"), files = new DataTransfer();
    files.items.add(prepared.file); byId("lens-upload-file").files = files.files;
    const action = new URL("https://lens.google.com/v3/upload");
    action.searchParams.set("ep","cntpubb"); action.searchParams.set("hl",navigator.language);
    action.searchParams.set("st",String(Date.now()));
    action.searchParams.set("vpw",prepared.width); action.searchParams.set("vph",prepared.height);
    form.action = action.href; HTMLFormElement.prototype.submit.call(form);
    reset(true);
  }
  search.addEventListener("click", submitSearch);
  new ResizeObserver(() => { if (active()) { if (current()) draw(); else reset(); } }).observe(stage);
  artifactDialog.addEventListener("close", () => { if (!artifactDialog.open) reset(); });
  document.addEventListener("klaude-auth-reset", () => reset());
  document.addEventListener("klaude-snapshot", () => { if (active() && !current()) reset(); });
  return Object.freeze({ reset });
})();
