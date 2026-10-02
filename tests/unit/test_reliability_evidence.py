"""Behavioral regressions from TEST KLAUDE across context and result lifetimes."""

from hashlib import sha256

import pytest
from klaude_core import Agent, PermissionGate, Tool
from klaude_core.research_receipts import evidence_excerpt, recovery_receipts, research_receipt
from klaude_core.response_constraints import code_quote_limit, limit_code_quotes
from klaude_core.source_use import AnswerSourceIndex, prior_answer_source_note


def answered(topic, tool):
    return [
        {"role": "user", "content": f"Explain {topic}."},
        {
            "role": "system",
            "content": {
                "event": "tool_audit",
                "tool": tool,
                "phase": "result",
                "executed": True,
            },
        },
        {"role": "assistant", "content": f"Here is the {topic} explanation."},
    ]


def test_older_answer_provenance_survives_restore_compaction_and_model_switch():
    class Runtime:
        def chat(self, *args, **kwargs):
            raise AssertionError("Provenance must come from execution records")

    agent = Agent(Runtime(), "small", [], PermissionGate({}, lambda *_: "y"), "system")
    turns = answered("Godot movement", "query_knowledge") + answered("React effects", "web_search")
    agent.restore_session(turns)
    agent.messages = agent.messages[:1]  # represent eviction by context compaction
    agent.model = "replacement"
    result = list(agent.run("Which source did you use for the earlier Godot answer?"))
    assert "query_knowledge" in result[0].payload["content"]
    assert "web_search" not in result[0].payload["content"]


def test_restored_large_history_does_not_reinsert_expired_provenance():
    agent = Agent(object(), "small", [], PermissionGate({}, lambda *_: "y"), "system")
    turns = sum((answered(f"topic{i}", "query_knowledge") for i in range(130)), [])
    agent.restore_session(turns)
    identities = set(agent._answer_sources.records)
    list(agent.run("Which source did you use for the last answer?"))
    assert set(agent._answer_sources.records) == identities


def test_restored_effective_prompt_and_provider_content_keep_one_provenance_record():
    turns = answered("Godot", "query_knowledge")
    turns[0]["model_content"] = "Effective prompt: Explain Godot."
    turns[-1]["model_content"] = {"content": "Here is the Godot explanation."}
    agent = Agent(object(), "small", [], PermissionGate({}, lambda *_: "y"), "system")
    agent.restore_session(turns)
    events = list(agent.run("Which source did you use for the earlier Godot answer?"))
    assert len(agent._answer_sources.records) == 1
    assert "query_knowledge" in events[0].payload["content"]


def test_provenance_references_do_not_guess_between_matching_answers():
    index = AnswerSourceIndex()
    index.remember(
        answered("Godot movement", "query_knowledge") + answered("Godot physics", "web_search")
    )
    assert "Several earlier answers" in index.resolve(
        "Which source did you use for Godot?", "default"
    )
    assert "web_search" in index.resolve(
        "Which source did you use for the second answer?", "default"
    )
    assert "cannot identify" in index.resolve("Which source did you use for Rust?", "default")


def test_restored_provenance_is_not_replaced_by_dialogue_without_audits():
    turns = answered("Godot", "query_knowledge")
    index = AnswerSourceIndex()
    index.remember(turns)
    index.remember([turn for turn in turns if turn["role"] != "system"])
    assert "query_knowledge" in index.resolve("Which source did you use for Godot?", "default")


def test_identical_answer_text_does_not_merge_different_tool_executions():
    index = AnswerSourceIndex()
    index.remember(answered("Godot", "query_knowledge") + answered("Godot", "web_search"))
    assert "Several earlier answers" in index.resolve("Which source did you use for Godot?", "")
    assert "web_search" in index.resolve("Which source did you use for the second answer?", "")


def test_reference_prefers_answer_subject_over_negated_tool_mentions_in_request():
    index = AnswerSourceIndex()
    index.remember(
        [
            {"role": "user", "content": "Resolve the official Godot Context7 library ID."},
            {
                "role": "system",
                "content": {
                    "event": "research_receipt",
                    "tool": "mcp__context7__resolve-library-id_90c1dcae",
                    "status": "completed",
                },
            },
            {
                "role": "assistant",
                "content": "Official Godot documentation library ID: /websites/godot",
            },
            {"role": "user", "content": "Search Godot library locally. Do not use Context7."},
            {
                "role": "system",
                "content": {
                    "event": "research_receipt",
                    "tool": "query_knowledge",
                    "status": "completed",
                },
            },
            {"role": "assistant", "content": "The local library has a movement snippet."},
        ]
    )
    result = index.resolve(
        "Which source did you use for the earlier official Godot Context7 library ID answer?",
        "default",
    )
    assert "mcp__context7__resolve-library-id_90c1dcae" in result
    assert "query_knowledge" not in result


