/* Material loading indicator browser adaptation. Apache-2.0.
 * Copyright 2024 The Android Open Source Project; 2026 Klaude contributors.
 * Geometry: unmodified MaterialShapes + AndroidX Morph export.
 * Motion: LoadingIndicatorAnimatorDelegate / AndroidX SpringForce.
 * See vendor/material-loading-{LICENSE,NOTICE,manifest}.txt/json and
 * docs/webui/material-loading-indicator.md for pinned sources and differences.
 */
"use strict";

window.MaterialLoading = (() => {
  const geometry = window.MaterialLoadingGeometry;
  if (!geometry?.morphs?.length) return null;
  const svgNS = "http://www.w3.org/2000/svg";
  const interval = 650, stiffness = 200, damping = 0.6;
  const omega = Math.sqrt(stiffness), decay = damping * omega;
  const damped = omega * Math.sqrt(1 - damping * damping);
  const systemReduced = matchMedia("(prefers-reduced-motion: reduce)");
  const states = new Map();
  let scheduled = null;

  // Closed form of AndroidX SpringForce's under-damped, unit-mass solution.
  // Native minimumVisibleChange=.01 sets value=.0075 and velocity=.46875
  // equilibrium thresholds. Once settled, retain the target until the next step.
  function spring(time) {
    const seconds = time / 1000;
    const cosine = Math.cos(damped * seconds), sine = Math.sin(damped * seconds);
    const envelope = Math.exp(-decay * seconds);
    const displacement = -cosine - decay / damped * sine;
    const value = 1 + envelope * displacement;
    const velocity = envelope * (-decay * displacement + damped * sine - decay * cosine);
    return { value, velocity };
  }
  let settledAt = interval;
  for (let ms = 1; ms <= interval; ms++) {
    const sample = spring(ms);
    if (Math.abs(sample.value - 1) < .0075 && Math.abs(sample.velocity) < .46875) {
      settledAt = ms; break;
    }
  }
  function frameAt(milliseconds) {
    const elapsed = Math.max(0, milliseconds);
    const step = Math.floor(elapsed / interval), time = elapsed % interval;
    const fraction = time >= settledAt ? 1 : spring(time).value;
    const morph = step + fraction;
    const base = Math.floor(morph), index = base % geometry.morphs.length;
    return { index, progress: morph - base,
      rotation: (-90 + step * 140 + 50 * time / interval + 90 * fraction) % 360 };
  }
  function pathAt(frame) {
    const { start, end } = geometry.morphs[frame.index];
    const values = start.map((value, index) => value + (end[index] - value) * frame.progress);
    let path = `M${values[0]},${values[1]}`;
    for (let i = 2; i < values.length; i += 6) path += `C${values.slice(i, i + 6).join(",")}`;
    return path + "Z";
  }
  function draw(state, frame) {
    state.path.setAttribute("d", pathAt(frame));
    state.group.setAttribute("transform", `rotate(${frame.rotation})`);
  }
  function reduced() {
    return systemReduced.matches || document.documentElement.dataset.motion === "reduced";
  }
  function schedule() {
    if (scheduled === null && !document.hidden && !reduced() &&
        [...states.values()].some(state => state.visible)) scheduled = requestAnimationFrame(tick);
  }
  function tick(now) {
    scheduled = null;
    for (const [element, state] of states) {
      if (!element.isConnected) { visibility.unobserve(element); states.delete(element); continue; }
      if (!state.visible || document.hidden || reduced()) continue;
      if (state.last !== null) state.elapsed += now - state.last;
      state.last = now;
      draw(state, frameAt(state.elapsed));
    }
    schedule();
  }
  const visibility = new IntersectionObserver(entries => {
    for (const entry of entries) {
      const state = states.get(entry.target);
      if (!state) continue;
      state.visible = entry.isIntersecting && entry.intersectionRatio > 0;
      state.last = null;
    }
    schedule();
  });
  function resetMotion() {
    if (scheduled !== null) cancelAnimationFrame(scheduled);
    scheduled = null;
    for (const state of states.values()) {
      state.last = null;
      if (reduced()) draw(state, frameAt(0));
    }
    schedule();
  }
  systemReduced.addEventListener("change", resetMotion);
  document.addEventListener("visibilitychange", resetMotion);
  new MutationObserver(resetMotion).observe(document.documentElement,
    { attributes: true, attributeFilter: ["data-motion"] });
  // Removed placeholders must release their paths even if no animation is running
  // (for example, a reduced-motion user navigating through hundreds of pages).
  new MutationObserver(() => {
    for (const [element] of states) if (!element.isConnected) {
      visibility.unobserve(element); states.delete(element);
    }
  }).observe(document.body, { childList: true, subtree: true });

  function create({ size = "small", contained = false, label = "" } = {}) {
    const element = document.createElement("span");
    element.className = "material-loading";
    element.dataset.size = ["small", "medium", "large"].includes(size) ? size : "small";
    element.dataset.contained = String(contained);
    if (label) {
      element.setAttribute("role", "progressbar"); element.setAttribute("aria-label", label);
    } else element.setAttribute("aria-hidden", "true");
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", "-24 -24 48 48");
    svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
    const group = document.createElementNS(svgNS, "g");
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("transform", "scale(19)"); path.setAttribute("fill", "currentColor");
    group.append(path); svg.append(group); element.append(svg);
    const state = { path, group, elapsed: 0, last: null, visible: false };
    draw(state, frameAt(0)); states.set(element, state); visibility.observe(element);
    return element;
  }
  return Object.freeze({ create, frameAt, pathAt,
    names: geometry.names, activeCount: () => states.size });
})();
