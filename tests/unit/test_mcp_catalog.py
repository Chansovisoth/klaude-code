import json

import httpx
import pytest
from klaude_core.mcp_catalog import (
    MCPCatalogClient,
    MCPCatalogError,
    install_plans,
)


def _entry(server: dict, *, active: bool = True, latest: bool = True) -> dict:
    return {
        "server": {
            "$schema": "https://static.modelcontextprotocol.io/schema.json",
            "name": "io.github.example/browser",
            "title": "Example Browser",
            "description": "Automate a browser through accessible page data.",
            "version": "1.2.3",
            "repository": {
                "url": "https://github.com/example/browser-mcp",
                "source": "github",
            },
            **server,
        },
        "_meta": {
            "io.modelcontextprotocol.registry/official": {
                "status": "active" if active else "deleted",
                "isLatest": latest,
                "publishedAt": "2026-01-01T00:00:00Z",
                "statusChangedAt": "2026-01-01T00:00:00Z",
            }
        },
    }


def _payload(*entries: dict) -> dict:
    return {"servers": list(entries), "metadata": {"count": len(entries)}}


def test_catalog_search_uses_official_latest_filter_and_private_cache(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.params["search"] == "browser"
        assert request.url.params["version"] == "latest"
        return httpx.Response(200, json=_payload(_entry({})))

    client = MCPCatalogClient(
        tmp_path / "catalog.json",
        transport=httpx.MockTransport(handler),
    )

    first, first_cached = client.search("browser", limit=10)
    second, second_cached = client.search("browser", limit=10)

    assert [item.name for item in first] == ["io.github.example/browser"]
    assert first_cached is False
    assert second == first
    assert second_cached is True
    assert len(calls) == 1
    assert (tmp_path / "catalog.json").stat().st_mode & 0o777 == 0o600


def test_catalog_filters_deleted_and_non_latest_entries(tmp_path):
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json=_payload(_entry({}, active=False), _entry({}, latest=False)),
        )
    )

    results, _cached = MCPCatalogClient(
        tmp_path / "catalog.json", transport=transport
    ).search("browser")

    assert results == []


def test_catalog_uses_recent_stale_cache_when_registry_is_temporarily_unavailable(
    tmp_path,
):
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json=_payload(_entry({})))
        raise httpx.ConnectError("offline")

    client = MCPCatalogClient(
        tmp_path / "catalog.json",
        transport=httpx.MockTransport(handler),
    )
    first, cached = client.search("browser")
    fallback, fallback_cached = client.search("browser", refresh=True)

    assert cached is False
    assert fallback == first
    assert fallback_cached is True


def test_remote_plan_collects_secret_as_environment_reference():
    payload = _payload(
        _entry(
            {
                "remotes": [
                    {
                        "type": "streamable-http",
                        "url": "https://mcp.example.com/mcp",
                        "headers": [
                            {
                                "name": "Authorization",
                                "description": "Bearer token",
                                "isSecret": True,
                            }
                        ],
                    }
                ]
            }
        )
    )
    from klaude_core.mcp_catalog import _parse_servers

    catalog_server = _parse_servers(payload)[0]
    plan = install_plans(catalog_server)[0]
    item = plan.inputs[0]

    configured, secrets = plan.materialize("example-browser", {item.key: "token-value"})

    assert configured.enabled is False
    assert configured.url == "https://mcp.example.com/mcp"
    assert configured.headers["Authorization"].startswith(
        "Bearer ${env:MCP_EXAMPLE_BROWSER_"
    )
    assert list(secrets.values()) == ["token-value"]
    assert "token-value" not in json.dumps(configured.to_dict())


def test_optional_remote_secret_can_be_omitted():
    from klaude_core.mcp_catalog import _parse_servers

    catalog_server = _parse_servers(
        _payload(
            _entry(
                {
                    "remotes": [
                        {
                            "type": "streamable-http",
                            "url": "https://mcp.example.com/mcp",
                            "headers": [
                                {
                                    "name": "Authorization",
                                    "description": "Optional bearer token",
                                    "isSecret": True,
                                    "isRequired": False,
                                }
                            ],
                        }
                    ]
                }
            )
        )
    )[0]

    configured, secrets = install_plans(catalog_server)[0].materialize("browser", {})

    assert configured.headers == {}
    assert secrets == {}


