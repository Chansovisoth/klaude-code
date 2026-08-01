"""Privacy-safe runtime context collection for model prompts."""

from __future__ import annotations

import ipaddress
import json
import locale as locale_module
import os
import platform
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
FASTFETCH_MODULES = (
    "os:host:kernel:uptime:packages:shell:display:terminal:"
    "cpu:gpu:memory:swap:disk:localip:locale"
)
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SECRETISH_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret|ssh|private[_-]?key)\b"
)
MAX_VALUE_CHARS = 160
COUNTRY_NAMES = {
    "KH": "Cambodia",
    "US": "United States",
    "GB": "United Kingdom",
    "CA": "Canada",
    "AU": "Australia",
    "DE": "Germany",
    "FR": "France",
    "JP": "Japan",
    "CN": "China",
    "IN": "India",
    "VN": "Vietnam",
    "TH": "Thailand",
    "LA": "Laos",
    "SG": "Singapore",
    "MY": "Malaysia",
    "ID": "Indonesia",
    "PH": "Philippines",
}


@dataclass
class RepositoryContext:
    root: str | None = None
    relative_path: str | None = None
    branch: str | None = None
    detached: bool = False
    dirty: bool | None = None
    changed_files: int | None = None
    error: str | None = None


@dataclass
class CpuInfo:
    name: str | None = None
    logical_threads: int | None = None
    physical_cores: int | None = None


@dataclass
class GpuInfo:
    name: str | None = None
    vendor: str | None = None
    memory_bytes: int | None = None


@dataclass
class DisplayInfo:
    name: str | None = None
    resolution: str | None = None
    refresh_rate: str | None = None


@dataclass
class DiskInfo:
    mount: str | None = None
    filesystem: str | None = None
    used_bytes: int | None = None
    total_bytes: int | None = None


@dataclass
class LocalAddress:
    interface: str | None = None
    address: str | None = None


@dataclass
class SystemContext:
    os_name: str | None = None
    os_version: str | None = None
    architecture: str | None = None
    host_name: str | None = None
    host_model: str | None = None
    kernel: str | None = None
    uptime_seconds: int | None = None
    shell: str | None = None
    terminal: str | None = None
    cpu: list[CpuInfo] = field(default_factory=list)
    gpu: list[GpuInfo] = field(default_factory=list)
    memory_total_bytes: int | None = None
    memory_used_bytes: int | None = None
    swap_total_bytes: int | None = None
    swap_used_bytes: int | None = None
    displays: list[DisplayInfo] = field(default_factory=list)
    disks: list[DiskInfo] = field(default_factory=list)
    local_addresses: list[LocalAddress] = field(default_factory=list)
    locale: str | None = None


@dataclass
class TemporalContext:
    local_iso: str
    utc_iso: str
    timezone: str | None
    utc_offset: str
    weekday: str


@dataclass
class LocationContext:
    country_code: str | None = None
    country_name: str | None = None
    region: str | None = None
    source: str = "unknown"
    confidence: str = "unknown"
    basis: str | None = None


@dataclass
class RuntimeContext:
    collected_at: datetime
    provider: str
    provider_version: str | None
    working_directory: str
    repository: RepositoryContext | None
    system: SystemContext
    temporal: TemporalContext
    location: LocationContext
    warnings: list[str] = field(default_factory=list)
    stable_collected_at: datetime | None = None
    cache_hit: bool = False


@dataclass
class RuntimeContextResult:
    context: RuntimeContext
    install_suggestion: str | None = None
    duration_ms: int = 0


Runner = Callable[[list[str], int], subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def default_runner(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


def sanitize_text(value: Any, *, max_chars: int = MAX_VALUE_CHARS) -> str:
    text = "" if value is None else str(value)
    text = ANSI_RE.sub("", text)
    text = CONTROL_RE.sub("", text)
    text = text.replace("</runtime_context>", "<\\/runtime_context>")
    text = " ".join(text.strip().split())
    if SECRETISH_RE.search(text):
        return "[redacted]"
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "..."
    return text


def parse_size_bytes(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, dict):
        for key in ("bytes", "value", "total", "used"):
            parsed = parse_size_bytes(value.get(key))
            if parsed is not None:
                return parsed
        return None
    text = sanitize_text(value)
    if not text:
        return None
    compact = text.replace(",", "")
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGTPE]?i?B|[KMGTPE]B|B)?", compact, re.I)
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "B").upper()
    factors = {
        "B": 1,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "TB": 1000**4,
        "KIB": 1024,
        "MIB": 1024**2,
        "GIB": 1024**3,
        "TIB": 1024**4,
    }
    return int(number * factors.get(unit, 1))


