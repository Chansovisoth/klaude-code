"""Connection/credential publication, privacy and recovery across real worker effects."""

import json
import uuid

import pytest
from klaude_application import browser_model_settings as settings
from klaude_application.operation_journal import OperationConflict, OperationJournal
from klaude_core.config import provider_secret_value
from klaude_core.model_connections import connection_registry
from klaude_core.settings_store import update_settings

from .test_model_store import native as native
from .test_web_management import _review, _submit
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


def add(host, service, auth):
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-add",
            "name": "Extra local",
            "authentication": True,
            "backend": "ollama",
            "url": service.cfg.ollama_url,
            "source": "Local",
        },
    )
    receipt, _ = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    result = _request(host, "GET", "/api/v1/settings/model-connections", **auth)[2]
    return next(c for c in result["connections"] if c["name"] == "Extra local")


def test_reviewed_connection_and_write_only_credentials(native):
    host, service, auth, _, _ = native
    before = host.application.agent.model_info.ref
    connection = add(host, service, auth)
    assert not connection["enabled"] and connection["credential_editable"]
    draft = {
        "operation": "model-connection-credential",
        "connection": connection["id"],
        "revision": connection["revision"],
        "value": "fixture-secret",
    }
    review = _review(host, auth, draft)
    assert "fixture-secret" not in json.dumps(review)
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    result = _request(host, "GET", "/api/v1/settings/model-connections", **auth)[2]
    assert "fixture-secret" not in json.dumps(result)
    assert next(c for c in result["connections"] if c["id"] == connection["id"])["credential_set"]
    registry = connection_registry(service.cfg)
    saved = registry.load()[connection["id"]]
    assert provider_secret_value(service.cfg.config_dir, saved.key_env) == "fixture-secret"
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-enabled",
            "connection": connection["id"],
            "revision": connection["revision"],
            "enabled": True,
        },
    )
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    saved = registry.load()[connection["id"]]
    assert saved.enabled
    assert host.application.agent.model_info.ref == before
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-edit",
            "connection": saved.id,
            "revision": saved.revision,
            "name": "Renamed",
            "url": saved.base_url,
            "source": "Local",
        },
    )
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    saved = registry.load()[saved.id]
    assert saved.name == "Renamed"
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-remove",
            "connection": saved.id,
            "revision": saved.revision,
        },
    )
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert saved.id not in registry.load()
    assert provider_secret_value(service.cfg.config_dir, saved.key_env) == "fixture-secret"


def test_current_connection_lan_csrf_and_stale_reviews(native):
    host, service, auth, _, identity = native
    connection = add(host, service, auth)
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-remove",
            "connection": connection["id"],
            "revision": connection["revision"],
        },
    )
    host.http.host_lan = True
    assert (
        _request(
            host,
            "POST",
            "/api/v1/library/submit",
            body={
                "review_id": review["review_id"],
                "request_id": uuid.uuid4().hex,
                "control_epoch": 0,
            },
            **auth,
        )[0]
        == 403
    )
    public = _request(host, "GET", "/api/v1/settings/model-connections", **auth)[2]
    assert not public["management_allowed"] and all(
        "url" not in row for row in public["connections"]
    )
    host.http.host_lan = False
    # Changing the active chat's exact connection is rejected before dispatch.
    current = connection_registry(service.cfg).load()[identity]
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-edit",
            "connection": identity,
            "revision": current.revision,
            "name": "Changed active",
            "url": current.base_url,
            "source": current.source,
        },
    )
    assert (
        _request(
            host,
            "POST",
            "/api/v1/library/submit",
            body={
                "review_id": review["review_id"],
                "request_id": uuid.uuid4().hex,
                "control_epoch": 0,
            },
            **auth,
        )[0]
        == 409
    )
    assert (
        _request(
            host,
            "POST",
            "/api/v1/settings/model-connections/test",
            body={"connection": connection["id"], "revision": "stale"},
            **auth,
        )[0]
        == 400
    )
    assert (
        _request(
            host,
            "POST",
            "/api/v1/settings/model-connections/test",
            body={"connection": connection["id"], "revision": connection["revision"]},
            **{**auth, "csrf": "wrong"},
        )[0]
        == 403
    )


