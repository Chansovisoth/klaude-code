"""Answer retrospective source-use questions from observed turn activity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from .memory import is_sensitive_memory

_ACTUAL_USE = re.compile(
    r"(?i)\b(?:which|what)\s+(?:(?:knowledge|research|external)\s+)?"
    r"(?:sources?|resources?|tools?)"
    r"(?:\s+(?:and|or)\s+(?:sources?|resources?|tools?)){0,2}\s+"
    r"(?:(?:did|have)\s+you\s+(?:actually\s+)?(?:use|used|consult|consulted)"
    r"|you\s+(?:actually\s+)?(?:used|consulted))\b"
    r"|\b(?:did|have)\s+(?:you|u)\s+(?:actually\s+)?(?:use|consult)\b"
    r"|\bwhere\s+did\s+(?:you\s+)?(?:get|find)\s+(?:that|this)\b"
)

_RETRIEVAL_NAMES = {
    "query_knowledge": "local knowledge",
    "web_search": "web search",
    "fetch_url": "a fetched web page",
    "code_search": "code search",
    "huggingface_search": "Hugging Face search",
    "huggingface_details": "Hugging Face details",
    "huggingface_readme": "a Hugging Face README",
}


def asks_what_was_used(message: str) -> bool:
    """A past-use question is different from asking what is available now."""
    return bool(_ACTUAL_USE.search(message))


def prior_answer_source_note(turns: list[dict[str, Any]]) -> str:
    """Use result records only; an invocation or audit success is not evidence text."""
    if not turns:
        return "I cannot verify which sources were used for an earlier answer."
    answer_index = next(
        (i for i in range(len(turns) - 1, -1, -1) if turns[i].get("role") == "assistant"),
        -1,
    )
    interruption_index = next(
        (
            i
            for i in range(len(turns) - 1, -1, -1)
            if turns[i].get("role") == "system"
            and isinstance(turns[i].get("content"), dict)
            and turns[i]["content"].get("event") == "interruption"
        ),
        -1,
    )
    if interruption_index > answer_index:
        return (
            "The previous turn was interrupted before a completed answer. "
            "Any tool audit only records execution, not the evidence returned."
        )
    if answer_index < 0:
        return "I cannot verify which sources were used for an earlier answer."
    start = next(
        (i for i in range(answer_index - 1, -1, -1) if turns[i].get("role") == "user"),
        -1,
    )
    if start < 0:
        return "I cannot verify which sources were used for an earlier answer."
    names: list[str] = []
    for turn in turns[start + 1 : answer_index]:
        role = turn.get("role")
        content = turn.get("content")
        if (
            role == "tool"
            and isinstance(turn.get("metadata"), dict)
            and (turn["metadata"].get("executed") is True)
        ):
            name = str(turn.get("tool_name", ""))
        elif (
            role == "system"
            and isinstance(content, dict)
            and (
                content.get("event") == "tool_audit"
                and content.get("phase") == "result"
                and content.get("executed") is True
            )
        ):
            name = str(content.get("tool", ""))
        elif (
            role == "system"
            and isinstance(content, dict)
            and (
                content.get("event") == "research_receipt" and content.get("status") == "completed"
            )
        ):
            # Older line-mode sessions stored this bounded result metadata but
            # did not store tool audits among the replayed turns.
            name = str(content.get("tool", ""))
        else:
            continue
        if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", name) and name not in names:
            names.append(name)
    if not names:
        return (
            "No retrieval tool was used for that answer. I generated it from the "
            "model's existing knowledge and the conversation context."
        )
    labels = [
        (
            f"{_RETRIEVAL_NAMES[name]} ({name})"
            if name in _RETRIEVAL_NAMES
            else f"MCP tool {name}"
            if name.startswith("mcp__")
            else name
        )
        for name in names
    ]
    return (
        "The recorded tool activity for that answer was: "
        + ", ".join(labels)
        + ". These records confirm tool execution, but do not by themselves "
        "preserve or prove the answer's specific evidence."
    )


_REFERENCE_WORDS = set(
    """which what where sources source resources resource tool tools
