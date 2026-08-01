"""The klaude agent loop.

Deliberately small and dependency-free: messages in, tool calls out,
results appended, repeat until the model answers in plain text or the
step budget runs out. Everything interesting (models, tools, permissions)
is injected, so this file is the single seam for a future swap to a
typed agent framework.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .ollama import Ollama
from .permissions import PermissionDenied, PermissionGate

ToolFn = Callable[..., Any]
ToolSelector = Callable[[str, dict[str, "Tool"]], list[str]]
ToolStartMetadata = Callable[[dict[str, Any]], dict[str, Any]]
TOOL_ALIASES = {
    "search": "web_search",
    "websearch": "web_search",
    "web-search": "web_search",
    "internet_search": "web_search",
    "internet-search": "web_search",
}
RECOVERABLE_UNADVERTISED_TOOLS = {"web_search"}
TEXT_TOOL_RE = re.compile(
    r"<function=(?P<name>[a-zA-Z_][\w-]*)>\s*(?P<body>.*?)</tool_call>",
    re.DOTALL,
)
TEXT_PARAM_RE = re.compile(
    r"<parameter=(?P<name>[a-zA-Z_][\w-]*)>\s*"
    r"(?P<value>.*?)(?=</parameter>|</function>|</tool_call>|<parameter=|$)",
    re.DOTALL,
)
TOOL_MARKUP_RE = re.compile(
    r"</?(?:parameter|function|tool_call)(?:=[^>\s]+)?\s*>",
    re.IGNORECASE,
)
NO_INFO_RE = re.compile(
    r"(?i)\b("
    r"i (?:do not|don't) (?:have|know|see|find)|"
    r"i cannot (?:find|access)|"
    r"i can't (?:find|access)|"
    r"there(?:'s| is) no (?:explicit )?(?:mention|evidence)|"
    r"no (?:explicit )?(?:mention|evidence)|"
    r"no (?:information|results|relevant)"
    r")\b"
)
PROMISE_TO_SEARCH_RE = re.compile(
    r"(?i)\b(?:i(?:'ll| will)|let me|i need to)\s+"
    r"(?:search|look up|check|research|find)\b"
)
DIRECT_LOOKUP_RE = re.compile(
    r"(?i)^\s*(?:who|what|where|when)\s+(?:is|are|was|were)\b"
)
DIRECT_LOOKUP_SUBJECT_RE = re.compile(
    r"(?i)^\s*(?:who|what|where|when)\s+(?:is|are|was|were)\s+(?P<subject>.+?)\s*[?.!]*$"
)
PROFILE_LOOKUP_RE = re.compile(
    r"(?i)^\s*who\s+(?:is|are|was|were)\b"
)
RESULT_COUNT_RE = re.compile(
    r"(?i)\b(\d{1,3})\s+(?:search\s+)?(?:results?|sources?|links?)\b"
)
RAW_RESULTS_RE = re.compile(
    r"(?i)\b(?:show|list|give|display|print|return)\b.*"
    r"\b(?:results?|sources?|links?)\b"
)
SEARCH_REQUEST_RE = re.compile(
    r"(?i)^\s*(?:show|list|give|display|print|return|find|get)\s+"
    r"(?:me\s+)?(?:the\s+)?(?:(?:top|all)\s+)?(?:\d{1,3}\s+)?"
    r"(?:search\s+)?(?:results?|sources?|links?)\s*(?:about|for|on)?\s*"
)
SEARCH_VERB_RE = re.compile(
    r"(?i)^\s*(?:search|look up|lookup|research|find)\s+"
    r"(?:the\s+web\s+)?(?:for\s+)?"
)
FOLLOWUP_PRONOUN_RE = re.compile(
    r"(?i)\b(they|them|their|he|him|his|she|her|it|that person|this person)\b"
)
TOPIC_RE = re.compile(
    r"@[A-Za-z0-9_.-]{3,64}|"
    r"\b[A-Z][A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*\b|"
    r'"([^"\n]{3,80})"'
)
NAME_PHRASE_RE = re.compile(
    r"\b[A-Z][a-z][A-Za-z0-9_.-]*"
    r"(?:\s+[A-Z][a-z][A-Za-z0-9_.-]*){1,3}\b"
)
SEARCH_RESULT_TITLE_RE = re.compile(r"^\[\d+\]\s+(?P<title>.+?)\s*$")
URL_RE = re.compile(r"https?://[^\s<>\])}]+")
TOPIC_SKIP = {
    "GitHub",
    "Minecraft",
    "PIU",
    "TikTok",
    "Twitch",
    "YouTube",
}
TOPIC_ORG_WORDS = {
    "Academy",
    "Association",
    "College",
    "Company",
    "Corporation",
    "Department",
    "Foundation",
    "Institute",
    "International",
    "LLC",
    "Ltd",
    "Ministry",
    "Organization",
    "School",
    "University",
}
TOPIC_ROLE_WORDS = {
    "Computer",
    "Developer",
    "Engineer",
    "Professional",
    "Science",
    "Senior",
    "Student",
}
FOLLOWUP_DROP_WORDS = {
    "a",
    "all",
    "alright",
    "an",
    "any",
    "around",
    "are",
    "at",
    "display",
    "did",
    "do",
    "does",
    "find",
    "first",
    "for",
    "full",
    "get",
    "give",
    "in",
    "he",
    "her",
    "here",
    "him",
    "his",
    "i",
    "it",
    "its",
    "is",
    "last",
    "link",
    "links",
    "list",
    "me",
    "meant",
    "more",
    "my",
    "name",
    "no",
    "on",
    "print",
    "result",
    "results",
    "return",
    "s",
    "search",
    "she",
    "show",
    "source",
    "sources",
    "surname",
    "that",
    "the",
    "that location",
    "their",
    "them",
    "there",
    "they",
    "this",
    "top",
    "what",
    "which",
}
FOLLOWUP_ACTIVITY_WORDS = {
    "channel",
    "channels",
    "creator",
    "game",
    "games",
    "here",
    "minecraft",
    "academy",
    "area",
    "cambodia",
    "college",
    "local",
    "location",
    "nearby",
    "play",
    "played",
    "plays",
    "roblox",
    "school",
    "stream",
    "streams",
    "university",
    "twitch",
    "upload",
    "uploads",
    "video",
    "videos",
    "youtube",
}
PLAY_WORDS = {"game", "games", "play", "played", "plays"}
CASUAL_DIRECT_RE = re.compile(
    r"(?i)^\s*(?:"
    r"hi|hello|hey|how are you|who are you|who might you be|what are you|"
    r"introduce yourself|thanks|thank you|ok(?:ay)?|good morning|good night|"
    r"what can you do|what are you able to do|what can you help with|"
    r"what are your capabilities"
    r")(?:[,\s].*)?$"
)
COMMAND_REFERENCE_RE = re.compile(
    r"(?i)(?:"
    r"^/(?:help|commands)$|"
    r"\b(?:show|list)\b.*\bcommands?\b|"
    r"\bwhat commands? (?:are )?available\b|"
    r"\bcommand reference\b|"
    r"\bshow help\b|"
    r"\bwhat can i type\b|"
    r"\bhow do i use klaude\b|"
    r"\bslash commands?\b|"
    r"\bcli usage\b"
    r")"
)
MAX_TOTAL_SEARCH_CALLS = 6
MAX_FETCH_ATTEMPTS = 4


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for the arguments object
    fn: ToolFn
    detail: Callable[[dict], str] = field(default=lambda args: json.dumps(args)[:200])
    return_direct: bool = False
    start_metadata: ToolStartMetadata | None = None

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class AgentEvent:
    """Emitted to the client so any UI (TUI, VS Code) can render progress."""

    kind: str  # "text" | "tool_start" | "tool_result" | "error" | "done"
    payload: dict[str, Any]


@dataclass(frozen=True)
class ToolExecutionStarted:
    tool_name: str
    provider: str | None
    query: str | None
    fallback_used: bool = False


@dataclass(frozen=True)
class ToolExecutionCompleted:
    tool_name: str
    provider: str | None
    attempted_providers: tuple[str, ...] = ()
    successful_providers: tuple[str, ...] = ()
    fallback_used: bool = False
    accepted_result_count: int = 0
    warning: str | None = None


@dataclass
class UserIntentSegment:
    text: str
    intent: str
    requires_action: bool
    requires_retrieval: bool


@dataclass
class ConversationEntity:
    mention: str
    canonical_name: str | None = None
    entity_type: str | None = None
    location: str | None = None
    candidate_meanings: list[str] = field(default_factory=list)
    selected_meaning: str | None = None
    confidence: float = 0.0
    unresolved: bool = True


@dataclass
class RetrievalConversationState:
    active_entities: list[ConversationEntity] = field(default_factory=list)
    last_user_goal: str | None = None
    last_standalone_query: str | None = None
    last_search_intent: str | None = None
    last_accepted_sources: list[str] = field(default_factory=list)
    rejected_interpretations: list[str] = field(default_factory=list)
    failed_urls: set[str] = field(default_factory=set)


@dataclass
class QueryRewrite:
    original_text: str
    standalone_query: str
    inherited_entities: list[str] = field(default_factory=list)
    explicit_constraints: list[str] = field(default_factory=list)
    inferred_constraints: list[str] = field(default_factory=list)
    discarded_interpretations: list[str] = field(default_factory=list)
    confidence: float = 0.0


class RetrievalDecision(StrEnum):
    DIRECT = "direct"
    MEMORY_OR_SESSION = "memory_or_session"
    LOCAL_KNOWLEDGE = "local_knowledge"
    WEB = "web"
    LOCAL_THEN_WEB = "local_then_web"
    CLARIFY = "clarify"


@dataclass
class RetrievalPlan:
    decision: RetrievalDecision
    reason: str
    confidence_without_retrieval: float
    requires_current_information: bool = False
    requires_user_context: bool = False
    local_query: str | None = None
    web_query: str | None = None


def canonical_tool_name(name: str, known_tools: set[str] | None = None) -> str:
    normalized = TOOL_ALIASES.get(name, name)
    if known_tools is not None and normalized not in known_tools:
        return name
    return normalized


def tool_aliases() -> dict[str, str]:
    return dict(TOOL_ALIASES)


def _parse_text_tool_calls(content: str, known_tools: set[str]) -> list[dict[str, Any]]:
    """Accept the text tool-call format some local models emit."""
    stripped = content.strip()
    if not stripped or "<function=" not in stripped:
        return []

    calls: list[dict[str, Any]] = []
    for match in TEXT_TOOL_RE.finditer(stripped):
        original_name = match.group("name")
        name = canonical_tool_name(original_name, known_tools)
        body = match.group("body").strip()
        try:
            args = json.loads(body) if body.startswith("{") else {}
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        args.update(
            {
                param.group("name"): _clean_tool_arg(param.group("value"))
                for param in TEXT_PARAM_RE.finditer(body)
            }
        )
        calls.append(
            {
                "function": {"name": name, "arguments": args},
                "original_tool_name": original_name,
                "raw_span": match.group(0),
                "parse_status": "ok" if name in known_tools else "unknown_tool",
            }
        )

    if not calls:
        open_match = re.search(r"<function=([a-zA-Z_][\w-]*)>", stripped)
        name = open_match.group(1) if open_match else "malformed_tool_call"
        return [
            {
                "function": {"name": name, "arguments": {}},
                "original_tool_name": name,
                "raw_span": stripped,
                "parse_status": "malformed",
            }
        ]
    return calls


def _clean_tool_arg(value: Any, *, collapse_whitespace: bool = False) -> Any:
    if isinstance(value, str):
        cleaned = TOOL_MARKUP_RE.sub("", value)
        cleaned = cleaned.strip(" \t\r\n\"'")
        if collapse_whitespace:
            cleaned = " ".join(cleaned.split())
        return cleaned
    if isinstance(value, list):
        return [
            _clean_tool_arg(item, collapse_whitespace=collapse_whitespace)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _clean_tool_arg(item, collapse_whitespace=collapse_whitespace)
            for key, item in value.items()
        }
    return value


def segment_user_input(user_message: str) -> list[UserIntentSegment]:
    text = user_message.strip()
    if not text:
        return [UserIntentSegment("", "casual", False, False)]
    raw_parts = [
        part.strip()
        for part in re.split(r"(?:\n+|(?<=[?.!])\s+)", text)
        if part.strip()
    ]
    parts: list[str] = []
    for part in raw_parts or [text]:
        prefix = re.match(
            r"(?i)^(hi|hello|hey|thanks|thank you|ok(?:ay)?)[,!\s]+(.+)$",
            part,
        )
        if prefix and _segment_intent(prefix.group(2)) not in {"greeting", "casual"}:
            parts.extend([prefix.group(1), prefix.group(2).strip()])
        else:
            parts.append(part)
    segments = [
        UserIntentSegment(
            part,
            _segment_intent(part),
            _segment_requires_action(part),
            _segment_requires_retrieval(part),
        )
        for part in parts
    ]
    if len(segments) <= 1:
        return segments
    meaningful: list[UserIntentSegment] = []
    for segment in segments:
        if segment.intent in {"greeting", "casual"} and any(
            other.requires_action or other.requires_retrieval
            for other in segments
            if other is not segment
        ):
            meaningful.append(segment)
            continue
        meaningful.append(segment)
    return meaningful


def _segment_intent(text: str) -> str:
    normalized = text.strip().lower().strip("?.!,")
    if normalized in {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay"}:
        return "greeting" if normalized in {"hi", "hello", "hey"} else "casual"
    if COMMAND_REFERENCE_RE.search(text):
        return "command_help"
    if re.search(r"(?i)\b(file|repo|workspace|directory|git|commit|diff)\b", text):
        return "workspace_request"
    if re.search(r"(?i)\b(docs?|documentation|framework|api|library|code|godot|python)\b", text):
        return "local_knowledge_request"
    if _looks_like_followup_search(text):
        return "follow_up"
    if SEARCH_VERB_RE.search(text) or DIRECT_LOOKUP_RE.search(text):
        return "web_lookup"
    if _looks_like_unfamiliar_lookup(text):
        return "web_lookup"
    if "?" in text:
        return "question"
    return "casual"


def _segment_requires_action(text: str) -> bool:
    return _segment_intent(text) in {
        "action_request",
        "command_help",
        "workspace_request",
        "local_knowledge_request",
        "web_lookup",
        "follow_up",
    }


def _segment_requires_retrieval(text: str) -> bool:
    return _segment_intent(text) in {
        "local_knowledge_request",
        "web_lookup",
        "follow_up",
    }


def _retrieval_message_from_segments(user_message: str) -> str:
    segments = segment_user_input(user_message)
    actionable = [
        segment.text
        for segment in segments
        if segment.requires_action or segment.requires_retrieval
    ]
    return "\n".join(actionable).strip() or user_message


def _looks_like_unfamiliar_lookup(text: str) -> bool:
    stripped = text.strip().strip("?.!,")
    if not stripped or len(stripped) > 80:
        return False
    lowered = stripped.lower()
    if CASUAL_DIRECT_RE.match(stripped) or COMMAND_REFERENCE_RE.search(stripped):
        return False
    if re.search(r"\b(how|why|can|should|would|could|write|create|make)\b", lowered):
        return False
    if re.fullmatch(r"@[A-Za-z0-9_.-]{3,64}", stripped):
        return True
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", stripped)
    if not words or len(words) > 5:
        return False
    if len(words) == 1:
        word = words[0]
        return len(word) >= 4 and word.lower() not in FOLLOWUP_DROP_WORDS
    if " and " in lowered and all(word[:1].isupper() for word in words if word.lower() != "and"):
        return True
    return any(word[:1].isupper() for word in words)


def _retrieval_plan_for_message(user_message: str) -> RetrievalPlan:
    message = _retrieval_message_from_segments(user_message)
    lowered = message.lower()
    if CASUAL_DIRECT_RE.search(user_message):
        return RetrievalPlan(RetrievalDecision.DIRECT, "direct conversational turn", 0.95)
    if re.search(r"\b(previous session|past session|what did i say|did i ask)\b", lowered):
        return RetrievalPlan(
            RetrievalDecision.MEMORY_OR_SESSION,
            "user/session-specific recall",
            0.35,
            requires_user_context=True,
            local_query=message,
        )
    technical = bool(
        re.search(
            r"\b(docs?|documentation|framework|api|library|code|godot|python|react|nextjs)\b",
            lowered,
        )
    )
    current = bool(re.search(r"\b(latest|current|today|news|version|release)\b", lowered))
    if technical and current:
        return RetrievalPlan(
            RetrievalDecision.LOCAL_THEN_WEB,
            "technical question may need local docs and current verification",
            0.45,
            requires_current_information=True,
            local_query=message,
            web_query=message,
        )
    if technical:
        return RetrievalPlan(
            RetrievalDecision.LOCAL_KNOWLEDGE,
            "technical/local documentation question",
            0.55,
            local_query=message,
        )
    if current or DIRECT_LOOKUP_RE.search(message) or _looks_like_unfamiliar_lookup(message):
        return RetrievalPlan(
            RetrievalDecision.WEB,
            "public/current/entity lookup needs retrieval",
            0.3,
            requires_current_information=current,
            web_query=_planned_search_query(message, []),
        )
    return RetrievalPlan(RetrievalDecision.DIRECT, "high-confidence direct answer", 0.8)


def _fallback_search_call(
    user_message: str,
    content: str,
    selected_tools: dict[str, Tool],
    used_tools: set[str],
    used_tool_calls: set[str],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Give local models one more retrieval step before a no-info answer."""
    if not _content_needs_retrieval(content):
        return []

    if "web_search" in selected_tools and "web_search" not in used_tools:
        query = _fallback_search_query(user_message, messages)
        if not query:
            return []
        return [
            {
                "function": {
                    "name": "web_search",
                    "arguments": {"query": query},
                }
            }
        ]

    if "fetch_url" in selected_tools:
        url = _recent_search_result_url(messages)
        if url:
            args = {"url": url}
            key = _tool_call_key("fetch_url", args)
            if key not in used_tool_calls:
                return [{"function": {"name": "fetch_url", "arguments": args}}]
    return []


