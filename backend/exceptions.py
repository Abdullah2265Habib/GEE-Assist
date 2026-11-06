"""Backend errors. The UI catches ``GeeAssistError`` and shows ``str(error)``."""


class GeeAssistError(Exception):
    """Base class for expected backend errors."""


class ValidationError(GeeAssistError):
    """User input is invalid (e.g. empty natural-language query, UC-02 5a)."""


class AOIImportError(GeeAssistError):
    """GeoJSON file is unsupported or invalid (UC-04 6a / 6b)."""


class LLMServiceError(GeeAssistError):
    """Gemini is not configured, failed, or returned an unusable answer (Interpret Query)."""
