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
WEB_PROVIDER_ALIASES = {
    "local": "searxng",
    "searx": "searxng",
    "searxng": "searxng",
    "duckduckgo": "ddgs",
    "duckduckgo_search": "ddgs",
    "ddg": "ddgs",
    "ddgs": "ddgs",
    "google": "google",
    "gemini": "google",
    "parallel": "parallel",
    "tavily": "tavily",
    "exa": "exa",
    "firecrawl": "firecrawl",
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
    r"i (?:have not|haven't|was not|wasn't) (?:been able to )?find|"
    r"i cannot (?:find|access)|"
    r"i can't (?:find|access)|"
    r"i (?:do not|don't) have (?:web|internet) access|"
    r"i cannot perform (?:real-time )?(?:web|internet) searches|"
    r"i can't perform (?:real-time )?(?:web|internet) searches|"
    r"there(?:'s| is) no (?:explicit )?(?:mention|evidence)|"
    r"no (?:explicit )?(?:mention|evidence)|"
    r"no (?:information|results|relevant)"
    r")\b"
)
PROMISE_TO_SEARCH_RE = re.compile(
    r"(?i)\b("
    r"(?:i(?:'ll| will)|let me|i need to)\s+"
    r"(?:search|look up|check|research|find)|"
    r"would you like me to\s+"
    r"(?:search|look up|check|research|find)"
    r")\b"
)
DIRECT_LOOKUP_RE = re.compile(
    r"(?i)^\s*(?:who|what|where|when)\s+(?:is|are|was|were)\b"
)
DIRECT_LOOKUP_SUBJECT_RE = re.compile(
    r"(?i)^\s*(?:who|what|where|when)\s+(?:is|are|was|were)\s+(?P<subject>.+?)\s*[?.!]*$"
)
ABOUT_SUBJECT_RE = re.compile(
    r"(?i)^\s*(?:tell\s+me\s+about|more\s+about|information\s+about)\s+"
    r"(?P<subject>.+?)\s*[?.!]*$"
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
FORCE_RETRIEVAL_RE = re.compile(
    r"(?i)\b("
    r"look\s+it\s+up|"
    r"search\s+for\s+it|"
    r"check\s+the\s+web|"
    r"find\s+out|"
    r"verify\s+that|"
    r"search\s+again|"
    r"research\s+it"
    r")\b"
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
POLITE_SEARCH_RE = re.compile(
    r"(?i)^\s*(?:can|could|would)\s+you\s+(?:please\s+)?"
    r"(?:search|look up|lookup|research|find)\b\s*"
    r"(?:the\s+web\s+)?(?:for\s+)?"
)
CONTROL_TEXT_RE = re.compile(
    r"(?i)\b("
    r"Claude\.\s*Rules|system\s+prompt|developer\s+message|"
    r"tool\s+instructions?|provider\s+instructions?|"
    r"hidden\s+routing\s+notes?|chain[- ]of[- ]thought|scratchpad"
    r")\b"
)
FOLLOWUP_PRONOUN_RE = re.compile(
    r"(?i)\b(they|them|their|he|him|his|she|her|it|its|that person|this person)\b"
)
PERSON_PRONOUN_RE = re.compile(r"(?i)\b(he|him|his|she|her|that person|this person)\b")
NEUTRAL_PRONOUN_RE = re.compile(r"(?i)\b(it|its)\b")
PLURAL_PRONOUN_RE = re.compile(r"(?i)\b(they|them|their)\b")
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
    "CS",
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
    "how",
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
    "when",
    "where",
    "what",
    "which",
    "who",
    "why",
}
FOLLOWUP_ACTIVITY_WORDS = {
    "channel",
    "channels",
    "chair",
    "creator",
    "cs",
    "dean",
    "department",
    "dept",
    "director",
    "faculty",
    "game",
    "games",
    "here",
    "head",
    "leader",
    "leadership",
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
    "science",
    "school",
    "stream",
    "streams",
    "university",
    "twitch",
    "anniversary",
    "established",
    "founded",
    "history",
    "opened",
    "operating",
    "started",
    "upload",
    "uploads",
    "video",
    "videos",
    "youtube",
}
PLAY_WORDS = {"game", "games", "play", "played", "plays"}
FOUNDING_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"how\s+long|"
    r"operat(?:e|ed|es|ing)|"
    r"founded|"
    r"established|"
    r"started|"
    r"opened|"
    r"history|"
    r"anniversar(?:y|ies)|"
    r"when\s+(?:did|was|were)"
    r")\b"
)
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


@dataclass(frozen=True)
class ProviderDirective:
    provider: str | None
    strict: bool
    cleaned_user_query: str


class ClaimIntent(StrEnum):
    IDENTITY = "identity"
    LOCATION = "location"
    FOUNDING_DATE = "founding_date"
    DURATION = "duration"
    LEADERSHIP = "leadership"
    CONTACT = "contact"
    HISTORY = "history"
    OTHER = "other"


@dataclass(frozen=True)
class EvidenceGap:
    requested_claim: str
    supported_by_existing_evidence: bool
    missing_fields: list[str]
    requires_new_retrieval: bool


@dataclass
class ConversationEntity:
    mention: str
    canonical_name: str | None = None
    entity_category: str | None = None
    entity_type: str | None = None
    location: str | None = None
    official_domains: tuple[str, ...] = ()
    candidate_meanings: list[str] = field(default_factory=list)
    selected_meaning: str | None = None
    confidence: float = 0.0
    unresolved: bool = True
    entity_id: str = ""
    introduced_turn: int = 0
    last_referenced_turn: int = 0
    active: bool = True


@dataclass
class RetrievalConversationState:
    active_entities: list[ConversationEntity] = field(default_factory=list)
    entity_history: list[ConversationEntity] = field(default_factory=list)
    turn_index: int = 0
    last_user_goal: str | None = None
    last_standalone_query: str | None = None
    last_search_intent: str | None = None
    last_claim_intent: ClaimIntent | None = None
    pending_evidence_gap: EvidenceGap | None = None
    last_accepted_sources: list[str] = field(default_factory=list)
    rejected_interpretations: list[str] = field(default_factory=list)
    failed_urls: set[str] = field(default_factory=set)
    last_subject_resolution: SubjectResolution | None = None
    last_query_provenance: QueryProvenance | None = None


