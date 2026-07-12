"""klaude — local-first AI coding agent.

Commands:
  klaude chat                 interactive agent session in the current repo
  klaude ask "question"       one-shot question (tools enabled)
  klaude learn URL|FILE -c X  ingest docs into the knowledge base
  klaude query "q" [-c X]     hybrid-search the knowledge base
  klaude search "q"           local web search (SearXNG)
  klaude remember "fact"      append a durable fact to memory
  klaude doctor               verify every service and model
"""

from __future__ import annotations

import time
import uuid
from importlib import resources
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from klaude_core import Agent, Memory, Ollama, PermissionGate, Tool, load_config

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def _ask_permission(tool: str, detail: str) -> str:
    console.print(Panel(detail, title=f"[bold yellow]{tool}[/]", border_style="yellow"))
    return console.input("[yellow]allow? \\[y]es / \\[n]o / \\[a]lways: [/]").strip().lower()[:1]


def _system_prompt(memory: Memory) -> str:
    template = (
        resources.files("klaude_core") / "prompts" / "system.md"
    ).read_text()
    return template.replace("{MEMORY}", memory.facts() or "(none)")


def _build_agent(workdir: Path, model: str | None = None) -> tuple[Agent, object]:
    from klaude_knowledge import Knowledge
    from klaude_tools import Workspace, build_tools
    from klaude_web import Web

    cfg = load_config()
    ollama = Ollama(cfg.ollama_url)
    memory = Memory(cfg.memory_file, cfg.sessions_db)
    ws = Workspace(workdir)
    tools = build_tools(ws)

    web = Web(cfg)
    kn = Knowledge(cfg, ollama)
    S = {"type": "string"}
    tools += [
        Tool(
            "web_search",
            "Search the web (local SearXNG). Use for current info not in local knowledge.",
            {"type": "object", "properties": {"query": S}, "required": ["query"]},
            lambda query: "\n\n".join(
                f"{r['title']}\n{r['url']}\n{r['snippet']}" for r in web.search(query)
            ) or "(no results)",
        ),
        Tool(
            "fetch_url",
            "Fetch a web page as markdown.",
            {"type": "object", "properties": {"url": S}, "required": ["url"]},
            lambda url: web.fetch(url)[:15_000],
        ),
        Tool(
            "query_knowledge",
            "Search the local docs knowledge base (learned documentation). "
            "Always try this before web_search for library/framework questions.",
            {
                "type": "object",
                "properties": {"question": S, "collection": S},
                "required": ["question"],
            },
            lambda question, collection="": kn.query_as_context(
                question, collection, cfg.retrieval_k
            ),
        ),
    ]

    gate = PermissionGate(cfg.permissions, _ask_permission)
    agent = Agent(
        ollama,
        model or cfg.models["coder"],
        tools,
        gate,
        _system_prompt(memory),
        max_steps=cfg.max_agent_steps,
    )
    branch_note = ws.ensure_work_branch(time.strftime("%Y%m%d-%H%M"))
    console.print(f"[dim]{branch_note}[/]")
    return agent, memory


def _render(agent: Agent, memory: Memory, session_id: str, user_msg: str) -> None:
    memory.log_turn(session_id, "user", user_msg)
    for event in agent.run(user_msg):
        if event.kind == "text" and event.payload.get("content"):
            console.print(Markdown(event.payload["content"]))
            memory.log_turn(session_id, "assistant", event.payload["content"])
        elif event.kind == "tool_start":
            console.print(f"[dim]-> {event.payload['tool']}[/]")
        elif event.kind == "tool_result":
            preview = event.payload["result"][:200].replace("\n", " ")
            console.print(f"[dim]   {preview}[/]")
        elif event.kind == "error":
            console.print(f"[red]error: {event.payload['message']}[/]")


def _resolve_model(ollama: Ollama, name: str) -> str | None:
    """Match a user-typed name against installed models (exact, then prefix,
    then substring). Returns the full model name or None."""
    installed = ollama.list_models()
    if name in installed:
        return name
    prefix = [m for m in installed if m.startswith(name)]
    if len(prefix) == 1:
        return prefix[0]
    sub = [m for m in installed if name.lower() in m.lower()]
    if len(sub) == 1:
        return sub[0]
    return None


