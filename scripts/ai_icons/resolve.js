"use strict";

// Bundled with the reviewed JSON catalog. No network or SVG injection; matching uses reviewed identities.
function createAIIconRegistry(catalog) {
  const own = (object, key) => Object.hasOwn(object, key);
  function freeze(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) {
      Object.values(value).forEach(freeze);
      Object.freeze(value);
    }
    return value;
  }
  freeze(catalog);
  const aliasKey = value => String(value || "").trim().toLowerCase().replace(/[\s._-]+/g, "");
  const providers = new Map(catalog.providers.map(provider => [provider.id, provider]));
  const providerAliases = new Map();
  const platformAliases = new Map();
  const namespaces = new Map();
  for (const provider of catalog.providers) {
    for (const name of [provider.id, provider.name, ...provider.aliases]) providerAliases.set(aliasKey(name), provider);
    for (const name of provider.namespaces) namespaces.set(name.toLowerCase(), provider);
  }
  for (const platform of catalog.platforms) {
    for (const name of [platform.id, platform.name, ...platform.aliases]) platformAliases.set(aliasKey(name), platform);
  }
  const prefixes = catalog.families.flatMap(family => family.prefixes.map(prefix => ({ prefix, family })))
    .sort((a, b) => b.prefix.length - a.prefix.length);
  function icon(id) {
    return typeof id === "string" && own(catalog.icons, id) ? catalog.icons[id] : catalog.icons.generic;
  }
  function identity(record) {
    if (!record) return null;
    return Object.freeze({ id: record.id, name: record.name, icon: icon(record.icon).mono,
      colorIcon: icon(record.icon).color || null, kind: record.kind || "api" });
  }
  function provider(value) { return identity(providerAliases.get(aliasKey(value))); }
  function platform(value) {
    const key = aliasKey(value);
    return identity(platformAliases.get(key) || providerAliases.get(key));
  }
  function transport(value) {
    const key = aliasKey(value);
    return platformAliases.get(key) || providerAliases.get(key) || null;
  }
  function familyFor(name, creator = null) {
    for (const candidate of prefixes) {
      if (creator && candidate.family.creator !== creator) continue;
      if (!name.startsWith(candidate.prefix)) continue;
      const next = name[candidate.prefix.length];
      if (next === undefined || /[-_.:]/.test(next) ||
          (!/\d$/.test(candidate.prefix) && /\d/.test(next))) return candidate.family;
    }
    return null;
  }
  function parse(reference, suppliedTransport) {
    let model = typeof reference === "string" ? reference.trim() : "";
    let via = transport(suppliedTransport);
    const result = { model: "", namespace: "", via, fineTuned: false, invalid: false };
    if (!model || model.length > 4096 || /[\u0000-\u0020\u007f\\]/.test(model)) {
      result.invalid = Boolean(model); return result;
    }
    model = model.toLowerCase();
    const configured = /^([a-z0-9_-]+)@[^/\s]{1,128}\/(.+)$/.exec(model);
    if (configured) { via = transport(configured[1]) || via; model = configured[2]; }
    if (/^https?:\/\//.test(model)) {
      try {
        const url = new URL(model);
        if (!["huggingface.co", "hf.co"].includes(url.hostname) || url.username || url.password ||
            url.port || url.search || url.hash) throw new Error("Unsupported source");
        model = url.pathname.slice(1);
      } catch { result.invalid = true; return result; }
    } else model = model.replace(/^(?:hf\.co|huggingface\.co)\//, "");
    // Runtime/API wrappers do not become the model's publisher.
    const wrapped = /^([^/:]+)[/:](.+)$/.exec(model);
    const wrapper = wrapped && platformAliases.get(aliasKey(wrapped[1]));
    if (wrapper && wrapper.id !== "huggingface") { via = wrapper; model = wrapped[2]; }
    if (model.startsWith("ft:")) { model = model.slice(3).split(":", 1)[0]; result.fineTuned = true; }
    if (/%|[?#]|(^|\/)\.{1,2}(\/|$)/.test(model)) { result.invalid = true; return result; }
    const parts = model.split("/");
    if (parts.length > 32 || parts.some(part => !part)) { result.invalid = true; return result; }
    if (parts.length > 1) result.namespace = parts[0];
    // HF resolve/blob URLs identify the repository, not a generic weights filename.
    const repository = parts.indexOf("resolve") === 2 || parts.indexOf("blob") === 2;
    model = repository ? parts[1] : parts.at(-1);
    // Bedrock's explicit publisher IDs, optionally prefixed by an inference region.
    const bedrock = /^(?:(?:us|eu|apac|global)\.)?(anthropic|amazon|meta|mistral|cohere|ai21)\.(.+)$/.exec(model);
    if (bedrock) { result.namespace = bedrock[1]; model = bedrock[2]; }
    result.model = model.replace(/\.(?:gguf|safetensors|bin)$/, "");
    result.via = via;
    return result;
  }
  function resolveModel(reference = "", options = {}) {
    if (typeof options === "string") options = { provider: options };
    const parsed = parse(reference, options.runtime || options.provider);
    const publisher = namespaces.get(parsed.namespace);
    const family = !parsed.invalid && familyFor(parsed.model);
    const scoped = publisher && familyFor(parsed.model, publisher.id);
    let creator = scoped ? publisher : family ? providers.get(family.creator) : publisher;
    let selectedFamily = scoped || family || null;
    let match = scoped ? "namespace-family" : family ? "family" : publisher ? "namespace" : "unknown";
    if (publisher && family && publisher.id !== family.creator && !scoped) {
      // A reviewed derivative publisher can identify its own fine-tune. An
      // otherwise contradictory official namespace is deliberately ambiguous.
      if (publisher.derivativePublisher) {
        creator = publisher; selectedFamily = null; match = "namespace-derivative";
      } else { creator = null; selectedFamily = null; match = "conflict"; }
    }
    if (parsed.invalid) { creator = null; selectedFamily = null; match = "invalid"; }
    const familyIcon = selectedFamily?.icon;
    const mark = icon(familyIcon && own(catalog.icons, familyIcon) ? familyIcon : creator?.icon);
    const via = identity(parsed.via);
    return Object.freeze({ model: parsed.model, creator: identity(creator),
      family: selectedFamily ? Object.freeze({ id: selectedFamily.id, name: selectedFamily.name }) : null,
      publisher: parsed.namespace || null,
      publisherVerified: Boolean(publisher),
      baseCreator: family && creator?.id !== family.creator ? identity(providers.get(family.creator)) : null,
      fineTuned: parsed.fineTuned || match === "namespace-derivative",
      match, icon: mark.mono, colorIcon: mark.color || null,
      runtime: via?.kind === "runtime" ? via : null,
      apiProvider: via && via.kind !== "runtime" ? via : null });
  }
  function paint(target, mark, { size, appearance = "mono" } = {}) {
    const id = icon(mark).mono;
    const colorId = icon(mark).color;
    target.dataset.brand = id;
    target.dataset.appearance = appearance === "color" && colorId ? "color" : "mono";
    if ([16, 20, 24, 32].includes(size)) target.dataset.iconSize = String(size);
    target.style.setProperty("--model-brand-image", `url("/icons/ai/${id}.svg")`);
    target.style.setProperty("--model-brand-color-image", `url("/icons/ai/${colorId || id}.svg")`);
    return id;
  }
  function setModelIcon(target, reference, options = {}) {
    const result = resolveModel(reference, options);
    paint(target, result.icon, options);
    target.dataset.creator = result.creator?.id || "";
    target.dataset.family = result.family?.id || "";
    target.title = result.creator ? `${result.creator.name}${result.family ? ` · ${result.family.name}` : ""}` : "AI model";
    return result;
  }
  function setPlatformIcon(target, value, options = {}) {
    const result = platform(value);
    paint(target, result?.icon, options);
    target.title = result?.name || "AI platform";
    return result;
  }
  return Object.freeze({ catalog, resolveModel, provider, platform, setModelIcon, setPlatformIcon });
}