def parse_uptime_seconds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, dict):
        for key in ("seconds", "uptime", "value"):
            parsed = parse_uptime_seconds(value.get(key))
            if parsed is not None:
                return parsed
        return None
    text = sanitize_text(value).lower()
    total = 0
    matched = False
    uptime_re = (
        r"(\d+)\s*"
        r"(day|days|hour|hours|hr|hrs|minute|minutes|min|mins|second|seconds|sec|secs)"
    )
    for number, unit in re.findall(uptime_re, text):
        matched = True
        n = int(number)
        if unit.startswith("day"):
            total += n * 86400
        elif unit.startswith(("hour", "hr")):
            total += n * 3600
        elif unit.startswith(("minute", "min")):
            total += n * 60
        else:
            total += n
    if matched:
        return total
    return int(text) if text.isdigit() else None


def _first(result: dict, *keys: str) -> Any:
    for key in keys:
        if key in result and result[key] not in (None, ""):
            return result[key]
    return None


def _nested(result: dict, *keys: str) -> Any:
    value: Any = result
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _private_address(value: Any) -> str | None:
    text = sanitize_text(value)
    if not text:
        return None
    try:
        addr = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return None
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        return str(addr)
    return None


def _module_result(entry: dict) -> tuple[str, Any, str | None]:
    module = sanitize_text(entry.get("type") or entry.get("module") or entry.get("name")).lower()
    return module, entry.get("result"), sanitize_text(entry.get("error") or "")


def parse_fastfetch_json(raw: str) -> tuple[SystemContext, list[str]]:
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Fastfetch JSON must be a list")
    system = SystemContext()
    warnings: list[str] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        module, result, error = _module_result(entry)
        if error:
            warnings.append(f"fastfetch {module or 'module'}: {error}")
            continue
        if result is None:
            continue
        result_dict = result if isinstance(result, dict) else {}
        if module == "os":
            system.os_name = sanitize_text(_first(result_dict, "name", "prettyName") or result)
            system.os_version = sanitize_text(_first(result_dict, "version", "versionId"))
            system.architecture = sanitize_text(_first(result_dict, "architecture", "arch"))
        elif module == "host":
            system.host_name = sanitize_text(_first(result_dict, "name", "hostName"))
            system.host_model = sanitize_text(_first(result_dict, "model", "product", "family"))
        elif module == "kernel":
            name = sanitize_text(_first(result_dict, "name") or "")
            release = sanitize_text(_first(result_dict, "release", "version") or result)
            system.kernel = " ".join(part for part in (name, release) if part)
        elif module == "uptime":
            system.uptime_seconds = parse_uptime_seconds(result)
        elif module == "shell":
            system.shell = sanitize_text(
                _first(result_dict, "processName", "name", "path") or result
            )
        elif module == "terminal":
            system.terminal = sanitize_text(_first(result_dict, "processName", "name") or result)
        elif module == "cpu":
            cores_value = result_dict.get("cores")
            cores = cores_value if isinstance(cores_value, dict) else {}
            system.cpu.append(
                CpuInfo(
                    name=sanitize_text(_first(result_dict, "name", "model", "cpu") or result),
                    logical_threads=_int_or_none(
                        _first(result_dict, "threads", "logicalCores")
                        or cores.get("logical")
                    ),
                    physical_cores=_int_or_none(
                        _first(result_dict, "physicalCores")
                        or (cores_value if not isinstance(cores_value, dict) else None)
                        or cores.get("physical")
                    ),
                )
            )
        elif module == "gpu":
            for gpu in _listify(result):
                gpu_dict = gpu if isinstance(gpu, dict) else {}
                system.gpu.append(
                    GpuInfo(
                        name=sanitize_text(_first(gpu_dict, "name", "model") or gpu),
                        vendor=sanitize_text(_first(gpu_dict, "vendor")),
                        memory_bytes=parse_size_bytes(_first(gpu_dict, "memory", "dedicated")),
                    )
                )
        elif module == "memory":
            system.memory_total_bytes = parse_size_bytes(_first(result_dict, "total"))
            system.memory_used_bytes = parse_size_bytes(_first(result_dict, "used"))
        elif module == "swap":
            swap_items = [
                item for item in _listify(result)
                if isinstance(item, dict)
            ]
            if swap_items:
                totals = [parse_size_bytes(item.get("total")) for item in swap_items]
                used = [parse_size_bytes(item.get("used")) for item in swap_items]
                system.swap_total_bytes = sum(value or 0 for value in totals) or None
                system.swap_used_bytes = sum(value or 0 for value in used) or None
            else:
                system.swap_total_bytes = parse_size_bytes(_first(result_dict, "total"))
                system.swap_used_bytes = parse_size_bytes(_first(result_dict, "used"))
        elif module == "display":
            for display in _listify(result):
                display_dict = display if isinstance(display, dict) else {}
                width = _first(display_dict, "width") or _nested(display_dict, "output", "width")
                height = _first(display_dict, "height") or _nested(display_dict, "output", "height")
                resolution = f"{width}x{height}" if width and height else sanitize_text(display)
                refresh = (
                    _first(display_dict, "refreshRate", "hz")
                    or _nested(display_dict, "output", "refreshRate")
                )
                system.displays.append(
                    DisplayInfo(
                        name=sanitize_text(_first(display_dict, "name")),
                        resolution=sanitize_text(resolution),
                        refresh_rate=sanitize_text(refresh),
                    )
                )
        elif module == "disk":
            for disk in _listify(result):
                disk_dict = disk if isinstance(disk, dict) else {}
                bytes_dict = (
                    disk_dict.get("bytes")
                    if isinstance(disk_dict.get("bytes"), dict)
                    else {}
                )
                system.disks.append(
                    DiskInfo(
                        mount=sanitize_text(_first(disk_dict, "mountpoint", "mount", "path")),
                        filesystem=sanitize_text(_first(disk_dict, "filesystem", "type")),
                        used_bytes=parse_size_bytes(
                            _first(disk_dict, "used") or bytes_dict.get("used")
                        ),
                        total_bytes=parse_size_bytes(
                            _first(disk_dict, "total", "size") or bytes_dict.get("total")
                        ),
                    )
                )
        elif module == "localip":
            for item in _listify(result):
                item_dict = item if isinstance(item, dict) else {}
                interface = sanitize_text(_first(item_dict, "name", "interface"))
                for key in ("ipv4", "ipv6", "address"):
                    for address in _listify(item_dict.get(key) if item_dict else item):
                        private = _private_address(address)
                        if private:
                            system.local_addresses.append(LocalAddress(interface, private))
        elif module == "locale":
            system.locale = sanitize_text(_first(result_dict, "name", "locale") or result)
    _dedupe_system(system)
    return system, warnings


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_neofetch_stdout(raw: str) -> tuple[SystemContext, list[str]]:
    system = SystemContext()
    gpu_lines: list[str] = []
    disk_lines: list[str] = []
    for raw_line in raw.splitlines():
        line = sanitize_text(raw_line, max_chars=300)
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key = key.lower()
        if not value:
            continue
        if key == "os":
            system.os_name = value
        elif key == "host":
            system.host_model = value
        elif key == "kernel":
            system.kernel = value
        elif key == "uptime":
            system.uptime_seconds = parse_uptime_seconds(value)
        elif key == "shell":
            system.shell = value
        elif key == "terminal":
            system.terminal = value
        elif key == "cpu":
            system.cpu.append(CpuInfo(name=value))
        elif key == "gpu":
            gpu_lines.append(value)
        elif key == "memory":
            used, total = _parse_used_total(value)
            system.memory_used_bytes = used
            system.memory_total_bytes = total
        elif key == "disk":
            disk_lines.append(value)
        elif key == "resolution":
            system.displays.append(DisplayInfo(resolution=value))
        elif key == "locale":
            system.locale = value
    system.gpu.extend(GpuInfo(name=value) for value in gpu_lines)
    system.disks.extend(_disk_from_neofetch(value) for value in disk_lines)
    _dedupe_system(system)
    return system, ["neofetch text output has lower parsing confidence"]


