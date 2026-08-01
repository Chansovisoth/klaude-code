import json
import zipfile
from pathlib import Path

import pytest
from klaude_knowledge.skills import (
    finalize_skill_package,
    install_skill_package,
    list_installed_skills,
)


class FakeConfig:
    def __init__(self, root: Path):
        self._root = root
        self.snapshot_retention = 1

    @property
    def skills_dir(self) -> Path:
        path = self._root / "skills"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def knowledge_dir(self) -> Path:
        path = self._root / "knowledge"
        path.mkdir(parents=True, exist_ok=True)
        return path


def test_install_skill_zip_persists_current_and_manifest(tmp_path):
    archive = tmp_path / "crawl4ai-skill.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("crawl4ai-skill/SKILL.md", "# Crawl4AI\n\nUse AsyncWebCrawler.")
        zf.writestr("crawl4ai-skill/references/extraction.md", "# Extraction")
        zf.writestr("crawl4ai-skill/assets/logo.png", b"\x89PNG\r\n\x1a\n")

    cfg = FakeConfig(tmp_path)
    installed = install_skill_package(cfg, archive, library="crawl4ai")

    assert installed.name == "crawl4ai"
    assert installed.library == "crawl4ai"
    assert (installed.current_dir / "SKILL.md").exists()
    assert not (installed.root / "source.zip").exists()
    assert [p.relative_to(installed.current_dir).as_posix() for p in installed.text_files] == [
        "SKILL.md",
        "references/extraction.md",
    ]
    assert installed.source_uris == [
        "skill://crawl4ai/SKILL.md",
        "skill://crawl4ai/references/extraction.md",
    ]

    assert installed.pending_manifest_path and installed.pending_manifest_path.exists()
    finalize_skill_package(installed)
    assert (installed.root / "source.zip").exists()
    assert (installed.root / "CURRENT").read_text().strip() == installed.version_id
    manifest = json.loads(installed.manifest_path.read_text())
    assert manifest["state"] == "active"
    assert manifest["indexed_sources"] == installed.source_uris
    assert list_installed_skills(cfg)[0]["name"] == "crawl4ai"


def test_reinstall_reports_previous_sources(tmp_path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    with zipfile.ZipFile(first, "w") as zf:
        zf.writestr("SKILL.md", "# First")
    with zipfile.ZipFile(second, "w") as zf:
        zf.writestr("SKILL.md", "# Second")

    cfg = FakeConfig(tmp_path)
    first_installed = install_skill_package(cfg, first, name="demo", library="demo")
    finalize_skill_package(first_installed)
    installed = install_skill_package(cfg, second, name="demo", library="demo")

    assert installed.previous_sources == ["skill://demo/SKILL.md"]
    assert (installed.current_dir / "SKILL.md").read_text() == "# Second"
    assert installed.version_id != first_installed.version_id
    assert (installed.root / "CURRENT").read_text().strip() == first_installed.version_id


def test_reinstall_same_skill_skips_snapshot_when_unchanged(tmp_path):
    archive = tmp_path / "same.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("SKILL.md", "# Same")

    cfg = FakeConfig(tmp_path)
    first = install_skill_package(cfg, archive, name="demo", library="demo")
    finalize_skill_package(first)
    installed = install_skill_package(cfg, archive, name="demo", library="demo")

    assert installed.previous_sources == ["skill://demo/SKILL.md"]
    assert installed.snapshot == ""
    assert not (installed.root / "snapshots").exists()


def test_reinstall_same_skill_into_new_library_reports_old_library(tmp_path):
    archive = tmp_path / "same.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("SKILL.md", "# Same")

    cfg = FakeConfig(tmp_path)
    first = install_skill_package(cfg, archive, name="demo", library="old")
    finalize_skill_package(first)
    installed = install_skill_package(cfg, archive, name="demo", library="new")

    assert installed.previous_library == "old"
    assert installed.previous_sources == ["skill://demo/SKILL.md"]
    assert installed.snapshot == ""


def test_skill_staged_replacement_does_not_move_active_pointer_before_finalize(tmp_path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    with zipfile.ZipFile(first, "w") as zf:
        zf.writestr("SKILL.md", "# First")
    with zipfile.ZipFile(second, "w") as zf:
        zf.writestr("SKILL.md", "# Second")

    cfg = FakeConfig(tmp_path)
    first_installed = install_skill_package(cfg, first, name="demo", library="demo")
    finalize_skill_package(first_installed)

    staged = install_skill_package(cfg, second, name="demo", library="demo")

    assert staged.version_id != first_installed.version_id
    assert (staged.root / "CURRENT").read_text().strip() == first_installed.version_id
    active_version = json.loads(staged.manifest_path.read_text())["active_version"]
    assert active_version == first_installed.version_id


def test_rejects_unsafe_zip_paths(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.md", "nope")

    with pytest.raises(ValueError, match="unsafe zip path"):
        install_skill_package(FakeConfig(tmp_path), archive)
