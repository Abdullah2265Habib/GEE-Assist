from __future__ import annotations

from abc import ABC, abstractmethod

from backend.dto import FormDTO


class IGeminiClient(ABC):
    """Class diagram: IGeminiClient. Gateway to the Gemini LLM."""

    @abstractmethod
    def process_query(self, prompt: str) -> FormDTO:
        """Interpret Query (LLM): turn a natural-language request into a FormDTO.

        The result is Gemini's raw interpretation; RequestService checks it
        against the supported datasets before it reaches the form.

        Raises:
            LLMServiceError: not configured, the API failed, or the answer is unusable.
        """

    @abstractmethod
    def generate_explanation(self, result) -> str:
        """UC-08 Get AI Explanation (ResultDTO -> text). Not part of this delivery."""