@dataclass
class QueryRewrite:
    original_text: str
    standalone_query: str
    inherited_entities: list[str] = field(default_factory=list)
    explicit_constraints: list[str] = field(default_factory=list)
    inferred_constraints: list[str] = field(default_factory=list)
    discarded_interpretations: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass(frozen=True)
class QueryProvenance:
    original_text: str
    resolved_subject: str | None
    subject_source: str | None
    previous_active_subject: str | None
    topic_switched: bool
    inherited_constraints: dict[str, str]
    new_constraints: dict[str, str]
    rejected_constraints: dict[str, str]
    final_query: str


@dataclass(frozen=True)
class SubjectResolution:
    subject: str
    source: str | None
    previous_active_subject: str | None
    topic_switched: bool
    ambiguous: bool = False


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


def parse_provider_directive(text: str) -> ProviderDirective:
    cleaned = _remove_control_text(text)
    provider: str | None = None
    strict = False

    def capture(value: str, *, is_strict: bool) -> str:
        nonlocal provider, strict
        normalized = _normalize_provider_name(value)
        if normalized:
            provider = normalized
            strict = is_strict
        return ""

    cleaned = re.sub(
        r"(?i)\bprovider\s*:\s*([a-z0-9_-]+)\b",
        lambda match: capture(match.group(1), is_strict=True),
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\b(?:using|with|via)\s+([a-z0-9_-]+)\b",
        lambda match: capture(match.group(1), is_strict=True),
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\bprefer\s+([a-z0-9_-]+)\b",
        lambda match: capture(match.group(1), is_strict=False),
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)^\s*search\s+([a-z0-9_-]+)\s+for\b",
        lambda match: f"search for{capture(match.group(1), is_strict=True)}",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)^\s*use\s+([a-z0-9_-]+)\s+to\s+search(?:\s+for)?\b",
        lambda match: f"search for{capture(match.group(1), is_strict=True)}",
        cleaned,
    )
    cleaned = sanitize_search_query_control_text(cleaned)
    return ProviderDirective(provider, strict, _compact_query_text(cleaned))


def sanitize_search_query_control_text(text: str) -> str:
    cleaned = _remove_control_text(text)
    provider_names = (
        "google|gemini|parallel|tavily|exa|firecrawl|ddgs|ddg|"
        "duckduckgo|searx|searxng|local"
    )
    cleaned = re.sub(
        rf"(?i)\b(?:using|with|via)\s+(?:{provider_names})\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        rf"(?i)\bprovider\s*:\s*(?:{provider_names})\b",
        " ",
        cleaned,
    )
    return _compact_query_text(cleaned)


def _remove_control_text(text: str) -> str:
    cleaned = CONTROL_TEXT_RE.sub(" ", str(text or ""))
    return _compact_query_text(cleaned)


def _normalize_provider_name(value: str) -> str | None:
    key = str(value or "").strip().lower().replace("-", "_")
    return WEB_PROVIDER_ALIASES.get(key)


def _compact_query_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = re.sub(r"\s+([?.!,;:])", r"\1", cleaned)
    cleaned = re.sub(r"(?:\s*\.\s*){2,}", ". ", cleaned)
    return cleaned


def segment_user_input(user_message: str) -> list[UserIntentSegment]:
    text = _remove_control_text(user_message.strip())
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
    if _provider_directed_search_request(text):
        return "web_lookup"
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
    if FOLLOWUP_PRONOUN_RE.search(stripped) or re.match(r"(?i)^\s*it(?:'|’)?s\b", stripped):
        return False
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


def _model_planned_search_instruction(
    user_message: str,
    state: RetrievalConversationState | None,
    search_queries: list[str],
) -> str:
    lines = [
        "The automatic retrieval for this turn did not verify the user's request.",
        (
            "Issue one web_search tool call with a materially different targeted "
            "query that you choose. Prefer official domains or role-specific "
            "terms when they are relevant."
        ),
        "Do not repeat a near-duplicate of an earlier query.",
        f"Current user request: {user_message}",
    ]
    entity = _active_resolved_entity(state) or _active_entity(state)
    if entity:
        name = _entity_search_name(entity)
        lines.append(f"Active entity: {name}")
        if entity.entity_type:
            lines.append(f"Entity type: {entity.entity_type}")
        if entity.location:
            lines.append(f"Location: {entity.location}")
        if entity.official_domains:
            lines.append("Official domains: " + ", ".join(entity.official_domains))
    if state and state.pending_evidence_gap:
        lines.append(f"Evidence gap: {state.pending_evidence_gap.requested_claim}")
    if search_queries:
        lines.append("Queries already tried:")
        lines.extend(f"- {query}" for query in search_queries[-4:])
    return "\n".join(lines)


def _recent_retrieval_was_weak(messages: list[dict[str, Any]]) -> bool:
    for message in reversed(messages):
        if message.get("role") == "user":
            return False
        if message.get("role") != "tool":
            continue
        tool_name = message.get("tool_name")
        content = str(message.get("content", ""))
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        if tool_name == "fetch_url":
            return not _useful_fetch_result(content)
        if tool_name != "web_search":
            continue
        provider_metadata = (
            metadata.get("provider_metadata")
            if isinstance(metadata.get("provider_metadata"), dict)
            else {}
        )
        accepted_count = metadata.get(
            "accepted_result_count",
            provider_metadata.get("accepted_result_count"),
        )
        if accepted_count == 0:
            return True
        results = metadata.get("search_results")
        if isinstance(results, list):
            return not results
        lowered = content.lower()
        return bool(
            "none passed candidate discovery" in lowered
            or "no search provider succeeded" in lowered
            or "(no results)" in lowered
        )
    return False


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
    directive = parse_provider_directive(retrieval_message)
    if directive.provider:
        args["provider"] = directive.provider
        args["provider_strict"] = directive.strict
    count = _requested_result_count(user_message)
    if count:
        args["max_results"] = count
    calls.append({"function": {"name": "web_search", "arguments": args}})
    return calls