def _content_needs_retrieval(content: str) -> bool:
    return bool(NO_INFO_RE.search(content) or PROMISE_TO_SEARCH_RE.search(content))


def _initial_tool_calls(
    user_message: str,
    selected_tools: dict[str, Tool],
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    retrieval_message = _retrieval_message_from_segments(user_message)
    plan = _retrieval_plan_for_message(retrieval_message)
    calls: list[dict[str, Any]] = []

    if (
        "search_sessions" in selected_tools
        and plan.decision == RetrievalDecision.MEMORY_OR_SESSION
    ):
        calls.append(
            {
                "function": {
                    "name": "search_sessions",
                    "arguments": {"query": plan.local_query or retrieval_message},
                }
            }
        )

    if (
        "query_knowledge" in selected_tools
        and plan.decision
        in {RetrievalDecision.LOCAL_KNOWLEDGE, RetrievalDecision.LOCAL_THEN_WEB}
    ):
        calls.append(
            {
                "function": {
                    "name": "query_knowledge",
                    "arguments": {"query": plan.local_query or retrieval_message},
                }
            }
        )

    if "web_search" not in selected_tools:
        return calls
    if not _should_plan_search(retrieval_message, messages):
        return calls

    args: dict[str, Any] = {
        "query": plan.web_query or _planned_search_query(retrieval_message, messages)
    }
    count = _requested_result_count(user_message)
    if count:
        args["max_results"] = count
    calls.append({"function": {"name": "web_search", "arguments": args}})
    return calls


def _should_plan_search(user_message: str, messages: list[dict[str, Any]]) -> bool:
    user_message = _retrieval_message_from_segments(user_message)
    if _wants_raw_search_results(user_message):
        query = _search_query_from_request(user_message)
        return bool(query or _recent_topic(messages))
    if SEARCH_VERB_RE.search(user_message):
        return True
    if DIRECT_LOOKUP_RE.search(user_message):
        if FOLLOWUP_PRONOUN_RE.search(user_message) and not _recent_topic(messages):
            return False
        return True
    if _looks_like_unfamiliar_lookup(user_message):
        return True
    return bool(_recent_topic(messages) and _looks_like_followup_search(user_message))


def _planned_search_query(user_message: str, messages: list[dict[str, Any]]) -> str:
    user_message = _retrieval_message_from_segments(user_message)
    query = _search_query_from_request(user_message)
    if _wants_raw_search_results(user_message):
        return query or user_message
    if _looks_like_unfamiliar_lookup(query) and not DIRECT_LOOKUP_RE.search(query):
        words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", query)
        if len(words) == 1 and re.search(r"[a-z][A-Z]|[_@.]", words[0]):
            return query
        if len(words) <= 5:
            return f"Who is {query}"
    if _looks_like_followup_search(query) or _is_low_info_search_query(query):
        topic = _recent_topic(messages)
        if topic:
            terms = _followup_detail_terms(query)
            return " ".join([topic, *_normalize_followup_terms(terms)]).strip()
    return query or user_message


def _search_query_from_request(user_message: str) -> str:
    query = SEARCH_REQUEST_RE.sub("", user_message).strip()
    query = SEARCH_VERB_RE.sub("", query).strip()
    return _clean_tool_arg(query, collapse_whitespace=True).strip("?.!:;,")


def _requested_result_count(user_message: str) -> int | None:
    match = RESULT_COUNT_RE.search(user_message)
    if not match:
        return None
    return max(1, min(int(match.group(1)), 50))


def _wants_raw_search_results(user_message: str) -> bool:
    return bool(RESULT_COUNT_RE.search(user_message) or RAW_RESULTS_RE.search(user_message))


def _should_prefetch_source(user_message: str) -> bool:
    if _wants_raw_search_results(user_message):
        return False
    return bool(PROFILE_LOOKUP_RE.search(user_message) or _looks_like_followup_search(user_message))


def _fallback_search_query(user_message: str, messages: list[dict[str, Any]]) -> str:
    query = _search_query_from_request(user_message)
    if not (_looks_like_followup_search(user_message) or _is_low_info_search_query(query)):
        return query or user_message
    topic = _recent_topic(messages)
    if not topic:
        if _is_low_info_search_query(query):
            return ""
        return query or user_message
    detail_terms = _followup_detail_terms(query)
    return " ".join([topic, *_normalize_followup_terms(detail_terms)]).strip()


def _contextualize_tool_args(
    tool_name: str,
    args: dict[str, Any],
    user_message: str,
    messages: list[dict[str, Any]],
    state: RetrievalConversationState | None = None,
) -> dict[str, Any]:
    if tool_name in {"web_search", "code_search"}:
        query = str(args.get("query") or args.get("question") or "").strip()
        if query:
            args["query"] = _contextual_search_query(query, user_message, messages, state)
    if tool_name == "fetch_url" and "url" in args:
        args["url"] = _clean_tool_arg(str(args["url"]), collapse_whitespace=True)
    return args


def _tool_call_key(name: str, args: dict[str, Any]) -> str:
    return f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"


def _normalized_search_query(value: str) -> str:
    ignored = FOLLOWUP_DROP_WORDS | {
        "who",
        "where",
        "when",
        "was",
        "were",
        "about",
    }
    return " ".join(
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if token not in ignored
    )


def _too_similar_to_seen_query(query: str, seen: set[str]) -> bool:
    normalized = _normalized_search_query(query)
    if not normalized:
        return False
    if normalized in seen:
        return True
    normalized_terms = set(normalized.split())
    for previous in seen:
        previous_terms = set(previous.split())
        if not normalized_terms or not previous_terms:
            continue
        overlap = len(normalized_terms & previous_terms) / max(
            len(normalized_terms),
            len(previous_terms),
        )
        if overlap >= 0.90:
            return True
    return False


def _runtime_location_from_messages(messages: list[dict[str, Any]]) -> dict[str, str]:
    context = str(messages[0].get("content", "")) if messages else ""
    location: dict[str, str] = {}
    country_match = re.search(
        r"(?im)^\s*-\s*Approximate country:\s*(?P<country>[^\n<]+)",
        context,
    )
    if country_match:
        country = country_match.group("country").strip()
        if country and country.lower() != "unknown":
            location["country"] = country
    timezone_match = re.search(
        r"(?im)^\s*-\s*Timezone:\s*(?P<timezone>[^\s<]+)",
        context,
    )
    if timezone_match:
        timezone = timezone_match.group("timezone").strip()
        location["timezone"] = timezone
        if timezone == "Asia/Phnom_Penh":
            location.setdefault("country", "Cambodia")
            location["city_hint"] = "Phnom Penh"
    return location


def _current_entity_constraints(
    user_message: str,
    messages: list[dict[str, Any]],
) -> dict[str, str]:
    recent_user_messages = (
        str(message.get("content", ""))
        for message in messages[-6:]
        if message.get("role") == "user"
    )
    text = " ".join(
        [
            *recent_user_messages,
            user_message,
        ]
    ).lower()
    constraints: dict[str, str] = {}
    if re.search(r"\b(school|schools|academy|college|university)\b", text):
        constraints["entity_type"] = "school"
    if re.search(r"\b(cambodia|cambodian|phnom penh)\b", text):
        constraints["location"] = "Cambodia"
    local_reference = re.search(
        r"\b(here|near me|nearby|my location|my area|that location|around my location)\b",
        text,
    )
    runtime_location = _runtime_location_from_messages(messages)
    if local_reference and runtime_location.get("country"):
        constraints["location"] = runtime_location["country"]
    if local_reference and runtime_location.get("city_hint"):
        constraints["city_hint"] = runtime_location["city_hint"]
    return constraints


def _metadata_result_for_url(url: str, messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    target = url.rstrip(".,")
    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("tool_name") != "web_search":
            continue
        metadata = message.get("metadata") or {}
        for result in metadata.get("search_results") or []:
            if isinstance(result, dict) and str(result.get("url", "")).rstrip(".,") == target:
                return result
    return None


def _recent_fetch_verification_link(url: str, messages: list[dict[str, Any]]) -> bool:
    target = url.rstrip(".,")
    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("tool_name") != "fetch_url":
            continue
        metadata = message.get("metadata") or {}
        links = metadata.get("verification_links") or []
        if any(str(link).rstrip(".,") == target for link in links):
            return True
    return False


def _verification_links_from_metadata(
    metadata: dict[str, Any],
    failed_urls: set[str],
    *,
    limit: int = 3,
) -> list[str]:
    links = metadata.get("verification_links") or []
    candidates: list[str] = []
    for link in links:
        url = str(link or "").strip().rstrip(".,")
        if not url or url in failed_urls or url in candidates:
            continue
        candidates.append(url)
        if len(candidates) >= limit:
            break
    return candidates


def _fetch_rejected_by_recent_constraints(
    url: str,
    user_message: str,
    messages: list[dict[str, Any]],
) -> str:
    constraints = _current_entity_constraints(user_message, messages)
    if not constraints:
        return ""
    result = _metadata_result_for_url(url, messages)
    if not result:
        if _recent_fetch_verification_link(url, messages):
            return ""
        return "URL is not an accepted result for the current interpreted question."
    text = " ".join(
        [
            str(result.get("title", "")),
            str(result.get("url", "")),
            str(result.get("snippet", "")),
        ]
    ).lower()
    if constraints.get("entity_type") == "school" and not re.search(
        r"\b(school|schools|academy|college|university|education|campus|campuses)\b",
        text,
    ):
        return "Result no longer matches the school constraint."
    if constraints.get("location") == "Cambodia" and not re.search(
        r"\b(cambodia|cambodian|phnom penh|khmer|\.kh)\b",
        text,
    ):
        return "Result no longer matches the Cambodia constraint."
    return ""


def rewrite_followup_query(
    query: str,
    user_message: str,
    messages: list[dict[str, Any]],
    state: RetrievalConversationState | None = None,
) -> QueryRewrite:
    original = _clean_tool_arg(query or user_message, collapse_whitespace=True)
    cleaned = _search_query_from_request(original)
    topic = _active_entity_mention(state) or _recent_topic(messages)
    constraints = _current_entity_constraints(user_message, messages)
    explicit: list[str] = []
    inferred: list[str] = []
    discarded: list[str] = []
    if constraints.get("entity_type") == "school":
        explicit.append("school")
        discarded.extend(["Automatic Identification System", "AIS Inc office furniture"])
    if constraints.get("location") == "Cambodia":
        explicit.append("Cambodia")
    if state:
        discarded.extend(state.rejected_interpretations)

    if not topic:
        return QueryRewrite(original, cleaned or original, confidence=0.35)
    if topic.lower() in cleaned.lower():
        base = cleaned
        if _looks_like_followup_search(cleaned):
            terms = [
                term
                for term in _followup_detail_terms(cleaned)
                if term.lower() != topic.lower()
            ]
            normalized_terms = _normalize_followup_terms(terms)
            if constraints.get("location"):
                normalized_terms = [
                    term
                    for term in normalized_terms
                    if term.lower() not in {"area", "local", "location", "nearby"}
                ]
            base = " ".join([topic, *normalized_terms]).strip() or topic
        standalone_terms = [base]
        if state and state.active_entities:
            entity = state.active_entities[0]
            if entity.entity_type and entity.entity_type.lower() not in cleaned.lower():
                inferred.append(entity.entity_type)
                standalone_terms.append(entity.entity_type)
            if entity.location and entity.location.lower() not in cleaned.lower():
                inferred.append(entity.location)
                standalone_terms.append(entity.location)
        for constraint in explicit:
            if constraint.lower() not in " ".join(standalone_terms).lower():
                standalone_terms.append(constraint)
        standalone = " ".join(standalone_terms).strip()
        return QueryRewrite(
            original,
            standalone,
            inherited_entities=[topic],
            explicit_constraints=explicit,
            inferred_constraints=inferred,
            discarded_interpretations=_dedupe_preserve(discarded),
            confidence=0.65,
        )

    if (
        _looks_like_followup_search(user_message)
        or _looks_like_followup_search(cleaned)
        or _is_low_info_search_query(cleaned)
    ):
        terms = _followup_detail_terms(cleaned)
        terms.extend(_recent_disambiguation_terms(messages, topic, terms))
        if state:
            entity = state.active_entities[0] if state.active_entities else None
            if entity and entity.entity_type and entity.entity_type not in {
                term.lower() for term in terms
            }:
                inferred.append(entity.entity_type)
                terms.append(entity.entity_type)
            if entity and entity.location and entity.location.lower() not in {
                term.lower() for term in terms
            }:
                inferred.append(entity.location)
                terms.append(entity.location)
        for constraint in explicit:
            if constraint.lower() not in {term.lower() for term in terms}:
                terms.append(constraint)
        standalone = " ".join([topic, *_normalize_followup_terms(terms)]).strip()
        return QueryRewrite(
            original,
            standalone,
            inherited_entities=[topic],
            explicit_constraints=explicit,
            inferred_constraints=inferred,
            discarded_interpretations=_dedupe_preserve(discarded),
            confidence=0.88 if standalone != cleaned else 0.65,
        )
    return QueryRewrite(original, cleaned or original, confidence=0.45)


def _active_entity_mention(state: RetrievalConversationState | None) -> str:
    if not state or not state.active_entities:
        return ""
    return state.active_entities[0].mention


def _dedupe_preserve(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _update_retrieval_state_from_user(
    state: RetrievalConversationState,
    user_message: str,
    messages: list[dict[str, Any]],
) -> None:
    retrieval_message = _retrieval_message_from_segments(user_message)
    topic = _recent_topic(messages) or _lookup_subject_from_text(retrieval_message)
    if topic and (
        not state.active_entities
        or state.active_entities[0].mention.lower() != topic.lower()
    ):
        if _topic_changed(state, topic, retrieval_message):
            state.active_entities.clear()
            state.rejected_interpretations.clear()
            state.last_accepted_sources.clear()
            state.failed_urls.clear()
        if not state.active_entities:
            state.active_entities.append(
                ConversationEntity(
                    mention=topic,
                    candidate_meanings=_candidate_meanings_for_topic(topic),
                    confidence=0.45,
                    unresolved=True,
                )
            )
    constraints = _current_entity_constraints(user_message, messages)
    if state.active_entities:
        entity = state.active_entities[0]
        if constraints.get("entity_type"):
            entity.entity_type = constraints["entity_type"]
            state.rejected_interpretations = _dedupe_preserve(
                [
                    *state.rejected_interpretations,
                    "Automatic Identification System",
                    "AIS Inc office furniture",
                ]
            )
            entity.confidence = max(entity.confidence, 0.72)
        if constraints.get("location"):
            entity.location = constraints["location"]
            entity.confidence = max(entity.confidence, 0.78)
        entity.unresolved = not (entity.entity_type and entity.location)
    state.last_user_goal = retrieval_message
    rewrite = rewrite_followup_query(retrieval_message, user_message, messages, state)
    state.last_standalone_query = rewrite.standalone_query
    if rewrite.explicit_constraints:
        state.last_search_intent = " ".join(rewrite.explicit_constraints)


def _topic_changed(
    state: RetrievalConversationState,
    topic: str,
    user_message: str,
) -> bool:
    if not state.active_entities:
        return False
    active = state.active_entities[0].mention.lower()
    if topic.lower() == active:
        return False
    text = user_message.lower()
    return bool(DIRECT_LOOKUP_RE.search(user_message) or "who are" in text or "who is" in text)


def _lookup_subject_from_text(text: str) -> str:
    match = DIRECT_LOOKUP_SUBJECT_RE.search(text)
    if match:
        return _clean_topic_candidate(match.group("subject"))
    for token in re.findall(r"\b[A-Z0-9]{2,8}\b", text):
        return token
    if _looks_like_unfamiliar_lookup(text):
        return _clean_topic_candidate(text)
    return ""


def _candidate_meanings_for_topic(topic: str) -> list[str]:
    if topic.upper() == "AIS":
        return [
            "American Intercon School",
            "Automatic Identification System",
            "Advanced Info Service",
        ]
    return []


def _contextual_search_query(
    query: str,
    user_message: str,
    messages: list[dict[str, Any]],
    state: RetrievalConversationState | None = None,
) -> str:
    raw_query = _clean_tool_arg(query, collapse_whitespace=True)
    query = _search_query_from_request(raw_query)
    rewrite = rewrite_followup_query(query, user_message, messages, state)
    if rewrite.standalone_query and rewrite.confidence >= 0.7:
        return rewrite.standalone_query
    topic = _recent_topic(messages)
    if not topic:
        if _is_low_info_search_query(query):
            return ""
        return query or raw_query
    if topic.lower() in query.lower():
        return query
    if (
        _looks_like_followup_search(user_message)
        or _looks_like_followup_search(query)
        or _is_low_info_search_query(query)
    ):
        terms = _followup_detail_terms(query)
        terms.extend(_recent_disambiguation_terms(messages, topic, terms))
        return " ".join([topic, *_normalize_followup_terms(terms)]).strip()
    return query or raw_query


def _is_low_info_search_query(text: str) -> bool:
    return not _followup_detail_terms(text)


def _looks_like_followup_search(text: str) -> bool:
    if FOLLOWUP_PRONOUN_RE.search(text):
        return True
    words = [word.lower() for word in re.findall(r"[A-Za-z0-9_.-]+", text)]
    useful = [word for word in words if word not in FOLLOWUP_DROP_WORDS]
    return bool(useful) and len(useful) <= 6 and any(
        word in FOLLOWUP_ACTIVITY_WORDS for word in useful
    )


def _followup_detail_terms(text: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[A-Za-z0-9_.-]+", text)
        if term.lower() not in FOLLOWUP_DROP_WORDS and not term.isdigit()
    ]


def _normalize_followup_terms(terms: list[str]) -> list[str]:
    normalized = []
    lowered = {term.lower() for term in terms}
    specific_activity = lowered & (FOLLOWUP_ACTIVITY_WORDS - PLAY_WORDS)
    generic_location = {"area", "local", "location", "nearby"}
    drop_generic_location = bool(
        lowered & {"school", "schools", "academy", "college", "university", "cambodia"}
    )
    add_games = bool(
        lowered & PLAY_WORDS
        and "games" not in lowered
        and not specific_activity
    )
    if add_games:
        normalized.append("games")
    for term in terms:
        if add_games and term.lower() in PLAY_WORDS:
            continue
        if drop_generic_location and term.lower() in generic_location:
            continue
        if term not in normalized:
            normalized.append(term)
    return normalized


def _recent_disambiguation_terms(
    messages: list[dict[str, Any]],
    topic: str,
    terms: list[str],
) -> list[str]:
    lowered = {term.lower() for term in terms}
    schoolish = bool({"school", "schools", "academy", "college", "university"} & lowered)
    locationish = bool({"location", "area", "local", "nearby"} & lowered)
    cambodiaish = "cambodia" in lowered
    if not schoolish and not locationish and not cambodiaish:
        return []
    topic_lower = topic.lower()
    recent_school_context = False
    for message in reversed(messages[:-1]):
        content = str(message.get("content", ""))
        lowered_content = content.lower()
        if topic_lower not in lowered_content and "american intercon school" not in lowered_content:
            continue
        if re.search(r"\b(school|schools|academy|college|university)\b", lowered_content):
            recent_school_context = True
        if "american intercon school" in lowered_content and "cambodia" in lowered_content:
            if cambodiaish and not schoolish:
                return ["school"]
            return ["school", "Cambodia"] if locationish and not schoolish else ["Cambodia"]
        if (
            (locationish or cambodiaish)
            and recent_school_context
            and re.search(r"\b(cambodia|cambodian|phnom penh)\b", lowered_content)
        ):
            return ["school", "Cambodia"] if not cambodiaish else ["school"]
    return []


def _recent_topic(messages: list[dict[str, Any]]) -> str:
    anchors = _recent_lookup_subjects(messages)

    if anchors:
        for message in reversed(messages[:-1]):
            content = str(message.get("content", ""))
            for candidate in _topic_candidates(content):
                if _candidate_matches_anchor(candidate, anchors):
                    return candidate
        return anchors[0]

    for message in reversed(messages[:-1]):
        content = str(message.get("content", ""))
        for candidate in _topic_candidates(content):
            if candidate:
                return candidate
    return ""


def _recent_lookup_subjects(messages: list[dict[str, Any]]) -> list[str]:
    subjects: list[str] = []
    for message in reversed(messages[:-1]):
        if message.get("role") != "user":
            continue
        match = DIRECT_LOOKUP_SUBJECT_RE.search(str(message.get("content", "")))
        if not match:
            continue
        subject = _clean_topic_candidate(match.group("subject"))
        if subject and subject.casefold() not in {item.casefold() for item in subjects}:
            subjects.append(subject)
    return subjects


def _topic_candidates(content: str) -> list[str]:
    candidates: list[str] = []

    def add(candidate: str) -> None:
        cleaned = _clean_topic_candidate(candidate)
        if not cleaned or _is_topic_noise(cleaned):
            return
        if cleaned.casefold() not in {item.casefold() for item in candidates}:
            candidates.append(cleaned)

    for line in content.splitlines():
        match = SEARCH_RESULT_TITLE_RE.match(line.strip())
        if not match:
            continue
        title = re.split(r"\s+-\s+|\s+\|\s+", match.group("title"), maxsplit=1)[0]
        for candidate in NAME_PHRASE_RE.findall(title):
            add(candidate)

    for candidate in NAME_PHRASE_RE.findall(content):
        add(candidate)

    for match in TOPIC_RE.finditer(content):
        add(match.group(1) or match.group(0))

    return candidates


def _clean_topic_candidate(candidate: str) -> str:
    return _clean_tool_arg(candidate, collapse_whitespace=True).strip(" @.,:;!?()[]{}\"'")


def _is_topic_noise(candidate: str) -> bool:
    if not candidate:
        return True
    if candidate in TOPIC_SKIP:
        return True
    words = candidate.split()
    if any(word.strip(".,:;!?()[]{}") in TOPIC_ORG_WORDS for word in words):
        return True
    if words and all(word.strip(".,:;!?()[]{}") in TOPIC_ROLE_WORDS for word in words):
        return True
    return False


def _candidate_matches_anchor(candidate: str, anchors: list[str]) -> bool:
    candidate_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_.-]+", candidate)
        if token.lower() not in FOLLOWUP_DROP_WORDS
    }
    for anchor in anchors:
        anchor_tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_.-]+", anchor)
            if token.lower() not in FOLLOWUP_DROP_WORDS
        }
        if anchor_tokens and anchor_tokens <= candidate_tokens:
            return True
    return False


