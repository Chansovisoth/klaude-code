# Task: Study OpenCode's TUI Design System and Apply Its Core Methodology to klaude-code

We are working on **klaude-code**.

klaude-code already has a functional interactive TUI.

I do **not** want the TUI blindly replaced, rewritten from scratch, or converted into OpenCode's architecture just because OpenCode uses a different framework.

Instead, I want you to deeply study the current OpenCode implementation and use its:

- TUI design methodology
- visual hierarchy
- interaction philosophy
- spacing
- formatting rules
- message presentation
- composer/input design
- AI activity presentation
- code formatting
- diff formatting
- session UX
- information density
- state presentation
- responsive behavior
- rendering methodology

as the primary reference for improving klaude-code.

You have explicit permission to closely follow and adapt OpenCode's **core TUI design methodology** for klaude-code.

This includes reproducing or adapting interaction and layout concepts when appropriate.

However:

- klaude-code must remain its own product.
- Do not copy OpenCode branding, logos, name, product wording, or identity.
- Prefer implementing equivalent concepts using klaude-code's existing architecture.
- Do not introduce unnecessary architectural complexity merely because OpenCode uses it.
- Treat OpenCode as a reference implementation and design system, not a dependency.
- If source code is copied directly rather than independently reimplemented, preserve all relevant license and attribution requirements.

---

# 1. Inspect klaude-code First

Before touching OpenCode, inspect the current klaude-code repository thoroughly.

Understand:

- CLI entry points
- interactive loop
- TUI renderer
- terminal framework/library
- state management
- conversation/message models
- session handling
- model/provider handling
- tool execution
- streaming
- status updates
- input/composer
- scrolling
- markdown
- code rendering
- diff rendering
- file operation rendering
- command execution rendering
- permissions
- errors
- warnings
- command palette
- slash commands
- project/context display
- terminal resize handling
- interruption/cancellation
- theme/style definitions
- terminal restoration on exit

Find where the current TUI implementation actually lives.

Trace the complete flow:

```text
CLI
→ interactive session
→ request lifecycle
→ orchestrator
→ model streaming
→ tool calls
→ state updates
→ renderer
→ terminal
```

Do not redesign anything yet.

First understand what we already have and what should be preserved.

---

# 2. Pull the Current OpenCode Repository

Clone the current OpenCode repository into a temporary/reference directory outside klaude-code.

Preferred:

```bash
gh repo clone anomalyco/opencode /tmp/opencode-reference
```

Then:

```bash
cd /tmp/opencode-reference
git fetch --all --prune
```

Inspect the currently active upstream development branch.

Do not:

- modify OpenCode
- vendor OpenCode
- add it as a submodule
- add it as a dependency
- copy the entire TUI wholesale

It is reference material only.

---

# 3. Find the Actual OpenCode TUI Implementation

Do not rely primarily on screenshots, README descriptions, marketing images, or assumptions.

Find the actual TUI source.

Trace:

```text
application startup
→ TUI initialization
→ session screen
→ message list
→ active composer
→ submitted user messages
→ assistant messages
→ tool actions
→ tool results
→ code blocks
→ diffs
→ status/activity
→ dialogs
→ overlays
→ keyboard handling
```

Identify the important:

- directories
- modules
- components
- renderers
- stores
- state models
- hooks
- formatters
- theme definitions
- border definitions
- spacing constants
- keyboard mappings

Understand how OpenCode separates:

```text
domain state
session state
execution state
presentation state
transient activity
persisted transcript
```

I want you to understand the implementation, not simply find visually similar components.

---

# 4. Primary OpenCode Files to Inspect

At minimum inspect the current equivalents of:

```text
packages/tui/src/component/prompt/
packages/tui/src/routes/session/
packages/tui/src/ui/
packages/tui/src/context/theme*
packages/tui/src/ui/border*
```

Especially inspect the active prompt/composer implementation and border utilities.

Search broadly too.

Do not assume these paths are unchanged.

---