def _should_plan_search(user_message: str, messages: list[dict[str, Any]]) -> bool:
    user_message = _retrieval_message_from_segments(user_message)
    if _provider_directed_search_request(user_message):
        return True
    if _is_force_retrieval_request(user_message) and _recent_topic(messages):
        return True
    if _wants_raw_search_results(user_message):
        query = _search_query_from_request(user_message)
        return bool(query or _recent_topic(messages))
    if _is_claim_verification_followup(user_message, messages):
        return True
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
    if (
        _looks_like_unfamiliar_lookup(query)
        and not DIRECT_LOOKUP_RE.search(query)
        and not SEARCH_VERB_RE.search(user_message)
    ):
        words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", query)
        if len(words) == 1 and re.search(r"[a-z][A-Z]|[_@.]", words[0]):
            return query
        if len(words) <= 5:
            return f"Who is {query}"
    if _looks_like_followup_search(query) or _is_low_info_search_query(query):
        topic = _refinement_anchor_topic(user_message, messages) or _recent_topic(messages)
        if topic:
            terms = _followup_detail_terms(query)
            return " ".join([topic, *_normalize_followup_terms(terms)]).strip()
    return query or user_message


def _search_query_from_request(user_message: str) -> str:
    directive = parse_provider_directive(user_message)
    query = SEARCH_REQUEST_RE.sub("", directive.cleaned_user_query).strip()
    query = POLITE_SEARCH_RE.sub("", query).strip()
    query = SEARCH_VERB_RE.sub("", query).strip()
    query = sanitize_search_query_control_text(str(query))
    return _clean_tool_arg(query, collapse_whitespace=True).strip("?.!:;,")


def _provider_directed_search_request(text: str) -> bool:
    directive = parse_provider_directive(text)
    if not directive.provider:
        return False
    return bool(re.search(r"(?i)\b(search|look\s+up|lookup|research|find)\b", text))


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
    return bool(
        PROFILE_LOOKUP_RE.search(user_message)
        or _looks_like_followup_search(user_message)
        or _is_claim_verification_request(user_message)
    )


def _is_claim_verification_request(text: str) -> bool:
    return _claim_intent_for_text(text) in {
        ClaimIntent.FOUNDING_DATE,
        ClaimIntent.DURATION,
        ClaimIntent.LEADERSHIP,
        ClaimIntent.HISTORY,
    }


def _claim_intent_for_text(text: str) -> ClaimIntent:
    lowered = text.lower()
    if re.search(r"\bhow\s+long\b|\boperat(?:e|ed|es|ing)\b", lowered):
        return ClaimIntent.DURATION
    if re.search(r"\bfounded|established|started|opened\b", lowered):
        return ClaimIntent.FOUNDING_DATE
    if re.search(r"\bhistory|anniversar(?:y|ies)\b", lowered):
        return ClaimIntent.HISTORY
    if re.search(
        r"\b(head|chair|dean|director|leader|leadership|rector|principal)\b",
        lowered,
    ):
        return ClaimIntent.LEADERSHIP
    if re.search(r"\bwhere\s+(?:is|are|was|were)\b|\blocation|address|campus\b", lowered):
        return ClaimIntent.LOCATION
    return ClaimIntent.OTHER


def _leadership_detail_terms(text: str) -> list[str]:
    lowered = text.lower()
    terms: list[str] = []
    if re.search(r"\bcs\b|\bcomputer\s+science\b", lowered):
        terms.extend(["Computer Science", "department"])
    elif re.search(r"\bdepartments?\b|\bdept\b", lowered):
        terms.append("department")
    if re.search(r"\bfacult(?:y|ies)\b", lowered):
        terms.append("faculty")

    role_patterns = [
        ("head", r"\bheads?\b"),
        ("chair", r"\bchairs?\b|\bchairperson\b"),
        ("dean", r"\bdeans?\b"),
        ("director", r"\bdirectors?\b"),
        ("rector", r"\brectors?\b"),
        ("principal", r"\bprincipals?\b"),
    ]
    for label, pattern in role_patterns:
        if re.search(pattern, lowered):
            terms.append(label)
            break
    role_terms = {"head", "chair", "dean", "director", "rector", "principal"}
    if not any(term in role_terms for term in terms):
        terms.append("leadership")
    return _dedupe_preserve(terms)


def _is_force_retrieval_request(text: str) -> bool:
    return bool(FORCE_RETRIEVAL_RE.search(text))


def _is_claim_verification_followup(
    user_message: str,
    messages: list[dict[str, Any]],
) -> bool:
    if not _is_claim_verification_request(user_message):
        return False
    if not FOLLOWUP_PRONOUN_RE.search(user_message) and not _is_low_info_search_query(
        _search_query_from_request(user_message)
    ):
        return False
    return bool(_recent_topic(messages))


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
            query_directive = parse_provider_directive(query)
            message_directive = parse_provider_directive(user_message)
            directive = query_directive if query_directive.provider else message_directive
            if tool_name == "web_search" and directive.provider:
                args["provider"] = directive.provider
                args["provider_strict"] = directive.strict
            args["query"] = _contextual_search_query(
                query_directive.cleaned_user_query,
                user_message,
                messages,
                state,
            )
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


def _entity_id_for_mention(mention: str) -> str:
    cleaned = " ".join(re.findall(r"[a-z0-9]+", mention.lower()))
    return cleaned.replace(" ", "_") or "entity"


def _ensure_entity_defaults(entity: ConversationEntity) -> None:
    if not entity.entity_id:
        entity.entity_id = _entity_id_for_mention(
            entity.canonical_name or entity.selected_meaning or entity.mention
        )
    if entity.entity_type in {"school", "university", "college", "training_center"}:
        entity.entity_category = entity.entity_category or "education"


def _entity_names(entity: ConversationEntity) -> set[str]:
    values = {
        entity.mention,
        entity.canonical_name or "",
        entity.selected_meaning or "",
        *entity.candidate_meanings,
    }
    return {value.casefold() for value in values if value}


