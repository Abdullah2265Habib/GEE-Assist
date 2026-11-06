import json

import pytest

from backend.config.download_settings import DEFAULT_CHUNK_SIZE_MB, DownloadSettings, DownloadSettingsStore
from backend.exceptions import ValidationError


@pytest.fixture
def store(tmp_path):
    return DownloadSettingsStore(tmp_path / "settings" / "download_settings.json")


def test_first_load_creates_the_file_with_a_500_mb_chunk_size(store):
    settings = store.load()

    assert settings.chunk_size_mb == DEFAULT_CHUNK_SIZE_MB == 500
    assert settings.chunk_size_bytes == 500_000_000  # decimal megabytes
    assert json.loads(store.path.read_text())["chunk_size_mb"] == 500


def test_changed_chunk_size_is_kept_in_the_file(store):
    store.load()
    store.set_chunk_size_mb(250)

    assert DownloadSettingsStore(store.path).load().chunk_size_mb == 250


def test_changing_the_chunk_size_keeps_the_retry_limit(store):
    store.save(DownloadSettings(chunk_size_mb=500, retry_limit=7))
    assert store.set_chunk_size_mb(100).retry_limit == 7


def test_edited_file_is_read(store):
    store.path.parent.mkdir(parents=True)
    store.path.write_text('{"chunk_size_mb": 1024, "retry_limit": 5}')

    assert store.load() == DownloadSettings(chunk_size_mb=1024, retry_limit=5)


@pytest.mark.parametrize("content", ["not json", '{"chunk_size_mb": 0}', '{"chunk_size_mb": "big"}', "[]"])
def test_invalid_file_falls_back_to_the_defaults(store, content):
    store.path.parent.mkdir(parents=True)
    store.path.write_text(content)

    assert store.load() == DownloadSettings()


@pytest.mark.parametrize("size", [0, -5, 200_000])
def test_out_of_range_chunk_size_is_rejected(store, size):
    with pytest.raises(ValidationError):
        store.set_chunk_size_mb(size)
