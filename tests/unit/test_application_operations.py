"""Non-chat admission keeps uncertain effects fenced across application instances."""

from __future__ import annotations

import sqlite3
import uuid
from multiprocessing import get_context

import pytest
from klaude_application.operation_journal import (
    OperationConflict,
    OperationFenceLost,
    OperationJournal,
)


def _competing_admission(path, request_id, result_queue):
    journal = OperationJournal(path)
    try:
        journal.admit(
            request_id=request_id,
            owner_id="other",
            kind="model_pull",
            resource="model:llama",
            payload={},
        )
    except OperationConflict:
        result_queue.put("fenced")
    else:
        result_queue.put("admitted")


def test_duplicate_intent_and_resource_fence_survive_a_second_instance(tmp_path):
    now = [1000.0]
    path = tmp_path / "operations.db"
    first = OperationJournal(path, clock=lambda: now[0])
    second = OperationJournal(path, clock=lambda: now[0])
    identity = uuid.uuid4().hex
    secret = "private-provider-key-123"
    accepted = first.admit(
        request_id=identity,
        owner_id="terminal-a",
        kind="model_pull",
        resource="model:llama",
        payload={"key": secret},
    )
    assert accepted.created and accepted.state == "accepted" and accepted.fence == 1
    assert not second.admit(
        request_id=identity,
        owner_id="terminal-a",
        kind="model_pull",
        resource="model:llama",
        payload={"key": secret},
    ).created
    with pytest.raises(OperationConflict):
        second.admit(
            request_id=identity,
            owner_id="terminal-a",
            kind="model_pull",
            resource="model:llama",
            payload={"key": "different"},
        )
    with pytest.raises(OperationConflict):
        second.admit(
            request_id=uuid.uuid4().hex,
            owner_id="terminal-b",
            kind="model_pull",
            resource="model:llama",
            payload={},
        )
    assert first.start(identity, "terminal-a", 1).state == "running"
    assert second.finish(identity, "terminal-a", 1, state="completed", outcome="ok").state == (
        "completed"
    )
    next_turn = second.admit(
        request_id=uuid.uuid4().hex,
        owner_id="terminal-b",
        kind="model_pull",
        resource="model:llama",
        payload={},
    )
    assert next_turn.fence == 2
    assert path.stat().st_mode & 0o077 == 0
    assert secret.encode() not in path.read_bytes()
    with sqlite3.connect(path) as db:
        assert secret not in repr(db.execute("SELECT * FROM operations").fetchall())


def test_expired_effect_is_unknown_until_explicit_reconciliation(tmp_path):
    now = [1000.0]
    path = tmp_path / "operations.db"
    owner = OperationJournal(path, clock=lambda: now[0])
    identity = uuid.uuid4().hex
    accepted = owner.admit(
        request_id=identity,
        owner_id="terminal-a",
        kind="image_generation",
        resource="image-service:main",
        payload={"prompt": "private subject"},
        lease_seconds=2,
    )
    owner.start(identity, "terminal-a", accepted.fence)
    now[0] += 3
    recovered = OperationJournal(path, clock=lambda: now[0])
    assert recovered.status(identity, "terminal-a").state == "unknown"
    with pytest.raises(OperationFenceLost):
        owner.finish(identity, "terminal-a", accepted.fence, state="completed")
    with pytest.raises(OperationConflict):
        recovered.admit(
            request_id=uuid.uuid4().hex,
            owner_id="terminal-b",
            kind="image_generation",
            resource="image-service:main",
            payload={},
        )
    evidence = "Checked the exact remote job and found saved output"
    result = recovered.reconcile(identity, "terminal-a", state="completed", evidence=evidence)
    assert result.state == "completed" and result.outcome == "reconciled"
    assert evidence.encode() not in path.read_bytes()
    assert (
        recovered.admit(
            request_id=uuid.uuid4().hex,
            owner_id="terminal-b",
            kind="image_generation",
            resource="image-service:main",
            payload={},
        ).fence
        == 2
    )


