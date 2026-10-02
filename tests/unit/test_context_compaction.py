from copy import deepcopy

from klaude_core.context_compaction import HEADER, build_recap


def test_recap_budget_uses_complete_attributed_entries_and_preserves_initial_request():
    messages = [{"role": "user", "content": "Build Atlas offline. Never push."}]
    for i in range(25):
        messages.extend(
            [
                {"role": "user", "content": f"Correction {i}: keep keyboard navigation"},
                {"role": "assistant", "content": "discussion " * 100},
            ]
        )
    snapshot = deepcopy(messages)
    recap = build_recap(messages, 1000)
    assert len(recap["content"]) <= 1000
    assert "Build Atlas offline. Never push." in recap["content"]
    assert "Correction 24" in recap["content"]
    for line in recap["content"][len(HEADER) :].splitlines():
        assert line.startswith(("User: ", "Assistant: ", "Tools requested: "))
    assert messages == snapshot
    assert build_recap([recap], 1000) == recap


def test_recap_whitelists_public_dialogue_and_keeps_unverified_claims_attributed():
    messages = [
        {"role": "user", "content": "Check Atlas"},
        {
            "role": "assistant",
            "content": "Tests passed",
            "openai_response_items": [
                {"type": "reasoning", "encrypted_content": "PRIVATE REASONING"}
            ],
        },
        {"role": "tool", "content": "SECRET RESULT"},
        {"role": "system", "content": "INTERNAL CONTROLLER STATE"},
    ]
    recap = build_recap(messages, 2000)
    assert "Assistant: Tests passed" in recap["content"]
    assert "not verified evidence" in recap["content"]
    assert "PRIVATE REASONING" not in str(recap)
    assert "SECRET RESULT" not in str(recap)
    assert "INTERNAL CONTROLLER STATE" not in str(recap)


def test_legacy_recap_recovers_only_complete_attributed_public_lines():
    recap = build_recap(
        [
            {
                "role": "system",
                "compaction_summary": True,
                "content": (
                    "Old recap:\nfragment without attribution\n"
                    "User: Preserve Atlas\nAssistant: Done"
                ),
            }
        ],
        1000,
    )
    assert "User: Preserve Atlas" in recap["content"]
    assert "fragment without attribution" not in recap["content"]
    assert build_recap([recap], 1000) == recap
    assert build_recap([], 1000) is None
    assert build_recap([{"role": "user", "content": "Atlas"}], 20) is None


def test_malformed_recap_metadata_cannot_promote_internal_state_or_crash():
    recap = build_recap([{
        "role": "system", "compaction_summary": True,
        "compaction_entries": [
            {"role": [], "text": "invalid"},
            {"role": "tool", "text": "PRIVATE RESULT"},
            {"role": "user", "text": "Keep Atlas offline"},
        ],
    }], 1000)
    assert "Keep Atlas offline" in recap["content"]
    assert "PRIVATE RESULT" not in str(recap)
    assert "invalid" not in str(recap)
