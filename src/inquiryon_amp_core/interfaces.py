"""Extension interfaces for the governance workflow (OSS-002).

Narrow adapter contracts: infrastructure (storage, identity, notification,
callbacks, audit transport, time, ids) is injected — never hard-coded.
Community and Enterprise both implement these; registration happens at each
distribution's composition root.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Protocol


class Clock(Protocol):
    def now_iso(self) -> str: ...
    def monotonic(self) -> float: ...


class SystemClock:
    def now_iso(self) -> str:
        return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    def monotonic(self) -> float:
        return time.monotonic()


class IdGenerator(Protocol):
    def new_id(self, kind: str) -> str: ...


class UuidGenerator:
    def new_id(self, kind: str) -> str:
        return f'{kind}-{uuid.uuid4()}'


@dataclass(frozen=True)
class AuditEvent:
    """Append-only audit record (v0). See contracts/schemas/audit-event.json."""
    event_id: str
    event_type: str      # e.g. evaluation.completed, hitl.requested, hitl.decided
    occurred_at: str     # ISO-8601 UTC
    request_id: str
    actor: str           # 'system' | 'provider:<name>' | 'user:<opaque-id>'
    payload: dict = field(default_factory=dict)
    scope: Optional[str] = None
    schema_version: str = 'v0'


class AuditEventSink(Protocol):
    """Append-only; implementations must not support update or delete."""
    def append(self, event: AuditEvent) -> None: ...


class InMemoryAuditSink:
    def __init__(self):
        self._events = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> tuple:
        return tuple(self._events)


class WorkItemStore(Protocol):
    def create(self, workitem: dict) -> str: ...
    def get(self, workitem_id: str) -> Optional[dict]: ...
    def update_status(self, workitem_id: str, status: str, patch: dict) -> None: ...
    def list_open(self) -> list: ...


class IdentityProvider(Protocol):
    """Answers authorization questions; carries no SaaS identity semantics."""
    def can_decide(self, principal: str, workitem: dict) -> bool: ...


class NotificationChannel(Protocol):
    def notify(self, subject: str, body: str, ref: Optional[str] = None) -> None: ...


class AgentCallback(Protocol):
    """Delivers a final decision back to the requesting agent.

    Implementations must be idempotent per ``delivery_id`` — the workflow may
    retry delivery.
    """
    def deliver(self, delivery_id: str, request_id: str, result: dict) -> None: ...