def _parse_used_total(value: str) -> tuple[int | None, int | None]:
    parts = re.split(r"\s*/\s*", value, maxsplit=1)
    if len(parts) != 2:
        return None, parse_size_bytes(value)
    return parse_size_bytes(parts[0]), parse_size_bytes(parts[1])


def _disk_from_neofetch(value: str) -> DiskInfo:
    used, total = _parse_used_total(value)
    mount = None
    match = re.search(r"\(([^)]+)\)", value)
    if match:
        mount = sanitize_text(match.group(1))
    return DiskInfo(mount=mount, used_bytes=used, total_bytes=total)


def collect_runtime_context(
    cfg: Any,
    workdir: Path,
    *,
    force_refresh: bool = False,
    now: datetime | None = None,
    runner: Runner = default_runner,
    which: Which = shutil.which,
    cache_path: Path | None = None,
) -> RuntimeContextResult:
    started = time.monotonic()
    now = now or datetime.now().astimezone()
    if not getattr(cfg, "runtime_context_enabled", True) or getattr(
        cfg, "runtime_context_provider", "auto"
    ) == "off":
        context = RuntimeContext(
            collected_at=now,
            provider="off",
            provider_version=None,
            working_directory=str(workdir.resolve()),
            repository=None,
            system=SystemContext(),
            temporal=temporal_context(now),
            location=LocationContext(source="off", confidence="unknown"),
            warnings=[],
        )
        return RuntimeContextResult(context, duration_ms=_duration_ms(started))

    cache_path = cache_path or getattr(cfg, "runtime_context_cache_file", None)
    cache = _load_cache(cache_path) if cache_path and not force_refresh else None
    stable = None
    if cache and _cache_is_fresh(cache, cfg):
        stable = _stable_from_cache(cache)
    if stable is None:
        stable = _collect_stable_context(cfg, runner, which)
        _write_cache(cache_path, stable, cfg)
    context = RuntimeContext(
        collected_at=now,
        provider=stable["provider"],
        provider_version=stable.get("provider_version"),
        working_directory=str(workdir.resolve()),
        repository=collect_repository_context(workdir, cfg, runner),
        system=stable["system"],
        temporal=temporal_context(now),
        location=infer_location(cfg, system_locale=stable["system"].locale),
        warnings=list(stable.get("warnings", [])),
        stable_collected_at=stable.get("stable_collected_at"),
        cache_hit=bool(stable.get("cache_hit")),
    )
    suggestion = installation_suggestion(context, which=which)
    return RuntimeContextResult(context, suggestion, _duration_ms(started))


