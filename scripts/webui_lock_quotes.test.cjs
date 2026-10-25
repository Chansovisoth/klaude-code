// node --test scripts/webui_lock_quotes.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const staticRoot = path.join(__dirname, '../apps/webhost/src/klaude_webhost/static');
const collection = JSON.parse(fs.readFileSync(path.join(staticRoot, 'lockscreen-quotes.json'), 'utf8'));
const source = fs.readFileSync(path.join(staticRoot, 'lockscreen-quotes.js'), 'utf8');
const storageKey = 'klaude-lock-quote-rotation-v1';
function store() {
  const values = new Map();
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
}
function load(data = collection, storage = store()) {
  const window = { KlaudeLockQuoteCollection: data, localStorage: storage };
  vm.runInNewContext(source, { window });
  return window.KlaudeLockQuotes;
}
function verifyCycles(next, cycles = 20, size = collection.quotes.length) {
  let previous = null;
  for (let cycle = 0; cycle < cycles; cycle++) {
    const seen = new Set();
    for (let index = 0; index < size; index++) {
      const quote = next();
      if (size > 1) assert.notEqual(quote.id, previous, 'Adjacent openings must differ, including cycle boundaries');
      assert(!seen.has(quote.id), 'Each quote appears once per cycle');
      seen.add(quote.id);
      previous = quote.id;
    }
    assert.equal(seen.size, size);
  }
}

test('curation retains complete, short, auditable records', () => {
  assert.equal(collection.quotes.length, collection.dataset.selected_rows + collection.easter_eggs.selected_rows);
  assert.equal(collection.dataset.reviewed_rows, 30);
  assert.equal(collection.dataset.selected_rows, 19);
  assert.equal(collection.dataset.license, 'other');
  assert.equal(new Set(collection.quotes.map(row => row.id)).size, collection.quotes.length);
  assert.equal(new Set(collection.quotes.map(row => row.quote)).size, collection.quotes.length);
  const eggs = collection.quotes.filter(row => row.source_kind === 'easter_egg');
  assert.equal(eggs.filter(row => row.category === 'pop_culture').length, collection.easter_eggs.pop_culture_rows);
  assert.equal(eggs.filter(row => row.category === 'meme').length, collection.easter_eggs.meme_rows);
  assert.equal(eggs.filter(row => row.category === 'greeting').length, collection.easter_eggs.greeting_rows);
  for (const quote of ['Also try Minecraft.', 'Also try Terraria.', 'Also try Hytale.',
    'TETSUOOOO', 'Hello, sugar.', '67']) {
    assert(eggs.some(row => row.quote === quote && row.origin === 'user_prompt'));
  }
  for (const row of collection.quotes) {
    assert([...row.quote].length <= 80);
    if (row.source_kind === 'easter_egg') {
      assert(['Klaude', 'User supplied'].includes(row.attribution));
      assert(!row.source_entry && !row.source_url && !row.detail_url);
    } else {
      assert.equal(row.attribution, 'English Proverb');
      assert.equal(row.source_compiler, 'Thomas Preston');
      assert(row.source_entry > 0);
      assert.equal(row.source_url, 'https://www.gutenberg.org/ebooks/39281');
      assert(row.public_domain_scope.includes('USA'));
      assert.equal(row.detail_url, `https://positivequotation.com/quote/${row.id}`);
    }
  }
});

test('shuffled cycles have no adjacent repeats for extreme and ordinary draws', () => {
  for (const random of [() => 0, () => .999999, Math.random]) {
    verifyCycles(load().createRotation(collection, { random }));
  }
});

test('reloads resume the bag, including its last quote, without storing text', () => {
  const storage = store();
  verifyCycles(() => load(collection, storage).next());
  const saved = JSON.parse(storage.getItem(storageKey));
  assert.deepEqual(Object.keys(saved).sort(), ['collection', 'last', 'remaining']);
  assert(saved.remaining.every(Number.isInteger));
  assert(!storage.getItem(storageKey).includes('quote"'));
});

test('blocked or corrupt browser storage cannot break rotation or sign-in', () => {
  const blocked = { getItem() { throw Error('Blocked'); }, setItem() { throw Error('Quota'); } };
  verifyCycles(load(collection, blocked).next);
  const storage = store();
  for (const saved of ['{broken', 'null', '{"remaining":[]}', 'x'.repeat(9000)]) {
    storage.setItem(storageKey, saved);
    verifyCycles(load(collection, storage).next);
  }
  const window = { KlaudeLockQuoteCollection: collection };
  Object.defineProperty(window, 'localStorage', { get() { throw Error('Blocked'); } });
  vm.runInNewContext(source, { window });
  verifyCycles(window.KlaudeLockQuotes.next);
});

test('changed or tampered bags are discarded without invalid IDs or repetition', () => {
  const storage = store();
  load(collection, storage).next();
  const saved = JSON.parse(storage.getItem(storageKey));
  for (const remaining of [[saved.last], [12345], [collection.quotes[0].id, collection.quotes[0].id], 'bad']) {
    storage.setItem(storageKey, JSON.stringify({ ...saved, remaining }));
    const next = load(collection, storage).next;
    const first = next();
    assert.notEqual(first.id, saved.last);
    assert(collection.quotes.some(q => q.id === first.id));
  }
  storage.setItem(storageKey, JSON.stringify({ ...saved, collection: 'old-version' }));
  verifyCycles(load(collection, storage).next);
});

test('sequential openings in existing tabs share a bag; write failures keep in-memory progress', () => {
  const storage = store();
  const tabs = [load(collection, storage), load(collection, storage)];
  let index = 0;
  verifyCycles(() => tabs[index++ % tabs.length].next());
  const saved = storage.getItem(storageKey);
  const readOnly = { getItem: () => saved, setItem() { throw Error('Quota'); } };
  verifyCycles(load(collection, readOnly).next);
});

test('missing or invalid data has a short, explicitly original offline fallback', () => {
  for (const data of [null, {}, { version: 99, quotes: collection.quotes },
    { version: 1, quotes: [null, { quote: 'invented' }, { ...collection.quotes[0], quote: 'x'.repeat(81) }] }]) {
    const quote = load(data).next();
    assert.equal(quote.id, 'klaude-original');
    assert.equal(quote.attribution, 'Klaude');
    assert.equal(quote.quote, 'Make a little room for a new idea.');
    assert([...quote.quote].length <= 80);
  }
  const one = { ...collection, quotes: [collection.quotes[0]] };
  verifyCycles(load(one).next, 10, 1);
});