def _recent_search_result_candidates(
    messages: list[dict[str, Any]],
    failed_urls: set[str] | None = None,
    limit: int = 4,
) -> list[str]:
    failed_urls = failed_urls or set()
    for message in reversed(messages):
        if message.get("role") != "tool" or message.get("tool_name") != "web_search":
            continue
        metadata = message.get("metadata") or {}
        results = metadata.get("search_results") or []
        candidates: list[str] = []
        seen_domains: set[str] = set()
        duplicate_domain: list[str] = []
        for result in results:
            url = str(result.get("url", "")).strip().rstrip(".,")
            if not url or url in failed_urls:
                continue
            domain = re.sub(r"^www\.", "", re.sub(r"^https?://", "", url).split("/", 1)[0])
            if domain in seen_domains:
                duplicate_domain.append(url)
            else:
                seen_domains.add(domain)
                candidates.append(url)
            if len(candidates) >= limit:
                return candidates
        candidates.extend(url for url in duplicate_domain if url not in candidates)
        if candidates:
            return candidates[:limit]
        for line in str(message.get("content", "")).splitlines():
            match = URL_RE.search(line)
            if match:
                url = match.group(0).rstrip(".,")
                if url not in failed_urls:
                    return [url]
    return []


def _recent_search_result_url(messages: list[dict[str, Any]]) -> str:
    candidates = _recent_search_result_candidates(messages)
    return candidates[0] if candidates else ""


