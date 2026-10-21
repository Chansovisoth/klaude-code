"""Typed embedded entrypoints for the existing durable Research workflow."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from klaude_core.research import execute_research_request


@dataclass(frozen=True)
class ResearchCreate:
    question: str
    model: str
    format: str
    settings: dict[str, Any] = field(repr=False)
    session: str = ""

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> ResearchCreate:
        if request.get("kind") != "research_control" or request.get("operation") != "create":
            raise ValueError("Invalid Research create action")
        draft = request.get("draft")
        settings = request.get("settings")
        session = request.get("session", "")
        if (
            not isinstance(draft, dict)
            or not {"question", "model", "format"} <= set(draft)
            or set(draft) - {"question", "model", "format", "queued"}
            or not all(
                isinstance(draft[key], str) for key in ("question", "model", "format")
            )
            or ("queued" in draft and type(draft["queued"]) is not bool)
            or not isinstance(settings, dict)
            or not isinstance(session, str)
        ):
            raise ValueError("Invalid Research create action")
        return cls(draft["question"], draft["model"], draft["format"], settings, session)

    def worker_fields(self) -> dict[str, Any]:
        return {
            "kind": "research_control",
            "operation": "create",
            "draft": {
                "question": self.question,
                "model": self.model,
                "format": self.format,
            },
            "settings": self.settings,
            "session": self.session,
        }


@dataclass(frozen=True)
class ResearchRun:
    target: str
    owner: str

    @classmethod
    def from_worker(cls, request: dict[str, Any]) -> ResearchRun:
        target = request.get("target")
        owner = request.get("owner")
        if (
            request.get("kind") != "research_run"
            or not isinstance(target, str)
            or not re.fullmatch(r"[a-f0-9]{32}", target)
            or not isinstance(owner, str)
            or not re.fullmatch(r"[a-f0-9]{32}", owner)
        ):
            raise ValueError("Invalid Research run action")
        return cls(target, owner)

    def worker_fields(self) -> dict[str, str]:
        return {"kind": "research_run", "target": self.target, "owner": self.owner}


@dataclass(frozen=True)
class ResearchDefaultsChange:
    values: dict[str, Any] = field(repr=False)
    expected: dict[str, Any] = field(repr=False)

    def worker_fields(self) -> dict[str, Any]:
        return {"kind": "research_control", "operation": "defaults",
                "values": self.values, "expected": self.expected}


@dataclass(frozen=True)
class ResearchLoad:
    target: str

    def worker_fields(self) -> dict[str, Any]:
        return {"kind": "research_control", "operation": "load", "target": self.target}


@dataclass(frozen=True)
class ResearchStop:
    target: str
    owner: str = ""
    queued_only: bool = False

    def worker_fields(self) -> dict[str, Any]:
        return {"kind": "research_control", "operation": "stop", "target": self.target,
                "owner": self.owner, "queued_only": self.queued_only}


@dataclass(frozen=True)
class ResearchReportAction:
    target: str
    revision: int
    action: Literal["learn-report", "discuss"]
    value: str

    def worker_fields(self) -> dict[str, Any]:
        return {"kind": "research_control", "operation": "report-action",
                "target": self.target, "revision": self.revision,
                "action": self.action, "value": self.value}


ResearchControl = (
    ResearchCreate | ResearchDefaultsChange | ResearchLoad | ResearchStop | ResearchReportAction
)


def research_control_from_worker(request: dict[str, Any]) -> ResearchControl:
    """Project one fixed control operation without trusting worker transport fields."""
    if request.get("kind") != "research_control":
        raise ValueError("Invalid Research control action")
    operation = request.get("operation")
    if operation == "create":
        return ResearchCreate.from_worker(request)
    if operation == "defaults":
        values, expected = request.get("values"), request.get("expected")
        if not isinstance(values, dict) or not isinstance(expected, dict):
            raise ValueError("Invalid Research defaults action")
        return ResearchDefaultsChange(values, expected)
    target = request.get("target")
    if operation in {"load", "stop"}:
        if not isinstance(target, str) or not re.fullmatch(r"[a-f0-9]{32}", target):
            raise ValueError("Invalid Research job ID")
        if operation == "load":
            return ResearchLoad(target)
        owner, queued_only = request.get("owner", ""), request.get("queued_only", False)
        if (
            not isinstance(owner, str) or len(owner) > 128
            or type(queued_only) is not bool
        ):
            raise ValueError("Invalid Research stop action")
        return ResearchStop(target, owner, queued_only)
    if operation == "report-action":
        revision, action, value = (
            request.get("revision"), request.get("action"), request.get("value")
        )
        if (
            not isinstance(target, str) or not 1 <= len(target) <= 128
            or type(revision) is not int or revision < 0
            or not isinstance(action, str) or action not in {"learn-report", "discuss"}
            or not isinstance(value, str) or len(value) > 4096
        ):
            raise ValueError("Invalid Research report action")
        return ResearchReportAction(
            target, revision, cast(Literal["learn-report", "discuss"], action), value
        )
    raise ValueError("Unknown Research control action")


class ResearchService:
    """Reuse Core's validated spec creation and durable ResearchStore admission."""

    def create(self, command: ResearchCreate) -> dict[str, Any]:
        if not isinstance(command, ResearchCreate):
            raise ValueError("Invalid Research create action")
        return execute_research_request(command.worker_fields())

    def run(self, command: ResearchRun) -> dict[str, Any]:
        if not isinstance(command, ResearchRun):
            raise ValueError("Invalid Research run action")
        return execute_research_request(command.worker_fields())

    def control(self, command: ResearchControl) -> dict[str, Any]:
        if not isinstance(command, (
            ResearchCreate, ResearchDefaultsChange, ResearchLoad,
            ResearchStop, ResearchReportAction,
        )):
            raise ValueError("Invalid Research control action")
        return execute_research_request(command.worker_fields())
