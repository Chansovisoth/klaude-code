from klaude_core.skill_drop import SkillDropDetector


def test_detector_waits_for_stability_ignores_installed_packages_and_retries_changes(tmp_path):
    source = tmp_path / "demo.zip"
    source.write_bytes(b"first")
    (tmp_path / "installed").mkdir()
    (tmp_path / "installed" / "SKILL.md").write_text("installed")
    (tmp_path / ".imports").mkdir()
    (tmp_path / ".hidden.md").write_text("hidden")
    (tmp_path / "link.md").symlink_to(source)
    (tmp_path / "image.png").write_bytes(b"image")
    detector = SkillDropDetector()
    assert detector.ready(tmp_path, 0) == []
    source.write_bytes(b"still copying")
    assert detector.ready(tmp_path, 2) == []
    ready = detector.ready(tmp_path, 4)
    assert len(ready) == 1 and ready[0][0] == source
    assert detector.ready(tmp_path, 6) == ready
    source.write_bytes(b"fixed input")
    assert detector.ready(tmp_path, 7) == []
    assert detector.ready(tmp_path, 9)[0][0] == source
    source.unlink()
    assert detector.ready(tmp_path, 10) == []


def test_detector_rejects_symlinked_root_and_empty_files(tmp_path):
    (tmp_path / "empty.md").touch()
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    detector = SkillDropDetector()
    assert detector.ready(link, 0) == []
    assert detector.ready(tmp_path, 0) == []
    assert detector.ready(tmp_path, 3) == []