# 5. Extract OpenCode's TUI Design System

Build a concrete design model of OpenCode's interface.

Study:

- layout
- spacing
- visual hierarchy
- semantic colors
- borders
- indentation
- typography through terminal semantics
- code presentation
- tool presentation
- submitted user messages
- input/composer
- footer
- session display
- status display
- overlays
- dialogs

Determine the underlying rules.

Do not just write:

> OpenCode uses cyan here.

Write:

> OpenCode uses an accent rail to identify an active interactive area while keeping the container itself low-noise.

That distinction matters.

---

# 6. Layout

Understand:

- primary vertical structure
- horizontal padding
- left/right margins
- spacing between messages
- spacing between tool actions
- indentation
- grouping
- separator usage
- border usage
- width constraints
- wide terminal behavior
- narrow terminal behavior
- scroll behavior
- footer placement
- prompt placement

Pay close attention to how OpenCode stays visually clean without surrounding everything with boxes.

---

# 7. OpenCode-Style Composer Side Rails

This is a specific visual treatment I want incorporated into klaude-code.

Study the actual OpenCode prompt/composer implementation carefully.

Do **not** approximate it with a literal ASCII:

```text
|
```

OpenCode uses Unicode box-drawing glyphs and actual TUI border rendering.

The important vertical rail is:

```text
┃
```

Unicode:

```text
U+2503 BOX DRAWINGS HEAVY VERTICAL
```

OpenCode also uses subtle related glyphs such as:

```text
╹
```

Unicode:

```text
U+2579 BOX DRAWINGS HEAVY UP
```

and:

```text
▀
```

Unicode:

```text
U+2580 UPPER HALF BLOCK
```

Study how these are used in the current OpenCode source.

Conceptually the composer resembles:

```text
┃██████████████████████████████████████┃
┃██  > user input                    ███┃
┃██████████████████████████████████████┃
```

where:

```text
┃
```

is the accent rail and the interior has a subtle element background.

It should **not** simply look like:

```text
| > user input
```

---

# 8. Composer Border Methodology

OpenCode's composer should be understood as:

```text
accent rail
+
subtle background fill
+
internal padding
+
minimal top/bottom decoration
```

rather than a conventional full rectangle.

Do not default to:

```text
┌─────────────────────────────────────┐
│ > input                             │
└─────────────────────────────────────┘
```

For the main composer, prefer something conceptually closer to:

```text
┃  > input
┃
┃
```

with the content area carrying a slightly differentiated background.

Use the current TUI framework's actual border/rendering primitives where possible.

Do **not** just concatenate `┃` characters into rendered strings unless the current framework requires that.

Why:

- multiline input must stay aligned
- cursor position must remain correct
- wrapping must remain correct
- mouse regions must remain correct
- colors must remain independent
- terminal width calculations must remain correct
- resizing must remain correct

---

# 9. Composer Background

The input should have a subtle filled background distinct from the terminal background.

The effect should conceptually be:

```text
terminal background

   ┃██████████████████████████████
   ┃██  > write something...    ██
   ┃██████████████████████████████
```

The composer must feel:

- interactive
- focused
- clean
- lightweight
- integrated

It should not look like a heavy modal or giant card.

---

# 10. Composer Rail Color

Do not hardcode cyan just because screenshots show cyan.

Study OpenCode's actual active-border color logic.

The side rail should use semantic state.

Potential states include:

- default active agent accent
- shell mode
- leader/shortcut mode
- disabled state
- permission state
- warning state
- error state

Use klaude-code's theme system.

Prefer semantic tokens such as:

```text
theme.border
theme.accent
theme.primary
theme.muted
theme.error
theme.warning
```

rather than raw RGB/hex values scattered across components.

---

# 11. Composer Rail Fallbacks

Preferred vertical rail:

```text
┃
```

Fallback:

```text
│
```

ASCII fallback only as a last resort:

```text
|
```

Meaning must not depend entirely on the glyph.

Ensure no terminal width/cursor issues are introduced.

