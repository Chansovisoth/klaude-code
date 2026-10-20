"""Public, version-only update candidates for registry-installed stdio MCPs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeGuard

from klaude_core.mcp_catalog import MCPCatalogServer, install_plans
from klaude_core.mcp_client import MCPServerConfig

_NPM_SPEC = re.compile(
    r"^((?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*)@([0-9]+)\.([0-9]+)\.([0-9]+)$"
)
_PYPI_SPEC = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9]+)\.([0-9]+)\.([0-9]+)$")


def _package_spec(command: str, value: str) -> tuple[str, tuple[int, int, int]] | None:
    match = (_NPM_SPEC if command == "npx" else _PYPI_SPEC if command == "uvx" else None)
    parsed = match.fullmatch(value) if match is not None else None
    if parsed is None:
        return None
    return (parsed.group(1).casefold(),
            (int(parsed.group(2)), int(parsed.group(3)), int(parsed.group(4))))


@dataclass(frozen=True)
class MCPPackageUpdate:
    old_arg: str
    new_arg: str
    old_version: str
    new_version: str
    registry_version: str
    description: str


def package_update_candidate(server: MCPServerConfig,
                             latest: MCPCatalogServer) -> MCPPackageUpdate | None:
    """Accept only one changed exact package version; preserve all other config."""
    if server.source.get("registry") != "official" or (
        server.source.get("name") != latest.name or server.transport != "stdio"
        or server.command not in {"npx", "uvx"}
    ):
        return None
    for plan in install_plans(latest):
        if plan.transport != "stdio" or plan.command != server.command or (
            len(plan.args) != len(server.args)
        ):
            continue
        changed = [index for index, (old, new) in enumerate(
            zip(server.args, plan.args, strict=True)
        ) if old != new]
        if len(changed) != 1:
            continue
        old_arg, new_arg = server.args[changed[0]], plan.args[changed[0]]
        old_spec = _package_spec(server.command, old_arg)
        new_spec = _package_spec(server.command, new_arg)
        if old_spec is None or new_spec is None or old_spec[0] != new_spec[0] or (
            new_spec[1] <= old_spec[1]
        ):
            continue
        old_version = ".".join(str(part) for part in old_spec[1])
        new_version = ".".join(str(part) for part in new_spec[1])
        return MCPPackageUpdate(old_arg, new_arg, old_version, new_version,
                                latest.version, latest.description)
    return None


def registry_package_source(server: MCPServerConfig) -> bool:
    return server.transport == "stdio" and server.command in {"npx", "uvx"} and (
        server.source.get("registry") == "official" and bool(server.source.get("name"))
    ) and any(_package_spec(server.command, arg) for arg in server.args)


def valid_version_only_change(command: str, old_arg: str, new_arg: str) -> bool:
    old_spec = _package_spec(command, old_arg)
    new_spec = _package_spec(command, new_arg)
    return old_spec is not None and new_spec is not None and (
        old_spec[0] == new_spec[0] and new_spec[1] > old_spec[1]
    )


def valid_candidate_payload(value: object) -> TypeGuard[dict[str, str]]:
    """Validate the public worker boundary before rendering or accepting a save."""
    if not isinstance(value, dict) or set(value) != {
        "old_arg", "new_arg", "old_version", "new_version",
        "registry_version", "description",
    } or not all(isinstance(item, str) and len(item) <= 500 and (
        all(char.isprintable() for char in item)
    ) for item in value.values()):
        return False
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,254}",
                        value["registry_version"]):
        return False
    for command in ("npx", "uvx"):
        if not valid_version_only_change(command, value["old_arg"], value["new_arg"]):
            continue
        old = _package_spec(command, value["old_arg"])
        new = _package_spec(command, value["new_arg"])
        assert old is not None and new is not None
        return (value["old_version"] == ".".join(map(str, old[1])) and
                value["new_version"] == ".".join(map(str, new[1])))
    return False
