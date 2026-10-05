"""Audit real Odysseus modules; scripted providers are explicitly test doubles.

Some tests characterize limitations, not desirable product behavior. No paid
provider, embedding service, browser, or real user data is used.
"""

# The separate checkout must be placed on sys.path before application imports.
# ruff: noqa: E402

from __future__ import annotations

import asyncio
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).parent / "odysseus"
sys.path.insert(0, str(REPO.resolve()))

import src.agent_loop as al
import src.context_compactor as cc
import src.model_context as mc
import src.teacher_escalation as teacher
from services.memory.skills import SkillsManager
from src.agent_tools.coding_tools import TodoWriteTool
from src.chat_processor import ChatProcessor
from src.context_budget import compute_input_token_budget
from src.tool_capabilities import ToolRunSecurityContext


@pytest.fixture
def loop_settings(monkeypatch):
    monkeypatch.setattr(al, "get_setting", lambda key, default=None: default)
    monkeypatch.setattr(al, "get_mcp_manager", lambda: None)
    monkeypatch.setattr(mc, "budget_context_for_model", lambda *args, **kwargs: 8192)
    # No embeddings are constructed. Selection is supplied explicitly by tests.
    al._cached_base_prompt = None
    al._cached_base_prompt_key = None


def drive(
    monkeypatch,
    replies,
    *,
    tools,
    workspace=None,
    disabled=None,
    approved_plan=None,
    max_rounds=8,
    endpoint="https://api.openai.com/v1",
    model="gpt-4o",
):
    requests = []
    chunks = []

    async def provider(candidates, messages, **kwargs):
        candidate = kwargs.get("candidate_request_factory")
        if candidate is not None:
            url, model, headers = candidates[0]
            built = await candidate(0, url, model, headers)
            shown = built["messages"]
            shown_tools = built["kwargs"].get("tools") or []
        else:
            shown = messages
            shown_tools = kwargs.get("tools") or []
        requests.append(dict(messages=copy.deepcopy(shown), tools=copy.deepcopy(shown_tools)))
        index = len(requests) - 1
        assert index < len(replies), "unexpected extra model request"
        reply = replies[index]
        if reply.get("calls"):
            yield "data: " + json.dumps(dict(type="tool_calls", calls=reply["calls"])) + "\n\n"
        if reply.get("text"):
            yield "data: " + json.dumps(dict(delta=reply["text"])) + "\n\n"
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(al, "stream_llm_with_fallback", provider)

    async def run():
        async for chunk in al.stream_agent_loop(
            endpoint,
            model,
            [dict(role="user", content="Inspect the project source and report the result.")],
            relevant_tools=set(tools),
            disabled_tools=set(disabled or []),
            workspace=str(workspace) if workspace else None,
            approved_plan=approved_plan,
            max_rounds=max_rounds,
            context_length=8192,
        ):
            chunks.append(chunk)

    asyncio.run(asyncio.wait_for(run(), timeout=15))
    events = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                events.append(json.loads(line[6:]))
    return requests, events, chunks


def call(name, arguments, id="call_1"):
    return dict(name=name, arguments=json.dumps(arguments), id=id)


def names(request):
    return {schema["function"]["name"] for schema in request["tools"]}


def test_imports_are_actual_checkout_modules():
    assert Path(al.__file__).resolve() == (REPO / "src/agent_loop.py").resolve()
    assert Path(cc.__file__).resolve() == (REPO / "src/context_compactor.py").resolve()


def test_ollama_unknown_tool_support_gets_native_contract_without_builtin_schemas(
    monkeypatch, loop_settings
):
    requests, _, _ = drive(
        monkeypatch,
        [dict(text="There is no source evidence yet.")],
        tools={"read_file"},
        endpoint="http://127.0.0.1:11434",
        model="qwen2.5-coder:3b",
    )
    assert names(requests[0]) == set()
    system = next(m["content"] for m in requests[0]["messages"] if m["role"] == "system")
    assert "Only the tool schemas provided by the API" in system and "read_file" in system


def test_real_read_and_schema_result_roundtrip(monkeypatch, loop_settings, tmp_path):
    (tmp_path / "sample.py").write_text("ANSWER = 42\n")
    requests, events, _ = drive(
        monkeypatch,
        [
            dict(calls=[call("read_file", dict(path="sample.py"))]),
            dict(text="The source defines ANSWER as 42."),
        ],
        tools={"read_file", "write_file", "ls"},
        workspace=tmp_path,
        disabled={"write_file"},
    )
    assert len(requests) == 2
    assert all("read_file" in names(r) and "write_file" not in names(r) for r in requests)
    result = next(e for e in events if e.get("type") == "tool_output")
    assert result["exit_code"] == 0 and "ANSWER = 42" in result["output"]
    tools = [m for m in requests[1]["messages"] if m["role"] == "tool"]
    assert tools and tools[0]["tool_call_id"] == "call_1"
    assert "ANSWER = 42" in tools[0]["content"]
    assert tools[0]["metadata"]["trusted"] is False


