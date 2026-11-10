"""Backend errors. The UI catches ``GeeAssistError`` and shows ``str(error)``."""


class GeeAssistError(Exception):
    """Base class for expected backend errors."""


class ValidationError(GeeAssistError):
    """User input is invalid (e.g. empty natural-language query, UC-02 5a)."""


class AOIImportError(GeeAssistError):
    """GeoJSON file is unsupported or invalid (UC-04 6a / 6b)."""


class LLMServiceError(GeeAssistError):
    """Gemini is not configured, failed, or returned an unusable answer (Interpret Query)."""


class GEEError(GeeAssistError):
    """Google Earth Engine is not set up, refused a request, or returned no data (Fetch Data)."""


class GEESetupError(GEEError):
    """Earth Engine cannot be used until the user fixes the setup (sign-in, project, API).

    Retrying does not help, so downloads stop at once with the message.
    """


class GEERequestTooHeavyError(GEEError):
    """Earth Engine ran out of memory or time computing a request.

    Sending the same request again does not help; a smaller one may. When even the
    smallest request fails, downloads stop at once so the user can make the request
    lighter (shorter date range, mosaic composite).
    """