---

# 12. New Session Presentation

Study exactly how OpenCode displays a newly created session.

Pay attention to:

- empty state
- logo/title area
- project information
- model information
- agent information
- hints
- shortcut display
- composer location
- footer
- status
- spacing
- intentionally hidden information

Compare this against klaude-code's current startup screen.

I want the same design reasoning:

```text
minimal
quiet
clear
focused
```

not necessarily a pixel-perfect copy.

---

# 13. Submitted / Already-Inputted User Messages

This is a high-priority area.

Study how OpenCode transforms:

```text
editable composer content
```

into:

```text
submitted transcript content
```

The active composer and historical user messages must feel clearly different.

Study:

- indentation
- rails
- background
- prompt prefix
- text color
- wrapping
- multiline prompts
- attachments
- file references
- pasted text
- commands
- long prompts

The submitted message should feel like part of the transcript, not like a disabled textarea.

Do not reuse the exact active-composer affordance for historical prompts unless appropriate.

---

# 14. Active Input / Composer

Study:

- cursor behavior
- prompt indicator
- multiline expansion
- internal padding
- placeholder
- background
- rail
- active state
- disabled state
- model indicator
- agent indicator
- context indicator
- mode indicator
- keyboard hints
- command autocomplete
- file autocomplete
- slash commands
- submit behavior
- cancel behavior
- input history

The composer should be visually obvious without dominating the terminal.

---

# 15. AI Activity / Actions

This is another highest-priority area.

Study how OpenCode renders actions such as:

```text
Thinking
Planning
Searching
Reading
Listing
Grepping
Web search
Fetching URL
Running command
Editing
Writing
Deleting
Testing
Invoking subagent
Waiting
Requesting permission
Failed
Completed
```

Understand the difference between:

```text
transient execution activity
```

and:

```text
persistent transcript content
```

Determine:

- what remains visible
- what disappears
- what gets collapsed
- what is replaced
- what is summarized

---

# 16. Tool Action Wording

Prefer meaningful activity wording.

Good:

```text
Searching project
Reading src/foo.py
Running tests
Editing server.ts
```

Bad:

```text
Executing internal tool dispatcher
Awaiting callback
Calling implementation handler
```

Show what matters to the user.

Hide internal protocol details.

---

# 17. Tool Activity Visual Style

Study:

- symbols
- icons
- indentation
- muted text
- accent text
- duration
- path formatting
- completion markers
- failure markers
- nested information
- command preview
- result preview

The interface should not resemble a verbose debug console.

---

# 18. AI Response Formatting

Study how OpenCode renders assistant responses.

Inspect:

- paragraphs
- headings
- lists
- numbered lists
- inline code
- fenced code
- quotes
- tables
- links
- file paths
- commands
- emphasis
- markdown
- long output
- wrapping

Pay particular attention to spacing between:

```text
user message
assistant prose
tool activity
code
diffs
next message
```

---

# 19. Code Areas

This is another major priority.

Study how OpenCode displays:

- fenced code
- syntax highlighting
- language labels
- file names
- commands
- command output
- file contents
- long code
- wrapped lines
- truncated content

The code area should feel visually distinct from prose without requiring heavy decoration.

---

# 20. Diff Rendering

Study OpenCode's diff rendering closely.

Inspect:

- file header
- line numbers
- old line numbers
- new line numbers
- added lines
- removed lines
- unchanged context
- inline modifications
- background colors
- foreground colors
- indentation
- gutters
- truncation
- multi-file changes

The user must be able to scan modifications quickly.

---

# 21. File Modification Presentation

Study how operations appear:

```text
Edit src/foo.py
Write src/bar.py
Delete src/old.py
```

Inspect:

- operation label
- path emphasis
- success/failure state
- diff
- multi-file grouping
- collapsed output
- expanded output

klaude-code should make repository changes extremely easy to scan.

---

# 22. Command Presentation

Study how shell commands are shown.

Understand the distinction between:

```text
command being executed
```

and:

```text
command output
```

Consider:

- prompt marker
- command background
- output indentation
- exit status
- elapsed time
- stdout
- stderr
- truncation
- failure styling

Do not dump raw command metadata unless useful.

---

# 23. Tool Result Formatting

Study results for:

```text
Search
Read
Glob
Grep
Bash
Web
Git
LSP
Tests
```

Determine:

- when full output is shown
- when output is summarized
- when output is collapsed
- when only result count is shown
- how paths are formatted
- how failures appear

---

# 24. Streaming

Study OpenCode's streaming behavior.

Inspect:

- first-token transition
- partial markdown
- unfinished code fences
- tool-call transitions
- status updates
- repaint behavior
- flicker
- reflow
- scroll anchoring
- input responsiveness during generation

The finished response and the streaming response should feel like the same component.

---

# 25. Reduce Flicker

A beautiful TUI that flickers is not acceptable.

Investigate whether OpenCode uses:

- selective rerendering
- batched renders
- incremental text updates
- stable component identity
- cached formatting
- deferred syntax highlighting
- render throttling
- virtualized message lists
- dirty-region rendering

Adopt suitable ideas only if klaude-code benefits.

---

# 26. Status Language

klaude-code currently has or has experimented with states such as:

```text
Starting
Planning
Thinking
Reading files
Searching project
Searching memory
Selecting tool
Calling tool
Running command
Writing code
Applying patch
Generating response
Running tests
Waiting for tool
Done
```

Use OpenCode as the design reference for deciding:

- which are worth showing
- which should be merged
- which should be transient
- which should remain
- where they should appear
- whether a spinner is appropriate
- how much detail to expose

Prefer:

```text
Searching project
```

over:

```text
Waiting for tool dispatcher callback
```

---

# 27. Visual Hierarchy

Extract OpenCode's hierarchy.

Suggested semantic layers:

## Highest emphasis

Things the user is actively interacting with.

Examples:

```text
composer
permission prompt
selected menu item
```

## Strong emphasis

```text
submitted user prompt
important assistant answer
```

## Medium emphasis

```text
code
diffs
file changes
significant actions
```

## Low emphasis

```text
tool activity
metadata
status
```

## Very low emphasis

```text
hints
timestamps
IDs
secondary shortcut text
token counts
```

Implement this intentionally.

---

# 28. Color System

Inspect OpenCode's actual theme system.

Extract semantic roles such as:

```text
text
muted
accent
primary
success
warning
error
border
background
backgroundElement
selected
code
diffAdd
diffRemove
tool
user
assistant
```

Do not hardcode arbitrary colors throughout klaude-code.

If necessary, introduce a semantic theme abstraction.

Prefer:

```text
theme.text
theme.muted
theme.accent
theme.error
```

over:

```text
"#73daca"
```

inside components.

---

# 29. Typography Through Terminal Semantics

Because terminal typography is limited, hierarchy should come from:

- foreground color
- background color
- bold
- dim
- spacing
- indentation
- glyphs
- grouping
- borders

Avoid excessive:

- boxes
- panels
- borders
- bright colors
- emoji
- separators
- persistent labels

unless they serve a clear function.

---

# 30. Information Density

OpenCode manages to show a lot of agent behavior without looking noisy.

Determine where it intentionally:

- omits information
- abbreviates information
- collapses information
- hides finished transient state
- uses muted styling
- puts metadata inline
- avoids headings
- avoids boxes
- avoids repeated labels

Apply the same philosophy.

---

# 31. Keyboard UX

Study:

- Enter
- Shift+Enter
- Ctrl+Enter if used
- Escape
- Ctrl+C
- Tab
- Shift+Tab
- arrow keys
- input history
- page navigation
- scrolling
- focus
- command palette
- autocomplete
- session switching
- modal interaction
- interrupt behavior

Do not copy shortcuts blindly if klaude-code already has sensible mappings.

Adopt interaction principles, not merely keys.

---

# 32. Session UX

Study the current OpenCode session experience.