def _duration_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _collect_stable_context(cfg: Any, runner: Runner, which: Which) -> dict[str, Any]:
    selected = getattr(cfg, "runtime_context_provider", "auto")
    timeout = int(getattr(cfg, "runtime_context_command_timeout_seconds", 3))
    warnings: list[str] = []
    providers = (
        ["fastfetch", "neofetch", "native"]
        if selected == "auto"
        else [selected, "fastfetch", "neofetch", "native"]
    )
    seen: set[str] = set()
    for provider in providers:
        if provider in seen:
            continue
        seen.add(provider)
        try:
            if provider == "fastfetch":
                executable = which("fastfetch")
                if not executable:
                    warnings.append("Fastfetch was not found")
                    continue
                system, provider_warnings = _collect_fastfetch(executable, runner, timeout)
                return _stable(
                    "fastfetch",
                    _version([executable, "--version"], runner, timeout),
                    system,
                    warnings + provider_warnings,
                )
            if provider == "neofetch":
                executable = which("neofetch")
                if not executable:
                    warnings.append("Neofetch was not found")
                    continue
                system, provider_warnings = _collect_neofetch(executable, runner, timeout)
                return _stable(
                    "neofetch",
                    _version([executable, "--version"], runner, timeout),
                    system,
                    warnings + provider_warnings,
                )
            if provider == "native":
                system = collect_native_system()
                native_warnings = []
                if not which("fastfetch") and not which("neofetch"):
                    native_warnings.append("Fastfetch and Neofetch were not found")
                return _stable("native", None, system, warnings + native_warnings)
        except (subprocess.TimeoutExpired, ValueError, OSError, RuntimeError) as exc:
            warnings.append(f"{provider} failed: {sanitize_text(exc)}")
            continue
    return _stable("native", None, collect_native_system(), warnings + ["all collectors failed"])


def _stable(
    provider: str,
    provider_version: str | None,
    system: SystemContext,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "provider_version": provider_version,
        "system": system,
        "warnings": warnings,
        "stable_collected_at": datetime.now().astimezone(),
        "cache_hit": False,
        "host_signature": _host_signature(provider, provider_version, system),
    }


def _collect_fastfetch(
    executable: str,
    runner: Runner,
    timeout: int,
) -> tuple[SystemContext, list[str]]:
    argv = [executable, "-s", FASTFETCH_MODULES, "--format", "json"]
    result = runner(argv, timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"fastfetch exited {result.returncode}")
    return parse_fastfetch_json(result.stdout)


def _collect_neofetch(
    executable: str,
    runner: Runner,
    timeout: int,
) -> tuple[SystemContext, list[str]]:
    result = runner([executable, "--off", "--stdout"], timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"neofetch exited {result.returncode}")
    return parse_neofetch_stdout(result.stdout)


def _version(argv: list[str], runner: Runner, timeout: int) -> str | None:
    try:
        result = runner(argv, timeout)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    lines = (result.stdout or result.stderr).splitlines()
    return sanitize_text(lines[0] if lines else "")


def collect_native_system() -> SystemContext:
    uname = platform.uname()
    os_name, os_version = _read_os_release()
    mem_total, mem_used, swap_total, swap_used = _read_meminfo()
    system = SystemContext(
        os_name=os_name or platform.system(),
        os_version=os_version or platform.version(),
        architecture=platform.machine(),
        host_name=platform.node(),
        kernel=f"{uname.system} {uname.release}",
        shell=sanitize_text(
            Path(os.environ.get("SHELL", "")).name or os.environ.get("COMSPEC", "")
        ),
        terminal=sanitize_text(os.environ.get("TERM_PROGRAM") or os.environ.get("TERM")),
        cpu=[CpuInfo(name=_read_cpu_name(), logical_threads=os.cpu_count())],
        memory_total_bytes=mem_total,
        memory_used_bytes=mem_used,
        swap_total_bytes=swap_total,
        swap_used_bytes=swap_used,
        locale=_locale_hint(),
    )
    try:
        usage = shutil.disk_usage(Path.cwd())
        system.disks.append(
            DiskInfo(
                mount=str(Path.cwd().anchor or Path.cwd()),
                used_bytes=usage.used,
                total_bytes=usage.total,
            )
        )
    except OSError:
        pass
    _dedupe_system(system)
    return system