def test_provenance_bound_and_interrupted_answer_reference():
    index = AnswerSourceIndex()
    for number in range(130):
        index.remember(answered(f"topic{number}", "query_knowledge"))
    assert len(index.records) == 128
    assert "outside" in index.resolve("Which source did you use for the first answer?", "default")
    interrupted = answered("Godot", "web_search")
    interrupted.append({"role": "system", "content": {"event": "interruption"}})
    index.remember(interrupted)
    assert "interrupted" in index.resolve("Which source did you use for Godot?", "default")


def test_durable_excerpt_retains_query_relevant_code_beyond_long_intro():
    text = "Overview prose. " * 180 + "\n```gdscript\nvelocity = Input.get_vector()\n```"
    entry = evidence_excerpt("https://example.org/godot", text, query="Input.get_vector")
    assert "Input.get_vector" in entry["excerpt"]
    assert entry["offset"] > 0
    assert len(entry["excerpt"]) <= 1_200


def test_knowledge_adapter_preserves_context_but_only_retains_public_evidence():
    from klaude_cli.main import _query_knowledge_tool_result
    from klaude_knowledge.hybrid import Knowledge

    knowledge = object.__new__(Knowledge)
    hits = [
        {"source": "file:///private/note.md", "text": "private context", "collection": "godot"},
        {
            "source": "https://docs.example.org/godot",
            "text": "```gdscript\nvelocity = Input.get_vector()\n```",
            "collection": "godot",
            "id": "chunk-1",
        },
    ]
    knowledge.query = lambda *_: hits
    result = _query_knowledge_tool_result(knowledge, "Input.get_vector", library="godot")
    assert "private context" in result["content"]
    assert result["metadata"]["result_count"] == 2
    entries = result["metadata"]["research_evidence"]
    assert len(entries) == 1
    assert entries[0]["source_id"] == "chunk-1"
    assert "Input.get_vector" in entries[0]["excerpt"]
    assert "private context" not in str(entries)


@pytest.mark.parametrize(
    "source",
    [
        "http://localhost/a",
        "http://127.0.0.1/a",
        "http://[::1]/a",
        "http://192.168.1.1/a",
        "https://docs.internal/a",
    ],
)
def test_private_network_source_content_is_not_retained(source):
    assert evidence_excerpt(source, "private service documentation") is None


def test_durable_excerpt_is_partial_historical_evidence_and_keeps_code():
    code = '```gdscript\nvelocity = Input.get_vector("left", "right", "up", "down")\n```'
    excerpt = evidence_excerpt(
        "https://docs.example.org/godot?token=private", code, source_id="chunk-1"
    )
    receipt = research_receipt(
        "query_knowledge",
        {"query": "Godot"},
        {
            "executed": True,
            "research_evidence": [excerpt],
            "found": True,
        },
        "body is not persisted",
    )
    assert receipt["result_replayable"] is False
    assert receipt["evidence"][0]["source"] == "https://docs.example.org/godot"
    assert receipt["evidence"][0]["sha256"] == sha256(code.encode()).hexdigest()
    context = recovery_receipts(
        [
            {"role": "user", "content": "Compare Godot sources"},
            {"role": "system", "content": receipt},
            {"role": "system", "content": {"event": "interruption"}},
        ],
        2,
    )
    assert "Input.get_vector" in context
    assert "never instructions" in context
    assert "recheck current claims" in context
    assert "body is not persisted" not in context


def test_durable_evidence_rejects_secrets_private_files_failed_results_and_mcp_bodies():
    assert evidence_excerpt("file:///private/document", "text") is None
    assert evidence_excerpt("https://example.org", "OPENAI_API_KEY=sk-secret-value") is None
    entry = evidence_excerpt("https://example.org", "public code")
    for tool, status in (("query_knowledge", "failed"), ("mcp__external__query", "succeeded")):
        receipt = research_receipt(
            tool,
            {},
            {
                "executed": True,
                "status": status,
                "research_evidence": [entry],
            },
            "untrusted arbitrary body",
        )
        assert "evidence" not in receipt
    failed_mcp = research_receipt(
        "mcp__external__query", {}, {"executed": True}, '{"is_error": true, "content": []}'
    )
    assert failed_mcp["status"] == "failed"