def test_disabled_tool_cannot_write_even_if_provider_calls_it(monkeypatch, loop_settings, tmp_path):
    requests, events, _ = drive(
        monkeypatch,
        [
            dict(calls=[call("write_file", dict(path="forbidden.py", content="x=1"))]),
            dict(text="The write was blocked."),
        ],
        tools={"read_file", "write_file"},
        workspace=tmp_path,
        disabled={"write_file"},
    )
    assert "write_file" not in names(requests[0])
    assert not (tmp_path / "forbidden.py").exists()
    assert any(e.get("type") == "tool_output" and e.get("exit_code") != 0 for e in events)


def test_active_plan_is_pinned_during_execution(monkeypatch, loop_settings, tmp_path):
    (tmp_path / "sample.py").write_text("ANSWER = 42\n")
    plan = "- [ ] inspect sample.py\n- [ ] report what it defines"
    requests, _, _ = drive(
        monkeypatch,
        [
            dict(calls=[call("read_file", dict(path="sample.py"))]),
            dict(text="ANSWER is 42."),
        ],
        tools={"read_file"},
        workspace=tmp_path,
        approved_plan=plan,
    )
    assert all(
        any(plan in m.get("content", "") for m in r["messages"] if m["role"] == "system")
        for r in requests
    )


def test_plan_update_does_not_rewrite_original_pinned_note(monkeypatch, loop_settings):
    original = "- [ ] inspect code\n- [ ] run checks"
    updated = "- [x] inspect code\n- [ ] run checks"
    requests, events, _ = drive(
        monkeypatch,
        [
            dict(calls=[call("update_plan", dict(plan=updated))]),
            dict(text="Checklist updated."),
        ],
        tools={"update_plan"},
        approved_plan=original,
    )
    assert any(e.get("type") == "plan_update" and e["data"]["plan"] == updated for e in events)
    assert any(
        original in m.get("content", "") for m in requests[1]["messages"] if m["role"] == "system"
    )
    # The complete update reaches the UI and remains in the model's call
    # arguments, but its result is only a short completion count.
    assert any(
        "Plan updated (1/2 steps complete)" in m.get("content", "")
        for m in requests[1]["messages"]
        if m["role"] == "tool"
    )
    assert any(
        json.loads(tc["function"]["arguments"])["plan"] == updated
        for m in requests[1]["messages"]
        for tc in m.get("tool_calls", [])
    )


def test_announced_actions_receive_two_bounded_nudges(monkeypatch, loop_settings):
    requests, events, _ = drive(
        monkeypatch, [dict(text="I will inspect the project files.")] * 3, tools={"read_file"}
    )
    assert len(requests) == 3
    assert any(e.get("type") == "intent_nudge_exhausted" for e in events)
    assert not any(e.get("type") == "tool_output" for e in events)


def test_completion_verifier_off_by_default_does_not_validate(monkeypatch, loop_settings, tmp_path):
    async def verifier(*args, **kwargs):
        pytest.fail("default turn must not invoke optional verifier")

    monkeypatch.setattr(al, "_run_verifier_subagent", verifier)
    # A missing read plus a false final claim is not an acceptance check.
    requests, events, chunks = drive(
        monkeypatch,
        [
            dict(calls=[call("read_file", dict(path="missing.py"))]),
            dict(text="Done. All requirements are satisfied."),
        ],
        tools={"read_file"},
        workspace=tmp_path,
    )
    assert len(requests) == 2
    assert any(e.get("type") == "tool_output" and e.get("exit_code") == 1 for e in events)
    assert any("All requirements are satisfied" in e.get("delta", "") for e in events)
    assert any("data: [DONE]" in chunk for chunk in chunks)


def test_teacher_default_off_makes_no_requests(monkeypatch):
    monkeypatch.setattr("src.settings.get_setting", lambda key, default=None: default)

    async def forbidden(*args, **kwargs):
        pytest.fail("teacher disabled must not request another model")

    monkeypatch.setattr(teacher, "_call_teacher", forbidden)

    async def run():
        return [
            event
            async for event in teacher.run_teacher_inline(
                student_endpoint_url="http://127.0.0.1:11434",
                student_messages=[],
                student_tool_events=[dict(error="failed")],
                student_reply="unable to complete",
            )
        ]

    assert asyncio.run(run()) == []


def test_teacher_classifier_misses_exit_status_without_error_phrase():
    assert teacher.evaluate_turn_regex(
        [dict(exit_code=1, output="3 failed, 8 passed")], "Done"
    ) == ("ok", None)
    assert teacher.evaluate_turn_regex([dict(error="failed")], "Done")[0] == "failure"


def test_verifier_unrecognized_reply_is_not_independent_success(monkeypatch):
    async def invalid(*args, **kwargs):
        return "I cannot evaluate this."

    monkeypatch.setattr("src.llm_core.llm_call_async", invalid)
    assert (
        asyncio.run(
            al._run_verifier_subagent(
                "Implement feature",
                "[write_file] changed.py",
                endpoint_url="unused",
                model="test",
                headers={},
            )
        )
        == []
    )


