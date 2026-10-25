"""Private account persistence and recovery contracts; no model/provider calls."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from klaude_webhost.accounts import AccountStore, LoginLimited, LoginLimiter
from klaude_webhost.hosting import WebHostController


def test_admin_creation_is_private_stable_and_race_safe(tmp_path):
    store = AccountStore(tmp_path)
    controller = WebHostController(tmp_path, tmp_path / "data")
    assert not controller.account_configured()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: AccountStore(tmp_path).initialize(), range(2)))
    password = store.initial_password()
    assert controller.account_configured()
    assert password and len(password) >= 24
    record = json.loads(store.path.read_text())
    assert password not in store.path.read_text()
    assert record["algorithm"] == "scrypt"
    assert store.path.stat().st_mode & 0o077 == 0
    assert store.initial_password_path.stat().st_mode & 0o077 == 0
    assert store.verify("admin", password).revision == 1
    assert store.verify("other", password) is None
    assert store.verify("admin", "incorrect-password") is None
    store.initialize()
    assert store.initial_password() == password


def test_password_change_and_local_reset_rotate_revision(tmp_path):
    store = AccountStore(tmp_path)
    store.initialize()
    password = store.initial_password()
    replacement = "a new passphrase with spaces"
    assert not store.change_password("wrong password", replacement, revision=1)
    assert store.change_password(password, replacement, revision=1)
    assert store.initial_password() is None
    assert not store.initial_password_path.exists()
    assert store.verify("admin", password) is None
    assert store.verify("admin", replacement).revision == 2
    assert not store.change_password(replacement, "another passphrase", revision=1)
    reset = store.reset_password()
    assert reset != password and reset != replacement
    assert store.initial_password() == reset
    assert store.verify("admin", reset).revision == 3
    assert store.verify("admin", replacement) is None


@pytest.mark.parametrize("kind", ["corrupt", "symlink", "permissions", "hardlink"])
def test_unsafe_account_never_becomes_a_new_default_account(tmp_path, kind):
    store = AccountStore(tmp_path / "config")
    store.initialize()
    before = store.initial_password_path.read_bytes()
    if kind == "corrupt":
        store.path.write_text("{broken")
    elif kind == "symlink":
        other = tmp_path / "outside"
        store.path.replace(other)
        store.path.symlink_to(other)
    elif kind == "permissions":
        store.path.chmod(0o644)
    else:
        (tmp_path / "hardlink").hardlink_to(store.path)
    with pytest.raises((OSError, ValueError)):
        store.initialize()
    assert store.initial_password_path.read_bytes() == before


def test_password_limits_and_corrupt_initial_secret_fail_closed(tmp_path):
    store = AccountStore(tmp_path)
    store.initialize()
    for password in ("short", "x" * 257):
        with pytest.raises(ValueError):
            store.change_password("incorrect", password, revision=1)
    store.initial_password_path.unlink()
    store.initial_password_path.symlink_to(store.path)
    with pytest.raises(OSError):
        store.initial_password()


def test_login_limiter_bounds_attempts_and_allows_retry_after_window(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("klaude_webhost.accounts.time.monotonic", lambda: now[0])
    limiter = LoginLimiter()
    for _ in range(5):
        limiter.admit("peer")
    with pytest.raises(LoginLimited):
        limiter.admit("peer")
    for i in range(25):
        limiter.admit(f"other-{i}")
    with pytest.raises(LoginLimited):
        limiter.admit("yet-another")
    now[0] += 61
    limiter.admit("peer")
    assert len(limiter._global) == 1


def test_roles_preserve_legacy_admin_and_do_not_promote_explicit_users(tmp_path):
    from klaude_core.settings_store import atomic_write_private

    store = AccountStore(tmp_path)
    store.initialize()
    password = store.initial_password()
    assert json.loads(store.path.read_text())["role"] == "admin"
    assert store.verify("admin", password).role == "admin"
    record = json.loads(store.path.read_text())
    del record["role"]
    atomic_write_private(store.path, json.dumps(record))
    assert store.verify("admin", password).role == "admin"
    record["role"] = "user"
    atomic_write_private(store.path, json.dumps(record))
    assert store.verify("admin", password).role == "user"
    assert store.identity("unknown") is None
    assert store.change_password(password, "replacement password for role test", revision=1)
    assert store.identity("admin").role == "user"
    store.reset_password()
    assert store.identity("admin").role == "user"
    record = json.loads(store.path.read_text())
    record["role"] = "administrator-typo"
    atomic_write_private(store.path, json.dumps(record))
    with pytest.raises(ValueError):
        store.verify("admin", "replacement password for role test")
