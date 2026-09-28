"""Caching and outage behaviour of the Quranpedia source (no network)."""

import json
import time

import pytest

from app import quran_source as qs


def test_payload_shape_is_validated():
    with pytest.raises(qs.SourceUnavailable):
        qs._flatten_mushaf({"surahs": [{"id": 1, "ayahs": [{"number": 1, "text": "بسم"}]}]})  # incomplete
    with pytest.raises(qs.SourceUnavailable):
        qs._flatten_mushaf({"error": "Mushaf not found"})


def test_fetch_once_then_memory_cache(tmp_path, records):
    calls = []

    def fetcher():
        calls.append(1)
        return records

    src = qs.QuranSource(cache_dir=str(tmp_path), fetcher=fetcher)
    a = src.get()
    b = src.get()
    assert a is b and len(calls) == 1
    assert (tmp_path / "hafs-mushaf-1.json").exists()


def test_disk_cache_reused_by_new_instance(tmp_path, records):
    qs.QuranSource(cache_dir=str(tmp_path), fetcher=lambda: records).get()

    def boom():
        raise AssertionError("should not fetch while the disk cache is fresh")

    idx = qs.QuranSource(cache_dir=str(tmp_path), fetcher=boom).get()
    assert idx.ayah_count == len(records)


def test_outage_without_cache_raises(tmp_path):
    def down():
        raise OSError("network down")

    src = qs.QuranSource(cache_dir=str(tmp_path), fetcher=down)
    with pytest.raises(qs.SourceUnavailable):
        src.get()


def test_outage_uses_recent_stale_cache_with_notice(tmp_path, records):
    path = tmp_path / "hafs-mushaf-1.json"
    path.write_text(json.dumps({"fetched_at": time.time() - 2 * 86400, "ayahs": records}, ensure_ascii=False), encoding="utf-8")

    def down():
        raise OSError("network down")

    idx = qs.QuranSource(cache_dir=str(tmp_path), fetcher=down).get()
    assert idx.stale and idx.notes


def test_outage_rejects_old_cache(tmp_path, records):
    path = tmp_path / "hafs-mushaf-1.json"
    path.write_text(json.dumps({"fetched_at": time.time() - 30 * 86400, "ayahs": records}, ensure_ascii=False), encoding="utf-8")

    def down():
        raise OSError("network down")

    with pytest.raises(qs.SourceUnavailable):
        qs.QuranSource(cache_dir=str(tmp_path), fetcher=down).get()


def test_disk_origin_is_reported(tmp_path, records):
    qs.QuranSource(cache_dir=str(tmp_path), fetcher=lambda: records).get()
    src = qs.QuranSource(cache_dir=str(tmp_path), fetcher=lambda: records)
    src.get()
    assert src.status()["loaded_from"] == "disk"


def test_fetch_retries_once_on_transient_error(monkeypatch, tmp_path):
    import httpx

    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"surahs": []})  # reaches validation => SourceUnavailable

    real = httpx.Client
    monkeypatch.setattr(qs.httpx, "Client", lambda *a, **k: real(*a, **{**k, "transport": httpx.MockTransport(handler)}))
    monkeypatch.setattr(qs.time, "sleep", lambda s: None)
    with pytest.raises(qs.SourceUnavailable):
        qs.QuranSource(cache_dir=str(tmp_path))._fetch_remote()
    assert len(calls) == 2
