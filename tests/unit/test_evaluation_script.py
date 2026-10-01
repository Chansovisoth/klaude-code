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
_aggregate_results = MODULE._aggregate_results
_valid_worker_output_path = MODULE._valid_worker_output_path
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


def test_live_evaluation_isolates_klaude_data_from_user_state(tmp_path):
    script = tmp_path / "report_data_dir.py"
    script.write_text(
        "import json, os, sys\n"
        "from klaude_core.config import DATA_DIR\n"
        "path = sys.argv[sys.argv.index('--result-file') + 1]\n"
        "open(path, 'w', encoding='utf-8').write(json.dumps("
        "{'data_dir': os.environ.get('KLAUDE_DATA_DIR', ''), "
        "'configured_data_dir': str(DATA_DIR)}))\n",
        encoding="utf-8",
    )

    result = _run_isolated(
        script,
        "test/model",
        "direct-answer",
        tmp_path,
        timeout=1,
    )

    assert "/klaude-eval-" in result["data_dir"]
    assert result["data_dir"].endswith("/data")
    assert result["configured_data_dir"] == result["data_dir"]


def test_timed_out_evaluation_preserves_only_sanitized_progress(tmp_path):
    script = tmp_path / "progress_worker.py"
    script.write_text(
        "import json, sys, time\n"
        "path = sys.argv[sys.argv.index('--progress-file') + 1]\n"
        "payload = {\n"
        "  'model_requests': 1, 'event_counts': {'tool_start': 1},\n"
        "  'tools_started': ['workspace_info'], 'answer': 'must not survive',\n"
        "  'raw_error': 'secret must not survive'\n"
        "}\n"
        "open(path, 'w', encoding='utf-8').write(json.dumps(payload))\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )

    result = _run_isolated(
        script,
        "test/model",
        "workspace-inspection",
        tmp_path,
        timeout=0.1,
    )

    assert result["error_categories"] == ["timeout"]
    assert result["model_requests"] == 1
    assert result["event_counts"] == {"tool_start": 1}
    assert result["tools_started"] == ["workspace_info"]
    assert "must not survive" not in str(result)


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


def test_learned_document_scenario_requires_exact_claim_source_pair():
    scenario = MODULE.SCENARIOS["learned-document"]

    assert scenario.expected_any_tools == ("query_knowledge",)
    assert scenario.network_required is False
    assert scenario.requires_retrieval_support is True
    assert scenario.grounding_expectations[0].claim_terms == ("17 minutes",)
    assert scenario.grounding_expectations[0].source_references == (
        "https://docs.example.invalid/aerolith/cache-beacons",
    )


def test_failed_grounding_scenario_retains_expected_claim_count():
    result = MODULE._failed_result("test/model", "learned-document", "timeout", 1.0)

    assert result["expected_claims"] == 1
    assert result["grounded_claims"] == 0
    assert result["grounding_score"] == 0.0
    assert result["retrieval_support"] == "unsupported"


def test_report_aggregation_compares_models_without_answer_content():
    rows = [
        {
            "model_ref": "ollama/small",
            "scenario": "grounding",
            "success": False,
            "elapsed_seconds": 10.0,
            "grounding_score": 0.0,
            "input_tokens": None,
            "output_tokens": None,
        },
        {
            "model_ref": "cloud/frontier",
            "scenario": "grounding",
            "success": True,
            "elapsed_seconds": 2.0,
            "grounding_score": 1.0,
            "input_tokens": 100,
            "output_tokens": 20,
        },
    ]

    by_model = _aggregate_results(rows, "model_ref")
    by_scenario = _aggregate_results(rows, "scenario")

    assert by_model["cloud/frontier"] == {
        "total": 1,
        "passed": 1,
        "pass_rate": 1.0,
        "mean_elapsed_seconds": 2.0,
        "mean_grounding_score": 1.0,
        "reported_input_tokens": 100,
        "reported_output_tokens": 20,
        "unknown_token_results": 0,
    }
    assert by_scenario["grounding"]["pass_rate"] == 0.5
    assert by_scenario["grounding"]["unknown_token_results"] == 1


def test_hidden_worker_only_writes_to_its_private_temporary_result(tmp_path):
    assert _valid_worker_output_path(tmp_path / "result.json") is False
