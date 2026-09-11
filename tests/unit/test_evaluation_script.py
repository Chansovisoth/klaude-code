import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "evaluate_agent_behavior.py"
SPEC = importlib.util.spec_from_file_location("klaude_evaluation_script", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
_run_isolated = MODULE._run_isolated
_valid_worker_result_path = MODULE._valid_worker_result_path
_worker_error_category = MODULE._worker_error_category


def test_live_evaluation_worker_has_a_hard_process_timeout(tmp_path):
    script = tmp_path / "slow_worker.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")

    result = _run_isolated(
        script,
        "test/model",
        "direct-answer",
        tmp_path,
        timeout=0.05,
    )

    assert result["success"] is False
    assert result["error_categories"] == ["timeout"]


def test_live_evaluation_rejects_network_scenario_without_explicit_flag():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model",
            "test/model",
            "--scenario",
            "web-retrieval",
            "--yes",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "require --include-network" in result.stderr


def test_live_evaluation_rejects_report_outside_workspace_before_running(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--model",
            "test/model",
            "--workspace",
            str(tmp_path),
            "--output",
            str(tmp_path.parent / "outside.json"),
            "--yes",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "must be a file inside" in result.stderr


def test_worker_errors_are_reduced_to_non_secret_categories():
    assert _worker_error_category(RuntimeError("secret token usage limit reached")) == (
        "rate_limit"
    )
    assert _worker_error_category(RuntimeError("credential expired")) == "authentication"
    assert _worker_error_category(ValueError("model is unavailable or ambiguous: x")) == (
        "model_unavailable"
    )


def test_hidden_worker_only_writes_to_its_private_temporary_result(tmp_path):
    assert _valid_worker_result_path(tmp_path / "result.json") is False