Understand:

- creating session
- restoring session
- switching session
- continuing session
- naming session
- session metadata
- session history
- current-session indication
- transcript restoration
- title display

Pay special attention to the **new session format**.

---

# 33. Dialogs and Overlays

Inspect OpenCode's:

- session picker
- model picker
- agent picker
- command palette
- permissions
- confirmation
- help
- errors
- selections

Extract reusable patterns for:

```text
modal
selector
searchable selector
confirmation
permission prompt
command palette
```

Create a consistent klaude-code visual vocabulary.

---

# 34. Error UX

Study:

- model errors
- provider errors
- tool failures
- shell failures
- network failures
- permission denial
- invalid input
- context overflow
- unavailable model
- interrupted generation

Errors must be noticeable without destroying the interface.

---

# 35. Resize and Responsive Behavior

Test or inspect behavior around:

```text
80 columns
100 columns
120 columns
160 columns
200+ columns
```

Also test short terminal heights.

klaude-code must remain usable on small terminals.

Avoid layouts that only look good at large widths.

---

# 36. Terminal Compatibility

Maintain:

- readable contrast
- NO_COLOR support where practical
- limited-color terminals
- Unicode fallback
- narrow terminal support
- keyboard-only usability
- terminal-safe width calculations

Meaning should not depend solely on color.

Examples:

```text
✓ success
✗ failure
+ added
- removed
```

may reinforce semantic coloring.

---

# 37. Compare OpenCode Against klaude-code

After studying both repositories, produce a design-gap analysis.

Use a structure such as:

```text
Component
Current klaude-code behavior
OpenCode behavior
Underlying design principle
Recommended klaude-code change
Difficulty
Priority
```

Example:

```text
Submitted prompt

klaude-code:
Looks nearly identical to editable input.

OpenCode:
Submitted prompt becomes compact transcript content.

Principle:
Editable and historical states need different affordances.

Recommendation:
Separate Composer and UserMessage rendering.
```

Focus on design principles, not screenshots.

---

# 38. Create a Small klaude-code TUI Design Specification

Before major implementation, define a small internal design system covering:

```text
spacing
indentation
message structure
colors
backgrounds
borders
side rails
symbols
tool actions
statuses
code
diffs
errors
input
sessions
modals
markdown
```

Do not create an enormous UI framework.

The goal is consistency.

---

# 39. Suggested Component Boundaries

Where appropriate, prefer conceptual boundaries similar to:

```text
App
SessionView
Transcript
UserMessage
AssistantMessage
ToolAction
ToolResult
CodeBlock
DiffBlock
Composer
StatusIndicator
PermissionPrompt
CommandPalette
SessionPicker
ModelPicker
Toast
ErrorMessage
```

These names are examples.

Adapt to klaude-code's current language/framework.

---

# 40. Preserve klaude-code's Existing Strengths

Do not remove working klaude-code functionality just to match OpenCode.

Preserve:

- local Ollama support
- local-first design
- project search
- local RAG
- local knowledge
- memory
- web tools
- Hugging Face tools
- git integration
- sessions
- slash commands
- controller/orchestrator architecture
- provider-specific behavior
- one-shot CLI mode
- interactive CLI mode

OpenCode is primarily a UX and TUI design reference for this task.

klaude-code does not need to become an OpenCode fork.

---

# 41. Avoid False Parity

Do not implement features merely because OpenCode has them.

For every borrowed concept ask:

```text
Does this improve klaude-code?

Does klaude-code already solve this?

Can it fit our architecture cleanly?

Does it reduce noise?

Does it improve usability?

Will the implementation cost be justified?
```

If not, leave it out.

---

# 42. Implementation Priorities

Use roughly this order.

## Priority 1 — Core transcript and composer

- new-session layout
- active composer
- OpenCode-style `┃` side rails
- subtle composer background fill
- correct rail coloring
- correct `╹` / lower-edge treatment where useful
- submitted user prompts
- assistant response layout
- spacing
- hierarchy