def test_lost_definition_ack_recovers_exact_state_without_replay(native, monkeypatch):
    from klaude_core import model_management

    _, service, _, _, _ = native
    fields, resource, _ = settings.prepare(
        service.cfg,
        {
            "operation": "model-connection-add",
            "name": "Witness",
            "backend": "ollama",
            "url": service.cfg.ollama_url,
            "source": "Local",
        },
    )
    journal = OperationJournal(service.data / "operations.db")
    identity = uuid.uuid4().hex
    receipt = journal.admit(
        request_id=identity,
        owner_id="web-admin",
        kind="model-connection-add",
        resource=resource,
        payload={},
    )
    original = model_management.write_registry
    calls = []

    def lose_ack(registry, value):
        calls.append(True)
        original(registry, value)
        raise OSError("simulated lost acknowledgement")

    monkeypatch.setattr(model_management, "write_registry", lose_ack)
    result = settings.run(
        service.cfg,
        {
            "operation": "model-connection-add",
            "request_id": identity,
            "fence": receipt.fence,
            **fields,
        },
    )
    assert not result["ok"] and journal.status(identity, "web-admin").state == "unknown"
    registry = connection_registry(service.cfg)
    actual = registry.path.read_text()
    changed = json.loads(actual)
    changed["unreviewed"] = True
    registry.path.write_text(json.dumps(changed))
    with pytest.raises(OperationConflict):
        settings.recover(service.cfg, journal, identity)
    registry.path.write_text(actual)
    assert settings.recover(service.cfg, journal, identity).state == "completed"
    assert len(calls) == 1


def test_definition_changes_protect_default_roles(native):
    host, service, auth, _, _ = native
    item = add(host, service, auth)
    reference = f"ollama@{item['id']}/kept:latest"
    update_settings(
        service.data / "chat-preferences.json",
        {("ai_defaults",): {"chat": None, "utility": reference}},
    )
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-remove",
            "connection": item["id"],
            "revision": item["revision"],
        },
    )
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert item["id"] in connection_registry(service.cfg).load()


def test_lost_credential_ack_reconciles_without_replaying_secret(native, monkeypatch):
    from klaude_core import config

    host, service, auth, state, _ = native
    item = add(host, service, auth)
    fields, resource, _ = settings.prepare(
        service.cfg,
        {
            "operation": "model-connection-credential",
            "connection": item["id"],
            "revision": item["revision"],
            "value": "private-recovery-token",
        },
    )
    journal = OperationJournal(service.data / "operations.db")
    identity = uuid.uuid4().hex
    receipt = journal.admit(
        request_id=identity,
        owner_id="web-admin",
        kind="model-connection-credential",
        resource=resource,
        payload={},
    )
    original = config._save_provider_secret_locked
    saves = []

    def lose_ack(path, name, value):
        saves.append(True)
        original(path, name, value)
        raise OSError("simulated acknowledgement loss")

    monkeypatch.setattr(config, "_save_provider_secret_locked", lose_ack)
    result = settings.run(
        service.cfg,
        {
            "operation": "model-connection-credential",
            "request_id": identity,
            "fence": receipt.fence,
            **fields,
        },
    )
    assert not result["ok"] and journal.status(identity, "web-admin").state == "unknown"
    calls = state["calls"][:]
    assert settings.recover(service.cfg, journal, identity).state == "completed"
    assert len(saves) == 1 and state["calls"] == calls
    assert b"private-recovery-token" not in journal.path.read_bytes()


def test_enabling_rejects_credential_changed_after_review(native):
    from klaude_core.config import save_provider_secret

    host, service, auth, _, _ = native
    item = add(host, service, auth)
    saved = connection_registry(service.cfg).load()[item["id"]]
    save_provider_secret(service.cfg.config_dir, saved.key_env, "before-review")
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-enabled",
            "connection": item["id"],
            "revision": item["revision"],
            "enabled": True,
        },
    )
    saved = connection_registry(service.cfg).load()[item["id"]]
    save_provider_secret(service.cfg.config_dir, saved.key_env, "changed-after-review")
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert not connection_registry(service.cfg).load()[item["id"]].enabled


def test_local_connection_without_authentication_enables_without_secret(native):
    host, service, auth, _, _ = native
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-add",
            "name": "No authentication",
            "backend": "ollama",
            "source": "Local",
            "url": service.cfg.ollama_url,
        },
    )
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    item = next(
        c for c in connection_registry(service.cfg).load().values() if c.name == "No authentication"
    )
    assert not item.key_env
    review = _review(
        host,
        auth,
        {
            "operation": "model-connection-enabled",
            "connection": item.id,
            "revision": item.revision,
            "enabled": True,
        },
    )
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert connection_registry(service.cfg).load()[item.id].enabled


def account_login(host, service, role):
    from klaude_core.settings_store import atomic_write_private
    from klaude_webhost.accounts import AccountStore

    accounts = AccountStore(service.cfg.config_dir)
    accounts.initialize()
    password = accounts.initial_password()
    record = json.loads(accounts.path.read_text())
    record["role"] = role
    atomic_write_private(accounts.path, json.dumps(record))
    host.accounts = accounts
    status, headers, login = _request(
        host,
        "POST",
        "/api/v1/auth/login",
        body={
            "username": "admin",
            "password": password,
        },
        origin=host.origin,
    )
    assert status == 200 and login["role"] == role
    auth = {
        "cookie": headers["Set-Cookie"].split(";", 1)[0],
        "csrf": login["csrf"],
        "origin": host.origin,
    }
    auth["client_id"] = _request(host, "POST", "/api/v1/clients", body={}, **auth)[2]["client_id"]
    assert _request(host, "GET", "/api/v1/auth", **auth)[2]["role"] == role
    return auth


