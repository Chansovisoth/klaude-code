"""Private-network address selection for the optional LAN listener."""

from __future__ import annotations

import ipaddress
import json
import subprocess
from pathlib import Path

_PRIVATE = tuple(ipaddress.ip_network(cidr) for cidr in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))


def private_lan_ip(value: str) -> ipaddress.IPv4Address:
    """Never bind the optional listener to a public, loopback or wildcard address."""
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise ValueError("LAN address must be a private IPv4 address") from None
    if not any(address in network for network in _PRIVATE):
        raise ValueError("LAN address must be in a private IPv4 network")
    return address


def lan_ipv4_addresses() -> tuple[str, ...]:
    """Read active Linux interface addresses; DNS names are not binding authority."""
    binary = next((path for path in (
        "/usr/sbin/ip", "/usr/bin/ip", "/sbin/ip", "/bin/ip",
    ) if Path(path).is_file()), "")
    if not binary:
        return ()
    try:
        result = subprocess.run(
            [binary, "-j", "-4", "address", "show", "scope", "global"],
            capture_output=True, text=True, check=True, timeout=3,
        )
        interfaces = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            json.JSONDecodeError):
        return ()
    found: list[str] = []
    if not isinstance(interfaces, list):
        return ()
    for interface in interfaces:
        if not isinstance(interface, dict) or "UP" not in interface.get("flags", []):
            continue
        for item in interface.get("addr_info", []):
            if not isinstance(item, dict) or item.get("family") != "inet":
                continue
            value = item.get("local")
            try:
                if not isinstance(value, str):
                    continue
                private_lan_ip(value)
            except ValueError:
                continue
            if value not in found:
                found.append(value)
    return tuple(found)