did have you actually use used consult consulted for from that this the a an and or
answer answers response earlier previous preceding last first second third before
about your me tell please can could would available capabilities giving gave in of
our conversation session record execution to with it was is on i code example
knowledge local web search general not do only merely list specific exact""".split()
)


def _topic_terms(text: str) -> frozenset[str]:
    return frozenset(
        token
        for token in re.findall(r"[a-z0-9_]+", text[:4_000].casefold())
        if len(token) > 1 and token not in _REFERENCE_WORDS
    )


@dataclass(frozen=True)
class AnswerSourceRecord:
    identity: str
    topics: frozenset[str]
    answer_topics: frozenset[str]
    note: str


class AnswerSourceIndex:
    """Bounded provenance independent of model context compaction.

    Keep topic tokens and execution descriptions, never retrieved bodies.
    An ambiguous reference stays ambiguous instead of attributing another run.
    """

    def __init__(self) -> None:
        self.records: dict[str, AnswerSourceRecord] = {}
        self.truncated = False

    def remember(self, turns: list[dict[str, Any]]) -> None:
        starts = [i for i, turn in enumerate(turns) if turn.get("role") == "user"]
        for offset, start in enumerate(starts):
            end = starts[offset + 1] if offset + 1 < len(starts) else len(turns)
            window = turns[start:end]
            answer_turn = next(
                (
                    turn
                    for turn in reversed(window)
                    if turn.get("role") == "assistant" and not turn.get("tool_calls")
                ),
                {},
            )
            request = str(turns[start].get("model_content") or turns[start].get("content", ""))
            model_answer = answer_turn.get("model_content")
            if isinstance(model_answer, dict):
                model_answer = model_answer.get("content")
            answer = str(model_answer or answer_turn.get("content", ""))
            if not answer:
                continue
            note = prior_answer_source_note(window)
            identity = sha256((request + answer).encode()).hexdigest()
            if identity in self.records:
                if self.records[identity].note == note:
                    continue
                # Restored dialogue omits audit bodies; do not replace its
                # authoritative record with an unsupported no-tool inference.
                has_execution = any(
                    turn.get("role") == "tool"
                    or (
                        turn.get("role") == "system"
                        and isinstance(turn.get("content"), dict)
                        and turn["content"].get("event") in {"tool_audit", "research_receipt"}
                    )
                    for turn in window
                )
                if not has_execution:
                    continue
                # Identical prose can result from distinct executions. Keep
                # both instead of silently attributing the later answer to the first.
                identity = sha256((identity + note).encode()).hexdigest()
                if identity in self.records:
                    continue
            topics = (
                frozenset()
                if asks_what_was_used(request) or is_sensitive_memory(request + answer)
                else (_topic_terms(request + " " + answer))
            )
            answer_topics = _topic_terms(answer) if topics else frozenset()
            self.records[identity] = AnswerSourceRecord(identity, topics, answer_topics, note)
        while len(self.records) > 128:
            self.records.pop(next(iter(self.records)))
            self.truncated = True

    def resolve(self, question: str, default: str) -> str:
        records = list(self.records.values())
        if not records:
            return default
        if re.search(r"(?i)\b(?:answer|response) before (?:the )?last\b", question):
            return (
                records[-2].note
                if len(records) > 1
                else ("That answer is outside the retained provenance history.")
            )
        if re.search(r"(?i)\b(?:immediately preceding|last|previous)\s+answer\b", question):
            return default
        ordinal = re.search(r"(?i)\b(first|second|third)\s+(?:answer|response)\b", question)
        if ordinal:
            if self.truncated:
                return "The earliest answers are outside the retained provenance history."
            offset = {"first": 0, "second": 1, "third": 2}[ordinal[1].casefold()]
            return (
                records[offset].note
                if offset < len(records)
                else (
                    "That answer is outside the retained provenance history. "
                    "I cannot verify its sources."
                )
            )
        if not re.search(r"(?i)\b(?:for|about|regarding|earlier|answer|response)\b", question):
            return default
        topics = _topic_terms(question)
        if not topics:
            return default
        ranked = [
            (len(topics & record.topics) + 2 * len(topics & record.answer_topics), record)
            for record in records
        ]
        best = max(score for score, _record in ranked)
        matches = [record for score, record in ranked if score == best and score > 0]
        if len(matches) == 1:
            return matches[0].note
        if not matches:
            return (
                "I cannot identify the referenced answer from retained provenance. "
                "Please name its topic."
            )
        return (
            "Several earlier answers match that topic. "
            "Please identify the answer more specifically."
        )
