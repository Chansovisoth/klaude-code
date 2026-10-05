"""Bounded read-only check of the real Odysseus loop and local Ollama.

This is a module-level integration check, not the browser/session application
or the CSV benchmark. The model, provider, tools, and route shaping are real.
Tool selection is explicit; no embedding download, teacher, or paid API is used.
"""

# Validate isolation and put the checkout on sys.path before importing it.
# ruff: noqa: E402

from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
import tempfile
import time
from pathlib import Path

if not os.getenv("ODYSSEUS_DATA_DIR") or not os.getenv("DATABASE_URL"):
    raise SystemExit("Set ODYSSEUS_DATA_DIR and DATABASE_URL to isolated temporary data first.")
if not Path(os.environ["ODYSSEUS_DATA_DIR"]).resolve().is_relative_to(Path("/tmp")):
    raise SystemExit("This research check requires ODYSSEUS_DATA_DIR under /tmp.")
database_url = os.environ["DATABASE_URL"]
if database_url != "sqlite:///:memory:" and not (
    database_url.startswith("sqlite:///")
    and Path(database_url.removeprefix("sqlite:///")).resolve().is_relative_to(Path("/tmp"))
):
    raise SystemExit("This research check requires an isolated SQLite database under /tmp.")

REPO = Path(__file__).parent / "odysseus"
sys.path.insert(0, str(REPO.resolve()))

import src.agent_loop as al
from src.model_context import estimate_tokens
from src.tool_policy import known_tool_names

MODEL = os.getenv("ODYSSEUS_AUDIT_MODEL", "qwen2.5-coder:3b")
ENDPOINT = "http://127.0.0.1:11434"
NATIVE = "--native-tools" in sys.argv
OUTPUT = Path(
    os.getenv(
        "ODYSSEUS_AUDIT_OUTPUT",
        str(
            Path("/tmp/klaude-odysseus-audit")
            / ("live-native-check.json" if NATIVE else "live-check.json")
        ),
    )
)
report = dict(
    model=MODEL,
    endpoint=ENDPOINT,
    native_support_configured=NATIVE,
    scope="real module loop, explicit read-only selection",
    turns=[],
)

if NATIVE:
    # Use the application's real endpoint configuration field, not a mocked
    # routing decision. DATABASE_URL must name an isolated temporary file.
    from core.database import Base, ModelEndpoint, SessionLocal, engine

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(
            ModelEndpoint(
                id="audit-ollama", name="Audit local Ollama", base_url=ENDPOINT, supports_tools=True
            )
        )
        db.commit()
actual_provider = al.stream_llm_with_fallback
requests = []


async def observed_provider(candidates, messages, **kwargs):
    factory = kwargs.get("candidate_request_factory")

    async def observed_factory(*args):
        request = await factory(*args)
        requests.append(copy.deepcopy(request))
        return request

    if factory is not None:
        kwargs["candidate_request_factory"] = observed_factory
    async for chunk in actual_provider(candidates, messages, **kwargs):
        yield chunk


al.stream_llm_with_fallback = observed_provider


async def turn(messages, workspace):
    start = time.monotonic()
    offset = len(requests)
    events = []
    final = ""
    async for chunk in al.stream_agent_loop(
        ENDPOINT,
        MODEL,
        copy.deepcopy(messages),
        workspace=str(workspace),
        relevant_tools={"read_file", "ls"},
        disabled_tools=known_tool_names() - {"read_file", "ls"},
        max_rounds=5,
        max_tokens=350,
        context_length=4096,
        temperature=0.0,
    ):
        for line in chunk.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            event = json.loads(line[6:])
            events.append(event)
            if event.get("delta") and not event.get("thinking"):
                final += event["delta"]
            if event.get("type") == "tool_output":
                print(json.dumps(event), flush=True)
    captured = requests[offset:]
    result = dict(
        elapsed_seconds=round(time.monotonic() - start, 2),
        final=final,
        tool_results=[e for e in events if e.get("type") == "tool_output"],
        events=events,
        requests=captured,
        request_estimated_message_tokens=[estimate_tokens(r["messages"]) for r in captured],
        request_schema_counts=[len(r.get("kwargs", {}).get("tools") or []) for r in captured],
    )
    report["turns"].append(result)
    OUTPUT.write_text(json.dumps(report, indent=2))
    print(
        json.dumps({k: v for k, v in result.items() if k not in {"events", "requests"}}), flush=True
    )
    if not captured:
        raise RuntimeError("No real provider request was captured")
    history = copy.deepcopy(captured[-1]["messages"])
    history.append(dict(role="assistant", content=final))
    return history


async def main():
    with tempfile.TemporaryDirectory(prefix="odysseus-read-only-") as root:
        workspace = Path(root)
        source = "CANARY = 'river-4827-moss'\n"
        (workspace / "sample.py").write_text(source)
        history = await turn(
            [
                dict(
                    role="user",
                    content="Read sample.py in this workspace using your read_file tool. "
                    "Report the exact string assigned to CANARY. "
                    "Do not modify files or run commands.",
                )
            ],
            workspace,
        )
        history.append(
            dict(
                role="user",
                content="Using the file content you just read, what are the three "
                "dash-separated parts of CANARY? "
                "Do not read the file again or call tools. Answer briefly.",
            )
        )
        await turn(history, workspace)
        report["source_unchanged"] = (workspace / "sample.py").read_text() == source
        report["first_turn_read_succeeded"] = any(
            e.get("tool") == "read_file"
            and e.get("exit_code") == 0
            and "river-4827-moss" in e.get("output", "")
            for e in report["turns"][0]["tool_results"]
        )
        report["first_answer_contains_canary"] = "river-4827-moss" in report["turns"][0]["final"]
        report["followup_no_tools"] = not report["turns"][1]["tool_results"]
        report["followup_contains_all_parts"] = all(
            p in report["turns"][1]["final"] for p in ("river", "4827", "moss")
        )
        OUTPUT.write_text(json.dumps(report, indent=2))
        print(json.dumps({k: v for k, v in report.items() if k != "turns"}), flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=110))
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        OUTPUT.write_text(json.dumps(report, indent=2))
        raise
