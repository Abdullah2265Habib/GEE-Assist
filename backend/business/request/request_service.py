from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import date
from pathlib import Path

from backend.business.request.geojson_utils import read_aoi_geometry, utm_epsg_for, validate_geometry
from backend.business.request.i_request_service import IRequestService
from backend.business.request.query_entities import IEntityExtractor, QueryEntityExtractor, format_entity_hints
from backend.business.request.query_interpretation import check_interpretation, ground_with_entities, has_form_values
from backend.config import AUTO_UTM, COMPOSITE_METHODS, get_dataset
from backend.config.limits import MAX_QUERY_LENGTH
from backend.data.i_data_facade import IDataFacade
from backend.dto import FormDTO, ValidationDTO
from backend.exceptions import LLMServiceError, ValidationError

_EPSG_CODE = re.compile(r"^EPSG:\d{4,5}$")


class RequestService(IRequestService):
    """Class diagram: RequestService (-dataFacade: IDataFacade).

    The data facade reaches Gemini (Interpret Query) and, later, MongoDB (saveProject).
    """

    def __init__(self, data_facade: IDataFacade | None = None, entity_extractor: IEntityExtractor | None = None):
        self._data_facade = data_facade
        self._entity_extractor = entity_extractor or QueryEntityExtractor()
        self._kept_requests: list[FormDTO] = []

    # ------------------------------------------------------------------
    # UC-02 Enter Natural Language Query + Interpret Query (LLM)
    # ------------------------------------------------------------------
    def submit_query(self, text: str) -> FormDTO:
        """Interpret the query and return form values to review.

        1. a local named-entity classifier finds places, dates, datasets, processes, ...
        2. Gemini interprets the query, with those entities as hints
        3. what the user explicitly wrote overrides Gemini's guesses
        4. everything is checked against the dataset catalogue

        If Gemini is unavailable, the form is filled from the entities alone.
        Nothing is kept here: the user checks the filled form and submits it.

        Raises:
            ValidationError: the query is empty (5a) or too long.
            LLMServiceError: Gemini failed and nothing could be recognised locally either.
        """
        query = " ".join((text or "").split())
        if not query:
            raise ValidationError("Please describe the data you need, e.g. the place, dates and dataset.")
        if len(query) > MAX_QUERY_LENGTH:
            raise ValidationError(f"The request is too long ({len(query)} characters, limit {MAX_QUERY_LENGTH}).")

        entities = self._entity_extractor.extract(query)
        try:
            if self._data_facade is None:
                raise LLMServiceError("Gemini isn't connected.")
            interpreted = self._data_facade.process_query(query + format_entity_hints(entities))
        except LLMServiceError as exc:
            fallback = ground_with_entities(FormDTO(source="nl", query_text=query), entities)
            if not has_form_values(fallback):
                raise
            note = f"{exc} The form was filled from what was recognised in your text."
            return check_interpretation(replace(fallback, notes=[note, *fallback.notes]))

        grounded = ground_with_entities(replace(interpreted, source="nl", query_text=query), entities)
        return check_interpretation(grounded)

    # ------------------------------------------------------------------
    # UC-03 Fill Parameter Form               (branch: query-input-form)
    # ------------------------------------------------------------------
    def validate_form(self, form: FormDTO) -> ValidationDTO:
        result = ValidationDTO()
        info = get_dataset(form.dataset)

        # 3. dataset
        if info is None:
            result.add_error("dataset", "Select a supported dataset.")

        # 4. AOI (imported GeoJSON, or a rectangle / circle / polygon drawn on the map)
        geometry = None
        if not form.aoi:
            result.add_error("aoi", "Specify an Area of Interest: import a GeoJSON file, or draw a rectangle, circle or polygon on the map.")
        else:
            try:
                geometry = json.loads(form.aoi)
                aoi_error = validate_geometry(geometry)
            except json.JSONDecodeError:
                aoi_error = "AOI is not valid GeoJSON."
            if aoi_error:
                result.add_error("aoi", aoi_error)
                geometry = None

        # 5. temporal range (8b)
        if form.start_date is None or form.end_date is None:
            result.add_error("dates", "Select both a start and an end date.")
        elif form.start_date > form.end_date:
            result.add_error("dates", "Start date must be on or before the end date.")
        elif form.end_date > date.today():
            result.add_error("dates", "End date cannot be in the future.")
        elif info is not None and form.start_date < info.min_date:
            result.add_error("dates", f"{info.name} data is only available from {info.min_date.isoformat()}.")
        elif info is not None and info.max_date is not None and form.end_date > info.max_date:
            result.add_error("dates", f"{info.name} data is only available until {info.max_date.isoformat()}.")

        # bands / scale / cloud / composite
        if info is not None:
            if not form.bands:
                result.add_error("bands", "Select at least one band.")
            else:
                unknown = [b for b in form.bands if b not in info.bands]
                if unknown:
                    result.add_error("bands", f"Bands not in {info.name}: {', '.join(unknown)}.")
        if form.scale is None or form.scale <= 0:
            result.add_error("scale", "Scale must be a positive number of metres per pixel.")
        if form.max_cloud_cover is not None:
            if info is not None and not info.supports_cloud_filter:
                result.add_error("max_cloud_cover", f"{info.name} does not support cloud filtering.")
            elif not 0 <= form.max_cloud_cover <= 100:
                result.add_error("max_cloud_cover", "Cloud cover must be between 0 and 100 %.")
        if form.composite not in COMPOSITE_METHODS:
            result.add_error("composite", f"Composite must be one of: {', '.join(COMPOSITE_METHODS)}.")

        # output: projection and folder for the downloaded GeoTIFF(s)
        if form.crs != AUTO_UTM and not _EPSG_CODE.match(form.crs or ""):
            result.add_error("crs", "Projection must be an EPSG code such as EPSG:4326.")
        output_dir = (form.output_dir or "").strip()
        if not output_dir:
            result.add_error("output_dir", "Choose a folder to save the download in.")
        elif Path(output_dir).exists() and not Path(output_dir).is_dir():
            result.add_error("output_dir", "The output location is a file, not a folder.")
        elif not Path(output_dir).is_absolute():
            result.add_error("output_dir", "Use a full folder path, e.g. C:\\GEE-Assist\\downloads.")

        # 6. analysis type: optional for now (empty = download only).
        #    When one is chosen, the dataset must support it (8c).
        supported = info.supported_analyses if info is not None else {}
        if not form.analysis_type:
            pass  # download only: nothing else to check
        elif info is not None and form.analysis_type not in supported:
            result.add_error(
                "analysis_type",
                f"{info.name} does not support {form.analysis_type} analysis. "
                f"Supported: {', '.join(supported) or 'none'}.",
            )
        elif not form.processes:
            result.add_error("processes", "Select at least one process.")
        elif info is not None:
            unsupported = [p for p in form.processes if p not in supported[form.analysis_type]]
            if unsupported:
                result.add_error("processes", f"Unsupported processes: {', '.join(unsupported)}.")

        # 9. keep validated parameters
        if result.is_valid:
            crs = utm_epsg_for(geometry) if form.crs == AUTO_UTM else form.crs
            processes = form.processes if form.analysis_type else []
            self._keep(replace(form, source="form", crs=crs, output_dir=output_dir, processes=processes))
            result.message = "Parameters accepted and kept."
        else:
            result.message = "Please correct the highlighted fields."
        return result

    # ------------------------------------------------------------------
    # UC-04 Import GeoJSON                    (branch: query-input-form)
    # ------------------------------------------------------------------
    def import_aoi(self, file_path: str) -> str:
        """Raises AOIImportError for unsupported (6b) or invalid (6a) files."""
        return json.dumps(read_aoi_geometry(file_path))

    # ------------------------------------------------------------------
    # Keeping the data
    # ------------------------------------------------------------------
    def get_kept_requests(self) -> list[FormDTO]:
        return list(self._kept_requests)

    def _keep(self, form: FormDTO) -> None:
        self._kept_requests.append(form)