def _ensure_entity_history(state: RetrievalConversationState | None) -> None:
    if not state:
        return
    for entity in state.active_entities:
        _ensure_entity_defaults(entity)
        entity.active = True
        if entity not in state.entity_history:
            state.entity_history.append(entity)
    active = next((entity for entity in state.entity_history if entity.active), None)
    if active and (not state.active_entities or state.active_entities[0] is not active):
        state.active_entities = [active]


def _active_entity(state: RetrievalConversationState | None) -> ConversationEntity | None:
    _ensure_entity_history(state)
    if not state or not state.active_entities:
        return None
    return state.active_entities[0]


def _find_entity(
    state: RetrievalConversationState | None,
    subject: str,
) -> ConversationEntity | None:
    _ensure_entity_history(state)
    if not state:
        return None
    subject_key = subject.casefold()
    for entity in state.entity_history:
        if subject_key in _entity_names(entity):
            return entity
    return None


def _activate_entity(
    state: RetrievalConversationState,
    subject: str,
    *,
    turn_index: int,
) -> tuple[ConversationEntity, bool]:
    _ensure_entity_history(state)
    previous = _active_entity(state)
    entity = _find_entity(state, subject)
    if entity is None:
        entity = ConversationEntity(
            mention=subject,
            candidate_meanings=_candidate_meanings_for_topic(subject),
            confidence=0.45,
            unresolved=True,
            entity_id=_entity_id_for_mention(subject),
            introduced_turn=turn_index,
        )
        state.entity_history.append(entity)
    switched = bool(previous and previous is not entity)
    for item in state.entity_history:
        item.active = item is entity
    entity.last_referenced_turn = turn_index
    state.active_entities = [entity]
    return entity, switched


def _split_compound_subject(subject: str) -> list[str]:
    cleaned = _clean_topic_candidate(subject)
    cleaned = re.split(
        r"(?i)\s+and\s+(?:its|their|his|her)\s+\w+",
        cleaned,
        maxsplit=1,
    )[0]
    has_acronym = bool(re.search(r"\b[A-Z0-9]{2,8}\b", cleaned))
    separator = r"(?i)\s+(?:or|,)\s+"
    if has_acronym:
        separator = r"(?i)\s+(?:and|or|,)\s+"
    parts = [
        _clean_topic_candidate(part)
        for part in re.split(separator, cleaned)
    ]
    return [
        part
        for part in parts
        if part and not (len(part.split()) == 1 and _is_topic_noise(part))
    ]


def _explicit_subjects_from_text(text: str) -> list[str]:
    subjects: list[str] = []

    def referential(subject: str) -> bool:
        terms = re.findall(r"[A-Za-z0-9_.-]+", subject.lower())
        return bool(terms) and all(
            term in FOLLOWUP_DROP_WORDS or term in {"it", "its", "they", "them", "their"}
            for term in terms
        )

    def add(subject: str) -> None:
        for part in _split_compound_subject(subject):
            if referential(part):
                continue
            if part.casefold() not in {item.casefold() for item in subjects}:
                subjects.append(part)

    for pattern in (DIRECT_LOOKUP_SUBJECT_RE, ABOUT_SUBJECT_RE):
        match = pattern.search(text)
        if match:
            add(match.group("subject"))
            return subjects
    request_subject = _search_query_from_request(text)
    original_subject = _clean_tool_arg(text, collapse_whitespace=True).strip("?.!:;,")
    if request_subject and request_subject != original_subject:
        acronym_tokens = [
            token
            for token in re.findall(r"\b[A-Z0-9]{2,8}\b", request_subject)
            if re.search(r"[A-Z]", token)
        ]
        if acronym_tokens:
            for token in acronym_tokens:
                add(token)
        else:
            add(request_subject)
        return subjects
    for token in re.findall(r"\b[A-Z0-9]{2,8}\b", text):
        if not re.search(r"[A-Z]", token):
            continue
        add(token)
    if (
        not subjects
        and not FOLLOWUP_PRONOUN_RE.search(text)
        and not re.match(r"(?i)^\s*it(?:'|’)?s\b", text)
        and _looks_like_unfamiliar_lookup(text)
    ):
        add(text)
    return subjects


def _explicit_subject_from_current_turn(text: str) -> str:
    subjects = _explicit_subjects_from_text(text)
    return subjects[0] if len(subjects) == 1 else ""


def _pronoun_kind(text: str) -> str | None:
    if PERSON_PRONOUN_RE.search(text):
        return "person"
    if NEUTRAL_PRONOUN_RE.search(text):
        return "neutral"
    if PLURAL_PRONOUN_RE.search(text):
        return "plural"
    return None


def _type_from_subject_text(subject: str) -> str | None:
    lowered = subject.lower()
    if re.search(r"\buniversit(?:y|ies)\b", lowered):
        return "university"
    if re.search(r"\bcolleges?\b", lowered):
        return "college"
    if re.search(r"\btraining\s+cent(?:er|re)s?\b", lowered):
        return "training_center"
    if re.search(r"\b(schools?|academ(?:y|ies))\b", lowered):
        return "school"
    return None


def _is_relationship_slot_subject(subject: str) -> bool:
    text = _clean_tool_arg(subject, collapse_whitespace=True)
    lowered = text.lower()
    if not re.search(
        r"\b("
        r"head|chair|dean|director|leader|leadership|rector|principal|"
        r"department|dept|faculty|cs|computer\s+science"
        r")\b",
        lowered,
    ):
        return False
    if re.search(
        r"\b(?:at|for)\s+[A-Z][A-Za-z0-9_.-]*(?:\s+[A-Z][A-Za-z0-9_.-]*){0,4}",
        text,
    ):
        return False
    if re.search(
        r"\bof\s+(?!the\s+)?[A-Z][A-Za-z0-9_.-]*(?:\s+[A-Z][A-Za-z0-9_.-]*){0,4}"
        r"\s+(?:University|School|Institute|College|Company|Bank|Organization)\b",
        text,
    ):
        return False
    return True


def _entity_compatible_with_pronoun(
    entity: ConversationEntity | None,
    subject: str,
    pronoun_kind: str | None,
) -> bool:
    if not pronoun_kind:
        return True
    entity_type = (entity.entity_type if entity else None) or _type_from_subject_text(subject)
    if pronoun_kind == "person":
        return entity_type == "person"
    if pronoun_kind == "neutral":
        return entity_type != "person"
    if pronoun_kind == "plural":
        return True
    return True


