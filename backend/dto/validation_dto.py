from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValidationDTO:
    """Result of validating user input.

    ``errors`` maps a field name to a readable message so the UI can point
    at the exact widget that is wrong.
    """

    is_valid: bool = True
    errors: dict[str, str] = field(default_factory=dict)
    message: str = ""

    def add_error(self, field_name: str, message: str) -> None:
        self.is_valid = False
        self.errors[field_name] = message
