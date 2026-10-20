"""Transport-independent Klaude application foundation."""

from .composition import compose_agent, open_local_session
from .contracts import ApprovalRequest, PublicEvent, TurnReceipt, UserInputRequest
from .knowledge import KnowledgeContext, KnowledgeEvidence, KnowledgeHit, KnowledgeReader
from .lifecycle import SessionTurn
from .service import HeadlessApplication, TurnHandle
from .sessions import (
    SessionArchiveChange,
    SessionArchiveReceipt,
    SessionDeleteChange,
    SessionDeleteReceipt,
    SessionDirectory,
    SessionForkChange,
    SessionMatch,
    SessionRenameChange,
    SessionsClearChange,
    SessionsClearReceipt,
    SessionSummary,
)
from .settings import ChatSettings, SettingView

__all__ = [
    "ApprovalRequest", "HeadlessApplication", "PublicEvent", "TurnHandle",
    "TurnReceipt", "UserInputRequest", "SessionTurn", "compose_agent", "open_local_session",
    "ChatSettings", "SettingView",
    "SessionArchiveChange", "SessionArchiveReceipt", "SessionDeleteChange",
    "SessionDeleteReceipt", "SessionDirectory", "SessionForkChange", "SessionMatch",
    "SessionRenameChange", "SessionSummary", "SessionsClearChange", "SessionsClearReceipt",
    "KnowledgeContext", "KnowledgeEvidence", "KnowledgeHit", "KnowledgeReader",
]