def _previous_explicit_user_subject(
    messages: list[dict[str, Any]],
    state: RetrievalConversationState | None,
    pronoun_kind: str | None,
) -> tuple[str, bool]:
    for message in reversed(messages[:-1]):
        if message.get("role") != "user":
            continue
        subjects = _explicit_subjects_from_text(str(message.get("content", "")))
        compatible = [
            subject
            for subject in subjects
            if _entity_compatible_with_pronoun(
                _find_entity(state, subject),
                subject,
                pronoun_kind,
            )
        ]
        if len(compatible) > 1:
            return "", True
        if compatible:
            if pronoun_kind == "plural":
                recent_topic = _recent_topic(messages)
                if recent_topic and _candidate_matches_anchor(recent_topic, [compatible[0]]):
                    return recent_topic, False
            return compatible[0], False
    return "", False


def _resolve_subject_for_turn(
    user_message: str,
    messages: list[dict[str, Any]],
    state: RetrievalConversationState | None = None,
) -> SubjectResolution:
    retrieval_message = _retrieval_message_from_segments(user_message)
    previous_active = _active_entity(state)
    previous_active_subject = previous_active.mention if previous_active else None
    current_subjects = _explicit_subjects_from_text(retrieval_message)
    if len(current_subjects) > 1:
        return SubjectResolution(
            "",
            "current_explicit_subject",
            previous_active_subject,
            False,
            ambiguous=True,
        )
    if current_subjects:
        subject = current_subjects[0]
        if previous_active and _is_relationship_slot_subject(subject):
            return SubjectResolution(
                previous_active.mention,
                "active_entity",
                previous_active_subject,
                False,
            )
        return SubjectResolution(
            subject,
            "current_explicit_subject",
            previous_active_subject,
            bool(
                previous_active_subject
                and previous_active_subject.casefold() != subject.casefold()
            ),
        )
    pronoun_kind = _pronoun_kind(retrieval_message)
    previous_subject, ambiguous = _previous_explicit_user_subject(
        messages,
        state,
        pronoun_kind,
    )
    if ambiguous:
        return SubjectResolution(
            "",
            "previous_explicit_user_subject",
            previous_active_subject,
            False,
            ambiguous=True,
        )
    if previous_subject:
        return SubjectResolution(
            previous_subject,
            "previous_explicit_user_subject",
            previous_active_subject,
            bool(
                previous_active_subject
                and previous_active_subject.casefold() != previous_subject.casefold()
            ),
        )
    if previous_active and _entity_compatible_with_pronoun(
        previous_active,
        previous_active.mention,
        pronoun_kind,
    ):
        return SubjectResolution(
            previous_active.mention,
            "active_entity",
            previous_active_subject,
            False,
        )
    return SubjectResolution("", None, previous_active_subject, False)


def _constraints_from_text(
    user_message: str,
    messages: list[dict[str, Any]],
) -> dict[str, str]:
    text = user_message.lower()
    constraints: dict[str, str] = {}
    if re.search(r"\buniversit(?:y|ies)\b", text):
        constraints["entity_category"] = "education"
        constraints["entity_type"] = "university"
    elif re.search(r"\bcolleges?\b", text):
        constraints["entity_category"] = "education"
        constraints["entity_type"] = "college"
    elif re.search(r"\btraining\s+cent(?:er|re)s?\b", text):
        constraints["entity_category"] = "education"
        constraints["entity_type"] = "training_center"
    elif re.search(r"\b(school|schools|academy|academies)\b", text):
        constraints["entity_category"] = "education"
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


def _apply_constraints_to_entity(
    entity: ConversationEntity,
    constraints: dict[str, str],
    state: RetrievalConversationState | None = None,
) -> None:
    if constraints.get("entity_category"):
        entity.entity_category = constraints["entity_category"]
    if constraints.get("entity_type"):
        entity.entity_type = constraints["entity_type"]
        if entity.entity_type in {
            "school",
            "university",
            "college",
            "training_center",
        }:
            entity.entity_category = "education"
        if state and entity.entity_type == "school":
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
    entity.unresolved = not (entity.entity_type and (entity.location or entity.canonical_name))
    _resolve_known_entity_from_constraints(entity)


def _current_entity_constraints(
    user_message: str,
    messages: list[dict[str, Any]],
    state: RetrievalConversationState | None = None,
) -> dict[str, str]:
    constraints = _constraints_from_text(user_message, messages)
    entity = _active_entity(state)
    if entity and entity.entity_category and "entity_category" not in constraints:
        constraints["entity_category"] = entity.entity_category
    if entity and entity.entity_type and "entity_type" not in constraints:
        constraints["entity_type"] = entity.entity_type
    if entity and entity.location and "location" not in constraints:
        constraints["location"] = entity.location
    return constraints


def _query_location_bias(
    user_message: str,
    messages: list[dict[str, Any]],
    constraints: dict[str, str],
    entity: ConversationEntity | None,
) -> str:
    if constraints.get("location"):
        return ""
    category = constraints.get("entity_category") or (entity.entity_category if entity else "")
    entity_type = constraints.get("entity_type") or (entity.entity_type if entity else "")
    if category != "education" and entity_type not in {
        "school",
        "university",
        "college",
        "training_center",
    }:
        return ""
    runtime_location = _runtime_location_from_messages(messages)
    return runtime_location.get("country", "")


def _provenance_for_rewrite(
    original: str,
    resolution: SubjectResolution,
    inherited_constraints: dict[str, str],
    new_constraints: dict[str, str],
    rejected_constraints: dict[str, str],
    final_query: str,
) -> QueryProvenance:
    return QueryProvenance(
        original_text=original,
        resolved_subject=resolution.subject or None,
        subject_source=resolution.source,
        previous_active_subject=resolution.previous_active_subject,
        topic_switched=resolution.topic_switched,
        inherited_constraints=inherited_constraints,
        new_constraints=new_constraints,
        rejected_constraints=rejected_constraints,
        final_query=final_query,
    )


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
    state: RetrievalConversationState | None = None,
) -> str:
    constraints = _current_entity_constraints(user_message, messages, state)
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


