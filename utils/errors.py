"""Application exceptions with structured, serializable diagnostic details."""

from typing import Any


class AgentError(Exception):
    """Base exception carrying a message, metadata, and optional root cause."""

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Initialize the exception while retaining structured context."""

        # Step 1: Preserve a user-facing message alongside structured metadata.
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause

    def __str__(self) -> str:
        """Render the message, metadata, and cause as one readable string."""

        base = self.message
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            base = f"{base} ({detail_str})"
        if self.cause:
            base = f"{base} [caused by: {self.cause}]"
        return base

    def to_dict(self) -> dict[str, Any]:
        """Return an API-safe representation of the exception."""

        # Step 1: Export the error in the shape used by API responses.
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }


class ConfigError(AgentError):
    """Configuration-specific error with optional key and file metadata."""

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        config_file: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Attach configuration location details before initializing the base error."""

        details = kwargs.pop("details", {}) or {}
        if config_key:
            details["config_key"] = config_key
        if config_file:
            details["config_file"] = config_file
        super().__init__(message, details=details, **kwargs)
        self.config_key = config_key
        self.config_file = config_file
