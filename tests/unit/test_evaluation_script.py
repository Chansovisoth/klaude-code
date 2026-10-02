import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "evaluate_agent_behavior.py"
SPEC = importlib.util.spec_from_file_location("klaude_evaluation_script", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
_run_isolated = MODULE._run_isolated
_aggregate_results = MODULE._aggregate_results
_valid_worker_output_path = MODULE._valid_worker_output_path
_worker_error_category = MODULE._worker_error_category


def test_interface_variant_is_forwarded_to_isolated_worker(tmp_path):
    script = tmp_path / "report_variant.py"
    script.write_text(
        "import json, sys\n"
        "variant = sys.argv[sys.argv.index('--knowledge-interface') + 1]\n"
        "path = sys.argv[sys.argv.index('--result-file') + 1]\n"
        "open(path, 'w').write(json.dumps({'variant': variant}))\n",
        encoding="utf-8",
    )
    result = _run_isolated(
        script,
        "test/model",
        "learned-document",
        tmp_path,
        timeout=2,
        knowledge_interface="name",
    )
    assert result == {"variant": "name"}


def test_repeated_interface_comparison_reports_each_run_and_aggregate(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    variants = ["baseline", "description", "schema", "name"]
    arguments = [
        str(SCRIPT),
        "--model",
        "test/model",
        "--scenario",
        "learned-document",
        "--workspace",
        str(tmp_path),
        "--output",
        str(output),
        "--repetitions",
        "2",
    ]
    for variant in variants:
        arguments.extend(["--knowledge-interface", variant])
    monkeypatch.setattr(sys, "argv", arguments)
    monkeypatch.setattr(MODULE, "_confirm", lambda *_: True)
    observed = []

    def run(_script, model, scenario, _workspace, _timeout, variant):
        observed.append(variant)
        return {"success": True, "model_ref": model, "scenario": scenario}

    monkeypatch.setattr(MODULE, "_run_isolated", run)
    assert MODULE.main() == 0
    report = json.loads(output.read_text())
    assert observed == variants * 2
    assert report["summary"] == {"total": 8, "passed": 8, "failed": 0}
    assert [row["repetition"] for row in report["results"]] == [1] * 4 + [2] * 4
    assert set(report["comparison"]["by_knowledge_interface"]) == set(variants)
    assert all(
        group["total"] == 2 for group in report["comparison"]["by_knowledge_interface"].values()
    )


def test_live_worker_uses_standard_mode_after_switching_from_initial_model(tmp_path, monkeypatch):
    import klaude_cli.main as cli

    agent = SimpleNamespace(
        ollama_think="high",
        ollama_code_think="high",
        gate=SimpleNamespace(set_ask_callback=lambda _callback: None),
    )
    selected = SimpleNamespace(ref="ollama/small")
    monkeypatch.setattr(MODULE, "load_config", lambda: SimpleNamespace())
    monkeypatch.setattr(cli, "_build_agent", lambda _workspace: (agent, None))
    monkeypatch.setattr(cli, "_agent_local_ollama", lambda _agent: object())
    monkeypatch.setattr(cli, "_resolve_requested_chat_model", lambda *_: selected)
    monkeypatch.setattr(cli, "_set_agent_model", lambda *_: None)
    monkeypatch.setattr(MODULE, "configure_knowledge_interface", lambda *_: None)

    def evaluate(actual, scenario, **kwargs):
        assert actual.reasoning_mode == "standard"
        assert actual.ollama_think is False
        assert actual.ollama_code_think is False
        return SimpleNamespace(to_dict=lambda: {"success": True})

    monkeypatch.setattr(MODULE, "evaluate_agent_turn", evaluate)
    assert (
        MODULE._worker(
            selected.ref,
            "direct-answer",
            tmp_path,
            tmp_path / "result.json",
            tmp_path / "progress.json",
        )
        == 0
    )


def test_cancelled_comparison_preserves_completed_results(tmp_path, monkeypatch):
    output = tmp_path / "partial.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--model",
            "fake",
            "--scenario",
            "direct-answer",
            "--workspace",
            str(tmp_path),
            "--output",
            str(output),
            "--repetitions",
            "2",
            "--yes",
        ],
    )
    calls = []

    def run(*_args):
        calls.append(True)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return {"success": True, "model_ref": "fake", "scenario": "direct-answer"}

    monkeypatch.setattr(MODULE, "_run_isolated", run)
    assert MODULE.main() == 130
    report = json.loads(output.read_text())
    assert report["cancelled"] is True
    assert report["summary"] == {"total": 1, "passed": 1, "failed": 0}
    assert report["results"][0]["repetition"] == 1


def test_worker_rejects_multiple_interfaces_before_running(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--worker",
            "--model",
            "fake",
            "--scenario",
            "direct-answer",
            "--result-file",
            str(tmp_path / "result.json"),
            "--progress-file",
            str(tmp_path / "progress.json"),
            "--knowledge-interface",
            "schema",
            "--knowledge-interface",
            "name",
        ],
    )
    monkeypatch.setattr(MODULE, "_worker", lambda *_: pytest.fail("Ambiguous worker ran"))
    assert MODULE.main() == 2


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