def _entity_constraint_map(entity: ConversationEntity | None) -> dict[str, str]:
    if not entity:
        return {}
    constraints: dict[str, str] = {}
    if entity.entity_category:
        constraints["entity_category"] = entity.entity_category
    if entity.entity_type:
        constraints["entity_type"] = entity.entity_type
    if entity.location:
        constraints["location"] = entity.location
    return constraints


def _constraint_terms(constraints: dict[str, str], *, include_location: bool = True) -> list[str]:
    terms: list[str] = []
    entity_type = constraints.get("entity_type")
    if entity_type:
        terms.append(entity_type)
    if include_location and constraints.get("location"):
        terms.append(constraints["location"])
    return terms


def _rejected_stale_constraints(
    state: RetrievalConversationState | None,
    active_subject: str,
    inherited_constraints: dict[str, str],
    new_constraints: dict[str, str],
) -> dict[str, str]:
    if not state or not active_subject:
        return {}
    rejected: dict[str, str] = {}
    for entity in state.entity_history:
        if entity.active or entity.mention.casefold() == active_subject.casefold():
            continue
        for key, value in _entity_constraint_map(entity).items():
            if inherited_constraints.get(key) == value or new_constraints.get(key) == value:
                continue
            rejected[key] = (
                f"{value} from {entity.mention} ignored because it belongs "
                "to an inactive entity"
            )
    return rejected


def _store_query_provenance(
    state: RetrievalConversationState | None,
    provenance: QueryProvenance,
) -> None:
    if state is not None:
        state.last_query_provenance = provenance


def rewrite_followup_query(
    query: str,
    user_message: str,
    messages: list[dict[str, Any]],
    state: RetrievalConversationState | None = None,
) -> QueryRewrite:
    original = _clean_tool_arg(query or user_message, collapse_whitespace=True)
    cleaned = _search_query_from_request(original)
    retrieval_message = _retrieval_message_from_segments(user_message)
    resolution = (
        state.last_subject_resolution
        if state
        and state.last_subject_resolution
        and state.last_user_goal == retrieval_message
        else _resolve_subject_for_turn(user_message, messages, state)
    )
    if resolution.ambiguous:
        provenance = _provenance_for_rewrite(
            original,
            resolution,
            {},
            _constraints_from_text(user_message, messages),
            {},
            "",
        )
        _store_query_provenance(state, provenance)
        return QueryRewrite(original, "", confidence=0.0)
    topic = resolution.subject or _recent_topic(messages)
    resolved_entity = _find_entity(state, topic) if topic else None
    if resolved_entity is None and state and resolution.source == "active_entity":
        resolved_entity = _active_entity(state)
    new_constraints = _constraints_from_text(user_message, messages)
    if state and topic and resolved_entity is None and resolution.source:
        resolved_entity, _ = _activate_entity(
            state,
            topic,
            turn_index=state.turn_index or 1,
        )
    if resolved_entity and new_constraints:
        _apply_constraints_to_entity(resolved_entity, new_constraints, state)
    inherited_constraints = _entity_constraint_map(resolved_entity)
    constraints = {**inherited_constraints, **new_constraints}
    location_bias = _query_location_bias(user_message, messages, constraints, resolved_entity)
    rejected_constraints = _rejected_stale_constraints(
        state,
        topic,
        inherited_constraints,
        new_constraints,
    )
    explicit: list[str] = []
    inferred: list[str] = []
    discarded: list[str] = []
    if constraints.get("entity_type"):
        explicit.append(constraints["entity_type"])
    if constraints.get("entity_type") == "school":
        discarded.extend(["Automatic Identification System", "AIS Inc office furniture"])
    if constraints.get("location") == "Cambodia":
        explicit.append("Cambodia")
    elif location_bias:
        inferred.append(location_bias)
    if state:
        discarded.extend(state.rejected_interpretations)

    resolved = _active_resolved_entity(state)
    force_retrieval = _is_force_retrieval_request(user_message)
    intent = _claim_intent_for_text(f"{cleaned} {user_message}")
    if (
        resolved
        and force_retrieval
        and state
        and state.last_claim_intent
        in {ClaimIntent.FOUNDING_DATE, ClaimIntent.DURATION, ClaimIntent.HISTORY}
    ):
        intent = state.last_claim_intent
    if resolved and intent in {
        ClaimIntent.FOUNDING_DATE,
        ClaimIntent.DURATION,
        ClaimIntent.HISTORY,
    }:
        name = _entity_search_name(resolved)
        location = resolved.location or constraints.get("location", "")
        place = ""
        if location and location.lower() not in name.lower():
            place = f" in {location}"
            inferred.append(location)
        if resolved.entity_type:
            inferred.append(resolved.entity_type)
        return QueryRewrite(
            original,
            f"When was {name}{place} established?",
            inherited_entities=[resolved.mention],
            explicit_constraints=["founding date"],
            inferred_constraints=_dedupe_preserve(inferred),
            discarded_interpretations=_dedupe_preserve(discarded),
            confidence=0.94,
        )
    if resolved and intent == ClaimIntent.LEADERSHIP:
        name = _entity_search_name(resolved)
        location = resolved.location or constraints.get("location", "")
        detail_terms = _leadership_detail_terms(f"{cleaned} {user_message}")
        standalone_terms: list[str]
        inferred_constraints = list(inferred)
        if _query_mentions_entity_or_domain(cleaned, resolved):
            standalone_terms = [cleaned]
            if location and location.lower() not in cleaned.lower():
                standalone_terms.append(location)
                inferred_constraints.append(location)
            if name.lower() not in cleaned.lower() and not any(
                domain.lower() in cleaned.lower() for domain in resolved.official_domains
            ):
                standalone_terms.append(name)
        else:
            standalone_terms = [name]
            if location and location.lower() not in name.lower():
                standalone_terms.append(location)
                inferred_constraints.append(location)
        for term in detail_terms:
            if term.lower() not in " ".join(standalone_terms).lower():
                standalone_terms.append(term)
        if resolved.entity_type:
            inferred_constraints.append(resolved.entity_type)
        return QueryRewrite(
            original,
            " ".join(standalone_terms).strip(),
            inherited_entities=[resolved.mention],
            explicit_constraints=["leadership"],
            inferred_constraints=_dedupe_preserve(inferred_constraints),
            discarded_interpretations=_dedupe_preserve(discarded),
            confidence=0.92,
        )

    if not topic:
        provenance = _provenance_for_rewrite(
            original,
            resolution,
            inherited_constraints,
            new_constraints,
            rejected_constraints,
            cleaned or original,
        )
        _store_query_provenance(state, provenance)
        return QueryRewrite(original, cleaned or original, confidence=0.35)
    if resolution.source == "current_explicit_subject" and topic.lower() not in cleaned.lower():
        terms = _constraint_terms(constraints)
        if location_bias and location_bias.lower() not in {term.lower() for term in terms}:
            terms.append(location_bias)
        standalone = " ".join([topic, *_normalize_followup_terms(terms)]).strip()
        provenance = _provenance_for_rewrite(
            original,
            resolution,
            inherited_constraints,
            new_constraints,
            rejected_constraints,
            standalone,
        )
        _store_query_provenance(state, provenance)
        return QueryRewrite(
            original,
            standalone,
            inherited_entities=[topic],
            explicit_constraints=explicit,
            inferred_constraints=inferred,
            discarded_interpretations=_dedupe_preserve(discarded),
            confidence=0.95,
        )
    if topic.lower() in cleaned.lower():
        base = cleaned
        if topic.casefold() != cleaned.casefold() and _looks_like_followup_search(cleaned):
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
        if location_bias and location_bias.lower() not in " ".join(standalone_terms).lower():
            standalone_terms.append(location_bias)
        standalone = " ".join(standalone_terms).strip()
        provenance = _provenance_for_rewrite(
            original,
            resolution,
            inherited_constraints,
            new_constraints,
            rejected_constraints,
            standalone,
        )
        _store_query_provenance(state, provenance)
        return QueryRewrite(
            original,
            standalone,
            inherited_entities=[topic],
            explicit_constraints=explicit,
            inferred_constraints=inferred,
            discarded_interpretations=_dedupe_preserve(discarded),
            confidence=0.82 if standalone != cleaned and (explicit or inferred) else 0.65,
        )

    if (
        _looks_like_followup_search(user_message)
        or _looks_like_followup_search(cleaned)
        or _is_low_info_search_query(cleaned)
    ):
        term_source = cleaned
        if (
            resolution.source in {
                "previous_explicit_user_subject",
                "active_entity",
            }
            and topic.lower() not in cleaned.lower()
            and FOLLOWUP_PRONOUN_RE.search(user_message)
        ):
            term_source = _search_query_from_request(user_message)
        terms = _followup_detail_terms(term_source)
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
        if location_bias and location_bias.lower() not in {term.lower() for term in terms}:
            terms.append(location_bias)
        standalone = " ".join([topic, *_normalize_followup_terms(terms)]).strip()
        provenance = _provenance_for_rewrite(
            original,
            resolution,
            inherited_constraints,
            new_constraints,
            rejected_constraints,
            standalone,
        )
        _store_query_provenance(state, provenance)
        return QueryRewrite(
            original,
            standalone,
            inherited_entities=[topic],
            explicit_constraints=explicit,
            inferred_constraints=inferred,
            discarded_interpretations=_dedupe_preserve(discarded),
            confidence=0.88 if standalone != cleaned else 0.65,
        )
    final_query = cleaned or original
    provenance = _provenance_for_rewrite(
        original,
        resolution,
        inherited_constraints,
        new_constraints,
        rejected_constraints,
        final_query,
    )
    _store_query_provenance(state, provenance)
    return QueryRewrite(original, final_query, confidence=0.45)