@app.command()
def chat(model: str = typer.Option("", help="override the coder model")):
    """Interactive agent session in the current directory."""
    agent, memory = _build_agent(Path.cwd(), model or None)
    session_id = str(uuid.uuid4())[:8]
    console.print(
        f"[bold]klaude[/] [dim]({agent.model})[/] — type your task; "
        "/models lists, /model NAME switches, /quit exits\n"
    )
    while True:
        try:
            user_msg = console.input("[bold cyan]you>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_msg:
            continue
        if user_msg in {"/quit", "/exit", "/q"}:
            break
        if user_msg == "/models":
            for m in agent.ollama.list_models():
                marker = " [green]<- active[/]" if m == agent.model else ""
                console.print(f"  {m}{marker}")
            continue
        if user_msg.startswith("/model"):
            target = user_msg.removeprefix("/model").strip()
            if not target:
                console.print(f"active model: [bold]{agent.model}[/]")
                continue
            resolved = _resolve_model(agent.ollama, target)
            if resolved:
                agent.model = resolved
                console.print(f"[green]switched to {resolved}[/] [dim](history kept)[/]")
            else:
                console.print(
                    f"[red]no unique match for '{target}'[/] — see /models"
                )
            continue
        _render(agent, memory, session_id, user_msg)
    console.print("[dim]bye[/]")


@app.command()
def ask(question: str, model: str = typer.Option("", help="override model")):
    """One-shot question with tools enabled."""
    agent, memory = _build_agent(Path.cwd(), model or None)
    _render(agent, memory, str(uuid.uuid4())[:8], question)


@app.command()
def learn(
    source: str,
    collection: str = typer.Option(..., "-c", "--collection", help="collection name"),
):
    """Ingest a URL or local file into the knowledge base."""
    from klaude_knowledge import Knowledge
    from klaude_web import Web

    cfg = load_config()
    kn = Knowledge(cfg)
    if source.startswith(("http://", "https://")):
        console.print(f"[dim]fetching {source}...[/]")
        text = Web(cfg).fetch(source)
        n = kn.learn_text(collection, text, source=source)
    else:
        n = kn.learn_file(collection, source)
    console.print(f"[green]learned {n} chunks into '{collection}'[/]")


@app.command()
def query(
    question: str,
    collection: str = typer.Option("", "-c", "--collection"),
    k: int = typer.Option(6, "-k"),
):
    """Hybrid-search the knowledge base (no LLM, raw chunks)."""
    from klaude_knowledge import Knowledge

    kn = Knowledge(load_config())
    for hit in kn.query(question, collection, k):
        src = hit.get("source") or hit.get("collection", "?")
        console.print(Panel(hit["text"][:600], title=src, border_style="dim"))


@app.command()
def search(q: str, n: int = typer.Option(8, "-n")):
    """Local web search via SearXNG."""
    from klaude_web import Web

    for r in Web(load_config()).search(q, n):
        console.print(f"[bold]{r['title']}[/]\n[blue]{r['url']}[/]\n{r['snippet']}\n")


@app.command()
def models():
    """List every model installed in Ollama and which role klaude assigns it."""
    cfg = load_config()
    ollama = Ollama(cfg.ollama_url, timeout=5)
    if not ollama.is_up():
        console.print(f"[red]ollama not reachable at {cfg.ollama_url}[/]")
        raise typer.Exit(1)
    roles = {v: k for k, v in cfg.models.items() if v}
    for m in ollama.list_models():
        role = roles.get(m) or roles.get(m.split(":")[0], "")
        tag = f"  [green]<- {role}[/]" if role else ""
        console.print(f"  {m}{tag}")
    console.print(
        "\n[dim]use any of these:  klaude chat --model NAME   or  /model NAME in chat\n"
        "make one permanent in ~/.config/klaude/config.toml under [models.override][/]"
    )


@app.command()
def remember(fact: str):
    """Append a durable fact to memory.md (goes into every system prompt)."""
    cfg = load_config()
    Memory(cfg.memory_file, cfg.sessions_db).remember(fact)
    console.print("[green]saved to memory[/]")


@app.command()
def doctor():
    """Check every service, model, and directory klaude needs."""
    cfg = load_config()
    ok = True

    def check(name: str, passed: bool, hint: str = ""):
        nonlocal ok
        mark = "[green]OK[/]" if passed else "[red]FAIL[/]"
        console.print(f"{mark}  {name}" + (f"  [dim]{hint}[/]" if not passed and hint else ""))
        ok = ok and passed

    ollama = Ollama(cfg.ollama_url, timeout=5)
    up = ollama.is_up()
    check(f"ollama at {cfg.ollama_url}", up, "start with: ollama serve")

    if up:
        installed = ollama.list_models()
        for role, model in cfg.models.items():
            if not model:
                continue
            have = any(m.startswith(model.split(":")[0]) for m in installed)
            check(f"model {role}: {model}", have, f"run: ollama pull {model}")

    try:
        import httpx

        r = httpx.get(f"{cfg.searxng_url}/search", params={"q": "test", "format": "json"}, timeout=8)
        check(f"searxng at {cfg.searxng_url}", r.status_code == 200,
              "docker compose up -d; ensure 'json' in search.formats")
    except Exception:
        check(f"searxng at {cfg.searxng_url}", False, "docker compose up -d")

    if cfg.crawl4ai_url:
        try:
            import httpx

            r = httpx.get(f"{cfg.crawl4ai_url}/health", timeout=5)
            check(f"crawl4ai at {cfg.crawl4ai_url}", r.status_code == 200)
        except Exception:
            check(f"crawl4ai at {cfg.crawl4ai_url}", False,
                  "docker compose --profile heavy up -d")
    else:
        console.print("[dim]--   crawl4ai not configured (optional; trafilatura fallback active)[/]")

    check(f"data dir {cfg.data_dir}", cfg.data_dir.exists() and cfg.data_dir.is_dir())
    console.print(f"\n[dim]hardware tier: {cfg.tier} -> coder model {cfg.models['coder']}[/]")
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
