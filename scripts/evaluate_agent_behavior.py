#!/usr/bin/env python3
"""Run opt-in, isolated live behavioral evaluations against configured models."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from klaude_core import EvaluationScenario, evaluate_agent_turn, load_config

SCENARIOS = {
    "direct-answer": EvaluationScenario(
        name="direct-answer",
        prompt=(
            "In two concise sentences, explain why deterministic tests matter. "
            "Do not inspect the workspace or use tools."
        ),
    ),
    "workspace-inspection": EvaluationScenario(
        name="workspace-inspection",
        prompt=(
            "Inspect this workspace read-only and identify its primary implementation "
            "language with one concrete file as evidence. Do not modify anything."
        ),
        expected_any_tools=("workspace_info", "list_dir", "read_file", "grep"),
    ),
    "contextual-diagnostic": EvaluationScenario(
        name="contextual-diagnostic",
        prior_messages=(
            {"role": "user", "content": "How can I inspect disk usage safely?"},
            {
                "role": "assistant",
                "content": "Use read-only storage diagnostics such as df and du.",
            },
        ),
        prompt="Run them and summarize the evidence. Do not modify anything.",
        expected_any_tools=("storage_usage",),
    ),
    "web-retrieval": EvaluationScenario(
        name="web-retrieval",
        prompt=(
            "Find the current official Python stable release and cite the supporting "
            "official source URL."
        ),
        expected_any_tools=("web_search", "fetch_url"),
        requires_retrieval_support=True,
        network_required=True,
    ),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run privacy-bounded live Klaude behavior probes. Every scenario runs in a "
            "separate process, read-only, with a hard timeout."
        )
    )
    parser.add_argument("--model", action="append", default=[], help="canonical model ref")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIOS),
        default=[],
        help="scenario to run; repeatable (default: all non-web scenarios)",
    )
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--timeout", type=float, default=180.0, help="seconds per scenario")
    parser.add_argument("--include-network", action="store_true")
    parser.add_argument("--output", type=Path, help="new JSON report path")
    parser.add_argument("--yes", action="store_true", help="confirm live provider usage")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--result-file", type=Path, help=argparse.SUPPRESS)
    return parser


def _worker(model_ref: str, scenario_name: str, workspace: Path, result_file: Path) -> int:
    # Import CLI wiring only in the isolated worker. The evaluator deliberately
    # exercises the same model resolution, runtime, tools, and prompt as Klaude.
    from klaude_cli.main import (
        _agent_local_ollama,
        _build_agent,
        _resolve_requested_chat_model,
        _set_agent_model,
    )

    cfg = load_config()
    agent, _memory = _build_agent(workspace)
    selected = _resolve_requested_chat_model(cfg, _agent_local_ollama(agent), model_ref)
    if selected is None:
        raise ValueError(f"model is unavailable or ambiguous: {model_ref}")
    _set_agent_model(agent, cfg, _agent_local_ollama(agent), selected)
    # A live evaluation must never block on an unattended approval modal. Keep
    # the user's actual policies so prompts remain measurable, but deny every
    # ask-policy invocation. Agent.run(read_only=True) independently removes
    # mutation and arbitrary-shell schemas before the provider request.
    agent.gate.set_ask_callback(lambda _tool, _detail: "n")
    result = evaluate_agent_turn(
        agent,
        SCENARIOS[scenario_name],
        model_ref=selected.ref,
    )
    result_file.write_text(json.dumps(result.to_dict(), sort_keys=True), encoding="utf-8")
    return 0


def _worker_error_category(error: Exception) -> str:
    """Reduce provider/setup failures to stable categories without returning details."""
    status_code = getattr(error, "status_code", None)
    lowered = f"{type(error).__name__} {error}".casefold()
    if status_code == 429 or "usage limit" in lowered or "rate limit" in lowered:
        return "rate_limit"
    if "auth" in lowered or "credential" in lowered or status_code in {401, 403}:
        return "authentication"
    if "unavailable or ambiguous" in lowered:
        return "model_unavailable"
    if "timeout" in lowered:
        return "provider_timeout"
    if any(marker in lowered for marker in ("connection", "network", "provider")):
        return "provider"
    return "harness"


def _valid_worker_result_path(path: Path) -> bool:
    temporary_root = Path(tempfile.gettempdir()).resolve()
    resolved = path.resolve()
    return (
        not resolved.exists()
        and resolved.parent.parent == temporary_root
        and resolved.parent.name.startswith("klaude-eval-")
    )


def _stop_worker(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:  # pragma: no cover - Windows compatibility
            process.terminate()
        process.wait(timeout=3)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:  # pragma: no cover - Windows compatibility
                process.kill()
        except ProcessLookupError:
            pass
        process.wait()


def _failed_result(model: str, scenario: str, category: str, elapsed: float) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "model_ref": model,
        "success": False,
        "elapsed_seconds": round(max(0.0, elapsed), 3),
        "completed": False,
        "answer_characters": 0,
        "answer_sha256": "",
        "model_requests": 0,
        "event_counts": {},
        "tools_started": [],
        "tools_completed": [],
        "tools_succeeded": [],
        "tool_failures": 0,
        "retries": 0,
        "invalid_tool_retries": 0,
        "permission_prompts": 0,
        "permission_denials": 0,
        "input_tokens": None,
        "output_tokens": None,
        "finalization_score": 0.0,
        "retrieval_support": "not_applicable",
        "source_references": 0,
        "safety_violations": [],
        "error_categories": [category],
    }


def _run_isolated(
    script: Path,
    model: str,
    scenario: str,
    workspace: Path,
    timeout: float,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="klaude-eval-") as temporary:
        result_file = Path(temporary) / "result.json"
        command = [
            sys.executable,
            str(script),
            "--worker",
            "--model",
            model,
            "--scenario",
            scenario,
            "--workspace",
            str(workspace),
            "--result-file",
            str(result_file),
        ]
        started = datetime.now(UTC)
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=os.name == "posix",
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _stop_worker(process)
            elapsed = (datetime.now(UTC) - started).total_seconds()
            return _failed_result(model, scenario, "timeout", elapsed)
        except KeyboardInterrupt:
            _stop_worker(process)
            raise
        elapsed = (datetime.now(UTC) - started).total_seconds()
        if process.returncode != 0 or not result_file.is_file():
            return _failed_result(model, scenario, "harness", elapsed)
        try:
            payload = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _failed_result(model, scenario, "harness", elapsed)
        return payload if isinstance(payload, dict) else _failed_result(
            model, scenario, "harness", elapsed
        )


def _confirm(args: argparse.Namespace, scenarios: list[str]) -> bool:
    if args.yes:
        return True
    if not sys.stdin.isatty():
        print("Refusing unattended live evaluation without --yes.", file=sys.stderr)
        return False
    print("This will send live evaluation prompts to the selected model providers.")
    print(f"Models: {', '.join(args.model)}")
    print(f"Scenarios: {', '.join(scenarios)}")
    return input("Continue? [y/N] ").strip().casefold() in {"y", "yes"}


def main() -> int:
    args = _parser().parse_args()
    if args.worker:
        if len(args.model) != 1 or len(args.scenario) != 1 or args.result_file is None:
            return 2
        if not _valid_worker_result_path(args.result_file):
            return 2
        try:
            return _worker(
                args.model[0],
                args.scenario[0],
                args.workspace.resolve(),
                args.result_file,
            )
        except Exception as exc:
            # The parent records a bounded category. Raw provider exceptions can
            # contain account or request details and are not emitted here.
            result = _failed_result(
                args.model[0],
                args.scenario[0],
                _worker_error_category(exc),
                0.0,
            )
            args.result_file.write_text(
                json.dumps(result, sort_keys=True),
                encoding="utf-8",
            )
            return 0

    if not args.model:
        print("At least one --model is required.", file=sys.stderr)
        return 2
    if not args.workspace.is_dir():
        print("--workspace must be an existing directory.", file=sys.stderr)
        return 2
    if not 1 <= args.timeout <= 3600:
        print("--timeout must be between 1 and 3600 seconds.", file=sys.stderr)
        return 2
    output: Path | None = None
    if args.output is not None:
        output = args.output.resolve()
        workspace = args.workspace.resolve()
        if output == workspace or workspace not in output.parents:
            print("--output must be a file inside --workspace.", file=sys.stderr)
            return 2
        if output.exists():
            print("Refusing to overwrite existing --output.", file=sys.stderr)
            return 2
    scenarios = args.scenario or [
        name for name, scenario in SCENARIOS.items() if not scenario.network_required
    ]
    if any(SCENARIOS[name].network_required for name in scenarios) and not args.include_network:
        print("Network scenarios require --include-network.", file=sys.stderr)
        return 2
    if not _confirm(args, scenarios):
        return 1

    script = Path(__file__).resolve()
    results: list[dict[str, Any]] = []
    try:
        for model in args.model:
            for scenario in scenarios:
                print(f"Evaluating {model} / {scenario} ...", flush=True)
                result = _run_isolated(
                    script,
                    model,
                    scenario,
                    args.workspace.resolve(),
                    args.timeout,
                )
                results.append(result)
                state = "PASS" if result.get("success") else "FAIL"
                print(f"  {state} ({result.get('elapsed_seconds', 0)}s)")
    except KeyboardInterrupt:
        print("\nEvaluation cancelled.", file=sys.stderr)
        return 130

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "results": results,
        "summary": {
            "total": len(results),
            "passed": sum(bool(item.get("success")) for item in results),
            "failed": sum(not bool(item.get("success")) for item in results),
        },
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Report: {output}")
    else:
        print(rendered)
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