def test_registry_secret_defaults_are_never_trusted_or_persisted():
    from klaude_core.mcp_catalog import _parse_servers

    catalog_server = _parse_servers(
        _payload(
            _entry(
                {
                    "remotes": [
                        {
                            "type": "streamable-http",
                            "url": "https://mcp.example.com/mcp",
                            "headers": [
                                {
                                    "name": "Authorization",
                                    "isSecret": True,
                                    "default": "registry-supplied-secret",
                                }
                            ],
                        }
                    ]
                }
            )
        )
    )[0]

    configured, secrets = install_plans(catalog_server)[0].materialize("browser", {})

    assert configured.headers == {}
    assert secrets == {}


def test_npm_plan_pins_exact_version_and_never_uses_latest():
    from klaude_core.mcp_catalog import _parse_servers

    catalog_server = _parse_servers(
        _payload(
            _entry(
                {
                    "packages": [
                        {
                            "registryType": "npm",
                            "identifier": "@example/browser-mcp",
                            "version": "1.2.3",
                            "runtimeHint": "npx",
                            "transport": {"type": "stdio"},
                        }
                    ]
                }
            )
        )
    )[0]

    plan = install_plans(catalog_server)[0]
    configured, secrets = plan.materialize("browser", {})

    assert configured.command == "npx"
    assert configured.args == ["--yes", "@example/browser-mcp@1.2.3"]
    assert all("latest" not in value for value in configured.args)
    assert secrets == {}


def test_unsupported_or_unsafe_transports_do_not_form_install_plans():
    from klaude_core.mcp_catalog import _parse_servers

    catalog_server = _parse_servers(
        _payload(
            _entry(
                {
                    "remotes": [
                        {"type": "sse", "url": "https://example.com/sse"},
                        {"type": "streamable-http", "url": "http://example.com/mcp"},
                        {"type": "streamable-http", "url": "https://127.0.0.1/mcp"},
                    ],
                    "packages": [
                        {
                            "registryType": "npm",
                            "identifier": "bad-package",
                            "version": "^1.2.3",
                            "runtimeHint": "npx",
                            "transport": {"type": "stdio"},
                        },
                        {
                            "registryType": "npm",
                            "identifier": "--malicious-option",
                            "version": "1.2.3",
                            "runtimeHint": "npx",
                            "transport": {"type": "stdio"},
                        },
                    ],
                }
            )
        )
    )[0]

    assert install_plans(catalog_server) == []


def test_catalog_rejects_oversized_response(tmp_path):
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, content=b"x" * 2_000_001)
    )

    with pytest.raises(MCPCatalogError, match="safety limit"):
        MCPCatalogClient(tmp_path / "catalog.json", transport=transport).search("browser")


def test_catalog_rejects_untrusted_origin(tmp_path):
    with pytest.raises(ValueError, match="HTTPS origin"):
        MCPCatalogClient(tmp_path / "catalog.json", base_url="http://registry.example.com")


def test_catalog_ignores_oversized_or_symlinked_cache(tmp_path):
    cache = tmp_path / "catalog.json"
    cache.write_bytes(b"x" * 8_000_001)
    client = MCPCatalogClient(
        cache,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=_payload(_entry({})))
        ),
    )
    assert client.search("browser")[1] is False

    target = tmp_path / "elsewhere.json"
    target.write_text(json.dumps({"version": 1, "entries": {}}))
    cache.unlink()
    cache.symlink_to(target)
    assert client.search("another")[1] is False


def test_cli_registry_install_saves_optional_auth_plan_disabled(monkeypatch, tmp_path):
    from klaude_cli.main import app
    from klaude_core.mcp_catalog import _parse_servers
    from klaude_core.mcp_client import MCPRegistry
    from typer.testing import CliRunner

    server = _parse_servers(
        _payload(
            _entry(
                {
                    "remotes": [
                        {
                            "type": "streamable-http",
                            "url": "https://mcp.example.com/mcp",
                            "headers": [
                                {
                                    "name": "Authorization",
                                    "description": "Optional bearer token",
                                    "isSecret": True,
                                }
                            ],
                        }
                    ]
                }
            )
        )
    )[0]
    registry = MCPRegistry(tmp_path / "mcp-servers.json")
    catalog = type("Catalog", (), {"get": lambda self, _name, refresh=False: server})()
    monkeypatch.setattr("klaude_cli.main._mcp_registry", lambda: registry)
    monkeypatch.setattr("klaude_cli.main._mcp_catalog", lambda: catalog)

    result = CliRunner().invoke(
        app,
        ["mcp", "install", server.name, "--name", "browser", "--yes"],
    )

    assert result.exit_code == 0, result.output
    configured = registry.load()["browser"]
    assert configured.enabled is False
    assert configured.headers == {}
