"""Explicit local launcher for Klaude's experimental WebUI."""

from __future__ import annotations

import argparse
import asyncio
import signal
from dataclasses import replace
from pathlib import Path

from klaude_application import HeadlessApplication, open_local_session
from klaude_application.library_management import LibraryManagement
from klaude_application.workspace_reads import WorkspaceReadService
from klaude_core.chat_images import ChatImages
from klaude_core.config import load_config
from klaude_core.model_runtime import OllamaRuntime
from klaude_core.ollama import Ollama

from .accounts import AccountStore
from .host import READ_ONLY_TOOLS, LocalWebHost
from .hosting import WEBUI_PORT, ManagedControl

WEB_CHAT_FORMATTING = (
    "Browser replies support CommonMark Markdown, tables, strikethrough and task lists. "
    "Use concise paragraphs by default, headings and lists when helpful, inline backticks "
    "for code identifiers, and fenced code blocks with language names for code. "
    "Do not wrap an entire normal reply in a code fence or emit raw HTML. "
    "Respect the user's requested output format, including plain text or structured data."
)


def create_application(workdir: Path, *, session_id: str | None = None) -> HeadlessApplication:
    """Use the shared Agent with safe initial tools and no branch setup."""
    cfg = load_config()
    runtime = OllamaRuntime(Ollama(cfg.ollama_url))
    agent, memory = open_local_session(workdir.resolve(), runtime, config=cfg)
    try:
        agent.set_system_prompt(f"{agent.messages[0]['content']}\n\n{WEB_CHAT_FORMATTING}")
        agent.image_context = ChatImages(cfg, agent)
        agent.tools = {name: tool for name, tool in agent.tools.items()
                       if name in READ_ONLY_TOOLS}
        reads = WorkspaceReadService(agent.workspace)
        agent.tools["read_file"] = replace(
            agent.tools["read_file"], fn=reads.read_file,
        )
        agent.tools["list_dir"] = replace(
            agent.tools["list_dir"], fn=reads.list_dir,
        )
        agent.tools["grep"] = replace(
            agent.tools["grep"], fn=reads.grep,
        )
        agent.tools["git_status"] = replace(
            agent.tools["git_status"], fn=reads.git_status,
        )
        agent.tools["git_diff"] = replace(
            agent.tools["git_diff"], fn=reads.git_diff,
        )
        agent.workspace.write_enabled = False
        agent.gate.policies["request_user_input"] = "allow"
        app = HeadlessApplication(agent, memory, session_id, allow_user_input_tool=True)
        if session_id is not None:
            app.resume_local(session_id)
        binding = app.turns.workspace(app.session_id)
        path = str(workdir.resolve())
        if binding is None:
            app.turns.bind_workspace(app.session_id, path, expected_revision=0)
        elif binding[0] != path:
            raise ValueError("session belongs to another workspace")
        return app
    except BaseException:
        close = getattr(runtime, "close", None)
        if callable(close):
            close()
        memory.db.close()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Klaude's experimental local WebUI")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--port", type=int, default=WEBUI_PORT)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--reset-admin-password", action="store_true",
                        help="Generate a new local admin password and sign out browsers")
    parser.add_argument("--managed", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--lan-ip", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()
    accounts = AccountStore(load_config().config_dir)
    accounts.initialize()
    if args.reset_admin_password:
        print("Username: admin")
        print(f"New password: {accounts.reset_password()}")
        return
    app = create_application(args.workspace, session_id=args.session_id)
    try:
        host = LocalWebHost(
            app, port=args.port, staging_dir=load_config().data_dir / "webui-staging",
            accounts=accounts,
            library=LibraryManagement(load_config(), args.workspace),
        )
    except BaseException:
        asyncio.run(app.close())
        raise
    control = None
    if args.managed:
        try:
            if args.lan_ip:
                host.start_lan(args.lan_ip, load_config().data_dir / "webhost")
            control = ManagedControl(load_config().data_dir / "webhost", host, args.workspace)
        except BaseException:
            host.stop_lan()
            host.http.server_close()
            if host.library is not None:
                host.library.close()
            if host.transfers is not None:
                host.transfers.close()
            asyncio.run(app.close())
            raise
    elif args.lan_ip:
        host.http.server_close()
        if host.library is not None:
            host.library.close()
        if host.transfers is not None:
            host.transfers.close()
        asyncio.run(app.close())
        parser.error("LAN binding is managed through /settings web")
    else:
        print(f"Open {host.bootstrap_url}", flush=True)
        if accounts.initial_password() is not None:
            print("Username: admin. Reveal the initial password in /settings web "
                  "or read the private local file:", flush=True)
            print(accounts.initial_password_path, flush=True)
        else:
            print("Sign in with your local admin account.", flush=True)
        print("Browser tools: read-only until local edit activation.", flush=True)
        print("Press Ctrl+C to stop the host.", flush=True)
    def stop(_signum: int, _frame: object) -> None:
        # shutdown() must run outside serve_forever's thread.
        import threading

        threading.Thread(target=host.http.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        host.serve_forever()
    finally:
        try:
            host.stop()
        finally:
            if control is not None:
                control.close()


if __name__ == "__main__":
    main()
