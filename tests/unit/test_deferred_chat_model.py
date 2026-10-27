"""A live turn keeps its runtime while future queued work follows model choice."""

import asyncio
import threading

import pytest
from klaude_application.browser_models import BrowserModels
from klaude_core.config import Config
from klaude_core.model_runtime import ModelInfo

from .test_application_bridge import ScriptedRuntime, _application
from .test_application_coordination import RUNTIME, _admit, _open


class WaitingRuntime(ScriptedRuntime):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.models = []

    def chat(self, model, messages, tools=None, options=None, think=None):
        self.models.append(model)
        self.entered.set()
        assert self.release.wait(5)
        return {"role": "assistant", "content": "Original reply"}


@pytest.mark.parametrize("backend", ["ollama", "openai_compatible"])
def test_live_model_choice_only_changes_next_and_already_queued_prompts(
    tmp_path, monkeypatch, backend,
):
    original = WaitingRuntime()
    app = _application(tmp_path, original)
    app.agent.tool_config = Config()
    created = []
    seen = []

    def runtime(_models, info):
        result = ScriptedRuntime([{"role": "assistant", "content": "New reply"}] * 3)
        result.backend = info.backend
        chat = result.chat

        def record(model, *args, **kwargs):
            seen.append(model)
            return chat(model, *args, **kwargs)

        result.chat = record
        created.append(result)
        return result

    monkeypatch.setattr(BrowserModels, "current", lambda *args: None)
    monkeypatch.setattr(BrowserModels, "runtime", runtime)

    async def exercise():
        try:
            handle = app.submit("First prompt", request_id="first")
            assert original.entered.wait(2)
            queued = app.enqueue("Already queued", request_id="queued-before")
            chosen = ModelInfo(backend, "next", "Next model")
            revision = app.choose_configured_model(
                chosen, expected_revision=0, request_id="select-next",
            )
            assert revision == 1
            assert app.agent.model == "fixture" and app.agent.runtime is original
            assert not original.closed and not original.cancelled
            assert app.model_selection() == (chosen, "standard", None, True)
            assert app.memory.session_runtime(app.session_id)["model"] == chosen.ref
            # Retrying an accepted queue receipt remains idempotent after retargeting.
            assert app.enqueue("Already queued", request_id="queued-before").id == queued.id
            app.enqueue("Queued after selection", request_id="queued-after")
            assert all(item["state"] == "queued" for item in app.queued())
            original.release.set()
            await handle.result()
            for _ in range(300):
                last = app.receipt("queued-after")
                if last and last.state == "completed":
                    break
                await asyncio.sleep(.01)
            assert last and last.state == "completed"
            assert original.models == ["fixture"] and original.closed
            assert seen == ["next", "next"]
            assert app.model_selection() == (chosen, "standard", None, False)
            assert not any(item["state"] == "needs_review" for item in app.queued())
        finally:
            original.release.set()
            await app.close()

    asyncio.run(exercise())


def test_latest_choice_wins_and_stale_selection_cannot_replace_it(tmp_path, monkeypatch):
    original = WaitingRuntime()
    app = _application(tmp_path, original)
    app.agent.tool_config = Config()
    monkeypatch.setattr(BrowserModels, "current", lambda *args: None)
    monkeypatch.setattr(BrowserModels, "runtime", lambda *args: ScriptedRuntime())

    async def exercise():
        try:
            handle = app.submit("Original", request_id="original")
            assert original.entered.wait(2)
            first = ModelInfo("ollama", "first-choice", "First")
            last = ModelInfo("ollama", "last-choice", "Last")
            app.choose_configured_model(first, expected_revision=0, request_id="choice-1")
            app.choose_configured_model(last, expected_revision=1, request_id="choice-2")
            with pytest.raises(ValueError, match="stale settings revision"):
                app.choose_configured_model(first, expected_revision=1, request_id="stale")
            assert app.model_selection()[0] == last and app.agent.model == "fixture"
            original.release.set()
            await handle.result()
            for _ in range(100):
                if not app.model_selection()[3]:
                    break
                await asyncio.sleep(.01)
            assert app.agent.model_info == last
            assert app.memory.session_runtime(app.session_id)["model"] == last.ref
        finally:
            original.release.set()
            await app.close()

    asyncio.run(exercise())


def test_deferred_choice_preserves_foreign_worker_fencing_and_paused_queue(tmp_path):
    memory, turns = _open(tmp_path)
    try:
        _admit(turns)
        item = turns.enqueue(session_id="session", creator_id="owner", request_id="queued",
                             text="Follow up", scope="standard", runtime=RUNTIME)
        # A recovered reservation remains paused until explicitly resumed.
        with memory.db:
            memory.db.execute("UPDATE application_queue SET state='paused' WHERE id=?",
                              (item.id,))
        selected = {**RUNTIME, "model": "ollama/next", "at": 2.0}
        lease = memory.db.execute("SELECT * FROM session_live").fetchall()
        with pytest.raises(RuntimeError, match="active worker"):
            turns.set_runtime_choice("session", selected, RUNTIME, expected_revision=0,
                                     next_turn_worker="foreign")
        assert memory.session_runtime("session")["model"] == RUNTIME["model"]
        assert turns.set_runtime_choice("session", selected, RUNTIME, expected_revision=0,
                                        next_turn_worker="worker") == 1
        assert memory.db.execute("SELECT * FROM session_live").fetchall() == lease
        assert turns.queue_receipt("queued").state == "paused"
        runtime = memory.db.execute(
            "SELECT runtime FROM application_queue WHERE id=?", (item.id,),
        ).fetchone()[0]
        assert '"model": "ollama/next"' in runtime
    finally:
        memory.db.close()
