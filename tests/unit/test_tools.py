import subprocess
import sys

import pytest
from klaude_tools import GitCommandError, Workspace, build_tools, classify_command


def _run(argv, cwd):
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path):
    _run(["git", "init"], path)
    _run(["git", "config", "user.email", "tests@example.test"], path)
    _run(["git", "config", "user.name", "Klaude Tests"], path)
    (path / "README.md").write_text("hello\n")
    _run(["git", "add", "README.md"], path)
    _run(["git", "commit", "-m", "initial"], path)


def test_run_shell_respects_dirty_worktree_write_lock(tmp_path):
    ws = Workspace(tmp_path)
    ws.write_enabled = False

    with pytest.raises(PermissionError, match="working tree is dirty"):
        ws.run_shell("touch generated.txt")


def test_git_diff_tool_description_matches_worktree_diff(tmp_path):
    tools = {tool.name: tool for tool in build_tools(Workspace(tmp_path))}

    assert tools["git_diff"].description == "Show the current working-tree diff."


def test_workspace_info_reports_working_directory_and_repo_root(tmp_path):
    _init_repo(tmp_path)
    nested = tmp_path / "src" / "package"
    nested.mkdir(parents=True)
    ws = Workspace(nested)

    info = ws.workspace_info()

    assert f"working_directory: {nested.resolve()}" in info
    assert f"repository_root: {tmp_path.resolve()}" in info
    assert "write_tools: enabled" in info


def test_workspace_info_description_discourages_system_specs(tmp_path):
    tools = {tool.name: tool for tool in build_tools(Workspace(tmp_path))}

    assert "current working directory and repository root" in tools["workspace_info"].description
    assert "omit hardware/system specs" in tools["workspace_info"].description


def test_workspace_info_reports_dirty_write_lock(tmp_path):
    ws = Workspace(tmp_path)
    ws.write_enabled = False

    assert "write_tools: disabled" in ws.workspace_info()


def test_git_returns_clear_failure_on_nonzero_exit(tmp_path):
    ws = Workspace(tmp_path)

    with pytest.raises(GitCommandError) as excinfo:
        ws._git("definitely-not-a-git-subcommand")

    error = excinfo.value
    assert error.argv == ["git", "definitely-not-a-git-subcommand"]
    assert error.exit_code != 0
    assert "stderr=" in str(error)


