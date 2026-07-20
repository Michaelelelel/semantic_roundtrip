"""Adapter exceptions that retain a provider's raw error response."""


class AdapterError(RuntimeError):
    """A provider or response-format failure."""

    def __init__(self, message: str, raw_response: str | None = None) -> None:
        super().__init__(message)
        self.raw_response = raw_response