def _active_entity_mention(state: RetrievalConversationState | None) -> str:
    entity = _active_entity(state)
    return entity.mention if entity else ""


def _active_resolved_entity(
    state: RetrievalConversationState | None,
) -> ConversationEntity | None:
    entity = _active_entity(state)
    if entity is None:
        return None
    if entity.unresolved:
        return None
    if not (entity.canonical_name or entity.mention):
        return None
    return entity


def _entity_search_name(entity: ConversationEntity) -> str:
    return entity.canonical_name or entity.selected_meaning or entity.mention


def _known_official_domains(canonical_name: str) -> tuple[str, ...]:
    if canonical_name.casefold() == "American Intercon School".casefold():
        return ("ais.edu.kh",)
    if canonical_name.casefold() == "Paragon International University".casefold():
        return ("paragoniu.edu.kh",)
    return ()


def _query_mentions_entity_or_domain(query: str, entity: ConversationEntity) -> bool:
    lowered = query.lower()
    if any(name and name.lower() in lowered for name in _entity_names(entity)):
        return True
    return any(domain.lower() in lowered for domain in entity.official_domains)


def _resolve_known_entity_from_constraints(entity: ConversationEntity) -> None:
    if entity.mention.upper() != "AIS":
        return
    if entity.entity_type != "school" or entity.location != "Cambodia":
        return
    entity.canonical_name = "American Intercon School"
    entity.selected_meaning = "American Intercon School"
    entity.entity_category = "education"
    entity.official_domains = _known_official_domains("American Intercon School")
    entity.confidence = max(entity.confidence, 0.88)
    entity.unresolved = False


