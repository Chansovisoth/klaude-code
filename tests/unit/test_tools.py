import subprocess

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
    assert [call[0][0] for call in calls] == ["rg", "find", "git"]


def test_simple_commands_execute_without_shell(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ws.run_shell("ls -la")

    assert calls[0][0] == ["ls", "-la"]
    assert calls[0][1]["shell"] is False


def test_shell_syntax_uses_explicit_shell_path(tmp_path, monkeypatch):
    ws = Workspace(tmp_path)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ws.run_shell("rg needle . | head")

    assert calls[0][0] == ["/bin/bash", "-lc", "rg needle . | head"]
    assert calls[0][1]["shell"] is False


def test_destructive_git_commands_receive_highest_risk():
    assert classify_command("git reset --hard").risk == "destructive"
    assert classify_command("git clean -fd").risk == "destructive"
    assert classify_command("git push --force origin main").risk == "destructive"


def test_run_shell_permission_detail_includes_classified_risk(tmp_path):
    tools = {tool.name: tool for tool in build_tools(Workspace(tmp_path))}

    detail = tools["run_shell"].detail({"command": "touch generated.txt"})

    assert "$ touch generated.txt" in detail
    assert "risk=workspace-writing" in detail
