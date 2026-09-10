import base64
import csv
import hashlib
import importlib.util
import io
import zipfile
from email.message import Message
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_release_artifacts.py"
SPEC = importlib.util.spec_from_file_location("verify_release_artifacts", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
EXPECTED_DISTRIBUTIONS = MODULE.EXPECTED_DISTRIBUTIONS
verify = MODULE.verify


def _wheel(directory: Path, distribution: str, version: str, content: str = "payload") -> Path:
    normalized = distribution.replace("-", "_")
    filename = directory / f"{normalized}-{version}-py3-none-any.whl"
    dist_info = f"{normalized}-{version}.dist-info"
    package = f"{normalized}/__init__.py"
    metadata = Message()
    metadata["Metadata-Version"] = "2.4"
    metadata["Name"] = distribution
    metadata["Version"] = version
    members = {
        package: content.encode(),
        f"{dist_info}/METADATA": metadata.as_bytes(),
    }
    rows = []
    for name, value in members.items():
        digest = hashlib.sha256(value).digest()
        encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        rows.append([name, f"sha256={encoded}", str(len(value))])
    record = f"{dist_info}/RECORD"
    rows.append([record, "", ""])
    stream = io.StringIO()
    csv.writer(stream, lineterminator="\n").writerows(rows)
    members[record] = stream.getvalue().encode()
    with zipfile.ZipFile(filename, "w") as archive:
        for name, value in members.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, value)
    return filename


def _wheel_set(directory: Path, version: str = "0.2.0a4") -> None:
    directory.mkdir()
    for distribution in EXPECTED_DISTRIBUTIONS:
        _wheel(directory, distribution, version)


def test_release_artifacts_verify_matching_reproducible_wheels(tmp_path, monkeypatch):
    primary = tmp_path / "primary"
    comparison = tmp_path / "comparison"
    _wheel_set(primary)
    _wheel_set(comparison)
    monkeypatch.setattr(MODULE, "_project_version", lambda: "0.2.0a4")

    checksums = verify(primary, comparison)

    assert checksums.name == "SHA256SUMS"
    assert len(checksums.read_text().splitlines()) == len(EXPECTED_DISTRIBUTIONS)


def test_release_artifacts_reject_version_mismatch(tmp_path, monkeypatch):
    primary = tmp_path / "primary"
    _wheel_set(primary, "0.2.0a3")
    monkeypatch.setattr(MODULE, "_project_version", lambda: "0.2.0a4")

    with pytest.raises(ValueError, match="metadata version"):
        verify(primary)


def test_release_artifacts_reject_non_reproducible_wheel(tmp_path, monkeypatch):
    primary = tmp_path / "primary"
    comparison = tmp_path / "comparison"
    _wheel_set(primary)
    _wheel_set(comparison)
    _wheel(comparison, "klaude-core", "0.2.0a4", content="changed")
    monkeypatch.setattr(MODULE, "_project_version", lambda: "0.2.0a4")

    with pytest.raises(ValueError, match="non-reproducible.*klaude-core"):
        verify(primary, comparison)


def test_release_artifacts_reject_unsafe_archive_member(tmp_path, monkeypatch):
    primary = tmp_path / "primary"
    _wheel_set(primary)
    wheel = next(primary.glob("klaude_core-*.whl"))
    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("../outside", b"unsafe")
    monkeypatch.setattr(MODULE, "_project_version", lambda: "0.2.0a4")

    with pytest.raises(ValueError, match="unsafe archive member"):
        verify(primary)
