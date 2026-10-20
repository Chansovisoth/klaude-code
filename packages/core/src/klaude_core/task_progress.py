"""Bounded execution evidence for requested outcomes; never an authority grant.

The model still resolves entities, chooses queries and judges source relevance.
This record only distinguishes missing work, attempted work and usable results.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .execution import FAILED_RESULT_PREFIXES, NO_EVIDENCE_RE


@dataclass
class TaskOutcome:
    key: str
    description: str
    tools: tuple[str, ...]
    source_required: bool = False
    attempted: bool = False
    evidence: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.evidence:
            return 'observed'
        return 'failed' if self.attempted else 'pending'


@dataclass
class TaskProgress:
    goal: str = ''
    prior_answer: str = ''
    outcomes: list[TaskOutcome] = field(default_factory=list)
    repaired: set[str] = field(default_factory=set)

    @property
    def repair_used(self) -> bool:
        return bool(self.repaired)

    @property
    def pending(self) -> list[TaskOutcome]:
        return [o for o in self.outcomes if not o.evidence]

    @property
    def status(self) -> str:
        if not self.pending:
            return 'complete'
        return 'partial' if any(o.attempted for o in self.outcomes) else 'pending'

    def observe(self, tool: str, result: str, metadata: dict[str, Any], *, failed: bool) -> None:
        # Metadata comes from the host-observed result, not an assistant claim.
        # Skipped, denied, malformed and failed calls never establish evidence.
        executed = metadata.get('executed') is True
        failed = failed or metadata.get('status') in {'failed', 'error'} or bool(
            metadata.get('error_type')
        ) or result.strip().casefold().startswith(FAILED_RESULT_PREFIXES)
        leads = metadata.get('search_results')
        empty = (isinstance(leads, list) and not leads) or not result.strip()
        if tool == 'web_search' and not isinstance(leads, list):
            # The built-in search contract returns structured leads. A raw
            # "None"/status string cannot masquerade as successful retrieval.
            empty = True
        empty |= bool(NO_EVIDENCE_RE.search(result)) and not (
            metadata.get('source_id') or isinstance(leads, list) and leads
        )
        # A namespaced tool is an alternative only when it returns the same
        # observed source-provenance contract. Its name/description alone is not proof.
        for outcome in self.outcomes:
            external_source = tool.startswith('mcp__') and bool(
                metadata.get('source_id') or not outcome.source_required
                and isinstance(leads, list) and leads
            )
            if tool not in outcome.tools and not external_source:
                continue
            outcome.attempted = True
            if not executed or failed or empty:
                reason = 'permission denied' if result.startswith('permission denied:') else (
                    'no usable source evidence' if empty else 'tool unavailable or failed'
                )
                if reason not in outcome.blockers:
                    outcome.blockers.append(reason)
                continue
            reference = metadata.get('execution_id')
            if reference and len(outcome.evidence) < 8:
                outcome.evidence.append(str(reference)[:80])

    def render(self) -> str:
        if not self.outcomes:
            return ''
        lines = ['<task_progress>Host-observed action state; source relevance remains unverified.']
        lines.append('Current user objective: ' + json.dumps(self.goal[:2000], ensure_ascii=False))
        if self.prior_answer:
            lines.append('Referent context from the previous assistant answer (unverified): '
                         + json.dumps(self.prior_answer[:600], ensure_ascii=False))
        for outcome in self.outcomes:
            lines.append(f'{outcome.description}: {outcome.status}; '
                         f'usable results={len(outcome.evidence)}; '
                         f'available routes={", ".join(outcome.tools) or "none"}.')
        lines.append('Choose dependent actions from the user goal and recent dialogue. '
                     'Image-derived names are candidate leads, not verified identities. '
                     'Do not report a lookup as completed without retrieved evidence. '
                     'If evidence is insufficient, label leads and uncertainty.</task_progress>')
        return '\n'.join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {'status': self.status, 'repair_used': self.repair_used, 'outcomes': [
            {'key': o.key, 'status': o.status, 'evidence': o.evidence.copy(),
             'blockers': o.blockers.copy()} for o in self.outcomes
        ]}