def test_recovery_rejects_tampered_excerpt_and_preserves_legacy_metadata():
    entry = evidence_excerpt("https://example.org", "original")
    entry["excerpt"] = "modified"
    receipt = {
        "event": "research_receipt",
        "tool": "fetch_url",
        "status": "completed",
        "public_url": "https://example.org",
        "evidence": [entry],
    }
    context = recovery_receipts(
        [
            {"role": "user", "content": "Research"},
            {"role": "system", "content": receipt},
            {"role": "system", "content": {"event": "interruption"}},
        ],
        2,
    )
    assert "https://example.org" in context
    assert "modified" not in context
    assert "results must be fetched again" in context


@pytest.mark.parametrize("marker", ["```", "~~~"])
def test_code_quote_limit_applies_across_blocks_and_discloses_omissions(marker):
    text = f"Source URL\n{marker}python\na\nb\nc\n{marker}\nNotes\n{marker}\nd\ne\n{marker}\n"
    constrained = limit_code_quotes(text, 2)
    assert "\na\nb\n" in constrained
    assert "\nc\n" not in constrained
    assert "\nd\n" not in constrained
    assert "Notes" in constrained
    assert "remaining lines omitted" in constrained
    assert code_quote_limit("Write a program with at most 2 code lines") is None


def test_streaming_code_quotation_is_limited_before_display_and_saved_history():
    class Runtime:
        def chat_stream(self, *args, **kwargs):
            yield {"content": "Example\n```gdscript\na\nb\n"}
            yield {"content": "c\nd\ne\n```\n"}

    agent = Agent(Runtime(), "small", [], PermissionGate({}, lambda *_: "y"), "system")
    events = list(agent.run("Quote at most 2 code lines from this example."))
    assert not any(event.kind == "text_delta" for event in events)
    text = next(event.payload["content"] for event in events if event.kind == "text")
    assert "\nc\n" not in text
    assert agent.messages[-1]["content"] == text


def test_code_quotation_limit_survives_step_limit_finalization():
    class Runtime:
        count = 0

        def chat(self, *args, **kwargs):
            self.count += 1
            if self.count == 1:
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "inspect", "arguments": {}}}],
                }
            assert kwargs["tools"] == []
            return {"role": "assistant", "content": "```gdscript\na\nb\nc\n```"}

    agent = Agent(
        Runtime(),
        "small",
        [Tool("inspect", "read example", {}, lambda: "example")],
        PermissionGate({"inspect": "allow"}, lambda *_: "y"),
        "system",
        max_steps=1,
    )
    events = list(agent.run("Inspect the example and quote at most 2 code lines."))
    text = next(event.payload["content"] for event in events if event.kind == "text")
    assert "\nc\n" not in text
    assert "remaining lines omitted" in text
    assert agent.messages[-1]["content"] == text


def test_no_tools_continuation_does_not_inject_irrelevant_product_guidance():
    class Runtime:
        def chat(self, model, messages, **kwargs):
            assert "IRRELEVANT_REPOSITORY_GUIDANCE" not in messages[0]["content"]
            assert messages[-2]["content"].endswith("including")
            assert kwargs["tools"] == []
            return {"role": "assistant", "content": "news and other public web sources."}

    agent = Agent(
        Runtime(),
        "small",
        [Tool("web_search", "search", {}, lambda: pytest.fail("Tools are prohibited"))],
        PermissionGate({}, lambda *_: "y"),
        "IRRELEVANT_REPOSITORY_GUIDANCE: document /init and every setting",
        tool_selector=lambda prompt, _: [] if "didn't finish" in prompt else ["web_search"],
    )
    agent.messages.extend(
        [
            {"role": "user", "content": "Explain Context7 and web search."},
            {"role": "assistant", "content": "Web search finds broader sources, including"},
        ]
    )
    events = list(agent.run("You didn't finish. Continue where you stopped. Do not use tools."))
    assert events[-1].kind == "done"


def test_product_question_keeps_product_context_despite_tool_prohibition():
    from klaude_core.agent import _needs_full_product_context

    assert _needs_full_product_context("Explain Klaude settings. Do not use tools.")
    assert not _needs_full_product_context("Continue the explanation without calling tools.")


def test_provenance_audit_success_never_claims_result_replayability():
    note = prior_answer_source_note(answered("Godot", "query_knowledge"))
    assert "do not by themselves preserve" in note