def _read_os_release() -> tuple[str | None, str | None]:
    path = Path("/etc/os-release")
    if not path.exists():
        return None, None
    values: dict[str, str] = {}
    try:
        for raw in path.read_text(errors="replace").splitlines():
            if "=" in raw:
                key, value = raw.split("=", 1)
                values[key] = value.strip().strip('"')
    except OSError:
        return None, None
    return values.get("PRETTY_NAME") or values.get("NAME"), values.get("VERSION")


def _read_cpu_name() -> str | None:
    path = Path("/proc/cpuinfo")
    try:
        for raw in path.read_text(errors="replace").splitlines():
            if raw.lower().startswith(("model name", "hardware")) and ":" in raw:
                return sanitize_text(raw.split(":", 1)[1])
    except OSError:
        pass
    return sanitize_text(platform.processor())


def _read_meminfo() -> tuple[int | None, int | None, int | None, int | None]:
    path = Path("/proc/meminfo")
    values: dict[str, int] = {}
    try:
        for raw in path.read_text(errors="replace").splitlines():
            parts = raw.split()
            if len(parts) >= 2 and parts[1].isdigit():
                values[parts[0].rstrip(":")] = int(parts[1]) * 1024
    except OSError:
        return None, None, None, None
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    used = total - available if total is not None and available is not None else None
    swap_total = values.get("SwapTotal")
    swap_free = values.get("SwapFree")
    swap_used = (
        swap_total - swap_free
        if swap_total is not None and swap_free is not None
        else None
    )
    return total, used, swap_total, swap_used


def temporal_context(now: datetime | None = None) -> TemporalContext:
    now = now or datetime.now().astimezone()
    offset = now.strftime("%z")
    offset = f"{offset[:3]}:{offset[3:]}" if offset else ""
    return TemporalContext(
        local_iso=now.isoformat(timespec="seconds"),
        utc_iso=now.astimezone(UTC).isoformat(timespec="seconds"),
        timezone=detect_iana_timezone() or now.tzname(),
        utc_offset=offset,
        weekday=now.strftime("%A"),
    )


def detect_iana_timezone() -> str | None:
    env_tz = os.environ.get("TZ", "").strip()
    if env_tz and "/" in env_tz and not env_tz.startswith(":"):
        return env_tz
    timezone_file = Path("/etc/timezone")
    try:
        if timezone_file.exists():
            value = timezone_file.read_text().strip()
            if "/" in value and not value.startswith("Etc/"):
                return value
    except OSError:
        pass
    try:
        target = Path("/etc/localtime").resolve()
        marker = "/usr/share/zoneinfo/"
        text = str(target)
        if marker in text:
            zone = text.split(marker, 1)[1]
            if "/" in zone and not zone.startswith("Etc/"):
                return zone
    except OSError:
        pass
    return None


def infer_location(cfg: Any, *, system_locale: str | None = None) -> LocationContext:
    mode = getattr(cfg, "runtime_context_location_mode", "local")
    configured_country = sanitize_text(getattr(cfg, "runtime_context_location_country", ""))
    configured_region = sanitize_text(getattr(cfg, "runtime_context_location_region", ""))
    if mode == "off":
        return LocationContext(source="unknown", confidence="unknown")
    if configured_country or mode == "configured":
        code = configured_country.upper() if len(configured_country) == 2 else None
        name = COUNTRY_NAMES.get(code or "", configured_country or None)
        return LocationContext(
            country_code=code,
            country_name=name,
            region=configured_region or None,
            source="configured",
            confidence="high" if configured_country else "unknown",
            basis="configured runtime_context.location",
        )
    if mode == "network" and getattr(cfg, "runtime_context_location_allow_network", False):
        # No default third-party geolocation service is configured in this release.
        local = _infer_local_location(system_locale)
        if local.source == "unknown":
            local.basis = "network lookup unavailable; no default service configured"
        return local
    return _infer_local_location(system_locale)


