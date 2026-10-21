"""Generated Research runs the existing evidence-checked Research owner."""

import uuid

from klaude_application.browser_jobs import prepare_generated_operation, run_generated_operation
from klaude_core.research import ResearchStore

from .test_research import cfg as cfg
from .test_research import job
from .test_research import services as services


def test_generated_research_run_uses_reviewed_spec_and_saves_cited_report(cfg, services):
    item = job(cfg)
    fields, resource, summary = prepare_generated_operation(cfg, {
        "operation": "research-run", "target": item["id"], "revision": item["revision"],
    })
    assert resource == f"research:{item['id']}" and item["question"] in summary
    assert run_generated_operation(cfg, {
        "operation": "research-run", "request_id": uuid.uuid4().hex, **fields,
    }) == {"ok": True}
    result = ResearchStore(cfg.data_dir / "library").get(item["id"])
    assert result["status"] == "completed" and result["report"].startswith("research:")
    assert len(services[1]) == 2
