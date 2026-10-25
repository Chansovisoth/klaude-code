"use strict";

// Data is embedded from lockscreen-quotes.json at build time, before this file.
// No network, credentials, clock callbacks, or timers enter the quote rotation.
window.KlaudeLockQuotes = (() => {
  const fallback = Object.freeze({ id: 'klaude-original', quote: 'Make a little room for a new idea.', attribution: 'Klaude' });
  const storageKey = 'klaude-lock-quote-rotation-v1';

  function createRotation(collection, { storage = null, random = Math.random } = {}) {
    const records = Array.isArray(collection?.quotes) && collection.version === 1 ? collection.quotes : [];
    const quotes = new Map();
    for (const row of records) {
      const validOrigin = row?.source_kind === 'easter_egg'
        ? ['pop_culture', 'meme', 'greeting'].includes(row.category)
          && ['user_prompt', 'original_microcopy'].includes(row.origin)
          && !row.source_entry && !row.source_url
        : row != null && row.source_kind === undefined && Number.isSafeInteger(row.source_entry) && row.source_entry > 0
          && typeof row.source_url === 'string' && row.source_url.startsWith('https://');
      if (!Number.isSafeInteger(row?.id) || row.id <= 0 || typeof row.quote !== 'string'
          || !row.quote.trim() || [...row.quote].length > 80 || /[\x00-\x1f\x7f]/.test(row.quote)
          || typeof row.attribution !== 'string' || !row.attribution.trim()
          || !validOrigin) continue;
      quotes.set(row.id, Object.freeze({ ...row }));
    }
    const ids = [...quotes.keys()];
    const signature = String(collection?.collection_id || '') + ':' + ids.join(',');
    let remaining = [], last = null, observed = null;
    function restore() {
      try {
        const raw = storage?.getItem(storageKey);
        if (raw === observed) return;
        observed = raw;
        const saved = raw && raw.length < 8192 ? JSON.parse(raw) : null;
        if (saved?.collection === signature && quotes.has(saved.last)) {
          last = saved.last;
          remaining = Array.isArray(saved.remaining) && saved.remaining.length < ids.length
            && new Set(saved.remaining).size === saved.remaining.length
            && saved.remaining.every(id => quotes.has(id) && id !== last) ? saved.remaining : [];
        }
      } catch { /* A blocked/corrupt store falls back to an in-memory rotation. */ }
    }

    return () => {
      if (!ids.length) return fallback;
      // Another already-open tab may have advanced the public bag since load.
      // Unchanged storage never overwrites our in-memory progress after a quota
      // failure, and the displayed quote still changes only on screen opening.
      restore();
      if (!remaining.length) {
        remaining = [...ids];
        for (let index = remaining.length - 1; index > 0; index--) {
          const swap = Math.floor(random() * (index + 1));
          [remaining[index], remaining[swap]] = [remaining[swap], remaining[index]];
        }
        if (remaining.length > 1 && remaining[0] === last) {
          const swap = 1 + Math.floor(random() * (remaining.length - 1));
          [remaining[0], remaining[swap]] = [remaining[swap], remaining[0]];
        }
      }
      last = remaining.shift();
      try {
        // Only public quote IDs/order are persisted. No account or session data.
        const saved = JSON.stringify({ collection: signature, remaining, last });
        if (storage) { storage.setItem(storageKey, saved); observed = saved; }
      } catch { /* Quota/private mode must never prevent sign-in. */ }
      return quotes.get(last);
    };
  }

  let storage = null;
  try { storage = window.localStorage; } catch { /* In-memory rotation remains usable. */ }
  return Object.freeze({ next: createRotation(window.KlaudeLockQuoteCollection, { storage }), createRotation });
})();
