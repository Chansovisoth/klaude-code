"""Validate and checksum Klaude release-candidate wheels."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import stat
import sys
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DISTRIBUTIONS = {
    "klaude-cli",
    "klaude-core",
    "klaude-knowledge",
    "klaude-tools",
    "klaude-web",
}


def _project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _normalized_distribution(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _validate_wheel(path: Path, expected_version: str) -> str:
    with zipfile.ZipFile(path) as wheel:
        corrupt = wheel.testzip()
        if corrupt:
            raise ValueError(f"{path.name}: corrupt member {corrupt}")
        members = wheel.infolist()
        names = [member.filename for member in members]
        if len(names) != len(set(names)):
            raise ValueError(f"{path.name}: duplicate archive member")
        for info in members:
            name = info.filename
            member = PurePosixPath(name)
            mode = info.external_attr >> 16
            if "\\" in name or member.is_absolute() or ".." in member.parts:
                raise ValueError(f"{path.name}: unsafe archive member {name!r}")
            if stat.S_ISLNK(mode):
                raise ValueError(f"{path.name}: symbolic links are not permitted")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(metadata_names) != 1 or len(record_names) != 1:
            raise ValueError(f"{path.name}: expected one METADATA and one RECORD")
        metadata = BytesParser().parsebytes(wheel.read(metadata_names[0]))
        distribution = _normalized_distribution(str(metadata.get("Name", "")))
        version = str(metadata.get("Version", ""))
        if version != expected_version:
            raise ValueError(
                f"{path.name}: metadata version {version!r} != {expected_version!r}"
            )

        rows = list(csv.reader(io.StringIO(wheel.read(record_names[0]).decode("utf-8"))))
        recorded = {row[0] for row in rows if row}
        if set(names) - recorded:
            missing = ", ".join(sorted(set(names) - recorded)[:3])
            raise ValueError(f"{path.name}: members missing from RECORD: {missing}")
        return distribution


def _wheel_map(directory: Path, expected_version: str) -> dict[str, Path]:
    wheels = sorted(directory.glob("*.whl"))
    if len(wheels) != len(EXPECTED_DISTRIBUTIONS):
        raise ValueError(
            f"{directory}: expected {len(EXPECTED_DISTRIBUTIONS)} wheels, found {len(wheels)}"
        )
    result: dict[str, Path] = {}
    for wheel in wheels:
        distribution = _validate_wheel(wheel, expected_version)
        if distribution in result:
            raise ValueError(f"{directory}: duplicate distribution {distribution}")
        result[distribution] = wheel
    if set(result) != EXPECTED_DISTRIBUTIONS:
        missing = EXPECTED_DISTRIBUTIONS - set(result)
        extra = set(result) - EXPECTED_DISTRIBUTIONS
        raise ValueError(
            f"{directory}: unexpected wheel set; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return result


def verify(primary: Path, comparison: Path | None = None) -> Path:
    version = _project_version()
    wheels = _wheel_map(primary, version)
    if comparison is not None:
        other = _wheel_map(comparison, version)
        mismatched = [
            name
            for name in sorted(wheels)
            if _digest(wheels[name]) != _digest(other[name])
        ]
        if mismatched:
            raise ValueError(
                "non-reproducible wheel output: " + ", ".join(mismatched)
            )
    checksum_path = primary / "SHA256SUMS"
    checksum_path.write_text(
        "".join(
            f"{_digest(path)}  {path.name}\n"
            for path in sorted(wheels.values(), key=lambda item: item.name)
        ),
        encoding="utf-8",
    )
    return checksum_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    try:
        checksum_path = verify(args.directory, args.compare)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"release artifact verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"release artifacts verified; checksums: {checksum_path}")


if __name__ == "__main__":
    main()