def test_expired_unstarted_operation_releases_resource_without_reconciliation(tmp_path):
    now = [1000.0]
    path = tmp_path / "operations.db"
    first = OperationJournal(path, clock=lambda: now[0])
    request_id = uuid.uuid4().hex
    receipt = first.admit(
        request_id=request_id,
        owner_id="terminal-a",
        kind="mcp_save",
        resource="mcp:profile",
        payload={"private": "never-publish"},
        lease_seconds=2,
    )
    now[0] += 3
    second = OperationJournal(path, clock=lambda: now[0])
    expired = second.status(request_id, "terminal-a")
    assert expired is not None and expired.state == "cancelled"
    assert expired.outcome == "cancelled"
    assert not second.resource_busy("mcp:profile")
    assert second.fenced_operation("mcp:profile") is None
    with pytest.raises(OperationFenceLost):
        first.start(request_id, "terminal-a", receipt.fence)
    assert second.admit(
        request_id=uuid.uuid4().hex,
        owner_id="terminal-b",
        kind="mcp_save",
        resource="mcp:profile",
        payload={},
    ).fence == 2
    assert b"never-publish" not in path.read_bytes()


def test_started_cancellation_expiry_remains_fenced(tmp_path):
    now = [1000.0]
    journal = OperationJournal(tmp_path / "operations.db", clock=lambda: now[0])
    request_id = uuid.uuid4().hex
    receipt = journal.admit(
        request_id=request_id,
        owner_id="terminal-a",
        kind="mcp_save",
        resource="mcp:profile",
        payload={},
        lease_seconds=2,
    )
    journal.start(request_id, "terminal-a", receipt.fence)
    assert journal.request_cancel(request_id, "terminal-a").state == "cancelling"
    now[0] += 3
    assert journal.status(request_id, "terminal-a").state == "unknown"
    assert journal.resource_busy("mcp:profile")
    restarted = OperationJournal(journal.path, clock=lambda: now[0])
    fenced = restarted.fenced_operation("mcp:profile")
    assert fenced is not None
    assert fenced.owner_id == "terminal-a"
    assert fenced.receipt.request_id == request_id
    assert fenced.receipt.state == "unknown"
    assert "payload" not in repr(fenced)


def test_cancelled_before_start_never_starts_and_does_not_claim_rollback(tmp_path):
    journal = OperationJournal(tmp_path / "operations.db")
    identity = uuid.uuid4().hex
    accepted = journal.admit(
        request_id=identity,
        owner_id="terminal-a",
        kind="model_delete",
        resource="model:old",
        payload={},
    )
    assert journal.request_cancel(identity, "terminal-a").state == "cancelled"
    with pytest.raises(OperationFenceLost):
        journal.start(identity, "terminal-a", accepted.fence)
    assert not journal.resource_busy("model:old")
    with pytest.raises(OperationFenceLost):
        journal.finish(
            identity, "terminal-a", accepted.fence, state="cancelled", outcome="cancelled"
        )
    with pytest.raises(OperationFenceLost):
        journal.renew(identity, "terminal-a", accepted.fence)


def test_cross_process_admission_and_cancelled_effect_gate(tmp_path):
    journal = OperationJournal(tmp_path / "operations.db")
    identity = uuid.uuid4().hex
    receipt = journal.admit(
        request_id=identity,
        owner_id="terminal-a",
        kind="model_pull",
        resource="model:llama",
        payload={},
    )
    context = get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(
        target=_competing_admission,
        args=(journal.path, uuid.uuid4().hex, result_queue),
    )
    process.start()
    try:
        assert result_queue.get(timeout=5) == "fenced"
    finally:
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join(5)
    assert process.exitcode == 0
    journal.start(identity, "terminal-a", receipt.fence)
    journal.check_effect(identity, "terminal-a", receipt.fence)
    journal.request_cancel(identity, "terminal-a")
    with pytest.raises(OperationFenceLost):
        journal.check_effect(identity, "terminal-a", receipt.fence)


def test_activity_is_bounded_and_owner_scoped(tmp_path):
    journal = OperationJournal(tmp_path / "operations.db")
    first = uuid.uuid4().hex
    second = uuid.uuid4().hex
    journal.admit(
        request_id=first, owner_id="alice", kind="mcp_toggle",
        resource="mcp:one", payload={"secret": "private-token"},
    )
    journal.admit(
        request_id=second, owner_id="bob", kind="mcp_toggle",
        resource="mcp:two", payload={},
    )
    assert [item.request_id for item in journal.recent("alice")] == [first]
    assert journal.recent("alice", offset=1) == ()
    assert "private-token" not in repr(journal.recent("alice"))
    with pytest.raises(ValueError):
        journal.recent("alice", limit=101)
