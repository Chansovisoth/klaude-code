# Canvas usage policy research — 2026-10-27

Official sources reviewed:

- [ChatGPT writing/code blocks](https://help.openai.com/en/articles/20001246-working-with-writing-blocks-and-code-blocks-in-chatgpt): editable drafts intended for revision/reuse include emails, updates and documents. Supported code blocks provide editing and preview actions. Available actions vary by context.
- [Claude Artifacts](https://support.claude.com/en/articles/17153992-what-are-artifacts-and-how-do-i-use-them): significant, independent work intended for editing/reuse; around fifteen lines is a typical signal, not a universal requirement. Examples include documents, code, web pages, SVG and diagrams.
- [OpenAI's original Canvas introduction](https://openai.com/index/introducing-canvas/), October 2024: distinguishes writing/code collaboration from general Q&A and describes conservative coding triggers. This is historical design rationale; the current help page above describes today's writing/code blocks. The old Canvas help URL returned 404.

## Klaude adaptation

The previous universal 600-character/three-paragraph gate was too rigid. Canvas
eligibility now combines the user's requested work with the actual output, using
`static/canvas-policy.js` bundled into the existing app route.

| Request/output | Klaude behavior |
| --- | --- |
| Requested essay, article, letter, email, report or other document | Offer Canvas for a meaningful draft; short reusable emails can qualify |
| Generic writing request without a named deliverable | Require substantive content; length does not activate Canvas without intent |
| Turn notes into a document; revise or translate a draft | Recognize the creation/revision intent |
| Make it shorter/more formal after a writing task | Inherit the immediately preceding artifact context |
| Ordinary explanation or Q&A, including how-to-writing questions | Stay in chat; unrelated questions clear inherited artifact intent |
| Requested named file, reusable script/component, full HTML/SVG or substantial code | Offer the code Canvas action |
| Tiny unnamed code example | Retain inline code actions |
| Explicit use/open Canvas or /canvas | Override ordinary size eligibility |
| No Canvas, keep inline or a negative writing request | Suppress contextual Canvas |

Writing drafts omit clear conversational introductions and closing offers when
opened in the editor. Header/menu Canvas opens an existing draft or the latest
eligible document rather than starting an unrelated blank editor. Response and
code actions still let users select the exact work to edit. Existing tab-local
drafts remain accessible. The panel continues to open through the user's action;
this slice adds no automatic popup, execution, network access or workspace edit.

These are Klaude's deterministic presentation heuristics, not a claim to reproduce
either product's private model classifier. English intent phrases are recognized;
explicit /canvas also provides a language-independent opt-in. Some ambiguous or
multilingual requests may still need an explicit instruction. No extra model call
is made to classify a response. Existing passive preview boundaries remain.

## Validation

- `/tmp/klaude_canvas_policy_test.js`: 17 policy cases, including output
  shape signals, short emails, negative/how-to requests, revision context, tiny
  examples, named code files, SVG and document-wrapper extraction.
- `/tmp/klaude_canvas_research_check.py`: saved essay/Q&A/email/revision pairs,
  actual header document opening, source extraction, explicit opt-in/opt-out,
  code eligibility and 1440/390/320px no-overflow checks; no browser exceptions.
- JavaScript syntax, app bundle consistency and `git diff --check` passed.

These checks use isolated fixtures, without live model generation or a live-host
restart. Full AI-driven document revision/history remains outside this trigger
policy change.