## Priority 2 — AI activity

- thinking
- search
- file reads
- commands
- tool calls
- tool results
- status transitions
- failures

## Priority 3 — Code experience

- code blocks
- command areas
- command output
- file paths
- edits
- diffs

## Priority 4 — Navigation

- sessions
- model picker
- agent picker
- command palette
- permissions
- overlays

## Priority 5 — Polish

- responsive behavior
- animations
- spinners
- metadata
- render optimization
- reduced flicker
- accessibility

---

# 43. Important Design Rule

Do not equate:

```text
clean
```

with:

```text
less information
```

The goal is:

> Show the right information, at the right visual priority, at the right time.

Examples:

A tool action may remain visible while its raw protocol disappears.

A status may be visible while active and disappear when no longer useful.

A submitted prompt may remain prominent while losing the visual affordance of an editable composer.

The active composer may use:

```text
┃
background fill
accent
cursor
```

while historical messages use a calmer transcript treatment.

This is the kind of reasoning I want adopted from OpenCode.

---

# 44. Permission to Make Structural TUI Improvements

You are explicitly authorized to refactor klaude-code's TUI where necessary.

You may:

- split large render functions
- introduce reusable TUI components
- introduce theme tokens
- introduce semantic border styles
- introduce OpenCode-inspired side rails
- introduce structured action models
- separate transient execution state from persisted transcript state
- improve session rendering
- improve tool rendering
- improve markdown
- improve code rendering
- improve diff rendering
- improve input handling
- improve spacing
- improve hierarchy
- consolidate duplicated styles
- remove obsolete TUI formatting

Do not unnecessarily rewrite:

- orchestration
- providers
- model APIs
- RAG
- memory
- tool infrastructure
- web infrastructure

just because the TUI is changing.

Keep UI refactors appropriately isolated.

---

# 45. Composer Acceptance Criteria

The final composer should visually follow this philosophy:

```text
┃██████████████████████████████████████
┃██  > type here                     ██
┃██████████████████████████████████████
```

with:

- a real border rail
- subtle background fill
- internal left/right padding
- clean multiline expansion
- low-noise metadata
- no heavy full rectangle
- responsive width
- correct cursor behavior
- no broken wrap behavior
- no width miscalculation
- no flicker

The rail should be visually narrow and elegant.

The interior background should remain subtle.

---

# 46. Composer Multi-Line Acceptance Test

Test:

```text
> Please inspect the backend and find
  where authentication is handled.

  Then update the session validation
  and run the tests.
```

The side rail must remain aligned across every row.

The cursor must remain correct.

Resizing the terminal must not corrupt the rails.

---

# 47. Submitted Prompt Acceptance Criteria

Once submitted, the user message should no longer look like an active textarea.

It should become transcript content.

Make sure the distinction between:

```text
editing
```

and:

```text
history
```

is immediately visible.

---

# 48. Testing

After implementation, test at minimum:

## New session

Open klaude-code without conversation history.

## Simple prompt

```text
hello
```

## Multiline input

Use 5-10 lines.

## Very long input

Test wrapping.

## Markdown response

Include:

- headings
- lists
- bold
- inline code
- quotes

## Code response

Multiple fenced languages.

## Tool sequence

Example:

```text
search project
→ read file
→ edit file
→ run tests
```

## Failed tool

Ensure error formatting is clear.

## Shell command

Test both success and failure.

## Diff

Test:

- one-line change
- many-line change
- multiple files

## Streaming

Watch live output.

## Interrupt

Cancel a generation.

## Resize

Resize during:

- idle
- typing
- streaming
- tool execution

## Long session

Ensure scrolling remains correct.

## Restored session

Ensure persisted messages still render correctly.

---

# 49. Regression Requirements

Do not break:

- one-shot CLI
- interactive CLI
- sessions
- command handling
- model switching
- provider selection
- Ollama
- web mode
- RAG
- memory
- tools
- git
- cancellation
- Ctrl+C
- prompt history
- terminal restoration after exit

