"""Isolated tool-interface experiments; never change persisted tool identities."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any
from weakref import WeakKeyDictionary

from .agent import Agent, Tool
from .knowledge_tool_contract import KNOWLEDGE_TOOL_DESCRIPTION, knowledge_tool_parameters
from .model_runtime import ModelRuntime

KNOWLEDGE_INTERFACES = ("current", "baseline", "description", "schema", "name")
_CANONICAL = "query_knowledge"
_CANDIDATE = "search_local_knowledge"
_ORIGINAL_TOOLS: WeakKeyDictionary[Agent, Tool] = WeakKeyDictionary()


class _NameExperimentRuntime:
    """Translate only this experiment's wire name; dispatch/audits stay canonical."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.backend = str(getattr(runtime, "backend", "ollama"))

    @property
    def last_chat_metadata(self) -> dict[str, Any]:
        return self.runtime.last_chat_metadata

    def cancel_active(self) -> bool:
        return self.runtime.cancel_active()

    def fork_for_child(self) -> ModelRuntime:
        return _NameExperimentRuntime(self.runtime.fork_for_child())

    def __getattr__(self, name: str) -> Any:
        return getattr(self.runtime, name)

    @staticmethod
    def _message(message: dict[str, Any], *, outgoing: bool) -> dict[str, Any]:
        result = deepcopy(message)
        source, target = (_CANONICAL, _CANDIDATE) if outgoing else (_CANDIDATE, _CANONICAL)
        if result.get("tool_name") == source:
            result["tool_name"] = target
        for call in result.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function", {})
            if isinstance(function, dict) and function.get("name") == source:
                function["name"] = target
        return result

    @classmethod
    def _request(cls, messages: list[dict[str, Any]], kwargs: dict[str, Any]):
        options = deepcopy(kwargs)
        for schema in options.get("tools") or []:
            if schema.get("function", {}).get("name") == _CANONICAL:
                schema["function"]["name"] = _CANDIDATE
        outgoing = [cls._message(message, outgoing=True) for message in messages]
        # Keep user text and evidence byte-for-byte intact. Explain the mapping
        # separately instead of substituting names in arbitrary message content.
        if any(
            schema.get("function", {}).get("name") == _CANDIDATE
            for schema in options.get("tools") or []
        ):
            outgoing.insert(
                0,
                {
                    "role": "system",
                    "content": (
                        "Evaluation tool interface: the internal query_knowledge identifier "
                        "is exposed in this request as search_local_knowledge. References "
                        "to query_knowledge in configuration or conversation refer to that "
                        "same tool. Use the name in the supplied tool schema when calling it."
                    ),
                },
            )
        return outgoing, options

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> dict[str, Any]:
        outgoing, request_options = self._request(
            messages,
            {"tools": tools, "options": options, "think": think},
        )
        return self._message(self.runtime.chat(model, outgoing, **request_options), outgoing=False)

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ):
        kwargs: dict[str, Any] = {"options": options, "think": think}
        if tools is not None:
            kwargs["tools"] = tools
        outgoing, request_options = self._request(messages, kwargs)
        for fragment in self.runtime.chat_stream(model, outgoing, **request_options):
            yield self._message(fragment, outgoing=False)


def configure_knowledge_interface(agent: Agent, variant: str) -> None:
    """Configure one private evaluation agent, keeping canonical policy and routing."""
    if variant not in KNOWLEDGE_INTERFACES:
        raise ValueError("Unknown knowledge interface experiment")
    runtime = agent.ollama
    if isinstance(runtime, _NameExperimentRuntime):
        runtime = runtime.runtime
    # Cloud runtimes carry provider-specific continuation items and signed
    # state. Translating only common tool_calls there would corrupt replay.
    if variant == "name" and getattr(runtime, "backend", "ollama") != "ollama":
        raise ValueError("The name experiment currently supports only Ollama")
    tool = _ORIGINAL_TOOLS.setdefault(agent, agent.tools[_CANONICAL])
    if isinstance(agent.ollama, _NameExperimentRuntime):
        adapter = agent.ollama
        agent.ollama = runtime
        if agent.runtime is adapter:
            agent.runtime = runtime
    if variant == "current":
        agent.tools[_CANONICAL] = tool
        return
    description = (
        "Search learned local documentation when it is relevant to the request."
        if variant == "baseline"
        else KNOWLEDGE_TOOL_DESCRIPTION
    )
    parameters = (
        {
            "type": "object",
            "properties": {
                key: {"type": "string"} for key in ("question", "query", "library", "collection")
            },
            "required": [],
        }
        if variant in {"baseline", "description"}
        else knowledge_tool_parameters()
    )
    agent.tools[_CANONICAL] = replace(tool, description=description, parameters=parameters)
    if variant == "name":
        runtime = _NameExperimentRuntime(agent.ollama)
        agent.ollama = runtime
        agent.runtime = runtime
