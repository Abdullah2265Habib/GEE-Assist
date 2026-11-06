from datetime import date

from backend.dto import ChunkDTO, DatasetDTO, DownloadJobDTO, EntityDTO, FormDTO
from backend.dto.download_dto import JOB_CANCELLED, JOB_COMPLETED, JOB_PAUSED


def _form() -> FormDTO:
    return FormDTO(
        dataset="sentinel2_sr", bands=["B4", "B8"], scale=10,
        start_date=date(2024, 6, 1), end_date=date(2024, 8, 31),
        entities=[EntityDTO("PLACE", "Faisalabad")],
    )


def _chunk(n: int, request: FormDTO | None = None) -> ChunkDTO:
    return ChunkDTO(
        id=n, bounds=(73.0, 31.0 + n, 73.5, 31.5 + n), crs="EPSG:4326",
        transform=(0.0001, 0.0, 73.0, 0.0, -0.0001, 31.5 + n),
        width=5000, height=100, row_offset=(n - 1) * 100, bands=["B4", "B8"],
        size_bytes=4_000_000, request=request,
    )


def test_form_round_trips_through_a_dictionary():
    form = _form()
    assert FormDTO.from_dict(form.to_dict()) == form


def test_form_from_dict_ignores_unknown_keys():
    assert FormDTO.from_dict({"dataset": "x", "added_later": 1}).dataset == "x"


def test_chunk_dictionary_leaves_out_the_shared_request():
    data = _chunk(1, _form()).to_dict()
    assert "request" not in data
    assert data["bounds"] == [73.0, 32.0, 73.5, 32.5]


def test_job_round_trip_gives_every_chunk_the_job_request():
    form = _form()
    job = DownloadJobDTO(
        id="job-1", name="Sentinel-2_73.2500_32.2500", folder="D:/downloads/Sentinel-2_73.2500_32.2500",
        status=JOB_PAUSED, total_chunks=2, chunks=[_chunk(1, form), _chunk(2, form)], request=form,
        total_bytes=8_000_000, downloaded_bytes=2_000_000,
        dataset=DatasetDTO("job-1", "COPERNICUS/S2_SR_HARMONIZED", "x.tif", bands=["B4", "B8"]),
    )
    restored = DownloadJobDTO.from_dict(job.to_dict())

    assert restored == job
    assert all(chunk.request == form for chunk in restored.chunks)


def test_job_progress_is_the_share_of_bytes_downloaded():
    job = DownloadJobDTO("j", "n", "f", total_bytes=1000, downloaded_bytes=250)
    assert job.progress == 0.25


def test_job_progress_without_a_size_estimate():
    assert DownloadJobDTO("j", "n", "f").progress == 0.0
    assert DownloadJobDTO("j", "n", "f", status=JOB_COMPLETED).progress == 1.0


def test_completed_and_cancelled_jobs_are_finished():
    assert DownloadJobDTO("j", "n", "f", status=JOB_COMPLETED).is_finished
    assert DownloadJobDTO("j", "n", "f", status=JOB_CANCELLED).is_finished
    assert not DownloadJobDTO("j", "n", "f", status=JOB_PAUSED).is_finished
