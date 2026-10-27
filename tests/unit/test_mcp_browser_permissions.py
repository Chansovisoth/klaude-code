"""Per-server permission updates share the existing atomic tool-policy store."""

import pytest
from klaude_application.browser_settings import mcp_permission_state, prepare_setting, save_setting
from klaude_core.config import Config
from klaude_core.mcp_client import MCPRegistry, MCPServerConfig, namespaced_tool_name
from klaude_core.settings_store import SettingsConflictError, read_settings, update_settings


@pytest.fixture
def permissions(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config()
    registry = MCPRegistry(cfg.mcp_servers_file)
    registry.save({name: MCPServerConfig(name, "http", True, url="https://example.test/mcp",
                                       tools=[{"name": "lookup"}, {"name": "write"}])
                   for name in ("one", "two")})
    return cfg, registry


def draft(cfg, policy="allow"):
    return {"operation": "setting-save", "id": "mcp_permissions.one", "value": policy,
            "revision": mcp_permission_state(cfg, "one")["revision"]}


@pytest.mark.parametrize("policy", ["allow", "ask", "deny"])
def test_bulk_policy_is_atomic_scoped_and_shared_with_terminal(permissions, policy):
    cfg, _ = permissions
    fields, _, _ = prepare_setting(cfg, draft(cfg, policy))
    save_setting(cfg, fields)
    saved = read_settings(cfg.data_dir / "chat-preferences.json")["permissions"]
    assert saved == {namespaced_tool_name("one", tool): policy for tool in ("lookup", "write")}
    assert mcp_permission_state(cfg, "one")["policy"] == policy
    assert mcp_permission_state(cfg, "two")["policy"] == "ask"


@pytest.mark.parametrize("change", ["permission", "definition"])
def test_changes_after_review_reject_entire_save(permissions, change):
    cfg, registry = permissions
    fields, _, _ = prepare_setting(cfg, draft(cfg))
    if change == "permission":
        update_settings(cfg.data_dir / "chat-preferences.json",
                        {("permissions", namespaced_tool_name("one", "lookup")): "deny"})
    else:
        servers = registry.load()
        servers["one"].url = "https://changed.test/mcp"
        registry.save(servers)
    before = read_settings(cfg.data_dir / "chat-preferences.json")
    with pytest.raises((ValueError, SettingsConflictError)):
        save_setting(cfg, fields)
    assert read_settings(cfg.data_dir / "chat-preferences.json") == before


def test_stale_draft_new_tools_and_invalid_policy(permissions):
    cfg, registry = permissions
    stale = draft(cfg)
    fields, _, _ = prepare_setting(cfg, stale)
    save_setting(cfg, fields)
    with pytest.raises(ValueError, match="changed"):
        prepare_setting(cfg, stale)
    with pytest.raises(ValueError):
        prepare_setting(cfg, draft(cfg, "anything"))
    servers = registry.load()
    servers["one"].tools.append({"name": "new_tool"})
    registry.save(servers)
    assert mcp_permission_state(cfg, "one")["policy"] == "mixed"
    assert namespaced_tool_name("one", "new_tool") not in read_settings(
        cfg.data_dir / "chat-preferences.json")["permissions"]