def test_trim_recent_protection_can_exceed_budget_at_eleven_messages():
    messages = [dict(role="system", content="Be helpful.")]
    messages += [dict(role="assistant", content="x" * 3000) for _ in range(10)]
    messages.append(dict(role="user", content="Continue the task."))
    trimmed = cc.trim_for_context(messages, 2048, reserve_tokens=512)
    assert mc.estimate_tokens(trimmed) > 2048


def test_trim_fits_budget_when_recent_protection_is_not_activated():
    messages = [dict(role="system", content="Be helpful.")]
    messages += [dict(role="assistant", content="x" * 3000) for _ in range(9)]
    messages.append(dict(role="user", content="Continue the task."))
    assert mc.estimate_tokens(cc.trim_for_context(messages, 2048, reserve_tokens=512)) <= 1536


def test_actual_memory_context_is_relevant_bounded_and_untrusted():
    rows = [
        dict(
            id="identity",
            text="User's name is Morgan.",
            category="identity",
            pinned=True,
            timestamp=3,
        ),
        dict(
            id="db",
            text="User prefers PostgreSQL databases.",
            category="preference",
            pinned=True,
            timestamp=2,
        ),
        dict(
            id="garden",
            text="User grows carrots in the garden.",
            category="preference",
            pinned=True,
            timestamp=1,
        ),
    ]
    used = []
    memory = SimpleNamespace(
        load=lambda owner=None: rows, increment_uses=lambda ids: used.extend(ids)
    )
    processor = ChatProcessor(memory, SimpleNamespace(rag_manager=None))
    preface, _, _ = processor.build_context_preface(
        "Configure PostgreSQL databases",
        SimpleNamespace(),
        use_rag=False,
        use_memory=True,
    )
    text = "\n".join(m.get("content", "") for m in preface)
    assert "Morgan" in text and "PostgreSQL" in text and "carrots" not in text
    # A static policy is system-role; retrieved facts remain user-role data.
    fact_messages = [
        m
        for m in preface
        if "Morgan" in m.get("content", "") or "PostgreSQL" in m.get("content", "")
    ]
    assert fact_messages
    assert all(m["role"] == "user" and m["metadata"]["trusted"] is False for m in fact_messages)
    assert len(processor._last_used_memories) <= 5 and set(used) == {"identity", "db"}


def test_protected_context_can_exceed_budget():
    messages = [
        dict(role="system", content="Be helpful."),
        dict(role="user", content="SOURCE" * 2000, _protected=True),
        dict(role="user", content="Review it."),
    ]
    assert mc.estimate_tokens(cc.trim_for_context(messages, 2048)) > 2048


def test_index_platform_filter_only_applies_if_platform_is_supplied(tmp_path):
    path = tmp_path / "skills/general/linux-only/SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: linux-only\ncategory: general\nstatus: published\nplatforms: [linux]\n"
        "description: Inspect Linux configuration\n---\n\n## Procedure\n1. Inspect files\n"
    )
    manager = SkillsManager(str(tmp_path))
    assert manager.index_for(platform="windows") == []
    assert any(s["name"] == "linux-only" for s in manager.index_for())


def test_low_confidence_teacher_draft_can_be_advertised_in_index(tmp_path):
    path = tmp_path / "skills/general/draft/SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: draft\ncategory: general\nstatus: draft\nsource: teacher-escalation\n"
        "confidence: 0.1\ndescription: Inspect project files\n---\n\n"
        "## Procedure\n1. Inspect files\n"
    )
    manager = SkillsManager(str(tmp_path))
    assert any(s["name"] == "draft" for s in manager.index_for())
    assert (
        manager.get_relevant_skills("Inspect project files", manager.load(), min_confidence=0.85)
        == []
    )


def test_todo_persists_only_one_active_item(monkeypatch, tmp_path):
    monkeypatch.setattr("src.agent_tools.coding_tools._TODO_DIR", str(tmp_path))
    tool = TodoWriteTool()
    bad = dict(
        todos=[dict(content="a", status="in_progress"), dict(content="b", status="in_progress")]
    )
    assert asyncio.run(tool.execute(json.dumps(bad), dict(session_id="audit")))["exit_code"] == 1
    good = dict(
        todos=[dict(content="a", status="completed"), dict(content="b", status="in_progress")]
    )
    assert asyncio.run(tool.execute(json.dumps(good), dict(session_id="audit")))["exit_code"] == 0
    assert json.loads((tmp_path / "audit.json").read_text()) == good | {
        "todos": [
            dict(content="a", status="completed", priority="medium"),
            dict(content="b", status="in_progress", priority="medium"),
        ]
    }


@pytest.mark.parametrize(
    "window,explicit,configured,expected",
    [
        (0, False, 6000, 6000),
        (8192, False, 6000, 6963),
        (16384, False, 6000, 13926),
        (16384, True, 4096, 4096),
    ],
)
def test_actual_budget_helper(window, explicit, configured, expected):
    assert compute_input_token_budget(configured, window, explicit) == expected


def test_tool_result_taint_requires_approval_for_later_writes():
    security = ToolRunSecurityContext()
    security.observe_tool_result("read_file", dict(output="x=1", exit_code=0), "sample.py")
    assert security.decision_for("read_file").allowed
    assert not security.decision_for("write_file").allowed
