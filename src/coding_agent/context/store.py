"""ConversationStore: full session history, system always first (docs/02 §5.2)."""

from __future__ import annotations

from collections.abc import Sequence

from coding_agent.domain.messages import ChatMessage, Role


class ConversationStore:
    def __init__(self, system: ChatMessage) -> None:
        if system.role is not Role.SYSTEM:
            raise ValueError("ConversationStore must be seeded with a system message")
        self._system = system
        self._messages: list[ChatMessage] = [system]

    def append(self, message: ChatMessage) -> None:
        self._messages.append(message)

    def all(self) -> tuple[ChatMessage, ...]:
        return tuple(self._messages)

    def reset_keeping_system(self) -> None:
        self._messages = [self._system]

    def replace_system(self, system: ChatMessage) -> None:
        if system.role is not Role.SYSTEM:
            raise ValueError("replace_system requires a system message")
        self._system = system
        if self._messages:
            self._messages[0] = system
        else:
            self._messages = [system]

    def replace_tail_view(self, view: Sequence[ChatMessage]) -> None:
        """Write back the compacted view; only ContextManager calls this."""
        if not view or view[0].role is not Role.SYSTEM:
            raise ValueError("compacted view must keep system as the first message")
        self._messages = list(view)