def test_failed_branch_switch_is_not_reported_as_success(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    ws = Workspace(tmp_path)

    def fake_git(*args):
        if args == ("status", "--porcelain"):
            return ""
        if args == ("branch", "--list", "klaude/session"):
            return ""
        if args == ("switch", "-c", "klaude/session"):
            raise GitCommandError(["git", *args], 128, "", "switch failed")
        return ""

    monkeypatch.setattr(ws, "_git", fake_git)

    result = ws.ensure_work_branch("session")

    assert result.startswith("git setup failed:")
    assert "switch failed" in result
    assert ws.write_enabled is False


def test_failed_commit_is_not_reported_as_success(tmp_path):
    _init_repo(tmp_path)
    ws = Workspace(tmp_path)

    with pytest.raises(GitCommandError):
        ws.git_commit("empty")


def test_file_write_refuses_changes_that_appeared_after_startup(tmp_path):
    _init_repo(tmp_path)
    ws = Workspace(tmp_path)
    (tmp_path / "README.md").write_text("user edit\n")

    with pytest.raises(PermissionError, match="changed after Klaude started"):
        ws.write_file("agent.txt", "agent edit\n")

    assert not (tmp_path / "agent.txt").exists()
    assert (tmp_path / "README.md").read_text() == "user edit\n"


def test_file_write_commits_only_its_target_path(tmp_path):
    _init_repo(tmp_path)
    ws = Workspace(tmp_path)

    ws.write_file("agent.txt", "agent edit\n")

    changed = _run(["git", "show", "--pretty=", "--name-only", "HEAD"], tmp_path).stdout
    assert changed.strip() == "agent.txt"
    assert _run(["git", "status", "--porcelain"], tmp_path).stdout == ""


def test_file_write_handles_spaces_and_quote_characters_in_git_paths(tmp_path):
    _init_repo(tmp_path)
    ws = Workspace(tmp_path)

    ws.write_file('odd "name".txt', "agent edit\n")

    changed = _run(["git", "show", "--format=", "--name-only", "-z", "HEAD"], tmp_path).stdout
    assert 'odd "name".txt' in changed.split("\0")
    assert _run(["git", "status", "--porcelain"], tmp_path).stdout == ""


def test_successful_workspace_recheck_reenables_writes(tmp_path):
    _init_repo(tmp_path)
    ws = Workspace(tmp_path)
    ws.write_enabled = False

    result = ws.ensure_work_branch("clean-target")

    assert result == "working on branch klaude/clean-target"
    assert ws.write_enabled is True


def test_nested_repository_directory_resolves_repo_root(tmp_path):
    _init_repo(tmp_path)
    nested = tmp_path / "packages" / "core"
    nested.mkdir(parents=True)

    ws = Workspace(nested)

    assert ws.root == nested.resolve()
    assert ws.repo_root == tmp_path.resolve()
    assert ws._is_repo()


def test_git_worktree_with_git_file_is_detected(tmp_path):
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    repo.mkdir()
    _init_repo(repo)
    _run(["git", "worktree", "add", str(worktree)], repo)

    ws = Workspace(worktree)

    assert (worktree / ".git").is_file()
    assert ws.repo_root == worktree.resolve()
    assert ws._is_repo()


def test_dirty_worktree_allows_read_only_shell_commands(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    ws.write_enabled = False
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert "exit=0" in ws.run_shell("rg needle .")
    assert "exit=0" in ws.run_shell("find . -type f")
    assert "exit=0" in ws.run_shell("git diff")
    assert all(call[0][1:3] == ["-m", "klaude_tools.sandbox"] for call in calls)
    assert [call[0][call[0].index("--") + 1] for call in calls] == ["rg", "find", "git"]


def test_simple_commands_execute_without_shell(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ws.run_shell("ls -la")

    sandbox_argv = calls[0][0]
    assert sandbox_argv[1:3] == ["-m", "klaude_tools.sandbox"]
    assert sandbox_argv[sandbox_argv.index("--") + 1 :] == ["ls", "-la"]
    assert calls[0][1]["shell"] is False


def test_shell_syntax_uses_explicit_shell_path(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ws.run_shell("rg needle . | head")

    sandbox_argv = calls[0][0]
    assert sandbox_argv[sandbox_argv.index("--") + 1 :] == [
        "/bin/bash",
        "-lc",
        "rg needle . | head",
    ]
    assert calls[0][1]["shell"] is False


def test_destructive_git_commands_receive_highest_risk():
    assert classify_command("git reset --hard").risk == "destructive"
    assert classify_command("git clean -fd").risk == "destructive"
    assert classify_command("git push --force origin main").risk == "destructive"


def test_destructive_find_and_nested_shell_commands_are_denied(tmp_path):
    ws = Workspace(tmp_path)

    assert classify_command("find . -delete").risk == "destructive"
    assert classify_command("bash -c 'rm -rf generated'").risk == "destructive"
    with pytest.raises(PermissionError, match="destructive command denied"):
        ws.run_shell("find . -delete")


def test_read_only_git_output_option_is_classified_as_writing():
    assert classify_command("git diff --output=patch.txt").risk == "workspace-writing"


def test_shell_rejects_explicit_paths_outside_workspace(tmp_path):
    ws = Workspace(tmp_path)

    with pytest.raises(PermissionError, match="path escapes workspace"):
        ws.run_shell("cat /etc/passwd")
    with pytest.raises(PermissionError, match="path escapes workspace"):
        ws.run_shell("cat ../../etc/passwd")


def test_tools_deny_or_redact_workspace_secrets(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / ".env").write_text("OPENAI_API_KEY=sk-example1234567890\n")
    ws = Workspace(tmp_path)

    with pytest.raises(PermissionError, match="secret file denied"):
        ws.read_file("config/.env")
    with pytest.raises(PermissionError, match="secret file denied"):
        ws.run_shell("cat config/.env")

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "sk-example1234567890", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert "sk-example1234567890" not in ws.run_shell("env")
    assert "[REDACTED]" in ws.run_shell("env")


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
def test_successful_shell_write_is_auto_committed(tmp_path):
    _init_repo(tmp_path)
    ws = Workspace(tmp_path)

    result = ws.run_shell("touch generated.txt")

    assert "exit=0" in result
    assert _run(["git", "status", "--porcelain"], tmp_path).stdout == ""
    changed = _run(["git", "show", "--pretty=", "--name-only", "HEAD"], tmp_path).stdout
    assert changed.strip() == "generated.txt"


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
def test_shell_landlock_blocks_implicit_reads_outside_workspace(tmp_path):
    ws = Workspace(tmp_path)

    result = ws.run_shell(
        "/usr/bin/python3 -c \"from pathlib import Path; print(Path('/etc/passwd').read_text())\""
    )

    assert "exit=1" in result
    assert "Permission denied" in result


def test_run_shell_permission_detail_includes_classified_risk(tmp_path):
    tools = {tool.name: tool for tool in build_tools(Workspace(tmp_path))}

    detail = tools["run_shell"].detail({"command": "touch generated.txt"})

    assert "$ touch generated.txt" in detail
    assert "risk=workspace-writing" in detail
