const assert = require('node:assert/strict');
const { test } = require('node:test');
const icons = require('../../apps/webhost/src/klaude_webhost/static/ai-icons.js');
const cases = [
  ['gpt-oss:20b','openai','openai'], ['qwen3.5:9b','alibaba','qwen'],
  ['qwen2.5-coder:3b','alibaba','qwen'], ['gemma4:12b','google','gemma'],
  ['deepseek-r1:7b','deepseek','deepseek'], ['llama3.2:3b','meta','meta'],
  ['mistral:7b','mistral','mistral'], ['phi4-mini','microsoft','microsoft'],
  ['glm-4.5','zai','zai'], ['kimi-k2','moonshot','kimi'],
  ['claude-sonnet-4','anthropic','claude'], ['openai/gpt-oss-20b','openai','openai'],
  ['anthropic/claude-sonnet-4','anthropic','claude'],
  ['ollama@local/gemma4:12b','google','gemma'],
  ['openrouter@cloud/google/gemma-3-27b-it','google','gemma'],
  ['openrouter/anthropic/claude-sonnet-4','anthropic','claude'],
  ['hf.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF:Q4_K_M','alibaba','qwen'],
  ['https://huggingface.co/google/gemma-3-4b-it/resolve/main/model.safetensors','google','gemma'],
  ['bartowski/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf','alibaba','qwen'],
  ['gpt-neox-20b','eleutherai','generic'], ['gpt-j-6b','eleutherai','generic'],
  ['gpt-neo-2.7B','eleutherai','generic'], ['grok-3','xai','grok'],
  ['x-ai/grok-3','xai','grok'], ['THUDM/chatglm3-6b','zai','chatglm'],
  ['ZAI-org/GLM-4.5','zai','zai'], ['01-ai/Yi-1.5-9B','01ai','yi'],
  ['deepseek-ai/DeepSeek-R1-Distill-Qwen-7B','deepseek','deepseek'],
  ['cognitivecomputations/dolphin-2.9-llama3-8b','cognitivecomputations','dolphin'],
  ['NousResearch/Llama-3.1-8B','nous','nousresearch'],
  ['ft:gpt-4o-mini:org:name:123','openai','openai'],
  ['us.anthropic.claude-sonnet-4-v1:0','anthropic','claude'],
  ['amazon.nova-pro-v1:0','aws','nova'], ['google/future-model','google','google'],
  ['bigcode/starcoder2-15b','bigcode','generic'], ['reflection/beam-28b','reflection','generic'],
];
for (const [model, creator, icon] of cases) test(model, () => {
  const result = icons.resolveModel(model, {provider:'ollama'});
  assert.equal(result.creator?.id, creator);
  assert.equal(result.icon, icon);
});
for (const model of ['unknown-custom', 'my-gemma', 'gemmatic', 'qwenish', 'groq', 'o10',
  'reflection-70b', 'google/claude-sonnet-4', 'openai/llama3', 'my-org/custom-model',
  'https://evil.example/gemma4', 'google/../gemma4', 'gemma4?x=1', 'gemma4\nhi',
  'openai_compatible@local/custom', 'custom-llama-tune']) test(`generic: ${model}`, () => {
  assert.equal(icons.resolveModel(model, {provider:'ollama'}).icon, 'generic');
});
test('runtime and API do not replace creator identity', () => {
  let r = icons.resolveModel('ollama@local/gemma4:12b');
  assert.equal(r.runtime.id,'ollama'); assert.equal(r.apiProvider,null);
  assert.equal(r.creator.id,'google');
  r = icons.resolveModel('openrouter@cloud/anthropic/claude-sonnet-4');
  assert.equal(r.apiProvider.id,'openrouter'); assert.equal(r.runtime,null);
  assert.equal(icons.resolveModel('custom', {provider:'openai'}).creator,null);
  assert.equal(icons.resolveModel('custom', {provider:'ollama'}).runtime.icon,'ollama');
});
test('aliases distinguish brands from API protocols and similarly named services', () => {
  for (const [alias,id] of [['Google AI','google'], ['Qwen','alibaba'], ['Z.ai','zai'],
    ['01.AI','01ai'], ['Cognitive Computations','cognitivecomputations']])
    assert.equal(icons.provider(alias)?.id,id,alias);
  for (const [alias,id] of [['LM Studio','lmstudio'], ['llama.cpp','llamacpp'],
    ['Together AI','together'], ['Fireworks AI','fireworks'], ['Groq','groq']])
    assert.equal(icons.platform(alias)?.id,id,alias);
  assert.equal(icons.provider('openai_compatible'),null);
  assert.equal(icons.provider('Groq'),null);
  assert.equal(icons.platform('not-a-service'),null);
});
test('complete records, assets, immutability and data-only expansion', () => {
  assert.equal(icons.catalog.providers.length,54);
  assert.equal(icons.catalog.platforms.length,19);
  for (const group of ['providers','families','platforms']) for (const r of icons.catalog[group]) {
    assert.ok(r.id && r.name && r.source);
    if (r.icon) assert.ok(icons.catalog.icons[r.icon],r.icon);
  }
  assert.ok(Object.isFrozen(icons.catalog.providers));
});
test('renderer uses approved local assets and supported sizes', () => {
  const target = {dataset:{},style:{setProperty(key,value){this[key]=value}}};
  icons.setModelIcon(target,'gemma4:12b',{size:20,appearance:'color'});
  assert.equal(target.dataset.creator,'google'); assert.equal(target.dataset.iconSize,'20');
  assert.ok(target.style['--model-brand-image'].includes('/icons/ai/gemma.svg'));
  icons.setPlatformIcon(target,'Ollama',{size:32});
  assert.equal(target.dataset.brand,'ollama'); assert.equal(target.dataset.iconSize,'32');
  icons.setModelIcon(target,'<script>',{size:21});
  assert.equal(target.dataset.brand,'generic');
});
