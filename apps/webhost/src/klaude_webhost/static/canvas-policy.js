"use strict";

// Local presentation policy: explicit intent plus reusable work, never reply length alone.
// Research and adaptation notes: docs/webui/canvas-trigger-research.md.
window.KlaudeCanvasPolicy = (() => {
  const none = () => ({kind:'none', explicit:false, reusable:false, name:'Draft.md'});
  const lead = '(?:^|[.!?\\n]\\s*|\\b(?:please help|please|can you|could you|would you|help me|help|i want you to|i need you to)\\s+)';
  const action = new RegExp(lead + '(write|draft|compose|author|rewrite|revise|reword|polish|edit|expand|translate|create|generate|make|prepare|give me|turn|convert|transform|refactor|debug|fix)\\b', 'i');
  const documents = /\b(?:essay|article|blog(?: post)?|email|letter|story|poem|report|document|proposal|speech|tutorial|guide|draft|paragraphs?|social post|slack update|announcement|resume|cover letter|readme|checklist|outline|plan)\b|\.md\b/i;
  const codeFile = /\b[\w-]+\.(?:py|js|ts|jsx|tsx|html?|svg|css|json|sh|rs|go|java|c|cpp|cs|rb|php|sql|ya?ml|toml|swift|kt)\b/i;
  const code = /\b(?:code|script|program|function|class|component|website|web page|app|html|svg|module|configuration|config|sql|stylesheet|diagram|flowchart|mermaid)\b/i;
  const reusableCode = /\b(?:script|program|component|website|web page|app|html|svg|module|file|configuration|stylesheet|diagram|flowchart|mermaid)\b/i;
  const revision = /\b(?:rewrite|revise|reword|polish|edit|expand|translate|refactor|debug|fix)\b/i;
  const followup = /^(?:(?:please|can you|could you|would you)\s+)?(?:(?:make|keep)\s+(?:it|this|the draft|the article|the essay|the code)\s+(?:shorter|longer|clearer|simpler|more|less)|(?:add|remove|change|replace)\b.{0,60}\b(?:paragraph|section|heading|introduction|conclusion|tone|function|comments?)\b|(?:continue|expand|shorten|lengthen|polish|revise|rewrite|refactor|debug|fix)\b)/i;
  function intent(value, previous = null) {
    if (typeof value !== 'string') return none();
    const request = value.slice(0, 8000).replace(/```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)/g, '')
      .replace(/^\s*>.*$/gm, '').trim();
    if (/\b(?:no|without)\s+(?:a\s+)?canvas\b|\b(?:do not|don't|dont|never|avoid)\s+(?:use|open|show|write|draft|compose|rewrite|create|generate)\b|\b(?:keep|leave)\b.{0,30}\b(?:in chat|inline)\b/i.test(request)) return none();
    const explicit = /(?:^|\s)\/canvas\b|\b(?:use|open|show)\s+(?:(?:a|the)\s+)?canvas\b|\b(?:in|using|with)\s+(?:(?:a|the)\s+)?canvas\b/i.test(request);
    if (!explicit && previous && previous.kind !== 'none' && followup.test(request) &&
        !documents.test(request) && !code.test(request) && !codeFile.test(request)) return {...previous, explicit:false};
    const match = action.exec(request);
    if (!match && !explicit) {
      return previous && previous.kind !== 'none' && followup.test(request) ? {...previous, explicit:false} : none();
    }
    const verb = match?.[1]?.toLowerCase() || '';
    const wantsDocument = documents.test(request), namedFile = codeFile.test(request), wantsCode = code.test(request) || namedFile;
    const isRevision = revision.test(verb);
    if (!explicit && !wantsDocument && !wantsCode && /^(?:create|generate|make|prepare|give me|turn|convert|transform|fix|debug|refactor)$/.test(verb)) return none();
    if (isRevision && !wantsDocument && !wantsCode && previous?.kind && previous.kind !== 'none')
      return {...previous, explicit};
    const kind = wantsCode && !wantsDocument ? 'code' : 'writing';
    const label = /\bessay\b/i.test(request) ? 'Essay' : /\bemail\b/i.test(request) ? 'Email draft' :
      /\bletter\b/i.test(request) ? 'Letter' : /\barticle|blog\b/i.test(request) ? 'Article' : 'Draft';
    return {kind, explicit, namedFile, reusable:kind === 'code' ? reusableCode.test(request) || namedFile : wantsDocument,
      name:`${label}.md`};
  }
  function documentSource(value) {
    const parts = String(value || '').trim().split(/\n\s*\n/);
    if (parts[0]?.length < 240 && /^(?:(?:sure|certainly)[!,.]?\s*)?(?:here(?:'s| is| are)|below is)\b[\s\S]*\b(?:draft|essay|article|email|letter|document|report|story)\b[\s\S]*:\s*$/i.test(parts[0])) parts.shift();
    if (parts.at(-1)?.length < 240 && /^(?:let me know if|would you like me to)\b/i.test(parts.at(-1))) parts.pop();
    return parts.join('\n\n').trim();
  }
  function document(value, request) {
    if (!request || request.kind === 'none' || request.kind === 'code') return false;
    const source = documentSource(value);
    if (!source || /^\s*(```|~~~)/.test(source)) return false;
    if (request.explicit) return true;
    if (/^(?:sorry\b|i (?:cannot|can't|am unable)\b|(?:what|which|could you|would you|can you)\b[\s\S]{0,160}\?$)/i.test(source)) return false;
    if (request.reusable) return source.length >= 40;
    const paragraphs = source.split(/\n\s*\n/).length, lines = source.split('\n').filter(line => line.trim()).length;
    return source.length >= 450 && (paragraphs >= 2 || lines >= 12 || source.split(/\s+/).length >= 90);
  }
  function codeBlock(value, request, namedFile = false) {
    if (!request || request.kind === 'none' || typeof value !== 'string' || !value.trim()) return false;
    if (request.explicit) return true;
    if (request.kind !== 'code') return false;
    const lines = value.split('\n').filter(line => line.trim()).length;
    return namedFile || request.namedFile || lines >= 15 || (request.reusable && (lines >= 3 || value.length >= 120)) ||
      /^\s*(?:<!doctype html|<html\b|<svg\b)/i.test(value);
  }
  return Object.freeze({intent, document, documentSource, codeBlock});
})();