def _infer_local_location(system_locale: str | None = None) -> LocationContext:
    timezone = detect_iana_timezone()
    if not timezone or timezone in {"UTC", "Etc/UTC"} or timezone.startswith("Etc/"):
        return LocationContext(source="unknown", confidence="unknown", basis=timezone)
    countries = countries_for_timezone(timezone)
    locale_country = _country_from_locale(system_locale or _locale_hint())
    if not countries:
        if locale_country:
            return LocationContext(
                country_code=locale_country,
                country_name=COUNTRY_NAMES.get(locale_country, locale_country),
                source="locale",
                confidence="low",
                basis=system_locale,
            )
        return LocationContext(source="unknown", confidence="unknown", basis=timezone)
    confidence = "medium" if len(countries) == 1 else "low"
    if locale_country and locale_country not in countries:
        confidence = "low"
    code = countries[0] if len(countries) == 1 else None
    country_name = COUNTRY_NAMES.get(code or "", ", ".join(countries))
    return LocationContext(
        country_code=code,
        country_name=country_name,
        source="timezone",
        confidence=confidence,
        basis=f"system timezone {timezone}",
    )


def countries_for_timezone(
    timezone: str,
    zoneinfo_dir: Path = Path("/usr/share/zoneinfo"),
) -> list[str]:
    if timezone in {"UTC", "Etc/UTC"} or timezone.startswith("Etc/"):
        return []
    country_names = _load_country_names(zoneinfo_dir)
    countries: list[str] = []
    for filename in ("zone1970.tab", "zone.tab"):
        path = zoneinfo_dir / filename
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for raw in lines:
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split("\t")
            if len(parts) >= 3 and parts[2] == timezone:
                for code in parts[0].split(","):
                    code = code.strip().upper()
                    if code and code not in countries:
                        countries.append(code)
        if countries:
            break
    for code, name in country_names.items():
        COUNTRY_NAMES.setdefault(code, name)
    return countries


def _load_country_names(zoneinfo_dir: Path) -> dict[str, str]:
    path = zoneinfo_dir / "iso3166.tab"
    names = {}
    try:
        for raw in path.read_text(errors="replace").splitlines():
            if raw and not raw.startswith("#") and "\t" in raw:
                code, name = raw.split("\t", 1)
                names[code.upper()] = sanitize_text(name)
    except OSError:
        pass
    return names


def _locale_hint() -> str | None:
    loc = locale_module.getlocale()[0] or os.environ.get("LANG")
    return sanitize_text(loc) if loc else None


def _country_from_locale(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"[_-]([A-Z]{2})", value)
    return match.group(1).upper() if match else None