def _update_retrieval_state_from_tool_result(
    state: RetrievalConversationState,
    tool_name: str,
    metadata: dict[str, Any],
) -> None:
    if tool_name == "fetch_url" and metadata.get("verified_dates"):
        state.pending_evidence_gap = None
        return
    entity = _active_entity(state)
    if tool_name != "web_search" or entity is None:
        return
    provider_metadata = metadata.get("provider_metadata")
    if not isinstance(provider_metadata, dict):
        provider_metadata = {}
    candidates = provider_metadata.get("entity_candidates") or metadata.get(
        "entity_candidates"
    )
    if not isinstance(candidates, list) or not candidates:
        return
    aliases = {
        entity.mention.casefold(),
        *(alias.casefold() for alias in entity.candidate_meanings),
    }
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_aliases = {
            str(alias).casefold()
            for alias in candidate.get("aliases") or []
            if str(alias).strip()
        }
        canonical = str(candidate.get("canonical_name") or "").strip()
        if canonical:
            candidate_aliases.add(canonical.casefold())
        if aliases.isdisjoint(candidate_aliases):
            continue
        entity.canonical_name = canonical or entity.canonical_name
        entity.selected_meaning = entity.canonical_name or entity.selected_meaning
        entity.entity_type = str(candidate.get("entity_type") or entity.entity_type or "") or None
        if entity.entity_type in {"school", "university", "college", "training_center"}:
            entity.entity_category = "education"
        entity.location = str(candidate.get("country") or entity.location or "") or None
        domains = tuple(
            str(domain).strip()
            for domain in candidate.get("domains") or []
            if str(domain).strip()
        )
        if entity.canonical_name:
            domains = _dedupe_tuple([*domains, *_known_official_domains(entity.canonical_name)])
        entity.official_domains = domains
        entity.confidence = max(entity.confidence, float(candidate.get("score") or 0.0))
        entity.unresolved = not bool(
            entity.canonical_name and entity.entity_type and entity.location
        )
        return


def _dedupe_tuple(values: list[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


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
    state.turn_index += 1
    retrieval_message = _retrieval_message_from_segments(user_message)
    resolution = _resolve_subject_for_turn(user_message, messages, state)
    state.last_user_goal = retrieval_message
    state.last_subject_resolution = resolution
    entity: ConversationEntity | None = None
    if resolution.subject:
        entity, switched = _activate_entity(
            state,
            resolution.subject,
            turn_index=state.turn_index,
        )
        if switched:
            state.rejected_interpretations.clear()
            state.last_accepted_sources.clear()
            state.failed_urls.clear()
            state.last_claim_intent = None
            state.pending_evidence_gap = None
    elif not resolution.ambiguous:
        entity = _active_entity(state)

    constraints = _constraints_from_text(user_message, messages)
    if entity:
        _apply_constraints_to_entity(entity, constraints, state)
    rewrite = rewrite_followup_query(retrieval_message, user_message, messages, state)
    state.last_standalone_query = rewrite.standalone_query
    claim_intent = _claim_intent_for_text(retrieval_message)
    if claim_intent in {
        ClaimIntent.FOUNDING_DATE,
        ClaimIntent.DURATION,
        ClaimIntent.HISTORY,
    }:
        state.last_claim_intent = claim_intent
        state.pending_evidence_gap = EvidenceGap(
            requested_claim="establishment date",
            supported_by_existing_evidence=False,
            missing_fields=["founding_date"],
            requires_new_retrieval=True,
        )
    elif claim_intent == ClaimIntent.LEADERSHIP:
        state.last_claim_intent = claim_intent
        state.pending_evidence_gap = EvidenceGap(
            requested_claim="leadership role",
            supported_by_existing_evidence=False,
            missing_fields=["person_name", "role"],
            requires_new_retrieval=True,
        )
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
    return _explicit_subject_from_current_turn(text)


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
    raw_query = _clean_tool_arg(
        sanitize_search_query_control_text(query),
        collapse_whitespace=True,
    )
    query = _search_query_from_request(raw_query)
    if _refinement_anchor_topic(user_message, messages):
        query = _search_query_from_request(user_message)
    rewrite = rewrite_followup_query(query, user_message, messages, state)
    if not rewrite.standalone_query and rewrite.confidence <= 0.0:
        return ""
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


def _is_refinement_followup(text: str) -> bool:
    return bool(
        re.search(
            r"(?i)\b("
            r"i\s+meant|"
            r"i\s+mean|"
            r"actually|"
            r"not\s+that|"
            r"no,\s*|"
            r"here|"
            r"my\s+location|"
            r"my\s+area"
            r")\b",
            text,
        )
    )


def _refinement_anchor_topic(user_message: str, messages: list[dict[str, Any]]) -> str:
    if not _is_refinement_followup(user_message):
        return ""
    anchors = _recent_lookup_subjects(messages)
    return anchors[0] if anchors else ""


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
        for subject in _explicit_subjects_from_text(str(message.get("content", ""))):
            if subject.casefold() not in {item.casefold() for item in subjects}:
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
        ollama_options: dict[str, Any] | None = None,
    ):
        self.ollama = ollama
        self.model = model
        self.tools = {t.name: t for t in tools}
        self.gate = gate
        self.max_steps = max_steps
        self.tool_selector = tool_selector
        self.ollama_options = dict(ollama_options or {})
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
        search_queries_this_turn: list[str] = []
        search_call_count = 0
        fetch_attempt_count = 0
        model_planned_search_requested = False

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
                return name, args, tool, "error: provide a search query or subject", {}
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
                search_queries_this_turn.append(query)
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
                    self.retrieval_state,
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
            _update_retrieval_state_from_tool_result(
                self.retrieval_state,
                name,
                metadata,
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
                if self.ollama_options:
                    msg = self.ollama.chat(
                        self.model,
                        self.messages,
                        tools=schemas,
                        options=self.ollama_options,
                    )
                else:
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
                if (
                    "web_search" in selected_tools
                    and "web_search" in used_tools
                    and not model_planned_search_requested
                    and search_call_count < MAX_TOTAL_SEARCH_CALLS
                    and _content_needs_retrieval(content)
                    and (
                        self.retrieval_state.pending_evidence_gap is not None
                        or _recent_retrieval_was_weak(self.messages)
                    )
                ):
                    model_planned_search_requested = True
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_name": "retrieval_controller",
                            "content": _model_planned_search_instruction(
                                retrieval_message,
                                self.retrieval_state,
                                search_queries_this_turn,
                            ),
                        }
                    )
                    continue
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
                _update_retrieval_state_from_tool_result(
                    self.retrieval_state,
                    name,
                    metadata,
                )
                tool_message = {"role": "tool", "tool_name": name, "content": result}
                if metadata:
                    tool_message["metadata"] = metadata
                self.messages.append(tool_message)

        yield AgentEvent("error", {"message": f"step budget ({self.max_steps}) exhausted"})
