"""DTOs shared by the frontend and backend (names follow the SRS class diagram)."""

from backend.dto.download_dto import ChunkDTO, DatasetDTO, DownloadJobDTO
from backend.dto.request_dto import EntityDTO, FormDTO
from backend.dto.validation_dto import ValidationDTO

__all__ = ["ChunkDTO", "DatasetDTO", "DownloadJobDTO", "EntityDTO", "FormDTO", "ValidationDTO"]
