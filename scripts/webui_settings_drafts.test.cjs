// Run with node --test scripts/webui_settings_drafts.test.cjs.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const context = { window: {}, document: { addEventListener() {} } };
// Load the reusable draft module from the existing management asset. No new
// asset route or structuredClone global is available.
const source = readFileSync('apps/webhost/src/klaude_webhost/static/management.js', 'utf8');
vm.runInNewContext(source.split('\n// Profile data remains')[0], context);
const Store = context.window.SettingsDraftState;
const field = (id, value, version = value) => ({ id, value, version, label: id });

test('JSON drafts work without structuredClone and own their nested values', () => {
  assert.equal(vm.runInNewContext('typeof structuredClone', context), 'undefined');
  const state = new Store();
  state.ingest([field('image', { endpoint: 'http://localhost:1234', enabled: false })]);
  const value = { endpoint: 'http://localhost:2345', enabled: true };
  state.set('image', value); value.endpoint = 'changed outside the draft';
  assert.equal(state.get('image').endpoint, 'http://localhost:2345');
  state.discard(); assert.equal(state.get('image').endpoint, 'http://localhost:1234');
});

test('returning a draft to its saved value clears it; discard uses the latest confirmed read', () => {
  const state = new Store(); state.ingest([field('a', 'ask')]);
  state.set('a', 'allow'); assert.equal(state.changed().length, 1);
  state.set('a', 'ask'); assert.equal(state.changed().length, 0);
  state.set('a', 'allow'); state.ingest([field('a', 'deny')]);
  assert.equal(state.entries.get('a').conflict, true);
  assert.equal(state.get('a'), 'allow');
  state.discard(); assert.equal(state.get('a'), 'deny'); assert.equal(state.changed().length, 0);
});

test('refresh never silently rebases a concurrent edit; keeping a draft requires an explicit rebase', () => {
  const state = new Store(); state.ingest([field('a', 1)]); state.set('a', 2);
  state.ingest([field('a', 3)]);
  assert.equal(state.entries.get('a').base.value, 1);
  assert.equal(state.entries.get('a').conflict, true);
  state.rebase('a'); assert.equal(state.get('a'), 2); assert.equal(state.entries.get('a').base.value, 3);
});

test('a receipt and a matching read do not clear an unconfirmed save; partial success is field-local', () => {
  const state = new Store(); state.ingest([field('a', 1), field('b', 2)]);
  state.set('a', 3); state.set('b', 4);
  const a = state.entries.get('a'); a.pending = { request_id: 'original', phase: 'unconfirmed' };
  state.ingest([field('a', 3), field('b', 2)]);
  assert.equal(a.base.value, 1); assert.equal(state.changed().length, 2);
  state.discard(); assert.equal(a.pending.request_id, 'original'); assert.equal(a.base.value, 1);
  assert.equal(state.get('b'), 2);
  state.set('b', 4); state.confirm(a);
  assert.equal(state.changed().length, 1); assert.equal(state.get('b'), 4);
});

test('category drafts are isolated and ordered fallback arrays compare by value', () => {
  const agent = new Store(), models = new Store();
  agent.ingest([field('a', true)]); models.ingest([field('fallbacks', ['a', 'b'])]);
  agent.set('a', false); models.set('fallbacks', ['b', 'a']);
  agent.discard(); assert.equal(models.changed().length, 1);
  models.set('fallbacks', ['a', 'b']); assert.equal(models.changed().length, 0);
});

test('a fresh confirmed read matching an unsubmitted draft has no remaining change', () => {
  const state = new Store(); state.ingest([field('a', 1)]); state.set('a', 2);
  state.ingest([field('a', 2)]);
  assert.equal(state.changed().length, 0); assert.equal(state.entries.get('a').base.value, 2);
});

test('security warnings distinguish grants from restrictions', () => {
  const warning = context.window.SettingsDrafts.accessWarning;
  const entry = (id, from, to) => ({ base: field(id, from), value: to });
  assert.ok(warning(entry('permissions.read_file', 'ask', 'allow')).includes('without an approval'));
  assert.ok(warning(entry('permissions.read_file', 'deny', 'ask')));
  assert.ok(warning(entry('tool_availability.read_file', false, true)));
  assert.equal(warning(entry('permissions.read_file', 'allow', 'deny')), null);
  assert.equal(warning(entry('tool_availability.read_file', true, false)), null);
  assert.equal(warning(entry('runtime_options.max_steps', 10, 20)), null);
});