The terminal must always return to a sane state after interruption or crash.

---

# 50. Work Incrementally

Do not perform one massive visual rewrite.

Prefer coherent batches.

Suggested batches:

```text
Batch 1
Design system + theme + border primitives

Batch 2
New session + composer + submitted prompts

Batch 3
Assistant messages + markdown + code blocks

Batch 4
Tool actions + statuses + results

Batch 5
Diffs + file edits + shell output

Batch 6
Sessions + dialogs + navigation

Batch 7
Responsive behavior + performance + polish
```

Adjust based on the actual repository architecture.

---

# 51. Before Editing

Before making substantial changes, report what you found.

Provide:

## Current klaude-code architecture

Relevant files and flow.

## Current OpenCode TUI architecture

Relevant files and flow.

## OpenCode design principles discovered

Not just file names.

## OpenCode composer implementation

Explain specifically:

- side rails
- border glyphs
- background
- padding
- accent coloring
- footer transition
- active state

## Major klaude-code UX gaps

Rank them.

## Proposed architecture

Explain:

- what stays
- what changes
- where components should split
- where semantic styles should live

## Implementation batches

Give the concrete sequence you intend to follow.

Then begin implementation unless you discover a real architectural blocker.

Do not stop merely to ask whether the obvious next step is okay.

---

# 52. During Implementation

Whenever you reproduce an OpenCode interaction pattern, explain the design reasoning internally and implement based on that reasoning.

Bad reasoning:

```text
OpenCode uses 2 spaces here, therefore use 2 spaces.
```

Better reasoning:

```text
OpenCode creates whitespace instead of surrounding every transcript item with boxes. This makes the conversation easier to scan. Apply the same principle within klaude-code's renderer.
```

Bad reasoning:

```text
OpenCode uses ┃, so prepend ┃ to strings.
```

Better reasoning:

```text
OpenCode uses a semantic vertical rail as an interactive affordance. Implement it as an actual border primitive so multiline layout, cursor movement, resize behavior, and coloring remain correct.
```

---

# 53. Do Not Over-Decorate

Avoid turning the interface into a dashboard.

Do not overuse:

```text
┌─────┐
│ box │
└─────┘
```

Do not place every action in a card.

Do not put every section behind a border.

Prefer:

- whitespace
- indentation
- muted metadata
- semantic accent
- side rails
- subtle backgrounds
- concise labels

---

# 54. TUI Philosophy to Preserve

klaude-code should feel:

```text
terminal-native
not GUI-inside-terminal
```

Use terminal primitives well.

Do not try to imitate a desktop application.

---

# 55. Definition of Success

The redesigned klaude-code TUI should feel:

- calm
- fast
- intentional
- compact
- modern
- keyboard-first
- developer-focused
- readable
- information-rich without being noisy
- terminal-native

A user familiar with OpenCode should recognize that klaude-code follows a similarly strong terminal UX philosophy.

But it should still clearly feel like **klaude-code**, not a reskinned OpenCode.

The most important improvements are:

1. OpenCode-style TUI design methodology.
2. Cleaner new-session presentation.
3. OpenCode-style composer with `┃` side rails.
4. Subtle composer background fill.
5. Strong distinction between active input and submitted prompts.
6. Excellent assistant response formatting.
7. Excellent code-block rendering.
8. Excellent diff/file-edit rendering.
9. Clean AI action/tool-call presentation.
10. Better thinking/searching/reading/running/writing hierarchy.
11. Less visual noise.
12. Consistent reusable theme and border primitives.
13. Smooth streaming.
14. Minimal flicker.
15. Responsive terminal behavior.
16. Polished session UX.
17. Preserve all important klaude-code functionality.

Treat OpenCode's **current TUI source code as the primary reference**.

Treat screenshots and documentation as secondary reference.

Understand it deeply first.

Then adapt the strongest ideas to klaude-code.

Do not blindly clone.

Do not superficially imitate.

Adopt the design reasoning.