@pytest.mark.parametrize("role", ["admin", "user"])
@pytest.mark.parametrize("lan", [False, True])
def test_account_role_authorizes_model_management_on_both_listeners(native, role, lan):
    from klaude_core.ai_defaults import read_defaults

    host, service, _, state, identity = native
    auth = account_login(host, service, role)
    host.http.host_lan = lan
    allowed = role == "admin"
    public = _request(host, "GET", "/api/v1/settings/model-connections", **auth)[2]
    assert public["management_allowed"] is allowed
    assert all(("url" in row) is allowed for row in public["connections"])
    assert (
        _request(host, "GET", "/api/v1/settings/models", **auth)[2]["management_allowed"] is allowed
    )
    for path in (
        "/api/v1/models/store",
        "/api/v1/models/downloads",
        "/api/v1/integrations/connections",
    ):
        assert _request(host, "GET", path, **auth)[2]["management_allowed"] is allowed
    current = connection_registry(service.cfg).load().get(identity)
    if current is None:
        from klaude_core.model_connections import legacy_connections

        current = next(c for c in legacy_connections(service.cfg) if c.id == identity)
    tested = _request(
        host,
        "POST",
        "/api/v1/settings/model-connections/test",
        body={
            "connection": identity,
            "revision": current.revision,
        },
        **auth,
    )
    assert tested[0] == (200 if allowed else 403)
    if allowed:
        assert tested[2]["available"]
        assert add(host, service, auth)["credential_editable"]
        for operation in ("model-pull", "model-delete"):
            review = _review(
                host,
                auth,
                {"operation": operation, "connection": identity, "model": "role-test:1b"},
            )
            assert _submit(host, service, auth, review)[0]["state"] == "completed"
        defaults = read_defaults(service.cfg)
        review = _review(
            host,
            auth,
            {
                "operation": "defaults-save",
                "field": "output_tokens",
                "expected": defaults.output_tokens,
                "value": 128,
            },
        )
        assert _submit(host, service, auth, review)[0]["state"] == "completed"
        assert state["calls"].count(("POST", "/api/pull")) == 1
    else:
        drafts = [
            {"operation": "model-pull", "connection": identity, "model": "role-test:1b"},
            {
                "operation": "model-connection-add",
                "name": "denied",
                "backend": "ollama",
                "source": "Local",
                "url": service.cfg.ollama_url,
            },
            {"operation": "defaults-save"},
            {"operation": "defaults-recover"},
            {"operation": "image-settings-save"},
            {"operation": "image-settings-recover"},
        ]
        before = state["calls"][:]
        for draft in drafts:
            assert (
                _request(host, "POST", "/api/v1/library/review", body={"draft": draft}, **auth)[0]
                == 403
            )
        for path in (
            "/api/v1/models/cancel",
            "/api/v1/models/reconcile",
            "/api/v1/settings/models/image-test",
        ):
            assert _request(host, "POST", path, body={}, **auth)[0] == 403
        assert state["calls"] == before
        assert (
            _request(
                host,
                "POST",
                "/api/v1/library/review",
                body={
                    "draft": {"operation": "model-pull"},
                    "role": "admin",
                },
                **auth,
            )[0]
            == 400
        )
    assert (
        _request(
            host,
            "POST",
            "/api/v1/settings/model-connections/test",
            body={
                "connection": identity,
                "revision": current.revision,
            },
            **{**auth, "csrf": "wrong"},
        )[0]
        == 403
    )


def test_role_change_revokes_existing_sessions_and_pending_reviews(native):
    from klaude_core.settings_store import atomic_write_private

    host, service, _, state, identity = native
    auth = account_login(host, service, "admin")
    review = _review(
        host, auth, {"operation": "model-pull", "connection": identity, "model": "role-test:1b"}
    )
    record = json.loads(host.accounts.path.read_text())
    # Even a role edit with the same credential revision must revoke the session.
    record["role"] = "user"
    atomic_write_private(host.accounts.path, json.dumps(record))
    assert (
        _request(
            host,
            "POST",
            "/api/v1/library/submit",
            body={
                "review_id": review["review_id"],
                "request_id": uuid.uuid4().hex,
                "control_epoch": 0,
            },
            **auth,
        )[0]
        == 401
    )
    assert _request(host, "GET", "/api/v1/auth", **auth)[0] == 401
    assert not any(method == "POST" for method, _ in state["calls"])
