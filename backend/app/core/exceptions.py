"""Domain exceptions. No bare `except: pass` anywhere in the project — raise one of these."""

from __future__ import annotations


class RagChatbotError(Exception):
    """Base class, so a caller can catch everything this project raises deliberately."""


class DocumentNotFound(RagChatbotError):
    def __init__(self, identifier: int | str) -> None:
        super().__init__(f"document not found: {identifier}")
        self.identifier = identifier


class UnsupportedFileType(RagChatbotError):
    def __init__(self, path: str, suffix: str) -> None:
        super().__init__(f"unsupported file type {suffix!r}: {path}")
        self.path = path
        self.suffix = suffix


class IngestFailed(RagChatbotError):
    """Raised when a document cannot be ingested.

    Carries the original cause so ingest_service can write it to documents.error_message
    instead of losing it.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"ingest failed for {path}: {reason}")
        self.path = path
        self.reason = reason


class PipelineNotFound(RagChatbotError):
    def __init__(self, name: str, available: list[str] | None = None) -> None:
        msg = f"pipeline not registered: {name!r}"
        if available:
            msg += f" (registered: {', '.join(sorted(available))})"
        super().__init__(msg)
        self.name = name