def collect_repository_context(workdir: Path, cfg: Any, runner: Runner) -> RepositoryContext | None:
    if not getattr(cfg, "runtime_context_include_git", True):
        return None
    timeout = int(getattr(cfg, "runtime_context_command_timeout_seconds", 3))

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return runner(["git", "-C", str(workdir), *args], timeout)

    try:
        root_result = git("rev-parse", "--show-toplevel")
        if root_result.returncode != 0:
            return RepositoryContext(error="outside a Git repository")
        root = Path(root_result.stdout.strip()).resolve()
        branch_result = git("rev-parse", "--abbrev-ref", "HEAD")
        branch = (
            sanitize_text(branch_result.stdout.strip())
            if branch_result.returncode == 0
            else None
        )
        detached = branch == "HEAD"
        if detached:
            branch = None
        status_result = git("status", "--porcelain")
        changed = [
            line for line in status_result.stdout.splitlines()
            if line.strip()
        ] if status_result.returncode == 0 else []
        try:
            relative_path = str(workdir.resolve().relative_to(root)) or "."
        except ValueError:
            relative_path = None
        return RepositoryContext(
            root=str(root),
            relative_path=relative_path,
            branch=branch,
            detached=detached,
            dirty=bool(changed) if status_result.returncode == 0 else None,
            changed_files=len(changed) if status_result.returncode == 0 else None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return RepositoryContext(error=sanitize_text(exc))


def render_runtime_context(context: RuntimeContext, cfg: Any) -> str:
    if context.provider == "off":
        return ""
    max_chars = int(getattr(cfg, "runtime_context_max_prompt_characters", 3500))
    lines = [
        "<runtime_context machine_generated=\"true\">",
        f"Collected: {context.temporal.local_iso}",
        f"Provider: {context.provider}"
        + (f" ({context.provider_version})" if context.provider_version else ""),
    ]
    _render_workspace(lines, context, cfg)
    _render_system(lines, context.system, cfg)
    _render_time_location(lines, context)
    if context.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in _dedupe(sanitize_text(w) for w in context.warnings if w):
            lines.append(f"- {warning}")
    lines.extend(
        [
            "",
            "Use this as situational context only. Mention it only when relevant.",
            "Approximate location may be incorrect and must not be treated as precise.",
            "</runtime_context>",
        ]
    )
    rendered = "\n".join(lines)
    if len(rendered) > max_chars:
        suffix = "\n...[runtime context truncated]\n</runtime_context>"
        rendered = rendered[: max(0, max_chars - len(suffix))].rstrip() + suffix
    return rendered


def _render_workspace(lines: list[str], context: RuntimeContext, cfg: Any) -> None:
    if not getattr(cfg, "runtime_context_include_workspace", True):
        return
    lines.append("")
    lines.append("Workspace:")
    lines.append(f"- Working directory: {sanitize_text(context.working_directory, max_chars=240)}")
    repo = context.repository
    if not repo:
        return
    if repo.root:
        lines.append(f"- Repository root: {sanitize_text(repo.root, max_chars=240)}")
    if repo.relative_path:
        lines.append(f"- Repository relative path: {sanitize_text(repo.relative_path)}")
    if repo.branch:
        lines.append(f"- Branch: {sanitize_text(repo.branch)}")
    if repo.detached:
        lines.append("- Branch: detached HEAD")
    if repo.dirty is not None:
        state = "dirty" if repo.dirty else "clean"
        detail = f"; changed files: {repo.changed_files}" if repo.changed_files else ""
        lines.append(f"- Worktree: {state}{detail}")
    elif repo.error:
        lines.append(f"- Git: {sanitize_text(repo.error)}")


def _render_system(lines: list[str], system: SystemContext, cfg: Any) -> None:
    lines.append("")
    lines.append("System:")
    os_parts = [system.os_name, system.os_version, system.architecture]
    if any(os_parts):
        lines.append(f"- OS: {sanitize_text(' '.join(p for p in os_parts if p))}")
    host = system.host_model or system.host_name
    if host:
        lines.append(f"- Host: {sanitize_text(host)}")
    if system.kernel:
        lines.append(f"- Kernel: {sanitize_text(system.kernel)}")
    if system.cpu:
        cpu = system.cpu[0]
        threads = f", {cpu.logical_threads} logical threads" if cpu.logical_threads else ""
        lines.append(f"- CPU: {sanitize_text(cpu.name or 'unknown')}{threads}")
    if getattr(cfg, "runtime_context_include_displays", True) and system.gpu:
        gpu_names = _dedupe(sanitize_text(g.name or "unknown") for g in system.gpu)
        lines.append(f"- GPUs: {'; '.join(gpu_names[:6])}")
    if system.memory_total_bytes:
        lines.append(
            f"- Memory: {_format_bytes(system.memory_used_bytes)} used / "
            f"{_format_bytes(system.memory_total_bytes)} total"
        )
    if system.swap_total_bytes:
        lines.append(
            f"- Swap: {_format_bytes(system.swap_used_bytes)} used / "
            f"{_format_bytes(system.swap_total_bytes)} total"
        )
    if getattr(cfg, "runtime_context_include_disks", True) and system.disks:
        disks = sorted(system.disks, key=lambda d: d.mount or "")
        rendered = [
            f"{sanitize_text(d.mount or '?')} "
            f"{_format_bytes(d.used_bytes)}/{_format_bytes(d.total_bytes)}"
            for d in disks[:6]
        ]
        lines.append(f"- Relevant disks: {'; '.join(rendered)}")
    if getattr(cfg, "runtime_context_include_displays", True) and system.displays:
        displays = _dedupe(
            sanitize_text(" ".join(p for p in (d.name, d.resolution, d.refresh_rate) if p))
            for d in system.displays
        )
        lines.append(f"- Displays: {'; '.join(displays[:4])}")
    if system.shell:
        lines.append(f"- Shell: {sanitize_text(system.shell)}")
    if system.terminal:
        lines.append(f"- Terminal: {sanitize_text(system.terminal)}")
    if getattr(cfg, "runtime_context_include_local_ip", True) and system.local_addresses:
        values = _dedupe(
            sanitize_text(f"{a.interface or '?'} {a.address}")
            for a in system.local_addresses
            if a.address
        )
        if values:
            lines.append(f"- Local addresses: {'; '.join(values[:6])}")
    if system.locale:
        lines.append(f"- Locale: {sanitize_text(system.locale)}")


def _render_time_location(lines: list[str], context: RuntimeContext) -> None:
    lines.append("")
    lines.append("Time and location:")
    lines.append(f"- Local time: {context.temporal.weekday}, {context.temporal.local_iso}")
    if context.temporal.timezone:
        lines.append(f"- Timezone: {sanitize_text(context.temporal.timezone)}")
    if context.location.country_name:
        lines.append(f"- Approximate country: {sanitize_text(context.location.country_name)}")
    elif context.location.country_code:
        lines.append(f"- Approximate country: {sanitize_text(context.location.country_code)}")
    else:
        lines.append("- Approximate country: unknown")
    lines.append(f"- Location source: {sanitize_text(context.location.source)}")
    lines.append(f"- Confidence: {sanitize_text(context.location.confidence)}")
    if context.location.basis:
        lines.append(f"- Location basis: {sanitize_text(context.location.basis)}")


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "?"
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{value} B"


def _dedupe(values) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _dedupe_system(system: SystemContext) -> None:
    system.gpu = _dedupe_dataclasses(system.gpu)
    system.displays = _dedupe_dataclasses(system.displays)
    system.disks = _dedupe_dataclasses(system.disks)
    system.local_addresses = _dedupe_dataclasses(system.local_addresses)


def _dedupe_dataclasses(items: list[Any]) -> list[Any]:
    seen = set()
    out = []
    for item in items:
        key = json.dumps(_dataclass_to_dict(item), sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def installation_suggestion(context: RuntimeContext, *, which: Which = shutil.which) -> str | None:
    if context.provider == "fastfetch":
        return None
    manager = _package_manager()
    if context.provider == "neofetch":
        prefix = (
            "System context: using Neofetch fallback. Fastfetch is recommended "
            "because it provides structured and more reliable system information."
        )
    else:
        prefix = (
            "System context: using limited native detection. Install Fastfetch for "
            "more complete hardware and operating-system context."
        )
    if which("fastfetch"):
        return None
    command = {
        "apt": "apt install fastfetch",
        "dnf": "dnf install fastfetch",
        "pacman": "pacman -S fastfetch",
        "brew": "brew install fastfetch",
        "scoop": "scoop install fastfetch",
        "choco": "choco install fastfetch",
    }.get(manager)
    if command:
        return f"{prefix} Suggested command: {command}"
    return f"{prefix} Check your OS package manager for a Fastfetch package."


def _package_manager() -> str | None:
    for name in ("apt", "dnf", "pacman", "brew", "scoop", "choco"):
        if shutil.which(name):
            return name
    return None


def context_to_dict(context: RuntimeContext) -> dict[str, Any]:
    return _dataclass_to_dict(context)


def _dataclass_to_dict(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {k: _dataclass_to_dict(v) for k, v in asdict(value).items()}
    if isinstance(value, list):
        return [_dataclass_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {k: _dataclass_to_dict(v) for k, v in value.items()}
    return value


def _host_signature(provider: str, provider_version: str | None, system: SystemContext) -> str:
    return "|".join(
        sanitize_text(part)
        for part in (
            provider,
            provider_version or "",
            system.kernel or "",
            system.host_model or "",
            system.os_name or "",
        )
    )


def _load_cache(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("schema_version") != SCHEMA_VERSION:
        return None
    return payload


def _cache_is_fresh(payload: dict[str, Any], cfg: Any) -> bool:
    try:
        collected = datetime.fromisoformat(payload["stable_collected_at"])
    except (KeyError, TypeError, ValueError):
        return False
    age = (datetime.now().astimezone() - collected).total_seconds()
    return age <= int(getattr(cfg, "runtime_context_refresh_seconds", 300))


def _stable_from_cache(payload: dict[str, Any]) -> dict[str, Any] | None:
    try:
        system = _system_from_dict(payload["system"])
        collected = datetime.fromisoformat(payload["stable_collected_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": payload.get("provider", "native"),
        "provider_version": payload.get("provider_version"),
        "system": system,
        "warnings": list(payload.get("warnings", [])),
        "stable_collected_at": collected,
        "cache_hit": True,
        "host_signature": payload.get("host_signature", ""),
    }


def _write_cache(path: Path | None, stable: dict[str, Any], cfg: Any) -> None:
    if not path:
        return
    payload = {
        "schema_version": SCHEMA_VERSION,
        "provider": stable["provider"],
        "provider_version": stable.get("provider_version"),
        "system": context_to_dict(stable["system"]),
        "warnings": stable.get("warnings", []),
        "stable_collected_at": stable["stable_collected_at"].isoformat(),
        "host_signature": stable.get("host_signature", ""),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        tmp.replace(path)
    except OSError:
        return


def _system_from_dict(data: dict[str, Any]) -> SystemContext:
    return SystemContext(
        os_name=data.get("os_name"),
        os_version=data.get("os_version"),
        architecture=data.get("architecture"),
        host_name=data.get("host_name"),
        host_model=data.get("host_model"),
        kernel=data.get("kernel"),
        uptime_seconds=data.get("uptime_seconds"),
        shell=data.get("shell"),
        terminal=data.get("terminal"),
        cpu=[CpuInfo(**item) for item in data.get("cpu", [])],
        gpu=[GpuInfo(**item) for item in data.get("gpu", [])],
        memory_total_bytes=data.get("memory_total_bytes"),
        memory_used_bytes=data.get("memory_used_bytes"),
        swap_total_bytes=data.get("swap_total_bytes"),
        swap_used_bytes=data.get("swap_used_bytes"),
        displays=[DisplayInfo(**item) for item in data.get("displays", [])],
        disks=[DiskInfo(**item) for item in data.get("disks", [])],
        local_addresses=[LocalAddress(**item) for item in data.get("local_addresses", [])],
        locale=data.get("locale"),
    )