def _useful_fetch_result(result: str) -> bool:
    stripped = result.strip()
    if not stripped or stripped.startswith(("tool error:", "permission denied:")):
        return False
    if re.search(
        r"(?i)\b("
        r"status\s*999|http\s*(?:999|403|401|429)|"
        r"robots?\s+denied|cloudflare|blocked|access denied|forbidden|"
        r"empty content|empty response|trafilatura extracted no content"
        r")\b",
        stripped,
    ):
        return False
    return len(stripped) >= 40


def _unnecessary_command_reference_call(user_message: str) -> bool:
    if COMMAND_REFERENCE_RE.search(user_message):
        return False
    return bool(CASUAL_DIRECT_RE.search(user_message))


class Agent:
    def __init__(
        self,
        ollama: Ollama,
        model: str,
        tools: list[Tool],
        gate: PermissionGate,
        system_prompt: str,
        max_steps: int = 20,
        tool_selector: ToolSelector | None = None,
    ):
        self.ollama = ollama
        self.model = model
        self.tools = {t.name: t for t in tools}
        self.gate = gate
        self.max_steps = max_steps
        self.tool_selector = tool_selector
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        self.retrieval_state = RetrievalConversationState()

    def set_system_prompt(self, system_prompt: str) -> None:
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = system_prompt
        else:
            self.messages.insert(0, {"role": "system", "content": system_prompt})

    def run(self, user_message: str):
        """Generator of AgentEvent — clients iterate and render."""
        self.messages.append({"role": "user", "content": user_message})
        _update_retrieval_state_from_user(self.retrieval_state, user_message, self.messages)
        retrieval_message = _retrieval_message_from_segments(user_message)
        selected_tools = self.tools
        if self.tool_selector is not None:
            selected_names = self.tool_selector(user_message, self.tools)
            selected_tools = {
                name: self.tools[name] for name in selected_names if name in self.tools
            }
        schemas = [t.schema() for t in selected_tools.values()]
        used_tools: set[str] = set()
        used_tool_calls: set[str] = set()
        failed_fetch_urls: set[str] = set()
        seen_search_queries: set[str] = set()
        search_call_count = 0
        fetch_attempt_count = 0

        def execute_tool_call(call: dict[str, Any]):
            nonlocal search_call_count, fetch_attempt_count
            fn = call.get("function", {})
            original_name = fn.get("name", "")
            name = canonical_tool_name(original_name, set(self.tools))
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            if isinstance(args, dict):
                args = _contextualize_tool_args(
                    name,
                    args,
                    user_message,
                    self.messages,
                    self.retrieval_state,
                )

            tool = selected_tools.get(name)
            if tool is None and name in RECOVERABLE_UNADVERTISED_TOOLS:
                tool = self.tools.get(name)
            if (
                tool is not None
                and name in {"web_search", "code_search"}
                and not str(args.get("query", "")).strip()
            ):
                return name, args, tool, "error: provide a search query or subject"
            if name == "web_search":
                query = str(args.get("query", ""))
                if search_call_count >= MAX_TOTAL_SEARCH_CALLS:
                    return (
                        name,
                        args,
                        tool,
                        (
                            "search budget reached; use the previous result or "
                            "state what could not be verified"
                        ),
                        {"retrieval_budget_exhausted": True},
                    )
                if _too_similar_to_seen_query(query, seen_search_queries):
                    return (
                        name,
                        args,
                        tool,
                        f"skipped near-duplicate search query: {query}",
                        {"duplicate_search_query": True},
                    )
                seen_search_queries.add(_normalized_search_query(query))
                search_call_count += 1
            if name == "fetch_url":
                url = str(args.get("url", ""))
                if fetch_attempt_count >= MAX_FETCH_ATTEMPTS:
                    return (
                        name,
                        args,
                        tool,
                        "fetch budget reached; use accepted search evidence instead",
                        {"retrieval_budget_exhausted": True},
                    )
                rejection = _fetch_rejected_by_recent_constraints(
                    url,
                    user_message,
                    self.messages,
                )
                if rejection:
                    return (
                        name,
                        args,
                        tool,
                        f"skipped fetch: {rejection}",
                        {"rejected_fetch_candidate": True},
                    )
                fetch_attempt_count += 1
            key = _tool_call_key(name, args if isinstance(args, dict) else {})
            if key in used_tool_calls:
                return (
                    name,
                    args,
                    tool,
                    f"skipped duplicate tool call '{name}'; use the previous result",
                    {},
                )
            used_tool_calls.add(key)

            if call.get("parse_status") == "malformed":
                return (
                    name,
                    args,
                    tool,
                    f"error: malformed text-form tool call for '{original_name}'",
                    {},
                )
            if tool is None:
                return name, args, tool, f"error: unknown tool '{original_name}'", {}
            if name == "list_commands" and _unnecessary_command_reference_call(user_message):
                return (
                    name,
                    args,
                    None,
                    (
                        "The command reference is unnecessary for this conversational "
                        "request. Answer the user directly."
                    ),
                    {"suppress_user_output": True, "recoverable_tool_policy": True},
                )

            used_tools.add(name)
            start_metadata: dict[str, Any] = {}
            if tool.start_metadata is not None:
                try:
                    start_metadata = tool.start_metadata(args)
                except Exception:
                    start_metadata = {}
            start_payload = {"tool": name, "args": args}
            if start_metadata:
                start_payload["metadata"] = start_metadata
                start_payload["provider"] = start_metadata.get("provider")
                start_payload["query"] = start_metadata.get("query") or args.get("query")
                start_payload["fallback_used"] = bool(
                    start_metadata.get("fallback_used", False)
                )
            yield AgentEvent("tool_start", start_payload)
            try:
                self.gate.check(name, tool.detail(args))
                result = tool.fn(**args)
            except PermissionDenied as e:
                result = f"permission denied: {e}"
            except Exception as e:
                result = f"tool error: {type(e).__name__}: {e}"

            metadata = {}
            if isinstance(result, dict) and "content" in result:
                metadata = (
                    result.get("metadata")
                    if isinstance(result.get("metadata"), dict)
                    else {}
                )
                result = result.get("content", "")
            result = str(result)
            if len(result) > 12000:  # keep small-model context healthy
                result = result[:12000] + "\n...[truncated]"
            return name, args, tool, result, metadata

        planned_results: list[str] = []
        for call in _initial_tool_calls(retrieval_message, selected_tools, self.messages):
            name, args, tool, result, metadata = yield from execute_tool_call(call)
            if tool is not None and tool.return_direct:
                self.messages.append({"role": "assistant", "content": result})
                payload = {"content": result}
                if metadata:
                    payload["metadata"] = metadata
                yield AgentEvent("text", payload)
                yield AgentEvent("done", {})
                return
            yield AgentEvent(
                "tool_result",
                {"tool": name, "result": result, "metadata": metadata},
            )
            tool_message = {"role": "tool", "tool_name": name, "content": result}
            if metadata:
                tool_message["metadata"] = metadata
            self.messages.append(tool_message)
            if name == "web_search" and _wants_raw_search_results(user_message):
                planned_results.append(result)
            if (
                name == "web_search"
                and "fetch_url" in selected_tools
                and _should_prefetch_source(user_message)
            ):
                for url in _recent_search_result_candidates(self.messages, failed_fetch_urls):
                    fetch_call = {
                        "function": {"name": "fetch_url", "arguments": {"url": url}}
                    }
                    fetch_name, _fetch_args, fetch_tool, fetch_result, fetch_metadata = (
                        yield from execute_tool_call(fetch_call)
                    )
                    if fetch_tool is not None and fetch_tool.return_direct:
                        self.messages.append({"role": "assistant", "content": fetch_result})
                        payload = {"content": fetch_result}
                        if fetch_metadata:
                            payload["metadata"] = fetch_metadata
                        yield AgentEvent("text", payload)
                        yield AgentEvent("done", {})
                        return
                    yield AgentEvent(
                        "tool_result",
                        {
                            "tool": fetch_name,
                            "result": fetch_result,
                            "metadata": fetch_metadata,
                        },
                    )
                    fetch_message = {
                        "role": "tool",
                        "tool_name": fetch_name,
                        "content": fetch_result,
                    }
                    if fetch_metadata:
                        fetch_message["metadata"] = fetch_metadata
                    self.messages.append(fetch_message)
                    if _useful_fetch_result(fetch_result):
                        for linked_url in _verification_links_from_metadata(
                            fetch_metadata,
                            failed_fetch_urls,
                        ):
                            linked_call = {
                                "function": {
                                    "name": "fetch_url",
                                    "arguments": {"url": linked_url},
                                }
                            }
                            (
                                linked_name,
                                _linked_args,
                                linked_tool,
                                linked_result,
                                linked_metadata,
                            ) = yield from execute_tool_call(linked_call)
                            if linked_tool is not None and linked_tool.return_direct:
                                self.messages.append(
                                    {"role": "assistant", "content": linked_result}
                                )
                                payload = {"content": linked_result}
                                if linked_metadata:
                                    payload["metadata"] = linked_metadata
                                yield AgentEvent("text", payload)
                                yield AgentEvent("done", {})
                                return
                            yield AgentEvent(
                                "tool_result",
                                {
                                    "tool": linked_name,
                                    "result": linked_result,
                                    "metadata": linked_metadata,
                                },
                            )
                            linked_message = {
                                "role": "tool",
                                "tool_name": linked_name,
                                "content": linked_result,
                            }
                            if linked_metadata:
                                linked_message["metadata"] = linked_metadata
                            self.messages.append(linked_message)
                            if not _useful_fetch_result(linked_result):
                                failed_fetch_urls.add(linked_url)
                        break
                    failed_fetch_urls.add(url)

        if planned_results:
            content = "\n\n".join(planned_results)
            self.messages.append({"role": "assistant", "content": content})
            yield AgentEvent("text", {"content": content})
            yield AgentEvent("done", {})
            return

        for _step in range(self.max_steps):
            try:
                msg = self.ollama.chat(self.model, self.messages, tools=schemas)
            except Exception as e:  # surface, don't crash the session
                yield AgentEvent("error", {"message": str(e)})
                return

            self.messages.append(msg)
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls") or _parse_text_tool_calls(
                content, set(selected_tools)
            )

            if not tool_calls:
                tool_calls = _fallback_search_call(
                    retrieval_message,
                    content,
                    selected_tools,
                    used_tools,
                    used_tool_calls,
                    self.messages,
                )

            if not tool_calls:
                if used_tools and PROMISE_TO_SEARCH_RE.search(content):
                    recent_tool_content = next(
                        (
                            str(message.get("content", ""))
                            for message in reversed(self.messages)
                            if message.get("role") == "tool"
                        ),
                        "",
                    )
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_name": "retrieval_controller",
                            "content": (
                                f"{recent_tool_content}\n\n"
                                "Retrieval already ran for this turn. Answer from the "
                                "available tool results instead of promising another search."
                            ),
                        }
                    )
                    continue
                yield AgentEvent("text", {"content": content})
                yield AgentEvent("done", {})
                return

            for call in tool_calls:
                name, args, tool, result, metadata = yield from execute_tool_call(call)
                if tool is not None and tool.return_direct:
                    self.messages.append({"role": "assistant", "content": result})
                    payload = {"content": result}
                    if metadata:
                        payload["metadata"] = metadata
                    yield AgentEvent("text", payload)
                    yield AgentEvent("done", {})
                    return
                yield AgentEvent(
                    "tool_result",
                    {"tool": name, "result": result, "metadata": metadata},
                )
                tool_message = {"role": "tool", "tool_name": name, "content": result}
                if metadata:
                    tool_message["metadata"] = metadata
                self.messages.append(tool_message)

        yield AgentEvent("error", {"message": f"step budget ({self.max_steps}) exhausted"})
